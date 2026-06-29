from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import sqlglot
import sqlparse
from sqlglot import exp
from sqlglot.lineage import lineage
from sqlglot.optimizer.qualify import qualify

from src.config import resolve_variables
from src.models import (
    ColumnLineage,
    FilterDetail,
    JoinDetail,
    LineageSource,
    ProcessStep,
    PublicationDetail,
    ProjectConfig,
    RuleDetail,
    SourceDetail,
    SqlAnalysis,
    TransformationDetail,
)

SQL_KEYWORDS = {"select", "from", "where", "join", "group", "order", "limit"}


def parse_sql_file(sql_path: str | Path, config: ProjectConfig) -> SqlAnalysis:
    path = Path(sql_path)
    raw_sql = path.read_text(encoding="utf-8")
    resolution = resolve_variables(raw_sql, config.variables)
    parseable_sql = resolution.masked_sql or resolution.resolved_sql
    relevant_statements, compute_stats_statements = _split_relevant_statements(parseable_sql)

    publish_statements = _find_publish_statements(relevant_statements)
    if not publish_statements:
        raise ValueError(f"No se encontro una publicacion soportada (INSERT o CREATE TABLE AS SELECT) en {path}")

    statement_type, publish_statement = publish_statements[-1]
    publish_ast = sqlglot.parse_one(publish_statement, read="hive")
    target_table = _normalize_target_table(publish_ast)
    select_expr = _extract_select_expression(publish_ast)
    compute_stats_tables = _extract_compute_stats_tables(compute_stats_statements)
    publications = _build_publications(publish_statements, compute_stats_tables)
    qualified_select = qualify(
        select_expr.copy(),
        dialect="hive",
        validate_qualify_columns=False,
        allow_partial_qualification=True,
        identify=False,
        quote_identifiers=False,
        infer_schema=False,
    )
    column_lineage = get_column_lineage(select_expr)

    alias_sources = _collect_top_level_sources(qualified_select, target_table)
    ctes = _collect_ctes(qualified_select, target_table, alias_sources)
    subqueries = sorted(
        {
            detail.alias
            for detail in alias_sources.values()
            if detail.source_kind in {"subquery", "cte"}
        }
    )
    filters = _collect_filters(qualified_select)
    joins = _collect_joins(qualified_select, alias_sources)
    source_lineage_by_alias, source_tables_by_alias = _build_source_resolution_maps(qualified_select)
    transformations, rules = _collect_transformations_and_rules(
        qualified_select,
        filters,
        joins,
        column_lineage,
        source_lineage_by_alias,
        source_tables_by_alias,
    )
    _assign_used_steps(alias_sources, qualified_select, filters)
    _assign_source_field_contributions(alias_sources, transformations)
    steps = _build_steps(
        select_expr=qualified_select,
        target_table=target_table,
        ctes=ctes,
        subqueries=subqueries,
        alias_sources=alias_sources,
        joins=joins,
        filters=filters,
        transformations=transformations,
        rules=rules,
        compute_stats_tables=compute_stats_tables,
    )

    return SqlAnalysis(
        file_name=path.name,
        sql_path=str(path),
        target_table=target_table,
        raw_sql=raw_sql,
        resolved_sql=resolution.resolved_sql,
        unresolved_variables=resolution.unresolved_variables,
        auto_resolved_variables=resolution.auto_resolved_variables,
        column_lineage=column_lineage,
        compute_stats_tables=compute_stats_tables,
        publications=publications,
        ctes=ctes,
        subqueries=subqueries,
        sources=list(alias_sources.values()),
        joins=joins,
        filters=filters,
        transformations=transformations,
        rules=rules,
        steps=steps,
        metadata={
            "statement_count": len(relevant_statements),
            "ignored_compute_stats_count": len(compute_stats_statements),
            "source_count": len(alias_sources),
            "field_count": len(transformations),
            "parse_archetype": detect_parse_archetype(statement_type, publish_ast, qualified_select, joins, ctes, subqueries),
            "masked_variables": resolution.masked_variables,
            "statement_type": statement_type,
        },
    )


def get_column_lineage(sql_text: str | exp.Expression) -> Dict[str, ColumnLineage]:
    if isinstance(sql_text, exp.Expression):
        select_expr = _extract_select_expression(sql_text)
    else:
        parsed = sqlglot.parse_one(sql_text, read="hive")
        select_expr = _extract_select_expression(parsed)

    lineage_map: Dict[str, ColumnLineage] = {}
    for projection in _query_projections(select_expr):
        alias = projection.alias_or_name or projection.sql(dialect="hive")
        alias_key = alias.lower()
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        node = lineage(
            alias,
            select_expr,
            dialect="hive",
            validate_qualify_columns=False,
            identify=False,
            quote_identifiers=False,
        )
        physical_sources = _extract_physical_sources_from_lineage(node)
        lineage_map[alias_key] = ColumnLineage(
            column_name=alias_key,
            display_name=alias,
            expression_sql=projection.sql(dialect="hive"),
            lineage_type="direct" if isinstance(expression, exp.Column) else "derived",
            source_aliases=_collect_source_aliases(expression),
            source_columns=_collect_column_names(expression),
            physical_sources=physical_sources,
            functions=_extract_functions(expression),
        )
    return lineage_map


def _split_relevant_statements(sql_text: str) -> Tuple[List[str], List[str]]:
    relevant: List[str] = []
    compute_stats: List[str] = []
    for statement in [stmt.strip() for stmt in sqlparse.split(sql_text) if stmt.strip()]:
        if _is_compute_stats_statement(statement):
            compute_stats.append(statement)
            continue
        relevant.append(statement)
    return relevant, compute_stats


def _is_compute_stats_statement(statement: str) -> bool:
    return bool(re.match(r"^\s*compute\s+stats\b", statement, flags=re.IGNORECASE))


