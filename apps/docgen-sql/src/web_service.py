from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.audit import audit_outputs
from src.config import load_project_config
from src.datacontract_exporter import (
    _load_csv_profile,
    _load_dictionary_profile,
    _load_impala_ddl_profile,
    _prepare_csv_for_cli,
    build_datacontract,
    resolve_best_tabular_profile,
)
from src.duckdb_ui import DEFAULT_DUCKDB_PATH
from src.document import render_document
from src.document_models import build_step_document_model
from src.document_renderer import render_step_docx
from src.models import FlowModuleConfig
from src.pipeline_diagram import build_pipeline_diagram, write_pipeline_diagram_artifacts
from src.runtime_paths import get_project_root, project_path
from src.run_repository import SupabaseRunRepository, load_supabase_settings
from src.sql_parser import parse_sql_file
from src.web_models import WebGenerationRequest, WebGenerationResponse, WebModuleInput, WebSqlFileInput

REPO_ROOT = get_project_root()
DEFAULT_STRUCTURAL_TEMPLATE = project_path("input", "templates", "DA_REQ_CD_IT_plantilla.docx")
DEFAULT_STEP_TEMPLATE = project_path("input", "templates", "DA_REQ_CD_IT_STEP_plantilla.docx")
WEB_RUNS_ROOT = project_path("output", "web_runs")


def preview_request(request: WebGenerationRequest) -> Dict[str, Any]:
    sql_name = _normalize_sql_name(request.sql_file_name)
    return {
        "mode": request.mode,
        "sql_file_name": sql_name,
        "product_name": request.product_name,
        "final_table_name": request.final_table_name,
        "variable_count": len(request.variables),
        "output_table_count": len(request.output_tables),
        "quick_reference_count": len([item for item in request.quick_reference if item.strip()]),
        "has_profile_db": bool(request.profile_db_path and request.profile_db_path.strip()),
        "has_ddl": bool(request.ddl_text and request.ddl_text.strip()),
        "has_dictionary": bool(request.dictionary_text and request.dictionary_text.strip()),
        "has_csv_sample": bool(request.csv_sample_text and request.csv_sample_text.strip()),
        "uses_custom_structural_template": request.structural_template is not None,
        "uses_custom_step_template": request.step_template is not None,
    }


