from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

from src.models import ProjectConfig, VariableResolution

VARIABLE_PATTERN = re.compile(r"\$\{[^}]+\}")


def load_project_config(config_path: str | Path = "config/proyecto.yml") -> ProjectConfig:
    path = resolve_config_path(config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    template = data.get("template")
    if template:
        template_path = Path(template)
        if not template_path.is_absolute():
            candidate = Path.cwd() / template_path
            if candidate.exists():
                data["template"] = str(template_path)
            else:
                fallback = Path.cwd() / "input/templates/DA_REQ_CD_IT_plantilla.docx"
                if fallback.exists():
                    data["template"] = "input/templates/DA_REQ_CD_IT_plantilla.docx"
    return ProjectConfig(**data)


def resolve_config_path(config_path: str | Path = "config/proyecto.yml") -> Path:
    path = Path(config_path)
    if path.exists():
        return path
    if not path.is_absolute() and path.parent == Path("."):
        candidate = Path("config") / path
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No existe el archivo de configuracion: {config_path}")


def resolve_variables(sql_text: str, variables: Dict[str, str]) -> VariableResolution:
    auto_resolved: Dict[str, str] = {}

    def replacer(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in variables:
            return str(variables[token])

        env_key = token[2:-1]
        env_value = os.getenv(env_key)
        if env_value:
            auto_resolved[token] = env_value
            return env_value

        lowered = env_key.lower()
        if lowered.startswith("fec_") or lowered.startswith("fecha_") or lowered.endswith("_date"):
            inferred = date.today().isoformat()
            auto_resolved[token] = inferred
            return inferred

        return token

    resolved_sql = VARIABLE_PATTERN.sub(replacer, sql_text)
    unresolved = sorted(set(VARIABLE_PATTERN.findall(resolved_sql)))
    masked_sql, masked_variables = mask_unresolved_variables(resolved_sql)
    return VariableResolution(
        resolved_sql=resolved_sql,
        unresolved_variables=unresolved,
        auto_resolved_variables=auto_resolved,
        masked_sql=masked_sql,
        masked_variables=masked_variables,
    )


def mask_unresolved_variables(sql_text: str) -> Tuple[str, Dict[str, str]]:
    masked_variables: Dict[str, str] = {}

    def replacer(match: re.Match[str]) -> str:
        token = match.group(0)
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", token[2:-1]).strip("_").lower()
        placeholder = f"var_{normalized or 'token'}"
        masked_variables[token] = placeholder
        return placeholder

    return VARIABLE_PATTERN.sub(replacer, sql_text), masked_variables


def extract_variable_tokens(sql_text: str) -> List[str]:
    return sorted(set(VARIABLE_PATTERN.findall(sql_text)))


def sync_variables_with_project(
    sql_path: str | Path,
    config_path: str | Path = "config/proyecto.yml",
) -> Dict[str, object]:
    sql_file = Path(sql_path)
    config_file = Path(config_path)

    sql_text = sql_file.read_text(encoding="utf-8")
    tokens = extract_variable_tokens(sql_text)

    config_data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
    variables = dict(config_data.get("variables") or {})

    added_tokens: List[str] = []
    for token in tokens:
        if token not in variables:
            variables[token] = ""
            added_tokens.append(token)

    config_data["variables"] = dict(sorted(variables.items()))
    config_file.write_text(
        yaml.safe_dump(config_data, allow_unicode=False, sort_keys=False),
        encoding="utf-8",
    )

    updated_sql = replace_sql_parameters_block(sql_text, tokens)
    sql_file.write_text(updated_sql, encoding="utf-8")

    return {
        "sql_path": str(sql_file),
        "config_path": str(config_file),
        "variables_found": tokens,
        "variables_added": added_tokens,
    }


def replace_sql_parameters_block(sql_text: str, tokens: List[str]) -> str:
    block_lines = ["--| @PARAMETROS"]
    if tokens:
        for token in tokens:
            block_lines.append(f"--|     # {token}")
    else:
        block_lines.append("--|     #")
    replacement = "\n".join(block_lines)

    pattern = re.compile(
        r"--\|\s*@PARAMETROS\s*\n(?:--\|.*\n)*?(?=--\\|_|--\\|@|--\\\|_|--\\)",
        re.MULTILINE,
    )
    match = pattern.search(sql_text)
    if match:
        return sql_text[: match.start()] + replacement + "\n" + sql_text[match.end() :]

    fallback_pattern = re.compile(
        r"--\|\s*@PARAMETROS\s*\n(?:--\|.*\n)*?(?=--\\)",
        re.MULTILINE,
    )
    fallback_match = fallback_pattern.search(sql_text)
    if fallback_match:
        return sql_text[: fallback_match.start()] + replacement + "\n" + sql_text[fallback_match.end() :]

    return sql_text