def _extract_physical_sources_from_lineage(node) -> List[LineageSource]:
    seen = set()
    results: List[LineageSource] = []
    for item in node.walk():
        if isinstance(item.expression, exp.Table):
            reference_name = item.name
            source_table_alias, source_column = _split_reference_name(reference_name)
            base_table = _table_identifier(item.expression)
            key = (base_table, source_column, source_table_alias, reference_name)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                LineageSource(
                    base_table=base_table,
                    source_column=source_column,
                    source_table_alias=source_table_alias,
                    reference_name=reference_name,
                )
            )
    return results


def _split_reference_name(reference_name: str) -> Tuple[Optional[str], str]:
    if "." in reference_name:
        table_alias, source_column = reference_name.rsplit(".", 1)
        return table_alias, source_column
    return None, reference_name


def _table_identifier(table: exp.Table) -> str:
    parts = [part for part in [table.catalog, table.db, table.name] if part]
    return ".".join(parts)


def _extract_functions(expression: exp.Expression) -> List[str]:
    functions: List[str] = []
    for node in expression.walk():
        if isinstance(node, exp.Case):
            functions.append("CASE")
        elif isinstance(node, exp.Coalesce):
            functions.append("COALESCE")
        elif isinstance(node, exp.If):
            functions.append("IF")
        elif isinstance(node, exp.Concat):
            functions.append("CONCAT")
        elif isinstance(node, exp.ConcatWs):
            functions.append("CONCAT_WS")
        elif isinstance(node, exp.Trim):
            functions.append("TRIM")
        elif isinstance(node, exp.Cast):
            functions.append("CAST")
        elif isinstance(node, exp.TryCast):
            functions.append("TRY_CAST")
        elif isinstance(node, exp.Anonymous):
            functions.append(node.name.upper())
        elif isinstance(node, exp.AggFunc):
            functions.append(node.key.upper())
    return _unique(functions)


def detect_parse_archetype(
    statement_type: str,
    publish_ast: exp.Expression,
    select_expr: exp.Expression,
    joins: List[JoinDetail],
    ctes: List[str],
    subqueries: List[str],
) -> str:
    parts = [statement_type]
    target = _normalize_target_table(publish_ast)
    if target.split(".")[-1].lower().startswith("cu_"):
        parts.append("curated_table")
    elif target.split(".")[-1].lower().startswith("cd_"):
        parts.append("crystal_table")
    else:
        parts.append("published_table")
    if joins:
        parts.append("with_enrichment")
    if ctes or subqueries:
        parts.append("with_preparation_layers")
    return "_".join(parts)


def _find_publish_statements(statements: Sequence[str]) -> List[Tuple[str, str]]:
    selected: List[Tuple[str, str]] = []
    for statement in statements:
        if re.search(r"\binsert\b", statement, flags=re.IGNORECASE):
            selected.append(("insert_overwrite", statement))
            continue
        if re.search(r"\bcreate\s+table\b", statement, flags=re.IGNORECASE) and re.search(
            r"\bas\s+select\b", statement, flags=re.IGNORECASE
        ):
            selected.append(("create_table_as_select", statement))
    return selected


def _build_publications(
    publish_statements: Sequence[Tuple[str, str]],
    compute_stats_tables: Sequence[str],
) -> List[PublicationDetail]:
    normalized_compute = {table.lower() for table in compute_stats_tables}
    publications: List[PublicationDetail] = []
    total = len(publish_statements)
    for index, (statement_type, statement) in enumerate(publish_statements, start=1):
        statement_ast = sqlglot.parse_one(statement, read="hive")
        target_table = _normalize_target_table(statement_ast)
        publications.append(
            PublicationDetail(
                sequence=index,
                statement_type=statement_type,
                target_table=target_table,
                role="final" if index == total else "intermedia",
                has_compute_stats=target_table.lower() in normalized_compute,
            )
        )
    return publications


def _normalize_target_table(statement_ast: exp.Expression) -> str:
    target = statement_ast.this
    if isinstance(target, exp.Table) and target.args.get("partition"):
        clean_target = target.copy()
        clean_target.set("partition", None)
        return clean_target.sql(dialect="hive")
    if isinstance(target, exp.Partition):
        return target.this.sql(dialect="hive")
    return target.sql(dialect="hive")


def _extract_select_expression(statement_ast: exp.Expression) -> exp.Select:
    if isinstance(statement_ast, exp.Insert):
        expression = statement_ast.expression
    elif isinstance(statement_ast, exp.Create):
        expression = statement_ast.expression
    else:
        expression = statement_ast

    if isinstance(expression, exp.Select):
        return expression
    # sqlglot removio exp.Subqueryable en versiones recientes y lo reemplazo
    # por exp.Query para representar SELECT/UNION/INTERSECT/EXCEPT.
    if isinstance(expression, getattr(exp, "Subqueryable", exp.Query)):
        return expression
    raise ValueError(f"No se pudo extraer el SELECT final de la sentencia {statement_ast.key}")


def _collect_ctes(
    select_expr: exp.Expression,
    target_table: str,
    alias_sources: Dict[str, SourceDetail],
) -> List[str]:
    with_expr = select_expr.args.get("with") or select_expr.args.get("with_")
    if not with_expr:
        return []

    ctes: List[str] = []
    for cte in with_expr.expressions:
        alias = cte.alias_or_name or f"cte_{len(ctes) + 1}"
        source_name = _source_name_for_cte_expression(cte.this, alias)
        alias_sources[alias] = SourceDetail(
            alias=alias,
            table_name=source_name,
            layer=_detect_layer(source_name),
            fields_generated=[],
            contains_description=_source_description(source_name, "cte"),
            used_in_steps=[],
            destination_table=target_table,
            source_kind="cte",
        )
        ctes.append(alias)
    return ctes