def execute_web_generation(request: WebGenerationRequest) -> WebGenerationResponse:
    run_id = _build_run_id()
    run_dir = WEB_RUNS_ROOT / run_id
    workspace_dir = run_dir / "workspace"
    sql_dir = workspace_dir / "sql"
    metadata_dir = workspace_dir / "metadata"
    artifact_dir = run_dir / "artifacts"

    sql_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    sql_inputs = _resolve_sql_inputs(request)
    sql_entries = []
    for index, item in enumerate(sql_inputs, start=1):
        sql_name = _normalize_sql_name(item.sql_file_name)
        sql_path = sql_dir / sql_name
        sql_path.write_text(item.sql_text, encoding="utf-8")
        sql_entries.append(
            {
                "index": index,
                "name": sql_name,
                "path": sql_path,
                "is_step": item.is_step,
            }
        )

    principal_entry = _select_principal_sql_entry(sql_entries, request.sql_file_name)
    sql_path = principal_entry["path"]

    structural_template_path = _resolve_template(
        request.structural_template,
        workspace_dir / "templates" / "structural.docx",
        DEFAULT_STRUCTURAL_TEMPLATE,
    )
    step_template_path = _resolve_template(
        request.step_template,
        workspace_dir / "templates" / "step.docx",
        DEFAULT_STEP_TEMPLATE,
    )

    config_path = workspace_dir / "config.yml"
    config_payload = _build_config_payload(
        request=request,
        sql_entries=sql_entries,
        principal_sql_path=sql_path,
        structural_template_path=structural_template_path,
        step_template_path=step_template_path,
    )
    config_path.write_text(
        yaml.safe_dump(config_payload, allow_unicode=False, sort_keys=False),
        encoding="utf-8",
    )

    config = load_project_config(config_path)
    analysis = parse_sql_file(str(sql_path), config)
    module_results = [
        _build_module_result(
            entry=principal_entry,
            config=config,
            analysis=analysis,
            is_principal=True,
        )
    ]

    analysis_json_path = artifact_dir / f"{config.prefijo_archivo}{sql_path.stem}.json"
    analysis_json_path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")

    docx_path = artifact_dir / f"{config.prefijo_archivo}{sql_path.stem}.docx"
    document = render_document(analysis, config, docx_path)

    audit_path = artifact_dir / f"{docx_path.stem}.audit.xlsx"
    audit = audit_outputs(analysis, document, audit_path)

    generated_files: Dict[str, str] = {
        "analysis_json": str(analysis_json_path),
        "document_docx": str(docx_path),
        "audit_xlsx": str(audit_path),
        "audit_json": str(audit_path.with_suffix(".json")),
    }

    step_results = _generate_step_artifacts(
        sql_entries=sql_entries,
        config=config,
        step_template_path=step_template_path,
        artifact_dir=artifact_dir,
    )
    generated_files.update(step_results["generated_files"])
    module_results.extend(step_results["module_results"])

    audit_warnings = list(audit.warnings)
    odcs_yaml_text = None
    if request.generate_datacontract:
        contract_file_name = _build_datacontract_file_name(request.final_table_name or analysis.target_table)
        contract_path = _generate_datacontract_artifact(
            request=request,
            run_dir=run_dir,
            analysis=analysis,
            config=config,
            output_path=artifact_dir / contract_file_name,
        )
        generated_files["datacontract_yaml"] = str(contract_path)
        odcs_yaml_text = Path(contract_path).read_text(encoding="utf-8")

    pipeline_diagram = build_pipeline_diagram(module_results)
    generated_files.update(write_pipeline_diagram_artifacts(artifact_dir, pipeline_diagram))
    if pipeline_diagram.warning:
        audit_warnings.append(pipeline_diagram.warning)

    workspace_inventory = _collect_workspace_inventory(workspace_dir)

    response = WebGenerationResponse(
        run_id=run_id,
        mode=request.mode,
        sql_file=str(sql_path),
        config_file=str(config_path),
        output_dir=str(artifact_dir),
        generated_files=generated_files,
        audit_passed=audit.passed,
        audit_errors=audit.errors,
        audit_warnings=audit_warnings,
        stats={
            "sources": len(analysis.sources),
            "joins": len(analysis.joins),
            "filters": len(analysis.filters),
            "transformations": len(analysis.transformations),
            "rules": len(analysis.rules),
            "steps": len(analysis.steps),
            "target_table": analysis.target_table,
            "document_kind": document.document_kind,
            "sql_files_uploaded": len(sql_entries),
            "step_documents_generated": step_results["count"],
        },
        pipeline_graph=pipeline_diagram.model_dump(mode="json"),
    )

    persistence_status = _persist_run_if_enabled(
        request=request,
        response=response,
        analysis=analysis,
        audit=audit,
        odcs_yaml_text=odcs_yaml_text,
        config_snapshot=config_payload,
        module_results=module_results,
        pipeline_graph=response.pipeline_graph,
        workspace_inventory=workspace_inventory,
    )
    response.stats["supabase_persisted"] = persistence_status["persisted"]
    response.stats["supabase_storage_uploaded"] = len(persistence_status["storage_objects"])
    response.workspace_inventory = _sanitize_workspace_inventory(
        persistence_status.get("workspace_inventory", workspace_inventory)
    )
    if persistence_status["message"]:
        response.audit_warnings.append(persistence_status["message"])

    return response


