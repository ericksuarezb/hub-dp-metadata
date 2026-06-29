from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List

import sqlparse
import yaml


HEADER_PATTERN = re.compile(r"^\s*--\|\s*@(?P<key>[A-Z_]+):?\s*(?P<value>.*)\s*$", re.MULTILINE)
INSERT_PATTERN = re.compile(r"insert\s+overwrite\s+table\s+([^\s(;/]+)", re.IGNORECASE)
CTAS_PATTERN = re.compile(r"create\s+table\s+([^\s(;/]+).*?\bas\s+select\b", re.IGNORECASE | re.DOTALL)
TABLE_PATTERN = re.compile(r"(?:from|join)\s+([a-zA-Z0-9_${}.]+)", re.IGNORECASE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza flujo.modulos en proyecto.yml a partir de encabezados SQL."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sql", help="Ruta del archivo SQL a sincronizar como modulo.")
    target.add_argument("--dir", help="Directorio con SQL para sincronizar todos los modulos.")
    parser.add_argument("--config", default="config/proyecto.yml", help="Ruta del YAML del proyecto.")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="No pedir valores faltantes; conserva existentes o deja propuestas automaticas.",
    )
    return parser


def sync_module_from_sql(
    sql_path: str | Path,
    config_path: str | Path = "config/proyecto.yml",
    prompt_for_values: bool = False,
    input_fn: Callable[[str], str] = input,
) -> Dict[str, object]:
    sql_file = Path(sql_path)
    config_file = resolve_config_path(config_path)
    config_data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}

    module = build_module_definition(sql_file, config_data, prompt_for_values, input_fn)
    flow = config_data.setdefault("flujo", {})
    flow.setdefault("tipo_documentacion", "modular")
    flow.setdefault(
        "documento_principal",
        {
            "nombre": "Documentacion Funcional Estructural",
            "template": config_data.get("template", "input/templates/DA_REQ_CD_IT_plantilla.docx"),
        },
    )
    modules = flow.setdefault("modulos", [])

    replaced = False
    for index, existing in enumerate(modules):
        if existing.get("sql") == str(sql_file) or existing.get("id") == module["id"]:
            merged = dict(existing)
            merged.update(module)
            modules[index] = merged
            replaced = True
            break
    if not replaced:
        modules.append(module)

    config_file.write_text(yaml.safe_dump(config_data, allow_unicode=False, sort_keys=False), encoding="utf-8")
    return {
        "config_path": str(config_file),
        "sql_path": str(sql_file),
        "module_id": module["id"],
        "nombre": module["nombre"],
        "intencion": module["intencion"],
        "updated": True,
    }


def sync_modules_from_dir(
    sql_dir: str | Path,
    config_path: str | Path = "config/proyecto.yml",
    prompt_for_values: bool = False,
    input_fn: Callable[[str], str] = input,
) -> Dict[str, object]:
    sql_directory = Path(sql_dir)
    results = []
    for sql_file in sorted(sql_directory.rglob("*.sql")):
        results.append(
            sync_module_from_sql(
                sql_file,
                config_path=config_path,
                prompt_for_values=prompt_for_values,
                input_fn=input_fn,
            )
        )
    return {
        "config_path": str(resolve_config_path(config_path)),
        "sql_dir": str(sql_directory),
        "modules_updated": results,
    }


def build_module_definition(
    sql_file: Path,
    config_data: Dict[str, object],
    prompt_for_values: bool,
    input_fn: Callable[[str], str],
) -> Dict[str, object]:
    sql_text = sql_file.read_text(encoding="utf-8")
    header = extract_header_metadata(sql_text)
    flow = config_data.get("flujo") or {}
    existing_modules = {module.get("sql"): module for module in flow.get("modulos", []) if isinstance(module, dict)}
    existing = existing_modules.get(str(sql_file), {})

    nombre_header = normalize_header_value(header.get("ARCHIVO", ""))
    descripcion_header = normalize_header_value(header.get("DESCRIPCION", ""))

    nombre = resolve_field_value(
        label=f"nombre ({sql_file.name})",
        current=existing.get("nombre", ""),
        candidate=nombre_header or humanize_sql_name(sql_file),
        prompt_for_values=prompt_for_values,
        input_fn=input_fn,
        required=True,
    )
    intencion = resolve_field_value(
        label=f"intencion ({sql_file.name})",
        current=existing.get("intencion", ""),
        candidate=descripcion_header,
        prompt_for_values=prompt_for_values,
        input_fn=input_fn,
        required=True,
    )
    extracted_outputs = extract_output_tables(sql_text)
    existing_outputs = existing.get("salida_tablas", [])

    return {
        "id": existing.get("id", build_module_id(sql_file)),
        "nombre": nombre,
        "intencion": intencion,
        "sql": str(sql_file),
        "template": existing.get("template", "input/templates/DA_REQ_CD_IT_STEP_plantilla.docx"),
        "depende_de": existing.get("depende_de", []),
        "salida_tablas": merge_unique(existing_outputs, extracted_outputs),
        "tags": existing.get("tags") or infer_tags(sql_file),
        "es_principal": existing.get("es_principal", infer_is_principal(existing, sql_text, config_data)),
    }