def _collect_top_level_sources(
    select_expr: exp.Expression,
    target_table: str,
) -> Dict[str, SourceDetail]:
    collected: "OrderedDict[str, SourceDetail]" = OrderedDict()
    for index, node in enumerate(_collect_query_source_nodes(select_expr), start=1):
        alias = _alias_for_source(node, default=f"S{index}")
        source_name = _source_name_for_expression(node, alias)
        source_kind = "table"
        if isinstance(node, exp.Subquery):
            source_kind = "subquery"
        elif isinstance(node, exp.Table):
            source_kind = "table"

        collected[alias] = SourceDetail(
            alias=alias,
            table_name=source_name,
            layer=_detect_layer(source_name),
            fields_generated=[],
            contains_description=_source_description(source_name, source_kind),
            used_in_steps=[],
            destination_table=target_table,
            source_kind=source_kind,
        )
    return collected


def _alias_for_source(node: exp.Expression, default: str) -> str:
    alias = getattr(node, "alias_or_name", None)
    if alias:
        return alias
    if isinstance(node, exp.Table):
        return node.name
    return default


def _source_name_for_expression(node: exp.Expression, alias: str) -> str:
    if isinstance(node, exp.Table):
        return _table_identifier(node)
    if isinstance(node, exp.Subquery):
        physical = sorted({table.sql(dialect="hive") for table in node.find_all(exp.Table)})
        if physical:
            joined = ", ".join(physical)
            return f"{joined} (subconsulta {alias})"
        return f"Subconsulta {alias}"
    return node.sql(dialect="hive")


def _source_name_for_cte_expression(node: exp.Expression, alias: str) -> str:
    physical = _extract_physical_table_names(node)
    if physical:
        joined = ", ".join(physical[:3])
        suffix = "..." if len(physical) > 3 else ""
        return f"CTE {alias} (derivada de {joined}{suffix})"
    return f"CTE {alias}"


def _extract_physical_table_names(node: exp.Expression) -> List[str]:
    seen: "OrderedDict[str, None]" = OrderedDict()
    for table in node.find_all(exp.Table):
        identifier = _table_identifier(table)
        if identifier and not table.name.startswith("_"):
            seen[identifier] = None
    return list(seen.keys())


def _detect_layer(source_name: str) -> str:
    last_token = source_name.split("(")[0].strip().split(",")[0].strip()
    table_name = last_token.split(".")[-1].lower()
    if table_name.startswith("cd_"):
        return "Crystal (cd_)"
    if table_name.startswith("rd_"):
        return "Raw (rd_)"
    if table_name.startswith("cu_"):
        return "Curada (cu_)"
    return "Logica derivada"


def _source_description(source_name: str, source_kind: str) -> str:
    if source_kind == "cte":
        return "Unidad logica preparada en una CTE para organizar reglas y campos intermedios."
    if source_kind == "subquery":
        return "Subconsulta que concentra lectura, filtros o preparacion previa antes del ensamble final."
    layer = _detect_layer(source_name)
    if layer.startswith("Raw"):
        return "Tabla operacional en bruto usada como insumo primario del proceso."
    if layer.startswith("Curada"):
        return "Tabla curada reutilizada como insumo ya depurado dentro del proceso."
    if layer.startswith("Crystal"):
        return "Tabla Crystal usada como salida previa o insumo ya procesado."
    return "Fuente logica usada para soportar la construccion del resultado final."


def _collect_joins(select_expr: exp.Expression, alias_sources: Dict[str, SourceDetail]) -> List[JoinDetail]:
    joins: List[JoinDetail] = []
    for branch in _iter_query_branches(select_expr):
        for join in branch.args.get("joins") or []:
            alias = _alias_for_source(join.this, default=f"J{len(joins) + 1}")
            source = alias_sources.get(alias)
            join_type = " ".join(
                [part for part in [join.args.get("side"), join.args.get("kind")] if part]
            ).strip() or "JOIN"
            condition = join.args.get("on")
            joins.append(
                JoinDetail(
                    source_alias=alias,
                    source_name=source.table_name if source else _source_name_for_expression(join.this, alias),
                    join_type=join_type.upper(),
                    condition_text=describe_condition(condition) if condition else "Cruce sin condicion explicita.",
                    meaning=_join_meaning(join_type),
                )
            )
    return joins


def _join_meaning(join_type: str) -> str:
    text = join_type.upper()
    if "ANTI" in text:
        return "Descarta coincidencias existentes para evitar registros ya procesados."
    if "LEFT" in text:
        return "Conserva la base principal aunque la tabla enriquecedora no tenga coincidencia."
    if "INNER" in text:
        return "Conserva solo los registros con coincidencia entre ambas fuentes."
    return "Integra informacion complementaria con base en la condicion de cruce."


def _collect_filters(select_expr: exp.Expression) -> List[FilterDetail]:
    filters: List[FilterDetail] = []
    root_selects = {id(branch) for branch in _iter_query_branches(select_expr)}
    for where in select_expr.find_all(exp.Where):
        parent_scope = "Paso 4"
        scope_name = "resultado final"
        parent_select = where.find_ancestor(exp.Select)
        if parent_select is not None and id(parent_select) not in root_selects:
            parent_scope = "Paso 1"
            alias = _nearest_subquery_alias(where)
            if alias:
                scope_name = f"subconsulta {alias}"
        filters.append(
            FilterDetail(
                scope=scope_name,
                condition_text=describe_condition(where.this),
                step=parent_scope,
            )
        )
    return filters


def _nearest_subquery_alias(node: exp.Expression) -> Optional[str]:
    current = node.parent
    while current is not None:
        if isinstance(current, exp.Subquery) and current.alias_or_name:
            return current.alias_or_name
        current = current.parent
    return None