def _build_config_payload(
    request: WebGenerationRequest,
    sql_entries: List[Dict[str, Any]],
    principal_sql_path: Path,
    structural_template_path: Path,
    step_template_path: Path,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "producto_funcional": request.product_name,
        "frecuencia": request.frequency,
        "tabla_final_pipeline": request.final_table_name,
        "prefijo_archivo": request.file_prefix,
        "variables": {
            item.name: item.value
            for item in request.variables
            if item.name.strip()
        },
        "template": str(structural_template_path),
        "seccion_1": {
            "ficha_producto": {
                "dominio": request.product_sheet.domain,
                "responsable": request.product_sheet.owner,
                "frecuencia": request.product_sheet.frequency or request.frequency,
                "dia_actualizacion": request.product_sheet.update_day,
                "horario_esperado": request.product_sheet.expected_schedule,
                "granularidad": request.product_sheet.granularity,
                "proposito": request.product_sheet.purpose,
                "salida_tipo": request.product_sheet.output_type,
                "consumidores_objetivo": request.product_sheet.target_consumers,
            },
            "tablas_salida": [
                {
                    "tabla": item.table,
                    "descripcion": item.description,
                }
                for item in request.output_tables
                if item.table.strip()
            ],
            "referencia_rapida": {
                "que_no_hace": [item for item in request.quick_reference if item.strip()],
            },
        },
        "flujo": {
            "tipo_documentacion": "modular",
            "documento_principal": {
                "nombre": request.document_title,
                "template": str(structural_template_path),
            },
            "modulos": _build_web_modules(sql_entries, principal_sql_path, step_template_path),
        },
    }
    payload["tabla_final_pipeline"] = request.final_table_name or str(principal_sql_path)

    return payload


def _build_web_modules(
    sql_entries: List[Dict[str, Any]],
    principal_sql_path: Path,
    step_template_path: Path,
) -> List[Dict[str, Any]]:
    modules: List[Dict[str, Any]] = []
    previous_module_id = None
    for entry in sql_entries:
        stem = Path(entry["name"]).stem
        module_id = f"paso_{entry['index']:02d}_{_slug_token(stem)}"
        modules.append(
            {
                "id": module_id,
                "nombre": build_module_name(entry["name"]),
                "intencion": f"Procesar el paso definido en {entry['name']}.",
                "sql": str(entry["path"]),
                "template": str(step_template_path),
                "depende_de": [previous_module_id] if previous_module_id else [],
                "salida_tablas": [],
                "tags": ["step"] if entry["is_step"] else ["principal"],
                "es_principal": entry["path"] == principal_sql_path,
            }
        )
        previous_module_id = module_id
    return modules


def _resolve_sql_inputs(request: WebGenerationRequest) -> List[WebSqlFileInput]:
    if request.sql_files:
        return request.sql_files
    return [
        WebSqlFileInput(
            sql_file_name=request.sql_file_name,
            sql_text=request.sql_text,
            is_step=request.mode == "step",
        )
    ]


def _select_principal_sql_entry(sql_entries: List[Dict[str, Any]], active_sql_file_name: str) -> Dict[str, Any]:
    active_name = _normalize_sql_name(active_sql_file_name)
    for entry in sql_entries:
        if entry["name"] == active_name and not entry["is_step"]:
            return entry
    for entry in sql_entries:
        if not entry["is_step"]:
            return entry
    for entry in sql_entries:
        if entry["name"] == active_name:
            return entry
    return sql_entries[-1]


