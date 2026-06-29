from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.export_entropy_bundle import build_entropy_bundle
from src.import_entropy import EntropyImporter
from src.run_repository import SupabaseRunRepository, load_supabase_settings
from src.supabase_table_client import SupabaseTableClient


VALID_SCHEMA_TYPES = {"RAW", "CURADO", "CRYSTAL", "TEMPORAL", "NO CLASIFICADO", "OTRO"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza el catalogo de esquemas y el registro de sources limpias para la ingesta a Entropy."
    )
    parser.add_argument("--schema-csv", help="CSV con columnas esquema, descripcion, proposito.")
    parser.add_argument("--run-id", help="Run ID persistido en Supabase para generar el registro de sources limpias.")
    parser.add_argument("--preview", action="store_true", help="Solo imprime el payload, no escribe en Supabase.")
    parser.add_argument("--output", help="Ruta opcional para guardar el preview JSON.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.schema_csv and not args.run_id:
        raise SystemExit("Debes indicar --schema-csv, --run-id o ambos.")

    client = SupabaseTableClient()
    if not client.is_enabled():
        raise SystemExit("Supabase no esta habilitado para sincronizar tablas de Entropy.")

    preview: Dict[str, Any] = {}
    schema_rows: List[Dict[str, Any]] = []
    if args.schema_csv:
        schema_rows = load_schema_catalog_csv(Path(args.schema_csv))
        preview["entropy_schema_catalog"] = schema_rows
        if not args.preview:
            client.upsert_rows("entropy_schema_catalog", schema_rows, on_conflict="schema_name")

    schema_map = {
        row["schema_name"]: row
        for row in schema_rows
    } or client.fetch_schema_catalog_map()

    source_rows: List[Dict[str, Any]] = []
    if args.run_id:
        source_rows = build_entropy_source_registry_rows(args.run_id, schema_map)
        preview["entropy_source_registry"] = source_rows
        if not args.preview:
            client.upsert_rows("entropy_source_registry", source_rows, on_conflict="run_id,target_table,source_table")

    rendered = json.dumps(preview, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)


def load_schema_catalog_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"No existe el archivo CSV: {path}")

    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for item in reader:
            schema_name = str(item.get("esquema") or "").strip()
            if not schema_name:
                continue
            schema_type = normalize_schema_type(item.get("proposito"))
            rows.append(
                {
                    "schema_name": schema_name,
                    "description": _nullable_text(item.get("descripcion")),
                    "business_purpose": _nullable_text(item.get("proposito")),
                    "schema_type": schema_type,
                    "is_temporary": infer_is_temporary(schema_name, schema_type),
                    "include_in_entropy": True,
                    "source_file_name": path.name,
                    "notes": None,
                }
            )
    return rows


def build_entropy_source_registry_rows(
    run_id: str,
    schema_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise SystemExit("Supabase no esta habilitado para leer la corrida.")

    payload = repository.get_run_export_payload(run_id)
    if not payload:
        raise SystemExit(f"No se encontro informacion exportable para run_id={run_id}")

    bundle = build_entropy_bundle(payload)
    importer = EntropyImporter()
    import_payload = importer.build_import_payload(bundle)
    target_dataset = (import_payload.get("datasets") or {}).get("target") or []
    target_table = str((target_dataset[0] if target_dataset else {}).get("qualified_name") or "")
    target_schema, target_object_name = split_qualified_name(target_table)

    rows: List[Dict[str, Any]] = []
    for source in (import_payload.get("datasets") or {}).get("sources") or []:
        source_table = str(source.get("qualified_name") or "").strip()
        source_schema, source_object_name = split_qualified_name(source_table)
        schema_row = schema_map.get(source_schema, {})
        schema_type = str(schema_row.get("schema_type") or "")
        is_temporary = infer_is_temporary(source_schema or source_table, schema_type)
        rows.append(
            {
                "run_id": run_id,
                "target_table": target_table,
                "source_table": source_table,
                "target_schema": target_schema,
                "target_object_name": target_object_name,
                "source_schema": source_schema,
                "source_object_name": source_object_name,
                "source_schema_type": schema_type or None,
                "source_kind": source.get("source_kind"),
                "is_temporary": is_temporary,
                "include_in_entropy": not is_temporary,
                "review_status": "candidate",
                "decision_source": "auto",
                "rationale": "Auto-generado desde sources limpias del bundle de interoperabilidad.",
            }
        )
    return rows


def normalize_schema_type(value: Any) -> str:
    candidate = str(value or "").strip().upper()
    if not candidate:
        return "NO CLASIFICADO"
    return candidate if candidate in VALID_SCHEMA_TYPES else "OTRO"


def infer_is_temporary(schema_name: str, schema_type: str) -> bool:
    candidate = str(schema_name or "").strip().lower()
    normalized_type = normalize_schema_type(schema_type)
    return (
        normalized_type == "TEMPORAL"
        or candidate.endswith("_tmp")
        or candidate.startswith("tmp_")
        or candidate.startswith("stg_")
    )


def split_qualified_name(value: str) -> tuple[Optional[str], Optional[str]]:
    candidate = str(value or "").strip()
    if not candidate or "." not in candidate:
        return None, candidate or None
    schema_name, object_name = candidate.split(".", 1)
    return schema_name, object_name


def _nullable_text(value: Any) -> Optional[str]:
    candidate = str(value or "").strip()
    return candidate or None


if __name__ == "__main__":
    main()