def _collect_transformations_and_rules(
    select_expr: exp.Expression,
    filters: List[FilterDetail],
    joins: List[JoinDetail],
    column_lineage: Dict[str, ColumnLineage],
    source_lineage_by_alias: Dict[str, Dict[str, ColumnLineage]],
    source_tables_by_alias: Dict[str, List[str]],
) -> Tuple[List[TransformationDetail], List[RuleDetail]]:
    rules: List[RuleDetail] = []
    rule_counter = 1
    for filter_detail in filters:
        filter_detail.rule_id = _rule_id(rule_counter)
        rules.append(
            RuleDetail(
                id=filter_detail.rule_id,
                description=f"Se conservan unicamente los registros donde {filter_detail.condition_text}",
                applies_in=filter_detail.step,
            )
        )
        rule_counter += 1

    cte_rules, rule_counter = _collect_cte_aggregation_rules(select_expr, rule_counter)
    rules.extend(cte_rules)

    transformations: List[TransformationDetail] = []
    for index, projection in enumerate(_query_projections(select_expr), start=1):
        alias = projection.alias_or_name or f"campo_{index}"
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        source_fields = _collect_column_names(expression)
        field_type, subtype = classify_expression(expression, alias)
        rule_id = None
        if _contains_case(expression):
            rule_id = _rule_id(rule_counter)
            rules.append(
                RuleDetail(
                    id=rule_id,
                    description=_build_case_rule(alias, expression),
                    applies_in="Paso 5",
                )
            )
            rule_counter += 1
        physical_source_fields = [
            f"{source.base_table}.{source.source_column}"
            for source in column_lineage.get(
                alias,
                ColumnLineage(
                    column_name=alias,
                    display_name=alias,
                    expression_sql="",
                    lineage_type="derived",
                ),
            ).physical_sources
        ]
        physical_source_fields = _expand_physical_source_fields(
            expression=expression,
            existing_fields=physical_source_fields,
            source_lineage_by_alias=source_lineage_by_alias,
            source_tables_by_alias=source_tables_by_alias,
        )
        transformations.append(
            TransformationDetail(
                index=index,
                field_name=alias,
                expression_name=expression.key,
                field_type=field_type,
                subtype=subtype,
                origin=" / ".join(_collect_source_aliases(expression)) or "—",
                source_fields=source_fields,
                description=describe_expression(expression, alias),
                step="Paso 5",
                rule_id=rule_id,
                participates_in_steps=_field_steps(expression, filters, joins),
                physical_source_fields=physical_source_fields,
            )
        )
    return transformations, rules


def _collect_cte_aggregation_rules(
    select_expr: exp.Select,
    rule_counter: int,
) -> Tuple[List[RuleDetail], int]:
    rules: List[RuleDetail] = []
    with_expr = select_expr.args.get("with") or select_expr.args.get("with_")
    for cte in with_expr.expressions if with_expr else []:
        cte_name = cte.alias_or_name or "cte"
        cte_select = cte.this if isinstance(cte.this, exp.Select) else cte.this.find(exp.Select)
        if cte_select is None:
            continue
        group = cte_select.args.get("group")
        if group is None:
            continue

        grouped_fields = [item.sql(dialect="hive") for item in group.expressions] or ["la llave agrupada"]
        for projection in cte_select.expressions:
            alias = projection.alias_or_name or projection.sql(dialect="hive")
            expression = projection.this if isinstance(projection, exp.Alias) else projection
            agg_node = next((node for node in expression.walk() if isinstance(node, exp.AggFunc)), None)
            if agg_node is None:
                continue
            rule_id = _rule_id(rule_counter)
            rules.append(
                RuleDetail(
                    id=rule_id,
                    description=_describe_aggregation_rule(cte_name, grouped_fields, alias, agg_node),
                    applies_in="Paso 1",
                )
            )
            rule_counter += 1
    return rules, rule_counter


def _describe_aggregation_rule(
    cte_name: str,
    grouped_fields: List[str],
    alias: str,
    agg_node: exp.Expression,
) -> str:
    group_text = ", ".join(grouped_fields)
    source_fields = _collect_column_names(agg_node) or [alias]
    source_text = ", ".join(source_fields)
    func_name = getattr(agg_node, "key", agg_node.__class__.__name__).upper()
    if func_name == "MIN":
        action = f"se conserva el menor valor de {source_text}"
    elif func_name == "MAX":
        action = f"se conserva el mayor valor de {source_text}"
    elif func_name == "SUM":
        action = f"se suma el valor de {source_text}"
    elif func_name == "COUNT":
        action = f"se cuenta la ocurrencia de {source_text}"
    elif func_name == "AVG":
        action = f"se calcula el promedio de {source_text}"
    else:
        action = f"se aplica la agregacion {func_name} sobre {source_text}"
    return f"En la CTE {cte_name}, para cada {group_text}, {action} para obtener {alias}."


def _build_source_resolution_maps(
    select_expr: exp.Expression,
) -> Tuple[Dict[str, Dict[str, ColumnLineage]], Dict[str, List[str]]]:
    cte_lineage_by_name: Dict[str, Dict[str, ColumnLineage]] = {}
    cte_tables_by_name: Dict[str, List[str]] = {}
    with_expr = select_expr.args.get("with") or select_expr.args.get("with_")
    for cte in with_expr.expressions if with_expr else []:
        cte_name = (cte.alias_or_name or "").lower()
        if not cte_name:
            continue
        cte_lineage_by_name[cte_name] = get_column_lineage(cte.this)
        cte_tables_by_name[cte_name] = _extract_physical_tables(cte.this)

    source_lineage_by_alias: Dict[str, Dict[str, ColumnLineage]] = {}
    source_tables_by_alias: Dict[str, List[str]] = {}
    for index, node in enumerate(_collect_query_source_nodes(select_expr), start=1):
        alias = _alias_for_source(node, default=f"s{index}").lower()
        if isinstance(node, exp.Subquery):
            source_lineage_by_alias[alias] = get_column_lineage(node.this)
            source_tables_by_alias[alias] = _extract_physical_tables(node.this)
            continue
        if isinstance(node, exp.Table):
            source_tables_by_alias[alias] = _extract_physical_tables(node)
            cte_name = (node.name or "").lower()
            if cte_name in cte_lineage_by_name:
                source_lineage_by_alias[alias] = cte_lineage_by_name[cte_name]
                source_tables_by_alias[alias] = cte_tables_by_name.get(cte_name, source_tables_by_alias[alias])

    return source_lineage_by_alias, source_tables_by_alias


