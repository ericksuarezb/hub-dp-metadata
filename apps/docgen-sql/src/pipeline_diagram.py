from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.config import mask_unresolved_variables
from src.runtime_paths import get_project_root, project_path
from src.sql_business_context import (
    LLM_CONFIG_PATH,
    _extract_chat_completion_text,
    _extract_response_text,
    _resolve_api_key,
    _resolve_api_style,
    load_llm_settings,
)

REPO_ROOT = get_project_root()
PIPELINE_PROMPT_PATH = project_path("config", "prompts", "pipeline_diagram_mermaid.txt")


class PipelineRelation(BaseModel):
    module_key: str
    module_name: str
    sql_file_name: str
    source_node: str
    target_node: str
    relation_label: str
    source_group: str
    target_group: str
    source_kind: str = "table"
    target_kind: str = "table"
    is_pivot: bool = False


class PipelineDiagram(BaseModel):
    mermaid: str
    relations: List[PipelineRelation] = Field(default_factory=list)
    provider: str = "heuristic"
    warning: Optional[str] = None


def build_pipeline_diagram(module_results: List[Dict[str, Any]]) -> PipelineDiagram:
    relations = _extract_pipeline_relations(module_results)
    fallback_mermaid = _build_fallback_mermaid(relations)
    settings = load_llm_settings(LLM_CONFIG_PATH)

    if os.getenv("PYTEST_CURRENT_TEST"):
        return PipelineDiagram(mermaid=fallback_mermaid, relations=relations, provider="heuristic")

    if not settings.enabled:
        return PipelineDiagram(
            mermaid=fallback_mermaid,
            relations=relations,
            provider="heuristic",
            warning="La generacion LLM del diagrama esta desactivada; se uso Mermaid heuristico.",
        )

    api_key = _resolve_api_key(settings)
    if not api_key:
        return PipelineDiagram(
            mermaid=fallback_mermaid,
            relations=relations,
            provider="heuristic",
            warning="No hay API key para generar el diagrama con LLM; se uso Mermaid heuristico.",
        )

    try:
        from openai import OpenAI
    except ImportError:
        return PipelineDiagram(
            mermaid=fallback_mermaid,
            relations=relations,
            provider="heuristic",
            warning="La libreria openai no esta instalada; se uso Mermaid heuristico.",
        )

    try:
        client = OpenAI(api_key=api_key, base_url=settings.api_base)
        messages = _build_llm_messages(module_results)
        api_style = _resolve_api_style(settings)
        if api_style == "chat_completions":
            response = client.chat.completions.create(
                model=settings.model,
                messages=messages,
            )
            raw_text = _extract_chat_completion_text(response)
        else:
            response = client.responses.create(
                model=settings.model,
                input=messages,
            )
            raw_text = _extract_response_text(response)
        mermaid = _normalize_mermaid(raw_text) or fallback_mermaid
        return PipelineDiagram(mermaid=mermaid, relations=relations, provider=settings.provider.lower().strip())
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        return PipelineDiagram(
            mermaid=fallback_mermaid,
            relations=relations,
            provider="heuristic",
            warning=f"No fue posible generar el diagrama con LLM; se uso Mermaid heuristico. Detalle: {exc}",
        )


def write_pipeline_diagram_artifacts(
    artifact_dir: Path,
    diagram: PipelineDiagram,
    base_name: str = "pipeline_diagram",
) -> Dict[str, str]:
    written: Dict[str, str] = {}
    mermaid_path = artifact_dir / f"{base_name}.mmd"
    mermaid_path.write_text(diagram.mermaid, encoding="utf-8")
    written["pipeline_diagram_mermaid"] = str(mermaid_path)
    png_path = artifact_dir / f"{base_name}.png"
    if _render_mermaid_png(mermaid_path, png_path):
        written["pipeline_diagram_png"] = str(png_path)
    return written


