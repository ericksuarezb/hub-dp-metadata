from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List

VARIABLE_PATTERN = re.compile(r"\$\{[^}]+\}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza variables ${...} del SQL hacia proyecto.yml y el bloque @PARAMETROS."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sql", help="Ruta del archivo SQL a sincronizar.")
    target.add_argument("--dir", help="Directorio que contiene archivos .sql a sincronizar de una sola vez.")
    parser.add_argument("--config", default="config/proyecto.yml", help="Ruta del YAML del proyecto.")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="No pedir valores por terminal; conserva los existentes y deja vacio lo nuevo.",
    )
    return parser


def extract_variable_tokens(sql_text: str) -> List[str]:
    return sorted(set(VARIABLE_PATTERN.findall(sql_text)))


def replace_sql_parameters_block(sql_text: str, tokens: List[str]) -> str:
    block_lines = ["--| @PARAMETROS"]
    if tokens:
        for token in tokens:
            block_lines.append(f"--|     # {token}")
    else:
        block_lines.append("--|     #")
    replacement = "\n".join(block_lines)

    pattern = re.compile(
        r"--\|\s*@PARAMETROS\s*\n(?:--\|.*\n)*?(?=--\\|_|--\\)",
        re.MULTILINE,
    )
    match = pattern.search(sql_text)
    if not match:
        return sql_text
    return sql_text[: match.start()] + replacement + "\n" + sql_text[match.end() :]


def replace_sql_parameters_block_with_values(sql_text: str, tokens: List[str], values: Dict[str, str]) -> str:
    block_lines = ["--| @PARAMETROS"]
    if tokens:
        for token in tokens:
            value = values.get(token, "")
            block_lines.append(f"--|     # {token} = {value}")
    else:
        block_lines.append("--|     #")
    replacement = "\n".join(block_lines)

    pattern = re.compile(
        r"--\|\s*@PARAMETROS\s*\n(?:--\|.*\n)*?(?=--\\|_|--\\)",
        re.MULTILINE,
    )
    match = pattern.search(sql_text)
    if not match:
        return sql_text
    return sql_text[: match.start()] + replacement + "\n" + sql_text[match.end() :]


def sync_variables_with_project(
    sql_path: str | Path,
    config_path: str | Path = "config/proyecto.yml",
    prompt_for_values: bool = False,
    input_fn: Callable[[str], str] = input,
) -> Dict[str, object]:
    sql_file = Path(sql_path)
    config_file = resolve_config_path(config_path)

    sql_text = sql_file.read_text(encoding="utf-8")
    tokens = extract_variable_tokens(sql_text)

    config_text = config_file.read_text(encoding="utf-8")
    config_text, added_tokens, resolved_values = update_yaml_variables_block(
        config_text,
        tokens,
        prompt_for_values=prompt_for_values,
        input_fn=input_fn,
    )
    config_file.write_text(config_text, encoding="utf-8")

    updated_sql = replace_sql_parameters_block_with_values(sql_text, tokens, resolved_values)
    sql_file.write_text(updated_sql, encoding="utf-8")

    return {
        "sql_path": str(sql_file),
        "config_path": str(config_file),
        "variables_found": tokens,
        "variables_added": added_tokens,
        "variables_values": resolved_values,
    }