def _extract_physical_tables(expression: exp.Expression) -> List[str]:
    seen: "OrderedDict[str, None]" = OrderedDict()
    for table in expression.find_all(exp.Table):
        if table.name:
            seen[_table_identifier(table)] = None
    return list(seen.keys())


def _expand_physical_source_fields(
    expression: exp.Expression,
    existing_fields: List[str],
    source_lineage_by_alias: Dict[str, Dict[str, ColumnLineage]],
    source_tables_by_alias: Dict[str, List[str]],
) -> List[str]:
    seen: "OrderedDict[str, None]" = OrderedDict((item, None) for item in existing_fields if item)

    for reference in _collect_column_names(expression):
        if "." not in reference:
            continue
        alias, column_name = reference.split(".", 1)
        alias_key = alias.lower()
        column_key = column_name.lower()

        for source in source_lineage_by_alias.get(alias_key, {}).get(
            column_key,
            ColumnLineage(
                column_name=column_key,
                display_name=column_name,
                expression_sql="",
                lineage_type="derived",
            ),
        ).physical_sources:
            seen[f"{source.base_table}.{source.source_column}"] = None

        for table_name in source_tables_by_alias.get(alias_key, []):
            seen[f"{table_name}.{column_name}"] = None

    return list(seen.keys())


def _contains_case(expression: exp.Expression) -> bool:
    return any(isinstance(node, exp.Case) for node in expression.walk())


def _build_case_rule(field_name: str, expression: exp.Expression) -> str:
    case = next(node for node in expression.walk() if isinstance(node, exp.Case))
    referenced_fields = ", ".join(_collect_column_names(case)) or "los campos disponibles"
    return (
        f"El campo {field_name} se clasifica evaluando {referenced_fields} y asignando un valor "
        "segun la condicion que se cumpla."
    )


def _rule_id(number: int) -> str:
    return f"RN-{number:02d}"


def _collect_column_names(expression: exp.Expression) -> List[str]:
    ordered: "OrderedDict[str, None]" = OrderedDict()
    for column in expression.find_all(exp.Column):
        name = column.sql(dialect="hive")
        ordered[name] = None
    return list(ordered.keys())


def _collect_source_aliases(expression: exp.Expression) -> List[str]:
    aliases = OrderedDict()
    for column in expression.find_all(exp.Column):
        if column.table:
            aliases[column.table] = None
    return list(aliases.keys())


def classify_expression(expression: exp.Expression, alias: str) -> Tuple[str, str]:
    if isinstance(expression, exp.Column):
        if expression.name.lower() == alias.lower():
            return "D", "—"
        return "T", "Renombre"

    flags: List[str] = []
    if any(isinstance(node, exp.AggFunc) for node in expression.walk()):
        flags.append("Agregacion")
    if any(isinstance(node, (exp.Cast, exp.TryCast)) for node in expression.walk()):
        flags.append("Conv. tipo")
    if any(isinstance(node, exp.Trim) for node in expression.walk()):
        flags.append("Limpieza")
    if any(isinstance(node, exp.Coalesce) for node in expression.walk()):
        flags.append("Cascada")
    if any(isinstance(node, exp.Case) for node in expression.walk()):
        flags.append("Clasificacion")
    if _is_constant_expression(expression):
        flags.append("Constante")

    if not flags and _has_calculation(expression):
        flags.append("Calculo")

    if not flags:
        flags.append("Calculo")

    subtype = " + ".join(_unique(flags))
    return "T", subtype


def _unique(values: Sequence[str]) -> List[str]:
    ordered: "OrderedDict[str, None]" = OrderedDict()
    for value in values:
        ordered[value] = None
    return list(ordered.keys())


def _is_constant_expression(expression: exp.Expression) -> bool:
    if isinstance(expression, (exp.CurrentTimestamp, exp.CurrentDate, exp.CurrentTime)):
        return True
    if isinstance(expression, exp.Literal):
        return True
    return not _collect_column_names(expression) and not any(
        isinstance(node, exp.Subquery) for node in expression.walk()
    )


def _has_calculation(expression: exp.Expression) -> bool:
    calculation_nodes = (
        exp.Func,
        exp.Add,
        exp.Sub,
        exp.Mul,
        exp.Div,
        exp.Concat,
        exp.Paren,
    )
    return any(isinstance(node, calculation_nodes) for node in expression.walk())


def describe_expression(expression: exp.Expression, alias: str) -> str:
    if isinstance(expression, exp.Column):
        if expression.name.lower() == alias.lower():
            return f"Se traslada sin cambios el campo {expression.sql(dialect='hive')} hacia {alias}."
        return f"Se renombra el campo {expression.sql(dialect='hive')} para publicarlo como {alias}."
    if isinstance(expression, (exp.Cast, exp.TryCast)):
        source = describe_value(expression.this)
        target = expression.to.sql(dialect="hive") if expression.to else "otro tipo"
        return f"Se convierte {source} al tipo {target} para obtener {alias}."
    if isinstance(expression, exp.Coalesce):
        values = " y luego ".join(describe_value(item) for item in expression.expressions)
        return f"Se toma el primer valor disponible entre {values} para construir {alias}."
    if isinstance(expression, exp.Case):
        fields = ", ".join(_collect_column_names(expression)) or "los campos disponibles"
        return f"Se clasifica {alias} evaluando {fields} y asignando un valor segun la condicion cumplida."
    if isinstance(expression, exp.Trim):
        return f"Se limpia el valor de {describe_value(expression.this)} eliminando espacios para obtener {alias}."
    if isinstance(expression, exp.Concat):
        parts = " con ".join(describe_value(item) for item in expression.expressions)
        return f"Se concatena {parts} para obtener {alias}."
    if isinstance(expression, exp.CurrentTimestamp):
        return f"Se asigna la fecha y hora actual del proceso al campo {alias}."
    if isinstance(expression, exp.CurrentDate):
        return f"Se asigna la fecha actual del proceso al campo {alias}."
    if any(isinstance(node, exp.AggFunc) for node in expression.walk()):
        fields = ", ".join(_collect_column_names(expression)) or "los registros agrupados"
        return f"Se agrega informacion a partir de {fields} para calcular {alias}."

    columns = _collect_column_names(expression)
    if columns:
        return f"Se calcula {alias} usando {', '.join(columns)}."
    return f"Se asigna un valor constante o derivado al campo {alias}."


