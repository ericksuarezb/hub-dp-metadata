from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.audit import audit_outputs
from src.config import load_project_config
from src.document_models import build_step_document_model
from src.document_renderer import render_step_docx
from src.document import render_document
from src.models import FlowModuleConfig
from src.sql_parser import parse_sql_file
from src.sync_variables import sync_variables_with_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genera especificaciones funcionales a partir de SQL.")
    parser.add_argument("--sql", help="Ruta del archivo SQL a procesar.")
    parser.add_argument("--module", help="Id del modulo configurado en flujo.modulos.")
    parser.add_argument(
        "--all-steps",
        action="store_true",
        help="Genera documentos STEP para todos los modulos definidos en flujo.modulos.",
    )
    parser.add_argument("--config", default="config/proyecto.yml", help="Ruta del YAML del proyecto.")
    parser.add_argument(
        "--mode",
        choices=["structural", "step"],
        default="structural",
        help="Tipo de documento a generar.",
    )
    parser.add_argument(
        "--sync-variables",
        action="store_true",
        help="Sincroniza variables ${...} del SQL hacia proyecto.yml y el bloque @PARAMETROS del SQL antes de procesar.",
    )
    return parser


def run(
    sql_path: str | None,
    config_path: str,
    sync_variables: bool = False,
    mode: str = "structural",
    module_id: str | None = None,
    all_steps: bool = False,
) -> dict:
    config = load_project_config(config_path)

    if all_steps:
        if mode != "step":
            raise ValueError("La opcion --all-steps solo se puede usar con --mode step.")
        return _run_all_steps(config, config_path, sync_variables)

    return _run_single(
        sql_path=sql_path,
        config_path=config_path,
        sync_variables=sync_variables,
        mode=mode,
        module_id=module_id,
    )


def _run_single(
    sql_path: str | None,
    config_path: str,
    sync_variables: bool = False,
    mode: str = "structural",
    module_id: str | None = None,
) -> dict:
    sync_result = None
    config = load_project_config(config_path)

    module_config = None
    if module_id:
        module_config = _get_module_config(config, module_id)
        sql_path = module_config.sql

    if not sql_path:
        raise ValueError("Debes indicar --sql o --module.")

    if sync_variables:
        sync_result = sync_variables_with_project(sql_path, config_path)

    config = load_project_config(config_path)
    if mode == "step" and module_config is None:
        module_config = _get_module_by_sql(config, sql_path)

    analysis = parse_sql_file(sql_path, config)

    stem = Path(sql_path).stem
    prefixed_stem = f"{config.prefijo_archivo}{stem}"
    json_path = Path("output/json") / f"{prefixed_stem}.json"
    docx_name = f"{prefixed_stem}{'_STEP' if mode == 'step' else ''}.docx"
    docx_path = Path("output/docx") / docx_name
    audit_path = Path("output/audit") / f"{prefixed_stem}{'_STEP' if mode == 'step' else ''}.xlsx"

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")

    if mode == "step":
        if module_config is None:
            raise ValueError(f"No se encontro un modulo configurado para el SQL {sql_path}")
        step_model = build_step_document_model(module_config, analysis, config)
        template_path = module_config.template or "input/templates/DA_REQ_CD_IT_STEP_plantilla.docx"
        document = render_step_docx(step_model, template_path, docx_path)
    else:
        document = render_document(analysis, config, docx_path)
    audit = audit_outputs(analysis, document, audit_path)

    return {
        "sql": sql_path,
        "mode": mode,
        "module": module_config.id if module_config else None,
        "json": str(json_path),
        "docx": str(docx_path),
        "audit": str(audit_path),
        "audit_passed": audit.passed,
        "audit_errors": audit.errors,
        "audit_warnings": audit.warnings,
        "variable_sync": sync_result,
    }


def _run_all_steps(config, config_path: str, sync_variables: bool) -> dict:
    if not config.flujo.modulos:
        raise ValueError("No hay modulos definidos en flujo.modulos.")

    generated = []
    failed = []
    for module in config.flujo.modulos:
        try:
            generated.append(
                _run_single(
                    sql_path=None,
                    config_path=config_path,
                    sync_variables=sync_variables,
                    mode="step",
                    module_id=module.id,
                )
            )
        except Exception as exc:
            failed.append(
                {
                    "module": module.id,
                    "sql": module.sql,
                    "error": str(exc),
                }
            )

    return {
        "mode": "step",
        "scope": "all_steps",
        "modules_requested": len(config.flujo.modulos),
        "modules_generated": len(generated),
        "modules_failed": len(failed),
        "audit_passed": len(failed) == 0 and all(item["audit_passed"] for item in generated),
        "results": generated,
        "errors": failed,
    }


def _get_module_config(config, module_id: str) -> FlowModuleConfig:
    for module in config.flujo.modulos:
        if module.id == module_id:
            return module
    raise ValueError(f"No se encontro el modulo {module_id} en flujo.modulos")


def _get_module_by_sql(config, sql_path: str) -> FlowModuleConfig | None:
    normalized = str(Path(sql_path))
    for module in config.flujo.modulos:
        if module.sql == normalized:
            return module
    return None


def main() -> None:
    args = build_parser().parse_args()
    result = run(
        args.sql,
        args.config,
        sync_variables=args.sync_variables,
        mode=args.mode,
        module_id=args.module,
        all_steps=args.all_steps,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