def _extract_pipeline_relations(module_results: List[Dict[str, Any]]) -> List[PipelineRelation]:
    relations: List[PipelineRelation] = []
    seen = set()

    for module in module_results:
        analysis = module["analysis"]
        target = analysis.target_table
        module_key = module["module_key"]
        module_name = module["module_name"]
        sql_file_name = module["sql_file_name"]
        sources = list(analysis.sources)

        if sources:
            first_source = sources[0]
            first_tables = _extract_physical_tables_from_source_name(first_source.table_name)
            if len(first_tables) > 1 and "union all" in analysis.resolved_sql.lower():
                union_node = f"{target}::union_all"
                for source_table in first_tables:
                    _append_relation(
                        relations,
                        seen,
                        PipelineRelation(
                            module_key=module_key,
                            module_name=module_name,
                            sql_file_name=sql_file_name,
                            source_node=source_table,
                            target_node=union_node,
                            relation_label="UNION ALL",
                            source_group=_schema_group(source_table),
                            target_group="process",
                            source_kind="table",
                            target_kind="process",
                            is_pivot=False,
                        ),
                    )
                _append_relation(
                    relations,
                    seen,
                    PipelineRelation(
                        module_key=module_key,
                        module_name=module_name,
                        sql_file_name=sql_file_name,
                        source_node=union_node,
                        target_node=target,
                        relation_label="FROM / BASE",
                        source_group="process",
                        target_group=_schema_group(target),
                        source_kind="process",
                        target_kind="table",
                        is_pivot=True,
                    ),
                )
            else:
                for index, source_table in enumerate(first_tables or [first_source.table_name]):
                    _append_relation(
                        relations,
                        seen,
                        PipelineRelation(
                            module_key=module_key,
                            module_name=module_name,
                            sql_file_name=sql_file_name,
                            source_node=source_table,
                            target_node=target,
                            relation_label="FROM / BASE" if index == 0 else "SOURCE",
                            source_group=_schema_group(source_table),
                            target_group=_schema_group(target),
                            is_pivot=index == 0,
                        ),
                    )

        join_by_alias = {join.source_alias.lower(): join.join_type.upper() for join in analysis.joins}
        for source in sources[1:]:
            source_tables = _extract_physical_tables_from_source_name(source.table_name)
            label = join_by_alias.get(source.alias.lower(), "JOIN")
            for source_table in source_tables:
                _append_relation(
                    relations,
                    seen,
                    PipelineRelation(
                        module_key=module_key,
                        module_name=module_name,
                        sql_file_name=sql_file_name,
                        source_node=source_table,
                        target_node=target,
                        relation_label=label,
                        source_group=_schema_group(source_table),
                        target_group=_schema_group(target),
                        is_pivot=False,
                    ),
                )

        known_sources = {relation.source_node for relation in relations if relation.module_key == module_key}
        for source_table in _extract_lineage_tables(module["analysis"]):
            if source_table in known_sources or source_table == target:
                continue
            _append_relation(
                relations,
                seen,
                PipelineRelation(
                    module_key=module_key,
                    module_name=module_name,
                    sql_file_name=sql_file_name,
                    source_node=source_table,
                    target_node=target,
                    relation_label="LINEAGE",
                    source_group=_schema_group(source_table),
                    target_group=_schema_group(target),
                    is_pivot=False,
                ),
            )

    return relations


def _extract_physical_tables_from_source_name(source_name: str) -> List[str]:
    normalized = source_name.split("(subconsulta", 1)[0]
    candidates = [item.strip() for item in normalized.split(",")]
    results: List[str] = []
    seen = set()
    for candidate in candidates:
        base = candidate.split(" AS ", 1)[0].strip()
        if not base or base.startswith("_"):
            continue
        if base not in seen:
            results.append(base)
            seen.add(base)
    return results


def _extract_lineage_tables(analysis) -> List[str]:
    seen: List[str] = []
    for transformation in analysis.transformations:
        for source_field in transformation.physical_source_fields:
            table_name = source_field.rsplit(".", 1)[0] if "." in source_field else source_field
            if table_name not in seen:
                seen.append(table_name)
    return seen


def _append_relation(relations: List[PipelineRelation], seen: set, relation: PipelineRelation) -> None:
    key = (
        relation.module_key,
        relation.source_node,
        relation.target_node,
        relation.relation_label,
    )
    if key in seen:
        return
    seen.add(key)
    relations.append(relation)


def _schema_group(table_name: str) -> str:
    lowered = table_name.lower()
    leaf = lowered.split(".")[-1]
    if lowered.startswith("rd_baz_bdclientes.") or leaf.startswith("rd_"):
        return "raw"
    if lowered.startswith("cd_baz_bdclientes.") or leaf.startswith("cd_"):
        return "cd"
    if lowered.startswith("cu_baz_bdclientes.") or lowered.startswith("ws_ec_cu_baz_bdclientes.") or leaf.startswith("cu_"):
        return "cu"
    if "::" in table_name:
        return "process"
    return "other"