def extract_header_metadata(sql_text: str) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    lines = sql_text.splitlines()
    for index, line in enumerate(lines):
        match = HEADER_PATTERN.match(line)
        if not match:
            continue
        key = match.group("key")
        value = normalize_header_value(match.group("value"))
        if not value and index + 1 < len(lines):
            next_line = lines[index + 1]
            next_match = re.match(r"^\s*--\|\s*#\s*(.*)\s*$", next_line)
            if next_match:
                value = normalize_header_value(next_match.group(1))
        metadata[key] = value
    return metadata


def normalize_header_value(value: str) -> str:
    cleaned = value.strip()
    if cleaned in {"", "#", ":", "-"}:
        return ""
    return cleaned


def resolve_field_value(
    label: str,
    current: str,
    candidate: str,
    prompt_for_values: bool,
    input_fn: Callable[[str], str],
    required: bool,
) -> str:
    if current:
        return current
    if candidate:
        return candidate
    if prompt_for_values:
        while True:
            entered = input_fn(f"Captura {label}: ").strip()
            if entered or not required:
                return entered
    return candidate or current or ""


def build_module_id(sql_file: Path) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", sql_file.stem).strip("_").lower()
    if stem and stem[0].isdigit():
        stem = f"paso_{stem}"
    return stem or "modulo_sql"


def humanize_sql_name(sql_file: Path) -> str:
    stem = sql_file.stem
    stem = re.sub(r"^\d+_", "", stem)
    stem = stem.replace("_", " ").strip()
    return stem.title() if stem else sql_file.name


def extract_output_tables(sql_text: str) -> List[str]:
    tables: List[str] = []
    for statement in [stmt.strip() for stmt in sqlparse.split(sql_text) if stmt.strip()]:
        insert_match = INSERT_PATTERN.search(statement)
        if insert_match:
            tables.append(insert_match.group(1))
            continue
        ctas_match = CTAS_PATTERN.search(statement)
        if ctas_match:
            tables.append(ctas_match.group(1))
    seen: List[str] = []
    for table in tables:
        if table not in seen:
            seen.append(table)
    return seen


def infer_tags(sql_file: Path) -> List[str]:
    parts = [part for part in re.split(r"[_\W]+", sql_file.stem.lower()) if part and not part.isdigit()]
    seen = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return seen[:4]


def infer_is_principal(existing: Dict[str, object], sql_text: str, config_data: Dict[str, object]) -> bool:
    if "es_principal" in existing:
        return bool(existing["es_principal"])

    final_target = str(config_data.get("tabla_final_pipeline") or "").strip()
    if not final_target:
        return False

    outputs = extract_output_tables(sql_text)
    return final_target in outputs


def merge_unique(*groups: List[str]) -> List[str]:
    seen: List[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.append(item)
    return seen


def resolve_config_path(config_path: str | Path = "config/proyecto.yml") -> Path:
    path = Path(config_path)
    if path.exists():
        return path
    if not path.is_absolute() and path.parent == Path("."):
        candidate = Path("config") / path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No existe el archivo de configuracion: {config_path}")


def main() -> None:
    args = build_parser().parse_args()
    prompt_for_values = sys.stdin.isatty() and not args.no_prompt
    if args.sql:
        result = sync_module_from_sql(
            args.sql,
            config_path=args.config,
            prompt_for_values=prompt_for_values,
        )
    else:
        result = sync_modules_from_dir(
            args.dir,
            config_path=args.config,
            prompt_for_values=prompt_for_values,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