def sync_directory_variables(
    sql_dir: str | Path,
    config_path: str | Path = "config/proyecto.yml",
    prompt_for_values: bool = False,
    input_fn: Callable[[str], str] = input,
) -> Dict[str, object]:
    sql_directory = Path(sql_dir)
    config_file = resolve_config_path(config_path)
    sql_files = sorted(sql_directory.rglob("*.sql"))

    tokens_by_file: Dict[str, List[str]] = {}
    all_tokens = set()
    for sql_file in sql_files:
        sql_text = sql_file.read_text(encoding="utf-8")
        tokens = extract_variable_tokens(sql_text)
        tokens_by_file[str(sql_file)] = tokens
        all_tokens.update(tokens)

    merged_tokens = sorted(all_tokens)
    config_text = config_file.read_text(encoding="utf-8")
    config_text, added_tokens, resolved_values = update_yaml_variables_block(
        config_text,
        merged_tokens,
        prompt_for_values=prompt_for_values,
        input_fn=input_fn,
    )
    config_file.write_text(config_text, encoding="utf-8")

    updated_files = []
    for sql_file in sql_files:
        sql_text = sql_file.read_text(encoding="utf-8")
        updated_sql = replace_sql_parameters_block_with_values(
            sql_text,
            tokens_by_file[str(sql_file)],
            resolved_values,
        )
        sql_file.write_text(updated_sql, encoding="utf-8")
        updated_files.append(
            {
                "sql_path": str(sql_file),
                "variables_found": tokens_by_file[str(sql_file)],
            }
        )

    return {
        "sql_dir": str(sql_directory),
        "config_path": str(config_file),
        "variables_found": merged_tokens,
        "variables_added": added_tokens,
        "variables_values": resolved_values,
        "files_updated": updated_files,
    }


def resolve_config_path(config_path: str | Path = "config/proyecto.yml") -> Path:
    path = Path(config_path)
    if path.exists():
        return path
    if not path.is_absolute() and path.parent == Path("."):
        candidate = Path("config") / path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No existe el archivo de configuracion: {config_path}")


def update_yaml_variables_block(
    config_text: str,
    tokens: List[str],
    prompt_for_values: bool = False,
    input_fn: Callable[[str], str] = input,
) -> tuple[str, List[str], Dict[str, str]]:
    lines = config_text.splitlines()
    start = _find_variables_start(lines)

    if start is None:
        values = _collect_variable_values({}, tokens, prompt_for_values, input_fn)
        insertion = ["variables:"] + [f'  "{token}": "{_escape_yaml_scalar(values[token])}"' for token in tokens]
        lines.extend(insertion)
        return "\n".join(lines) + "\n", tokens, values

    end = _find_variables_end(lines, start)
    existing = _parse_existing_variables(lines[start + 1 : end])
    added_tokens = [token for token in tokens if token not in existing]
    values = _collect_variable_values(existing, tokens, prompt_for_values, input_fn)

    merged = sorted(set(existing) | set(tokens))
    new_block = ["variables:"]
    for token in merged:
        value = values.get(token, existing.get(token, ""))
        new_block.append(f'  "{token}": "{_escape_yaml_scalar(value)}"')

    updated_lines = lines[:start] + new_block + lines[end:]
    return (
        "\n".join(updated_lines) + ("\n" if config_text.endswith("\n") or updated_lines else ""),
        added_tokens,
        {token: values.get(token, "") for token in tokens},
    )


def _find_variables_start(lines: List[str]) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() == "variables:":
            return index
    return None


def _find_variables_end(lines: List[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        if not line.startswith("  "):
            return index
    return len(lines)


def _parse_existing_variables(lines: List[str]) -> Dict[str, str]:
    existing: Dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = _strip_quotes(key.strip())
        value = _strip_quotes(value.strip())
        if key.startswith("${") and key.endswith("}"):
            existing[key] = value
    return existing


def _collect_variable_values(
    existing: Dict[str, str],
    tokens: List[str],
    prompt_for_values: bool,
    input_fn: Callable[[str], str],
) -> Dict[str, str]:
    values = dict(existing)
    if not prompt_for_values:
        for token in tokens:
            values.setdefault(token, "")
        return values

    for token in tokens:
        current = values.get(token, "")
        shown = current if current else "<vacio>"
        entered = input_fn(f"Valor para {token} [{shown}]: ").strip()
        if entered:
            values[token] = entered
        else:
            values[token] = current
    return values


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _escape_yaml_scalar(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def main() -> None:
    args = build_parser().parse_args()
    prompt_for_values = sys.stdin.isatty() and not args.no_prompt
    if args.sql:
        result = sync_variables_with_project(args.sql, args.config, prompt_for_values=prompt_for_values)
    else:
        result = sync_directory_variables(args.dir, args.config, prompt_for_values=prompt_for_values)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