def _build_fallback_mermaid(relations: List[PipelineRelation]) -> str:
    lines = ["flowchart TB", ""]
    groups = {
        "other": "Otros esquemas",
        "raw": "Raw - rd_baz_bdclientes",
        "cu": "CU - cu_baz_bdclientes",
        "cd": "CD - cd_baz_bdclientes",
    }
    nodes_by_group: Dict[str, List[Tuple[str, str]]] = {key: [] for key in groups}
    process_nodes: List[Tuple[str, str]] = []
    seen_nodes = set()

    for relation in relations:
        for node_name, group, is_pivot, kind in (
            (relation.source_node, relation.source_group, relation.is_pivot, relation.source_kind),
            (relation.target_node, relation.target_group, False, relation.target_kind),
        ):
            if node_name in seen_nodes:
                continue
            seen_nodes.add(node_name)
            label = _node_label(node_name, is_pivot, kind)
            if group == "process":
                process_nodes.append((node_name, label))
            elif group in nodes_by_group:
                nodes_by_group[group].append((node_name, label))

    for group_key in ("other", "raw", "cu", "cd"):
        nodes = nodes_by_group[group_key]
        if not nodes:
            continue
        lines.append(f'subgraph {group_key.upper()}["{groups[group_key]}"]')
        for node_name, label in nodes:
            lines.append(f'  {_mermaid_id(node_name)}["{label}"]')
        lines.append("end")
        lines.append("")

    for node_name, label in process_nodes:
        lines.append(f'{_mermaid_id(node_name)}["{label}"]')
    if process_nodes:
        lines.append("")

    for relation in relations:
        lines.append(
            f'{_mermaid_id(relation.source_node)} -->|"{relation.relation_label}"| {_mermaid_id(relation.target_node)}'
        )

    lines.extend(
        [
            "",
            "classDef raw fill:#8B2E1A,stroke:#5C1E11,color:#FFFFFF;",
            "classDef cd fill:#2E7D32,stroke:#1B5E20,color:#FFFFFF;",
            "classDef cu fill:#BDBDBD,stroke:#616161,color:#000000;",
            "classDef other fill:#F9C74F,stroke:#B8860B,color:#000000;",
            "classDef pivot stroke-width:4px;",
            "classDef process fill:#FFFFFF,stroke:#333333,color:#000000,stroke-dasharray: 5 5;",
        ]
    )

    for relation in relations:
        lines.append(f"class {_mermaid_id(relation.source_node)} {relation.source_group};")
        lines.append(f"class {_mermaid_id(relation.target_node)} {relation.target_group};")
        if relation.is_pivot:
            lines.append(f"class {_mermaid_id(relation.source_node)} pivot;")

    return "\n".join(_dedupe_preserve(lines))


def _dedupe_preserve(lines: List[str]) -> List[str]:
    seen = set()
    results: List[str] = []
    for line in lines:
        if line and line in seen:
            continue
        if line:
            seen.add(line)
        results.append(line)
    return results


def _node_label(node_name: str, is_pivot: bool, kind: str) -> str:
    pretty = node_name.replace("::union_all", "")
    if kind == "process" or "::union_all" in node_name:
        return "④ UNION ALL"
    if is_pivot:
        return f"① FROM / PIVOTE<br/>{pretty}"
    return f"③ OUTPUT<br/>{pretty}"


def _build_llm_messages(module_results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    prompt = PIPELINE_PROMPT_PATH.read_text(encoding="utf-8")
    payload = []
    for index, module in enumerate(module_results, start=1):
        analysis = module["analysis"]
        masked_sql, _ = mask_unresolved_variables(analysis.resolved_sql)
        payload.append(
            {
                "process": index,
                "module_key": module["module_key"],
                "module_name": module["module_name"],
                "sql_file_name": module["sql_file_name"],
                "target_table": analysis.target_table,
                "sql": masked_sql,
            }
        )
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": "Genera el diagrama Mermaid para esta secuencia de queries SQL:\n\n" + json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]


def _normalize_mermaid(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.strip()
    fenced = re.search(r"```mermaid\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    text = _strip_mermaid_comments(text)
    if not text.lower().startswith("flowchart"):
        return ""
    text = re.sub(r"(?im)^flowchart\s+lr\b", "flowchart TB", text, count=1)
    text = re.sub(r"(?im)^graph\s+lr\b", "flowchart TB", text, count=1)
    if text.lower().startswith("flowchart ") and not text.lower().startswith("flowchart tb"):
        text = re.sub(r"(?im)^flowchart\s+\w+\b", "flowchart TB", text, count=1)
    text = _normalize_mermaid_class_shorthand(text)
    return text


def _strip_mermaid_comments(text: str) -> str:
    cleaned_lines: List[str] = []
    for line in text.splitlines():
        if "%%" not in line:
            cleaned_lines.append(line)
            continue
        content, _comment = line.split("%%", 1)
        if content.strip():
            cleaned_lines.append(content.rstrip())
    return "\n".join(cleaned_lines).strip()


def _normalize_mermaid_class_shorthand(text: str) -> str:
    normalized_lines: List[str] = []
    pattern = re.compile(r":::\s*([A-Za-z_][\w.-]*(?:\.[A-Za-z_][\w.-]*)+)")

    for line in text.splitlines():
        def replacer(match: re.Match[str]) -> str:
            class_names = [item for item in match.group(1).split(".") if item]
            return "".join(f":::{class_name}" for class_name in class_names)

        normalized_lines.append(pattern.sub(replacer, line))

    return "\n".join(normalized_lines)


def _mermaid_id(value: str) -> str:
    return "n_" + "".join(char.lower() if char.isalnum() else "_" for char in value)


def _render_mermaid_png(input_path: Path, output_path: Path) -> bool:
    mermaid_cli = shutil.which("mmdc") or str(project_path("web", "node_modules", ".bin", "mmdc"))
    cli_path = Path(mermaid_cli)
    if not cli_path.exists():
        return False
    try:
        subprocess.run(
            [str(cli_path), "-i", str(input_path), "-o", str(output_path), "-b", "transparent"],
            check=True,
            capture_output=True,
            text=True,
        )
        return output_path.exists()
    except Exception:  # pragma: no cover - depends on local CLI/runtime
        return False