def _generate_step_artifacts(
    sql_entries: List[Dict[str, Any]],
    config,
    step_template_path: Path,
    artifact_dir: Path,
) -> Dict[str, Any]:
    generated_files: Dict[str, str] = {}
    module_results: List[Dict[str, Any]] = []
    count = 0
    module_by_sql = {module.sql: module for module in config.flujo.modulos}

    for entry in sql_entries:
        if not entry["is_step"]:
            continue
        sql_path = str(entry["path"])
        analysis = parse_sql_file(sql_path, config)
        module_config = module_by_sql.get(sql_path)
        if module_config is None:
            continue
        module_results.append(
            _build_module_result(
                entry=entry,
                config=config,
                analysis=analysis,
                is_principal=False,
            )
        )
        step_model = build_step_document_model(module_config, analysis, config)
        prefixed_stem = f"{config.prefijo_archivo}{Path(sql_path).stem}"
        step_docx_path = artifact_dir / f"{prefixed_stem}_STEP.docx"
        step_document = render_step_docx(step_model, step_template_path, step_docx_path)
        step_audit_path = artifact_dir / f"{step_docx_path.stem}.audit.xlsx"
        step_audit = audit_outputs(analysis, step_document, step_audit_path)
        generated_files[f"step_docx__{Path(sql_path).stem}"] = str(step_docx_path)
        generated_files[f"step_audit_xlsx__{Path(sql_path).stem}"] = str(step_audit_path)
        generated_files[f"step_audit_json__{Path(sql_path).stem}"] = str(step_audit_path.with_suffix(".json"))
        count += 1

    return {"generated_files": generated_files, "count": count, "module_results": module_results}


def _build_module_result(
    entry: Dict[str, Any],
    config,
    analysis,
    is_principal: bool,
) -> Dict[str, Any]:
    sql_path = str(entry["path"])
    module_by_sql = {module.sql: module for module in config.flujo.modulos}
    module_config = module_by_sql.get(sql_path)
    return {
        "module_key": module_config.id if module_config is not None else f"sql_{entry['index']:02d}",
        "module_name": module_config.nombre if module_config is not None else build_module_name(entry["name"]),
        "sql_file_name": entry["name"],
        "is_step": entry["is_step"],
        "is_principal": is_principal,
        "analysis": analysis,
    }


def _build_datacontract_file_name(table_name: str) -> str:
    candidate = (table_name or "datacontract").strip()
    if not candidate:
        candidate = "datacontract"
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in candidate).strip("._")
    return f"{safe or 'datacontract'}.odcs.yaml"


