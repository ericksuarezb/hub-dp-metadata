from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.run_repository import SupabaseRunRepository, load_supabase_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Genera un bundle de interoperabilidad para poblar Entropy a partir de una corrida persistida."
    )
    parser.add_argument("--run-id", required=True, help="Run ID persistido en Supabase.")
    parser.add_argument(
        "--output-dir",
        default="output/entropy_bundle",
        help="Directorio base donde se escribirán los artefactos de salida.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repository = SupabaseRunRepository(load_supabase_settings())
    payload = repository.get_run_export_payload(args.run_id)
    if not payload:
        raise SystemExit(f"No se encontró información exportable para run_id={args.run_id}")

    bundle = build_entropy_bundle(payload)
    written = write_entropy_bundle(args.run_id, bundle, Path(args.output_dir))
    print(json.dumps(written, indent=2, ensure_ascii=False))


def build_entropy_bundle(payload: Dict[str, Any]) -> Dict[str, Any]:
    app_run = payload.get("app_run") or {}
    analysis_row = payload.get("run_analysis") or {}
    datacontract_version = payload.get("datacontract_version") or {}
    contract_yaml = datacontract_version.get("yaml_text") or ""
    contract = _safe_load_yaml(contract_yaml)
    relations = payload.get("run_pipeline_relations") or []
    sources = payload.get("run_sources") or []
    transformations = payload.get("run_transformations") or []
    modules = payload.get("run_modules") or []
    module_sources = payload.get("run_module_sources") or []
    workspace_files = payload.get("run_workspace_files") or []
    audit_summary = payload.get("run_audit_summary") or {}
    audit_findings = payload.get("run_audit_findings") or []

    lineage_events = build_openlineage_events(app_run, modules, module_sources, relations)
    assets = build_asset_inventory(app_run, contract, sources, workspace_files)
    data_product = build_data_product_summary(app_run, contract, sources, transformations)

    return {
        "exported_at": _utc_now_iso(),
        "source": {
            "system": "docgen-sql",
            "repository": "supabase_mvp",
            "run_id": app_run.get("run_id"),
        },
        "data_product": data_product,
        "datacontract": {
            "file_name": datacontract_version.get("file_name"),
            "storage_path": datacontract_version.get("storage_path"),
            "yaml": contract_yaml,
            "parsed": contract,
        },
        "assets": assets,
        "lineage": {
            "relations": relations,
            "openlineage_events": lineage_events,
        },
        "transformations": {
            "count": len(transformations),
            "items": transformations,
        },
        "quality": {
            "summary": audit_summary,
            "findings": audit_findings,
        },
        "workspace_files": workspace_files,
        "analysis_snapshot": analysis_row,
        "entropy_population_plan": build_population_plan(contract, assets, lineage_events, workspace_files),
    }


def build_data_product_summary(
    app_run: Dict[str, Any],
    contract: Dict[str, Any],
    sources: List[Dict[str, Any]],
    transformations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    schema_items = contract.get("schema") if isinstance(contract, dict) else []
    primary_schema = schema_items[0] if isinstance(schema_items, list) and schema_items else {}
    properties = primary_schema.get("properties") if isinstance(primary_schema, dict) else []

    return {
        "name": contract.get("dataProduct") or app_run.get("product_name") or app_run.get("target_table"),
        "target_table": app_run.get("target_table"),
        "domain": contract.get("domain"),
        "status": contract.get("status") or app_run.get("status"),
        "description": contract.get("description"),
        "tags": contract.get("tags") or [],
        "schema_name": primary_schema.get("name"),
        "schema_physical_name": primary_schema.get("physicalName"),
        "field_count": len(properties) if isinstance(properties, list) else len(transformations),
        "source_count": len(sources),
        "sources": sorted({row.get("source_table") for row in sources if row.get("source_table")}),
    }


def build_asset_inventory(
    app_run: Dict[str, Any],
    contract: Dict[str, Any],
    sources: List[Dict[str, Any]],
    workspace_files: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    seen = set()

    target_table = app_run.get("target_table")
    if target_table:
        schema_items = contract.get("schema") if isinstance(contract, dict) else []
        primary_schema = schema_items[0] if isinstance(schema_items, list) and schema_items else {}
        properties = primary_schema.get("properties") if isinstance(primary_schema, dict) else []
        _append_unique_asset(
            assets,
            seen,
            {
                "asset_type": "dataset",
                "qualified_name": target_table,
                "display_name": primary_schema.get("name") or target_table,
                "description": primary_schema.get("description"),
                "tags": contract.get("tags") or [],
                "columns": properties if isinstance(properties, list) else [],
                "role": "target",
            },
        )

    for row in sources:
        source_table = row.get("source_table")
        if not source_table:
            continue
        _append_unique_asset(
            assets,
            seen,
            {
                "asset_type": "dataset",
                "qualified_name": source_table,
                "display_name": source_table.split(".")[-1],
                "description": row.get("contains_description"),
                "tags": [row.get("layer")] if row.get("layer") else [],
                "role": "source",
                "source_kind": row.get("source_kind"),
            },
        )

    for row in workspace_files:
        relative_path = row.get("relative_path")
        if not relative_path:
            continue
        _append_unique_asset(
            assets,
            seen,
            {
                "asset_type": "file",
                "qualified_name": relative_path,
                "display_name": Path(relative_path).name,
                "file_category": row.get("file_category"),
                "size_bytes": row.get("size_bytes"),
                "storage_path": row.get("storage_path"),
                "role": "evidence",
            },
        )

    return assets


def build_openlineage_events(
    app_run: Dict[str, Any],
    modules: List[Dict[str, Any]],
    module_sources: List[Dict[str, Any]],
    relations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    source_by_module: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in module_sources:
        module_key = row.get("module_key")
        if module_key:
            source_by_module[module_key].append(row)

    relation_targets: Dict[str, List[str]] = defaultdict(list)
    for row in relations:
        module_key = row.get("module_key")
        target_node = row.get("target_node")
        if module_key and target_node and target_node not in relation_targets[module_key]:
            relation_targets[module_key].append(target_node)

    events: List[Dict[str, Any]] = []
    for module in modules:
        module_key = module.get("module_key") or "module"
        inputs = []
        for item in source_by_module.get(module_key, []):
            source_table = item.get("source_table")
            if not source_table:
                continue
            namespace, name = split_dataset_name(source_table)
            inputs.append({"namespace": namespace, "name": name})

        target_table = module.get("target_table") or app_run.get("target_table")
        outputs = []
        if target_table:
            namespace, name = split_dataset_name(target_table)
            outputs.append({"namespace": namespace, "name": name})

        events.append(
            {
                "eventType": "COMPLETE",
                "eventTime": _utc_now_iso(),
                "producer": "https://github.com/algorithia/docgen-sql",
                "job": {
                    "namespace": "docgen-sql",
                    "name": module_key,
                },
                "run": {
                    "runId": f"{app_run.get('run_id')}::{module_key}",
                },
                "inputs": inputs,
                "outputs": outputs,
                "facets": {
                    "documentation": {
                        "_producer": "docgen-sql",
                        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/DocumentationJobFacet.json",
                        "description": module.get("module_name") or module_key,
                    },
                    "sql": {
                        "_producer": "docgen-sql",
                        "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SQLJobFacet.json",
                        "query": str((module.get("analysis_json") or {}).get("resolved_sql") or ""),
                    },
                    "docgenModule": {
                        "module_name": module.get("module_name"),
                        "sql_file_name": module.get("sql_file_name"),
                        "relation_targets": relation_targets.get(module_key, []),
                    },
                },
            }
        )
    return events


def build_population_plan(
    contract: Dict[str, Any],
    assets: List[Dict[str, Any]],
    lineage_events: List[Dict[str, Any]],
    workspace_files: List[Dict[str, Any]],
) -> Dict[str, Any]:
    immediate = []
    if contract:
        immediate.append("Registrar el data product y su schema a partir del ODCS ya generado.")
    if assets:
        immediate.append("Crear o reconciliar datasets físicos para tablas fuente y tabla destino.")
    if lineage_events:
        immediate.append("Publicar linaje técnico por módulo con OpenLineage.")
    if workspace_files:
        immediate.append("Adjuntar evidencia documental y artefactos auxiliares como archivos relacionados.")

    next_wave = [
        "Conectar catálogo de base origen para enriquecer owner, freshness y profiling real.",
        "Conectar storage o Git para asociar SQL, DDL, diccionarios y documentos como evidencia navegable.",
        "Añadir clasificaciones y glosario cuando existan fuentes curadas para PII, dominio y stewardship.",
    ]

    return {
        "can_populate_now": immediate,
        "needs_additional_connectors": next_wave,
    }


def write_entropy_bundle(run_id: str, bundle: Dict[str, Any], output_dir: Path) -> Dict[str, str]:
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    bundle_path = run_dir / "entropy_bundle.json"
    assets_path = run_dir / "assets.json"
    data_product_path = run_dir / "data_product.json"
    lineage_path = run_dir / "openlineage_events.json"
    contract_path = run_dir / "datacontract.odcs.yaml"

    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    assets_path.write_text(json.dumps(bundle.get("assets", []), indent=2, ensure_ascii=False), encoding="utf-8")
    data_product_path.write_text(
        json.dumps(bundle.get("data_product", {}), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lineage_path.write_text(
        json.dumps((bundle.get("lineage") or {}).get("openlineage_events", []), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    contract_path.write_text((bundle.get("datacontract") or {}).get("yaml") or "", encoding="utf-8")

    return {
        "bundle": str(bundle_path),
        "assets": str(assets_path),
        "data_product": str(data_product_path),
        "openlineage_events": str(lineage_path),
        "datacontract_yaml": str(contract_path),
    }


def split_dataset_name(qualified_name: str) -> tuple[str, str]:
    candidate = (qualified_name or "").strip()
    if "." not in candidate:
        return "default", candidate or "unknown"
    namespace, name = candidate.rsplit(".", 1)
    return namespace, name


def _append_unique_asset(assets: List[Dict[str, Any]], seen: set, item: Dict[str, Any]) -> None:
    key = (item.get("asset_type"), item.get("qualified_name"))
    if key in seen:
        return
    assets.append(item)
    seen.add(key)


def _safe_load_yaml(raw_text: str) -> Dict[str, Any]:
    if not raw_text.strip():
        return {}
    loaded = yaml.safe_load(raw_text)
    return loaded if isinstance(loaded, dict) else {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
