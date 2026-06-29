from __future__ import annotations

import re
import sqlite3
from csv import DictReader
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    import duckdb
except ImportError:  # pragma: no cover - optional dependency
    duckdb = None

from src.config import load_project_config
from src.models import ProjectConfig, SqlAnalysis
from src.sql_parser import parse_sql_file

EXPORT_OPTIONS = {
    "include_contract_custom_properties": False,
    "include_schema_custom_properties": False,
    "include_field_custom_properties": False,
    "include_classification": True,
    "include_primary_key_flags": False,
    "include_partition_flags_when_true": True,
    "include_examples": True,
}


def export_datacontract(
    sql_path: str,
    config_path: str,
    output_path: str | Path,
    profile_path: str | Path | None = None,
    profile_table: str | None = None,
    profile_engine: str | None = None,
    sqlite_path: str | Path | None = None,
    sqlite_table: str | None = None,
    ddl_path: str | Path | None = None,
    csv_path: str | Path | None = None,
) -> Dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    config = load_project_config(config_path)
    analysis = parse_sql_file(sql_path, config)
    resolved_profile_path = profile_path or sqlite_path
    resolved_profile_table = profile_table or sqlite_table or analysis.target_table
    table_profile = _load_tabular_profile(
        resolved_profile_path,
        resolved_profile_table,
        profile_engine=profile_engine,
    )
    resolved_ddl_path = ddl_path or _resolve_table_sidecar_path(analysis.target_table, "input/ddl")
    ddl_profile = _load_impala_ddl_profile(resolved_ddl_path)
    prepared_csv_path = _prepare_csv_for_cli(csv_path, output.parent)
    csv_profile = _load_csv_profile(prepared_csv_path)
    dictionary_profile = _load_dictionary_profile(analysis.target_table)
    contract = build_datacontract(analysis, config, table_profile, ddl_profile, csv_profile, dictionary_profile)

    output.write_text(
        yaml.safe_dump(contract, allow_unicode=False, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )

    return {
        "sql": sql_path,
        "config": config_path,
        "output": str(output),
        "format": "odcs",
        "profile_path": str(resolved_profile_path) if resolved_profile_path else None,
        "profile_table": table_profile["table"] if table_profile else None,
        "profile_engine": table_profile["engine"] if table_profile else None,
        "sqlite_path": str(sqlite_path) if sqlite_path else None,
        "sqlite_table": table_profile["table"] if table_profile and table_profile["engine"] == "sqlite" else None,
        "ddl_path": ddl_profile["path"] if ddl_profile else None,
        "csv_path": str(prepared_csv_path) if prepared_csv_path else None,
        "dictionary_path": dictionary_profile["path"] if dictionary_profile else None,
        "field_count": len(analysis.transformations),
    }


def build_datacontract(
    analysis: SqlAnalysis,
    config: ProjectConfig,
    table_profile: Optional[Dict[str, Any]] = None,
    ddl_profile: Optional[Dict[str, Any]] = None,
    csv_profile: Optional[Dict[str, Any]] = None,
    dictionary_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    table_name = analysis.target_table.split(".")[-1]
    field_profiles = (table_profile or {}).get("fields", {})
    ddl_fields = (ddl_profile or {}).get("fields", {})
    csv_fields = (csv_profile or {}).get("fields", {})
    dictionary_fields = (dictionary_profile or {}).get("fields", {})
    schema_object = {
        "name": table_name,
        "physicalName": (ddl_profile or {}).get("table_name") or analysis.target_table,
        "logicalType": "object",
        "physicalType": "table",
        "description": _model_description(config, analysis, dictionary_profile),
        "dataGranularityDescription": (
            config.seccion_1.ficha_producto.granularidad
            or f"Una fila por registro publicado en {analysis.target_table}."
        ),
        "tags": _schema_tags(config),
        "properties": _build_fields(analysis, field_profiles, ddl_fields, csv_fields, dictionary_fields),
    }

    contract: Dict[str, Any] = {
        "apiVersion": "v3.1.0",
        "kind": "DataContract",
        "id": _slugify(analysis.target_table),
        "name": _slugify(config.producto_funcional),
        "version": "0.1.0",
        "status": "active",
        "domain": config.seccion_1.ficha_producto.dominio or None,
        "dataProduct": config.producto_funcional,
        "description": {
            "purpose": config.seccion_1.ficha_producto.proposito or f"Contrato del dataset {analysis.target_table}.",
            "usage": (
                f"Frecuencia: {config.seccion_1.ficha_producto.frecuencia or config.frecuencia}. "
                f"Consumidores: {', '.join(config.seccion_1.ficha_producto.consumidores_objetivo or ['Por definir'])}."
            ),
            "limitations": "; ".join(
                config.seccion_1.referencia_rapida.que_no_hace
                or ["No sustituye reglas de negocio no visibles en el SQL."]
            ),
        },
        "tags": _contract_tags(config),
        "schema": [schema_object],
        "servers": _build_servers(csv_path=(csv_profile or {}).get("path")),
        "contractCreatedTs": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }

    schema_custom_properties = _object_custom_properties(analysis)
    if schema_custom_properties and EXPORT_OPTIONS["include_schema_custom_properties"]:
        schema_object["customProperties"] = schema_custom_properties

    contract_custom_properties = _contract_custom_properties(
        config,
        analysis,
        table_profile,
        ddl_profile,
        csv_profile,
        dictionary_profile,
    )
    if contract_custom_properties and EXPORT_OPTIONS["include_contract_custom_properties"]:
        contract["customProperties"] = contract_custom_properties

    return _prune_none(contract)


def _build_fields(
    analysis: SqlAnalysis,
    field_profiles: Dict[str, Dict[str, Any]],
    ddl_fields: Dict[str, Dict[str, Any]],
    csv_fields: Dict[str, Dict[str, Any]],
    dictionary_fields: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    for transformation in analysis.transformations:
        key = transformation.field_name.lower()
        profile = field_profiles.get(key, {})
        ddl_field = ddl_fields.get(key, {})
        csv_field = csv_fields.get(key, {})
        dictionary_field = dictionary_fields.get(key, {})
        field = {
            "name": transformation.field_name,
            "logicalType": profile.get("logical_type")
            or ddl_field.get("logical_type")
            or _infer_logical_type(transformation, analysis),
            "physicalType": ddl_field.get("physical_type") or profile.get("physical_type") or None,
            "description": dictionary_field.get("description") or transformation.description,
            "required": bool(profile.get("required", ddl_field.get("required", False))),
            "businessName": dictionary_field.get("business_name") or _business_name(transformation.field_name),
        }
        if EXPORT_OPTIONS["include_classification"]:
            field["classification"] = transformation.field_type
        if EXPORT_OPTIONS["include_primary_key_flags"]:
            field["primaryKey"] = False
            field["primaryKeyPosition"] = -1
        if EXPORT_OPTIONS["include_partition_flags_when_true"] and ddl_field.get("partitioned", False):
            field["partitioned"] = True
            field["partitionKeyPosition"] = 1
        if EXPORT_OPTIONS["include_examples"]:
            field["examples"] = _build_examples(profile, csv_field)

        field_custom_properties = _field_custom_properties(transformation, profile, ddl_field, csv_field)
        if field_custom_properties and EXPORT_OPTIONS["include_field_custom_properties"]:
            field["customProperties"] = field_custom_properties

        fields.append(_prune_none(field))
    return fields


def _model_description(
    config: ProjectConfig,
    analysis: SqlAnalysis,
    dictionary_profile: Optional[Dict[str, Any]] = None,
) -> str:
    ficha = config.seccion_1.ficha_producto
    if dictionary_profile and dictionary_profile.get("table_description"):
        return dictionary_profile["table_description"]
    return ficha.proposito or f"Modelo tabular publicado en {analysis.target_table}."


def _infer_logical_type(transformation, analysis: SqlAnalysis) -> str:
    lineage = analysis.column_lineage.get(transformation.field_name.lower())
    functions = {item.upper() for item in (lineage.functions if lineage else [])}
    name = transformation.field_name.lower()

    if any(token in name for token in ["fecha", "fec_", "_fec", "date"]):
        return "date"
    if any(token in name for token in ["timestamp", "ts", "hora", "datetime"]):
        return "timestamp"
    if any(token in name for token in ["flag", "indicador", "es_", "tiene_", "activo"]):
        return "boolean"
    if any(token in name for token in ["id", "folio", "numero", "saldo", "monto", "importe", "total"]):
        return "number"
    if "COUNT" in functions or "SUM" in functions:
        return "number"
    return "string"


def _load_tabular_profile(
    profile_path: str | Path | None,
    requested_table: str,
    profile_engine: str | None = None,
) -> Optional[Dict[str, Any]]:
    if not profile_path:
        return None

    engine = _detect_profile_engine(profile_path, profile_engine)
    if engine == "duckdb":
        return _load_duckdb_profile(profile_path, requested_table)
    if engine == "sqlite":
        return _load_sqlite_profile(profile_path, requested_table)
    raise ValueError(f"Motor de profile no soportado: {engine}")


def _detect_profile_engine(profile_path: str | Path, profile_engine: str | None = None) -> str:
    if profile_engine:
        normalized = profile_engine.strip().lower()
        if normalized in {"duckdb", "sqlite"}:
            return normalized
        raise ValueError(f"Motor de profile no soportado: {profile_engine}")

    suffixes = {suffix.lower() for suffix in Path(profile_path).suffixes}
    if ".duckdb" in suffixes or ".ddb" in suffixes:
        return "duckdb"
    return "sqlite"


def resolve_best_tabular_profile(
    profile_paths: List[str | Path],
    requested_tables: List[str],
    profile_engine: str | None = None,
) -> Optional[Dict[str, Any]]:
    for profile_path in profile_paths:
        if not profile_path:
            continue
        for requested_table in requested_tables:
            if not requested_table:
                continue
            profile = _load_tabular_profile(
                profile_path,
                requested_table,
                profile_engine=profile_engine,
            )
            if profile and profile.get("table"):
                return profile

    for profile_path in profile_paths:
        if not profile_path:
            continue
        fallback = _load_tabular_profile(
            profile_path,
            requested_tables[0] if requested_tables else "",
            profile_engine=profile_engine,
        )
        if fallback:
            return fallback
    return None


def _load_duckdb_profile(
    duckdb_path: str | Path,
    requested_table: str,
) -> Optional[Dict[str, Any]]:
    if duckdb is None:
        raise ImportError("DuckDB no esta instalado. Agrega la dependencia 'duckdb' para usar profiles persistidos.")

    path = Path(duckdb_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe la base DuckDB: {path}")

    connection = duckdb.connect(str(path), read_only=True)
    try:
        table_rows = connection.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
            """
        ).fetchall()
        resolved = _resolve_tabular_table_name(table_rows, requested_table)
        if not resolved:
            return {
                "database": str(path),
                "engine": "duckdb",
                "table": None,
                "sample_size": 0,
                "fields": {},
            }

        schema_name, table_name = resolved
        column_rows = connection.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema_name, table_name],
        ).fetchall()
        sample_rows = connection.execute(
            f"SELECT * FROM {_quote_table_reference(schema_name, table_name)} LIMIT 5"
        ).fetchall()

        fields: Dict[str, Dict[str, Any]] = {}
        columns: List[str] = []
        for index, row in enumerate(column_rows):
            column_name = row[0]
            physical_type = (row[1] or "").strip()
            required = str(row[2] or "").upper() == "NO"
            columns.append(column_name)
            fields[column_name.lower()] = {
                "physical_type": physical_type,
                "logical_type": _map_tabular_type(physical_type),
                "required": required,
                "example": _first_non_null_value(sample_rows, index),
            }

        return {
            "database": str(path),
            "engine": "duckdb",
            "table": _display_table_name(schema_name, table_name),
            "sample_size": len(sample_rows),
            "columns": columns,
            "fields": fields,
        }
    finally:
        connection.close()


def _load_sqlite_profile(
    sqlite_path: str | Path | None,
    requested_table: str,
) -> Optional[Dict[str, Any]]:
    if not sqlite_path:
        return None

    path = Path(sqlite_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe la base SQLite: {path}")

    with sqlite3.connect(str(path)) as connection:
        table = _resolve_sqlite_table(connection, requested_table)
        if not table:
            return {
                "database": str(path),
                "engine": "sqlite",
                "table": None,
                "sample_size": 0,
                "fields": {},
            }

        pragma_rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
        sample_rows = connection.execute(f'SELECT * FROM "{table}" LIMIT 5').fetchall()
        columns = [row[1] for row in pragma_rows]

        fields: Dict[str, Dict[str, Any]] = {}
        for index, row in enumerate(pragma_rows):
            column_name = row[1]
            sqlite_type = (row[2] or "").strip()
            notnull = bool(row[3])
            example = _first_non_null_value(sample_rows, index)
            fields[column_name.lower()] = {
                "physical_type": sqlite_type,
                "logical_type": _map_tabular_type(sqlite_type),
                "required": notnull,
                "example": example,
            }

        return {
            "database": str(path),
            "engine": "sqlite",
            "table": table,
            "sample_size": len(sample_rows),
            "columns": columns,
            "fields": fields,
        }


def _resolve_sqlite_table(connection: sqlite3.Connection, requested_table: str) -> Optional[str]:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
        ).fetchall()
    ]
    if not tables:
        return None

    candidates = []
    raw = requested_table.strip()
    last_name = raw.split(".")[-1]
    candidates.extend([raw, last_name, _slugify(last_name), last_name.lower()])

    normalized = {table.lower(): table for table in tables}
    for candidate in candidates:
        exact = normalized.get(candidate.lower())
        if exact:
            return exact

    compact_requested = _slugify(last_name).replace("_", "")
    for table in tables:
        if _slugify(table).replace("_", "") == compact_requested:
            return table
    return None


def _resolve_tabular_table_name(table_rows: List[tuple], requested_table: str) -> Optional[tuple[str, str]]:
    if not table_rows:
        return None

    candidates: Dict[str, tuple[str, str]] = {}
    compact_index: Dict[str, tuple[str, str]] = {}
    for schema_name, table_name in table_rows:
        for candidate in {table_name, f"{schema_name}.{table_name}", _display_table_name(schema_name, table_name)}:
            candidates[candidate.lower()] = (schema_name, table_name)
        compact_index[_slugify(table_name).replace("-", "")] = (schema_name, table_name)

    raw = requested_table.strip()
    last_name = raw.split(".")[-1]
    for candidate in [raw, last_name]:
        exact = candidates.get(candidate.lower())
        if exact:
            return exact

    return compact_index.get(_slugify(last_name).replace("-", ""))


def _display_table_name(schema_name: str | None, table_name: str) -> str:
    if schema_name and schema_name not in {"", "main"}:
        return f"{schema_name}.{table_name}"
    return table_name


def _quote_table_reference(schema_name: str | None, table_name: str) -> str:
    if schema_name:
        return f'"{schema_name}"."{table_name}"'
    return f'"{table_name}"'


def _first_non_null_value(rows: List[tuple], index: int) -> Any:
    for row in rows:
        value = row[index]
        if value is not None:
            return value
    return None


def _map_tabular_type(raw_type: str) -> str:
    normalized = raw_type.strip().upper()
    if not normalized:
        return "string"
    if "INT" in normalized:
        return "integer"
    if any(token in normalized for token in ["REAL", "FLOA", "DOUB", "NUMERIC", "DECIMAL", "HUGEINT", "UBIGINT"]):
        return "number"
    if "BOOL" in normalized:
        return "boolean"
    if "DATE" in normalized and "TIME" not in normalized:
        return "date"
    if any(token in normalized for token in ["TIME", "TIMESTAMP", "DATETIME"]):
        return "timestamp"
    return "string"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "datacontract"


def _business_name(value: str) -> str:
    return value.replace("_", " ").strip().title()


def _contract_tags(config: ProjectConfig) -> List[str]:
    tags = [config.seccion_1.ficha_producto.dominio, config.frecuencia]
    tags.extend(config.seccion_1.ficha_producto.consumidores_objetivo)
    return [str(tag).strip().lower().replace(" ", "_") for tag in tags if tag]


def _schema_tags(config: ProjectConfig) -> List[str]:
    tags = [item.tabla for item in config.seccion_1.tablas_salida]
    return [tag.split(".")[-1] for tag in tags if tag]


def _contract_custom_properties(
    config: ProjectConfig,
    analysis: SqlAnalysis,
    table_profile: Optional[Dict[str, Any]],
    ddl_profile: Optional[Dict[str, Any]],
    csv_profile: Optional[Dict[str, Any]],
    dictionary_profile: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    properties = [
        {"property": "owner", "value": config.seccion_1.ficha_producto.responsable or "Por definir"},
        {"property": "targetTable", "value": analysis.target_table},
        {"property": "sqlFile", "value": analysis.sql_path},
        {"property": "parseArchetype", "value": analysis.metadata.get("parse_archetype")},
        {"property": "fieldCount", "value": len(analysis.transformations)},
        {"property": "sourceCount", "value": len(analysis.sources)},
        {"property": "publicationCount", "value": len(analysis.publications)},
        {"property": "ruleCount", "value": len(analysis.rules)},
        {"property": "publicationsJson", "value": yaml.safe_dump([item.model_dump() for item in analysis.publications], sort_keys=False)},
        {"property": "sourcesJson", "value": yaml.safe_dump([item.model_dump() for item in analysis.sources], sort_keys=False)},
        {"property": "rulesJson", "value": yaml.safe_dump([item.model_dump() for item in analysis.rules], sort_keys=False)},
    ]
    if table_profile:
        properties.extend(
            [
                {"property": "profileEngine", "value": table_profile["engine"]},
                {"property": "profileDatabase", "value": table_profile["database"]},
                {"property": "profileTable", "value": table_profile["table"]},
                {"property": "profileSampleSize", "value": table_profile["sample_size"]},
            ]
        )
    if ddl_profile:
        properties.extend(
            [
                {"property": "ddlDialect", "value": "impala"},
                {"property": "ddlSourcePath", "value": ddl_profile["path"]},
            ]
        )
    if csv_profile:
        properties.extend(
            [
                {"property": "sampleFormat", "value": "csv"},
                {"property": "samplePath", "value": csv_profile["path"]},
                {"property": "sampleRowCount", "value": csv_profile["row_count"]},
            ]
        )
    if dictionary_profile:
        properties.append(
            {"property": "dictionaryPath", "value": dictionary_profile["path"]}
        )
    return [item for item in properties if item["value"] is not None]


def _object_custom_properties(analysis: SqlAnalysis) -> List[Dict[str, Any]]:
    return [
        {"property": "sourceAliases", "value": _json_value([item.alias for item in analysis.sources])},
        {"property": "dependsOnSources", "value": _json_value([item.table_name for item in analysis.sources])},
    ]


def _field_custom_properties(
    transformation,
    profile: Dict[str, Any],
    ddl_field: Dict[str, Any],
    csv_field: Dict[str, Any],
) -> List[Dict[str, Any]]:
    properties = [
        {"property": "subtype", "value": transformation.subtype},
        {"property": "origin", "value": transformation.origin},
        {"property": "sourceFields", "value": _json_value(transformation.source_fields)},
        {"property": "physicalSourceFields", "value": _json_value(transformation.physical_source_fields)},
        {"property": "participatesInSteps", "value": _json_value(transformation.participates_in_steps)},
        {"property": "ruleId", "value": transformation.rule_id},
        {"property": "impalaType", "value": ddl_field.get("physical_type")},
        {"property": "isPartitionColumn", "value": ddl_field.get("partitioned")},
    ]
    return [item for item in properties if item["value"] not in (None, [], "", "—")]


def _build_servers(csv_path: str | None) -> List[Dict[str, str]]:
    if not csv_path:
        return []
    return [
        {
            "type": "local",
            "environment": "mvp",
            "description": "Archivo CSV local para validacion temporal del contrato con Data Contract CLI.",
            "path": csv_path,
            "format": "csv",
        }
    ]


def _load_impala_ddl_profile(ddl_path: str | Path | None) -> Optional[Dict[str, Any]]:
    if not ddl_path:
        return None

    path = Path(ddl_path)
    ddl_text = path.read_text(encoding="utf-8")
    table_match = re.search(r"CREATE\s+TABLE\s+([^\s(]+)\s*\(", ddl_text, flags=re.IGNORECASE)
    table_name = table_match.group(1) if table_match else None

    column_block_match = re.search(
        r"CREATE\s+TABLE\s+[^\s(]+\s*\((.*?)\)\s*PARTITIONED\s+BY",
        ddl_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not column_block_match:
        column_block_match = re.search(
            r"CREATE\s+TABLE\s+[^\s(]+\s*\((.*?)\)\s*(?:STORED|;)",
            ddl_text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    partition_block_match = re.search(
        r"PARTITIONED\s+BY\s*\((.*?)\)\s*(?:STORED|;)",
        ddl_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    fields: Dict[str, Dict[str, Any]] = {}
    for line in _split_ddl_lines(column_block_match.group(1) if column_block_match else ""):
        parsed = _parse_ddl_line(line, partitioned=False)
        if parsed:
            fields[parsed["name"].lower()] = parsed

    for line in _split_ddl_lines(partition_block_match.group(1) if partition_block_match else ""):
        parsed = _parse_ddl_line(line, partitioned=True)
        if parsed:
            fields[parsed["name"].lower()] = parsed

    return {
        "path": str(path),
        "table_name": table_name,
        "fields": fields,
    }


def _split_ddl_lines(block: str) -> List[str]:
    lines = []
    for raw_line in block.splitlines():
        line = raw_line.strip().rstrip(",")
        if line:
            lines.append(line)
    return lines


def _parse_ddl_line(line: str, partitioned: bool) -> Optional[Dict[str, Any]]:
    match = re.match(r"([A-Za-z0-9_]+)\s+([A-Za-z]+(?:\s*\(\s*[\d,\s]+\s*\))?)", line)
    if not match:
        return None
    name, physical_type = match.groups()
    return {
        "name": name,
        "physical_type": physical_type.upper().replace(" ", ""),
        "logical_type": _map_impala_type(physical_type),
        "required": "NOT NULL" in line.upper(),
        "partitioned": partitioned,
    }


def _map_impala_type(physical_type: str) -> str:
    normalized = physical_type.strip().upper()
    if normalized.startswith(("STRING", "CHAR", "VARCHAR")):
        return "string"
    if normalized.startswith(("INT", "BIGINT", "SMALLINT", "TINYINT")):
        return "integer"
    if normalized.startswith(("DECIMAL", "DOUBLE", "FLOAT")):
        return "number"
    if normalized.startswith("BOOLEAN"):
        return "boolean"
    if normalized.startswith("TIMESTAMP"):
        return "timestamp"
    if normalized.startswith("DATE"):
        return "date"
    return "string"


def _load_csv_profile(csv_path: str | Path | None) -> Optional[Dict[str, Any]]:
    if not csv_path:
        return None

    path = Path(csv_path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = DictReader(handle)
        fieldnames = reader.fieldnames or []
        examples = {name.lower(): None for name in fieldnames}
        row_count = 0
        for row in reader:
            row_count += 1
            for field in fieldnames:
                key = field.lower()
                if examples[key] in (None, ""):
                    value = row.get(field)
                    if value not in (None, ""):
                        examples[key] = value

    return {
        "path": str(path),
        "row_count": row_count,
        "fields": {
            name.lower(): {
                "example": examples[name.lower()],
            }
            for name in fieldnames
        },
    }


def _load_dictionary_profile(target_table: str, base_dir: str | Path = "input/diccionario") -> Optional[Dict[str, Any]]:
    table_name = target_table.split(".")[-1]
    resolved_path = _resolve_table_sidecar_path(target_table, base_dir)
    if not resolved_path:
        return None
    path = Path(resolved_path)
    if not path.exists():
        return None

    fields: Dict[str, Dict[str, Any]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        name, description = cells[0], cells[1]
        if not name or name.lower() in {"nombre", "----------------------"}:
            continue
        if set(name) == {"-"}:
            continue
        fields[name.lower()] = {
            "business_name": _business_name(name),
            "description": description,
        }

    return {
        "path": str(path),
        "table_name": table_name,
        "fields": fields,
        "table_description": None,
    }


def _resolve_table_sidecar_path(target_table: str, base_dir: str | Path) -> Optional[str]:
    table_name = target_table.split(".")[-1]
    path = Path(base_dir) / f"{table_name}.txt"
    if path.exists():
        return str(path)
    return None


def _prepare_csv_for_cli(csv_path: str | Path | None, output_dir: Path) -> Optional[str]:
    if not csv_path:
        return None

    source = Path(csv_path)
    raw_bytes = source.read_bytes()
    if b"\x00" not in raw_bytes:
        return str(source)

    sanitized = raw_bytes.replace(b"\x00", b"")
    target = output_dir / f"{source.stem}.clean.csv"
    target.write_bytes(sanitized)
    return str(target)


def _build_examples(profile: Dict[str, Any], csv_field: Dict[str, Any]) -> List[Any]:
    example = profile.get("example", csv_field.get("example"))
    if example in (None, ""):
        return []
    return [example]


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _prune_none(item)
            for key, item in value.items()
            if item is not None and _prune_none(item) not in ({}, [])
        }
    if isinstance(value, list):
        return [_prune_none(item) for item in value if item is not None and _prune_none(item) not in ({}, [])]
    return value