def describe_value(expression: Optional[exp.Expression]) -> str:
    if expression is None:
        return "valor no identificado"
    if isinstance(expression, exp.Column):
        return expression.sql(dialect="hive")
    if isinstance(expression, exp.Literal):
        return expression.this.strip("'\"")
    if isinstance(expression, exp.Trim):
        return f"el valor limpio de {describe_value(expression.this)}"
    if isinstance(expression, (exp.Cast, exp.TryCast)):
        return describe_value(expression.this)
    if isinstance(expression, exp.Coalesce):
        return "el primer valor disponible"
    if isinstance(expression, exp.Concat):
        return "la concatenacion de " + " y ".join(describe_value(item) for item in expression.expressions)
    if isinstance(expression, (exp.CurrentTimestamp, exp.CurrentDate, exp.CurrentTime)):
        return "la marca de tiempo del proceso"
    if isinstance(expression, exp.Paren):
        return describe_value(expression.this)
    columns = _collect_column_names(expression)
    if columns:
        return ", ".join(columns)
    return _sanitize_sql_words(expression.sql(dialect="hive"))


def describe_condition(expression: Optional[exp.Expression]) -> str:
    if expression is None:
        return "no se definio una condicion"
    if isinstance(expression, exp.And):
        return f"{describe_condition(expression.this)} y {describe_condition(expression.expression)}"
    if isinstance(expression, exp.Or):
        return f"{describe_condition(expression.this)} o {describe_condition(expression.expression)}"
    if isinstance(expression, exp.Paren):
        return describe_condition(expression.this)
    if isinstance(expression, exp.EQ):
        return f"{describe_value(expression.this)} es igual a {describe_value(expression.expression)}"
    if isinstance(expression, exp.NEQ):
        return f"{describe_value(expression.this)} es distinto de {describe_value(expression.expression)}"
    if isinstance(expression, exp.GT):
        return f"{describe_value(expression.this)} es mayor que {describe_value(expression.expression)}"
    if isinstance(expression, exp.GTE):
        return f"{describe_value(expression.this)} es mayor o igual que {describe_value(expression.expression)}"
    if isinstance(expression, exp.LT):
        return f"{describe_value(expression.this)} es menor que {describe_value(expression.expression)}"
    if isinstance(expression, exp.LTE):
        return f"{describe_value(expression.this)} es menor o igual que {describe_value(expression.expression)}"
    if isinstance(expression, exp.Like):
        return f"{describe_value(expression.this)} coincide con el valor {describe_value(expression.expression)}"
    if isinstance(expression, exp.ILike):
        return f"{describe_value(expression.this)} coincide sin distinguir mayusculas con {describe_value(expression.expression)}"
    if isinstance(expression, exp.Not):
        return f"no se cumple que {describe_condition(expression.this)}"
    if isinstance(expression, exp.Is):
        return f"{describe_value(expression.this)} es {describe_value(expression.expression)}"
    if isinstance(expression, exp.Between):
        low = describe_value(expression.args.get("low"))
        high = describe_value(expression.args.get("high"))
        return f"{describe_value(expression.this)} se encuentra entre {low} y {high}"
    if isinstance(expression, exp.In):
        options = ", ".join(describe_value(item) for item in expression.expressions)
        return f"{describe_value(expression.this)} toma alguno de estos valores: {options}"
    return _sanitize_sql_words(expression.sql(dialect="hive"))


