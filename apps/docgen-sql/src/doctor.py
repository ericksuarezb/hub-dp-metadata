from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, List

from src.credentials import find_credentials_file
from src.runtime_paths import get_project_root


RUNTIME_DEPENDENCIES = [
    "yaml",
    "pydantic",
    "sqlglot",
    "sqlparse",
    "docx",
    "openpyxl",
]

WEB_DEPENDENCIES = [
    "fastapi",
    "uvicorn",
    "duckdb",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Valida que docgen-sql pueda integrarse sin romper rutas ni dependencias.")
    parser.add_argument("--json", action="store_true", help="Imprime el reporte en JSON.")
    parser.add_argument("--strict", action="store_true", help="Falla si faltan archivos opcionales recomendados.")
    return parser


def inspect_project(strict: bool = False) -> Dict[str, object]:
    root = get_project_root()
    checks = [
        _check_path(root, "src", required=True, kind="dir"),
        _check_path(root, "config", required=True, kind="dir"),
        _check_path(root, "input", required=True, kind="dir"),
        _check_path(root, "input/templates", required=True, kind="dir"),
        _check_path(root, "output", required=False, kind="dir", create=True),
        _check_path(root, "data/duckdb", required=False, kind="dir", create=True),
        _check_path(root, "data/samples", required=False, kind="dir", create=True),
        _check_path(root, "config/proyecto.yml", required=False, kind="file"),
        _check_path(root, "config/llm.yml", required=False, kind="file"),
        _check_path(root, "config/supabase.yml", required=False, kind="file"),
        _check_path(root, "web/package.json", required=False, kind="file"),
        _check_path(root, "docker-compose.yml", required=False, kind="file"),
    ]

    dependencies = [
        _check_dependency(name, required=True) for name in RUNTIME_DEPENDENCIES
    ] + [
        _check_dependency(name, required=False) for name in WEB_DEPENDENCIES
    ]

    errors = [item["message"] for item in checks + dependencies if item["status"] == "error"]
    warnings = [item["message"] for item in checks + dependencies if item["status"] == "warning"]
    if strict:
        warnings.extend(
            item["message"]
            for item in checks
            if item["status"] == "ok" and item["required"] is False and item["exists"] is False
        )

    return {
        "project_root": str(root),
        "credentials_file": str(find_credentials_file()) if find_credentials_file() else "",
        "python": sys.version.split()[0],
        "ok": not errors and (not strict or not warnings),
        "checks": checks,
        "dependencies": dependencies,
        "errors": errors,
        "warnings": warnings,
        "recommendation": (
            "Integra el proyecto copiando la carpeta completa y ejecuta 'pip install -e .[web]' desde la raiz."
        ),
    }


def _check_path(
    root: Path,
    relative_path: str,
    *,
    required: bool,
    kind: str,
    create: bool = False,
) -> Dict[str, object]:
    path = root / relative_path
    if create:
        path.mkdir(parents=True, exist_ok=True)

    exists = path.exists()
    status = "ok"
    if not exists and required:
        status = "error"
    elif not exists:
        status = "warning"
    elif kind == "dir" and not path.is_dir():
        status = "error"
    elif kind == "file" and not path.is_file():
        status = "error"

    return {
        "type": "path",
        "path": str(path),
        "required": required,
        "exists": exists,
        "status": status,
        "message": _path_message(relative_path, status, required),
    }


def _check_dependency(module_name: str, *, required: bool) -> Dict[str, object]:
    installed = importlib.util.find_spec(module_name) is not None
    status = "ok"
    if not installed and required:
        status = "error"
    elif not installed:
        status = "warning"

    return {
        "type": "dependency",
        "module": module_name,
        "required": required,
        "installed": installed,
        "status": status,
        "message": _dependency_message(module_name, status, required),
    }


def _path_message(relative_path: str, status: str, required: bool) -> str:
    if status == "ok":
        return f"Ruta disponible: {relative_path}"
    if required:
        return f"Falta una ruta obligatoria para la integracion: {relative_path}"
    return f"Ruta recomendada no encontrada: {relative_path}"


def _dependency_message(module_name: str, status: str, required: bool) -> str:
    if status == "ok":
        return f"Dependencia disponible: {module_name}"
    if required:
        return f"Falta una dependencia obligatoria: {module_name}"
    return f"Dependencia opcional no instalada: {module_name}"


def main() -> None:
    args = build_parser().parse_args()
    report = inspect_project(strict=args.strict)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"project_root: {report['project_root']}")
        print(f"credentials_file: {report['credentials_file'] or 'none'}")
        print(f"python: {report['python']}")
        print(f"ok: {report['ok']}")
        print("errors:")
        for message in report["errors"] or ["none"]:
            print(f"  - {message}")
        print("warnings:")
        for message in report["warnings"] or ["none"]:
            print(f"  - {message}")
        print(f"recommendation: {report['recommendation']}")

    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