def _generate_datacontract_artifact(
    request: WebGenerationRequest,
    run_dir: Path,
    analysis,
    config,
    output_path: Path,
) -> Path:
    metadata_dir = run_dir / "workspace" / "metadata"
    target_table_name = analysis.target_table.split(".")[-1]

    ddl_path = None
    if request.ddl_text and request.ddl_text.strip():
        ddl_path = metadata_dir / "ddl" / f"{target_table_name}.txt"
        ddl_path.parent.mkdir(parents=True, exist_ok=True)
        ddl_path.write_text(request.ddl_text, encoding="utf-8")

    dictionary_base_dir = None
    if request.dictionary_text and request.dictionary_text.strip():
        dictionary_path = metadata_dir / "dictionary" / f"{target_table_name}.txt"
        dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        dictionary_path.write_text(request.dictionary_text, encoding="utf-8")
        dictionary_base_dir = dictionary_path.parent

    prepared_csv_path = None

    profile_candidates = _build_profile_path_candidates(request, analysis)
    requested_tables = _build_profile_table_candidates(request, analysis)
    resolved_profile_engine = request.profile_engine or "duckdb"
    table_profile = resolve_best_tabular_profile(
        profile_paths=profile_candidates,
        requested_tables=requested_tables,
        profile_engine=resolved_profile_engine,
    )
    ddl_profile = _load_impala_ddl_profile(ddl_path)
    csv_profile = _load_csv_profile(prepared_csv_path)
    dictionary_profile = _load_dictionary_profile(
        analysis.target_table,
        dictionary_base_dir or metadata_dir / "dictionary",
    )
    contract = build_datacontract(
        analysis=analysis,
        config=config,
        table_profile=table_profile,
        ddl_profile=ddl_profile,
        csv_profile=csv_profile,
        dictionary_profile=dictionary_profile,
    )
    output_path.write_text(
        yaml.safe_dump(contract, allow_unicode=False, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return output_path


def _resolve_template(template_input, destination: Path, fallback: Path) -> Path:
    if template_input is None:
        return fallback

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(template_input.content_base64))
    return destination


def _normalize_sql_name(sql_file_name: str) -> str:
    candidate = (sql_file_name or "consulta_web.sql").strip()
    if not candidate.endswith(".sql"):
        candidate = f"{candidate}.sql"
    return Path(candidate).name


def build_module_name(sql_file_name: str) -> str:
    stem = Path(sql_file_name).stem
    return stem.replace("_", " ").replace("-", " ").strip().title()


def _slug_token(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "sql"


def _persist_run_if_enabled(
    request: WebGenerationRequest,
    response: WebGenerationResponse,
    analysis,
    audit,
    odcs_yaml_text: Optional[str],
    config_snapshot: Dict[str, Any],
    module_results: List[Dict[str, Any]],
    pipeline_graph: Dict[str, Any],
    workspace_inventory: List[Dict[str, Any]],
) -> Dict[str, Any]:
    settings = load_supabase_settings()
    repository = SupabaseRunRepository(settings)
    if not repository.is_enabled():
        return {
            "persisted": False,
            "message": None,
            "storage_objects": {},
            "workspace_inventory": workspace_inventory,
        }

    try:
        storage_objects = repository.persist_run(
            run_id=response.run_id,
            request_payload=request,
            response_payload=response,
            analysis=analysis,
            audit=audit,
            odcs_yaml_text=odcs_yaml_text,
            config_snapshot=config_snapshot,
            module_results=module_results,
            pipeline_graph=pipeline_graph,
            workspace_inventory=workspace_inventory,
        )
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        return {
            "persisted": False,
            "message": f"Supabase no se pudo actualizar: {exc}",
            "storage_objects": {},
            "workspace_inventory": workspace_inventory,
        }

    return {
        "persisted": True,
        "message": None,
        "storage_objects": storage_objects,
        "workspace_inventory": workspace_inventory,
    }


def _collect_workspace_inventory(workspace_dir: Path) -> List[Dict[str, Any]]:
    inventory: List[Dict[str, Any]] = []
    for path in sorted(workspace_dir.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(workspace_dir).as_posix()
        inventory.append(
            {
                "relative_path": relative_path,
                "file_category": _workspace_file_category(relative_path),
                "size_bytes": path.stat().st_size,
                "local_path": str(path),
            }
        )
    return inventory


def _workspace_file_category(relative_path: str) -> str:
    first_part = relative_path.split("/", 1)[0].lower()
    if first_part == "sql":
        return "sql"
    if first_part == "metadata":
        return "metadata"
    if first_part == "templates":
        return "template"
    if relative_path.lower() == "config.yml":
        return "config"
    return "other"


def _sanitize_workspace_inventory(workspace_inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            key: value
            for key, value in item.items()
            if key != "local_path"
        }
        for item in workspace_inventory
    ]


def _build_profile_path_candidates(request: WebGenerationRequest, analysis) -> List[str]:
    candidates: List[str] = []

    if request.profile_db_path and request.profile_db_path.strip():
        candidates.append(request.profile_db_path.strip())

    if DEFAULT_DUCKDB_PATH.exists():
        candidates.append(str(DEFAULT_DUCKDB_PATH))

    table_hint = request.final_table_name or analysis.target_table
    schema_name = table_hint.split(".")[0] if "." in table_hint else ""
    if schema_name:
        home_candidate = Path.home() / f"{schema_name}.db"
        if home_candidate.exists():
            candidates.append(str(home_candidate))

    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        normalized = str(Path(candidate).expanduser())
        if normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def _build_profile_table_candidates(request: WebGenerationRequest, analysis) -> List[str]:
    candidates = [
        request.profile_table or "",
        request.final_table_name or "",
        analysis.target_table,
        (request.final_table_name or analysis.target_table).split(".")[-1],
    ]
    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if normalized and normalized.lower() not in seen:
            deduped.append(normalized)
            seen.add(normalized.lower())
    return deduped


def _get_single_module_config(config) -> FlowModuleConfig:
    if not config.flujo.modulos:
        raise ValueError("Para modo step debes capturar la metadata del modulo.")
    return config.flujo.modulos[0]


def _build_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"