def _sanitize_sql_words(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized.lower() in SQL_KEYWORDS:
        return f"el valor {normalized}"
    return normalized


def _field_steps(
    expression: exp.Expression,
    filters: List[FilterDetail],
    joins: List[JoinDetail],
) -> List[str]:
    steps = ["Paso 5", "Paso 6"]
    if any(isinstance(node, exp.Subquery) for node in expression.walk()):
        steps.insert(0, "Paso 1")
    if _collect_source_aliases(expression):
        steps.insert(0, "Paso 2")
    if joins:
        steps.append("Paso 3")
    if filters:
        steps.append("Paso 4")
    return _unique(steps)


def _assign_used_steps(
    alias_sources: Dict[str, SourceDetail],
    select_expr: exp.Expression,
    filters: List[FilterDetail],
) -> None:
    step_map: Dict[str, Set[str]] = {alias: set() for alias in alias_sources}
    root_select_ids = {id(branch) for branch in _iter_query_branches(select_expr)}

    primary_branch = _first_select(select_expr)
    from_expr = primary_branch.args.get("from_") if primary_branch is not None else None
    if from_expr and from_expr.this is not None:
        primary_alias = _alias_for_source(from_expr.this, default="")
        if primary_alias in step_map:
            step_map[primary_alias].add("Paso 2")

    for alias, source in alias_sources.items():
        if source.source_kind in {"cte", "subquery"}:
            step_map[alias].add("Paso 1")

    for branch in _iter_query_branches(select_expr):
        for join in branch.args.get("joins") or []:
            join_alias = _alias_for_source(join.this, default="")
            if join_alias in step_map:
                step_map[join_alias].add("Paso 3")
            for alias in _collect_source_aliases(join.args.get("on")) if join.args.get("on") else []:
                if alias in step_map:
                    step_map[alias].add("Paso 3")

    for where in select_expr.find_all(exp.Where):
        parent_select = where.find_ancestor(exp.Select)
        if parent_select is not None and id(parent_select) not in root_select_ids:
            subquery_alias = _nearest_subquery_alias(where)
            if subquery_alias in step_map:
                step_map[subquery_alias].update({"Paso 1", "Paso 4"})
        else:
            for alias in _collect_source_aliases(where.this):
                if alias in step_map:
                    step_map[alias].add("Paso 4")

    for projection in _query_projections(select_expr):
        expression = projection.this if isinstance(projection, exp.Alias) else projection
        for alias in _collect_source_aliases(expression):
            if alias in step_map:
                step_map[alias].update({"Paso 5", "Paso 6"})

    for alias, source in alias_sources.items():
        source.used_in_steps = _sort_steps(step_map.get(alias, set()))


def _sort_steps(steps: Set[str]) -> List[str]:
    def key(value: str) -> Tuple[int, str]:
        match = re.search(r"(\d+)", value)
        return (int(match.group(1)) if match else 999, value)

    return sorted(steps, key=key)


def _assign_source_field_contributions(
    alias_sources: Dict[str, SourceDetail],
    transformations: List[TransformationDetail],
) -> None:
    contributions: Dict[str, Set[str]] = {alias: set() for alias in alias_sources}
    for transformation in transformations:
        for alias in transformation.origin.split(" / "):
            if alias and alias != "—" and alias in contributions:
                contributions[alias].add(transformation.field_name)

    for alias, source in alias_sources.items():
        fields = sorted(contributions.get(alias, set()))
        source.fields_generated = fields or ["No genera campos finales directos"]


def _extract_compute_stats_tables(statements: Sequence[str]) -> List[str]:
    tables: List[str] = []
    pattern = re.compile(r"compute\s+stats\s+([^\s;]+)", re.IGNORECASE)
    for statement in statements:
        match = pattern.search(statement)
        if match:
            tables.append(match.group(1))
    return tables


def _build_steps(
    select_expr: exp.Expression,
    target_table: str,
    ctes: List[str],
    subqueries: List[str],
    alias_sources: Dict[str, SourceDetail],
    joins: List[JoinDetail],
    filters: List[FilterDetail],
    transformations: List[TransformationDetail],
    rules: List[RuleDetail],
    compute_stats_tables: List[str],
) -> List[ProcessStep]:
    source_names = [source.table_name for source in alias_sources.values()]
    join_rule_ids = [join.rule_id for join in joins if join.rule_id]
    filter_rule_ids = [flt.rule_id for flt in filters if flt.rule_id]
    transformation_rule_ids = [item.rule_id for item in transformations if item.rule_id]
    base_set_ops = _collect_base_set_operations(select_expr)
    base_source_names = _collect_base_source_tables(select_expr)
    step_2_title = "Lectura y consolidacion de fuente base" if base_set_ops else "Lectura de fuente base"
    step_2_objective = (
        "Leer la fuente base y consolidar sus entradas antes de ubicar los campos que alimentan el resultado final."
        if base_set_ops
        else "Leer la fuente base y ubicar los campos que alimentan el resultado final."
    )
    step_2_result = (
        "Base principal consolidada y lista para ser enriquecida."
        if base_set_ops
        else "Base principal lista para ser enriquecida."
    )

    steps = [
        ProcessStep(
            number=1,
            title="Preparacion logica",
            objective="Preparar CTEs y subconsultas antes del ensamble final.",
            depends_on="Ninguno",
            tables_involved=ctes + subqueries or ["No aplica"],
            join_criteria=[],
            join_type=[],
            meaning=[],
            selection_criteria=[flt.condition_text for flt in filters if flt.step == "Paso 1"] or ["No aplica"],
            extracted_fields=[item.field_name for item in transformations[: min(5, len(transformations))]] or ["No aplica"],
            rule_ids=[rule.id for rule in rules if rule.applies_in == "Paso 1"],
            result="Conjuntos logicos preparados para alimentar el ensamble.",
        ),
        ProcessStep(
            number=2,
            title=step_2_title,
            objective=step_2_objective,
            depends_on="Paso 1 si existe logica previa; en otro caso, Ninguno",
            tables_involved=base_source_names or source_names[:1] or ["No identificada"],
            join_criteria=[item["criteria"] for item in base_set_ops] or [],
            join_type=[item["operation"] for item in base_set_ops] or [],
            meaning=[item["meaning"] for item in base_set_ops] or [],
            selection_criteria=["No aplica"],
            extracted_fields=sorted(
                {field for item in transformations for field in item.source_fields[:3]}
            )[:12]
            or ["No aplica"],
            rule_ids=[],
            result=step_2_result,
        ),
        ProcessStep(
            number=3,
            title="Cruces y enriquecimiento",
            objective="Cruzar la base principal con otras fuentes para completar contexto.",
            depends_on="Paso 2",
            tables_involved=[join.source_name for join in joins] or ["No aplica"],
            join_criteria=[join.condition_text for join in joins] or ["No aplica"],
            join_type=[join.join_type for join in joins] or ["No aplica"],
            meaning=[join.meaning for join in joins] or ["No aplica"],
            selection_criteria=["No aplica"],
            extracted_fields=["Los campos enriquecidos se documentan en la Seccion 5."],
            rule_ids=join_rule_ids,
            result="Fuentes integradas para el armado final.",
        ),
        ProcessStep(
            number=4,
            title="Aplicacion de filtros",
            objective="Aplicar criterios de inclusion o exclusion sobre el conjunto integrado.",
            depends_on="Paso 3",
            tables_involved=source_names or ["No aplica"],
            join_criteria=[],
            join_type=[],
            meaning=[],
            selection_criteria=[flt.condition_text for flt in filters if flt.step == "Paso 4"] or ["No aplica"],
            extracted_fields=["No se agregan transformaciones; ver Seccion 5 para el detalle de campos."],
            rule_ids=filter_rule_ids,
            result="Conjunto depurado segun las reglas activas del proceso.",
        ),
        ProcessStep(
            number=5,
            title="Proyeccion de campos finales",
            objective="Construir los campos finales del producto con reglas y transformaciones.",
            depends_on="Paso 4",
            tables_involved=source_names or ["No aplica"],
            join_criteria=[],
            join_type=[],
            meaning=[],
            selection_criteria=["Las reglas RN aplicables se documentan en la Seccion 6."],
            extracted_fields=[item.field_name for item in transformations],
            rule_ids=transformation_rule_ids,
            result="Estructura final del producto lista para publicacion.",
        ),
        ProcessStep(
            number=6,
            title="Publicacion",
            objective="Publicar el resultado final en la tabla destino del pipeline.",
            depends_on="Paso 5",
            tables_involved=[target_table],
            join_criteria=[],
            join_type=[],
            meaning=[],
            selection_criteria=["No aplica"],
            extracted_fields=[item.field_name for item in transformations],
            rule_ids=[],
            result=f"Tabla destino {target_table} actualizada mediante sobreescritura controlada.",
        ),
        ProcessStep(
            number=7,
            title="Cierre y estadisticas",
            objective="Actualizar operaciones posteriores a la publicacion del resultado.",
            depends_on="Paso 6",
            tables_involved=compute_stats_tables or [target_table],
            join_criteria=[],
            join_type=[],
            meaning=[],
            selection_criteria=["No aplica"],
            extracted_fields=["No aplica"],
            rule_ids=[],
            result=(
                "Se ejecutan operaciones de estadisticas sobre la salida."
                if compute_stats_tables
                else "No se detectaron operaciones de estadisticas explicitas en el SQL."
            ),
        ),
    ]
    return steps


def _collect_base_set_operations(select_expr: exp.Select) -> List[Dict[str, str]]:
    base_node: Optional[exp.Expression] = None
    if isinstance(select_expr, exp.SetOperation):
        base_node = select_expr
    else:
        first_select = _first_select(select_expr)
        from_expr = first_select.args.get("from_") if first_select is not None else None
        if from_expr and from_expr.this is not None and isinstance(from_expr.this, exp.Subquery):
            base_node = from_expr.this.this
    if base_node is None:
        return []

    operations: List[Dict[str, str]] = []
    seen: Set[Tuple[str, str, str]] = set()
    for node in base_node.walk():
        if not isinstance(node, exp.Union):
            continue
        operation = "UNION ALL" if node.args.get("distinct") is False else "UNION"
        left_sources = _extract_physical_table_names(node.left)
        right_sources = _extract_physical_table_names(node.right)
        criteria = _describe_set_operation_criteria(left_sources, right_sources)
        meaning = _describe_set_operation_meaning(operation)
        key = (operation, criteria, meaning)
        if key in seen:
            continue
        seen.add(key)
        operations.append(
            {
                "operation": operation,
                "criteria": criteria,
                "meaning": meaning,
            }
        )
    return operations


def _collect_base_source_tables(select_expr: exp.Expression) -> List[str]:
    if isinstance(select_expr, exp.SetOperation):
        return _extract_physical_table_names(select_expr)
    first_select = _first_select(select_expr)
    from_expr = first_select.args.get("from_") if first_select is not None else None
    if not from_expr or from_expr.this is None:
        return []
    if isinstance(from_expr.this, exp.Subquery):
        return _extract_physical_table_names(from_expr.this.this)
    if isinstance(from_expr.this, exp.Table):
        return [from_expr.this.sql(dialect="hive")]
    return []


def _describe_set_operation_criteria(left_sources: List[str], right_sources: List[str]) -> str:
    left_text = ", ".join(left_sources) if left_sources else "la primera entrada"
    right_text = ", ".join(right_sources) if right_sources else "la segunda entrada"
    return f"Se apilan los registros de {left_text} con los de {right_text}."


def _describe_set_operation_meaning(operation: str) -> str:
    if operation == "UNION ALL":
        return "Integra ambas entradas y conserva todos los registros, incluso si existen duplicados."
    return "Integra ambas entradas y elimina duplicados en el conjunto resultante."


def _query_projections(select_expr: exp.Expression) -> List[exp.Expression]:
    projections = list(getattr(select_expr, "expressions", []) or [])
    if projections:
        return projections
    first_select = _first_select(select_expr)
    return list(first_select.expressions) if first_select is not None else []


def _first_select(expression: exp.Expression) -> Optional[exp.Select]:
    if isinstance(expression, exp.Select):
        return expression
    if isinstance(expression, exp.Subquery):
        return _first_select(expression.this)
    if isinstance(expression, exp.SetOperation):
        return _first_select(expression.left) or _first_select(expression.right)
    return expression.find(exp.Select)


def _iter_query_branches(select_expr: exp.Expression) -> Iterable[exp.Select]:
    if isinstance(select_expr, exp.SetOperation):
        yield from _iter_query_branches(select_expr.left)
        yield from _iter_query_branches(select_expr.right)
        return
    first_select = _first_select(select_expr)
    if first_select is not None:
        yield first_select


def _collect_query_source_nodes(select_expr: exp.Expression) -> List[exp.Expression]:
    source_nodes: List[exp.Expression] = []
    for branch in _iter_query_branches(select_expr):
        from_expr = branch.args.get("from_")
        if from_expr and from_expr.this is not None:
            source_nodes.append(from_expr.this)
        for join in branch.args.get("joins") or []:
            if join.this is not None:
                source_nodes.append(join.this)
    return source_nodes
