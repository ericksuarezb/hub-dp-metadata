from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
import yaml

from src.config import mask_unresolved_variables
from src.credentials import first_non_empty, get_credential
from src.runtime_paths import project_path

LLM_CONFIG_PATH = project_path("config", "llm.yml")
TARGET_PATTERN = re.compile(
    r"(?is)\b(?:insert\s+overwrite\s+table|insert\s+into|create\s+table(?:\s+if\s+not\s+exists)?)\s+([a-zA-Z0-9_$.]+)"
)
SOURCE_PATTERN = re.compile(r"(?is)\b(?:from|join)\s+([a-zA-Z0-9_$.]+)")


class SqlBusinessContextSuggestion(BaseModel):
    purpose: str
    non_goals: List[str] = Field(default_factory=list)
    provider: str = "heuristic"
    warning: Optional[str] = None


class LlmSettings(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4.1-mini"
    api_base: str = "https://api.openai.com/v1"
    api_style: str = "auto"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""
    max_input_chars: int = 12000


def infer_sql_business_context(sql_text: str, sql_file_name: Optional[str] = None) -> SqlBusinessContextSuggestion:
    heuristic = _infer_with_heuristic(sql_text, sql_file_name)
    settings = load_llm_settings()

    if not settings.enabled:
        heuristic.warning = "La inferencia LLM esta desactivada en config/llm.yml; se uso inferencia local."
        return heuristic

    api_key = _resolve_api_key(settings)
    provider = settings.provider.lower().strip()
    if provider not in {"openai", "gemini"}:
        heuristic.warning = f"El provider '{settings.provider}' no esta soportado aun; se uso inferencia local."
        return heuristic

    if not api_key:
        heuristic.warning = (
            f"No hay API key configurada en config/llm.yml ni en la variable {settings.api_key_env}; "
            "se uso inferencia local."
        )
        return heuristic

    try:
        from openai import OpenAI
    except ImportError:
        heuristic.warning = "La libreria openai no esta instalada; se uso inferencia local."
        return heuristic

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=settings.api_base,
        )
        masked_sql, _ = mask_unresolved_variables(sql_text)
        prompt_messages = _build_prompt_messages(masked_sql[:settings.max_input_chars], sql_file_name)
        api_style = _resolve_api_style(settings)
        if api_style == "chat_completions":
            response = client.chat.completions.create(
                model=settings.model,
                messages=prompt_messages,
                response_format={"type": "json_object"},
            )
            payload = json.loads(_extract_chat_completion_text(response))
        else:
            response = client.responses.create(
                model=settings.model,
                input=prompt_messages,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "sql_business_context",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "purpose": {"type": "string"},
                                "non_goals": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["purpose", "non_goals"],
                        },
                    }
                },
            )
            payload = json.loads(_extract_response_text(response))
        return _normalize_suggestion(
            SqlBusinessContextSuggestion(
                purpose=payload.get("purpose") or heuristic.purpose,
                non_goals=payload.get("non_goals") or heuristic.non_goals,
                provider=provider,
            )
        )
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        heuristic.warning = f"No fue posible usar el LLM; se uso inferencia local. Detalle: {exc}"
        return heuristic


def load_llm_settings(config_path: Path = LLM_CONFIG_PATH) -> LlmSettings:
    if not config_path.exists():
        return LlmSettings()

    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    llm_data = raw_data.get("llm") if isinstance(raw_data, dict) and "llm" in raw_data else raw_data
    return LlmSettings(**(llm_data or {}))


def _resolve_api_style(settings: LlmSettings) -> str:
    configured = (settings.api_style or "auto").strip().lower()
    if configured in {"responses", "chat_completions"}:
        return configured

    provider = settings.provider.lower().strip()
    api_base = settings.api_base.lower()
    model = settings.model.lower().strip()
    if provider == "gemini" or "generativelanguage.googleapis.com" in api_base or model.startswith("gemini-"):
        return "chat_completions"
    return "responses"


def _resolve_api_key(settings: LlmSettings) -> str:
    configured = (settings.api_key or "").strip()
    if configured:
        return configured

    env_name = (settings.api_key_env or "").strip()
    provider = settings.provider.lower().strip()
    resolved_key = first_non_empty(
        os.getenv(env_name, "") if env_name else "",
        get_credential("llm", "api_key"),
        get_credential("llm", f"{provider}_api_key") if provider else "",
        get_credential("llm", env_name),
        get_credential("llm", env_name.lower()) if env_name else "",
        get_credential("env", env_name),
    )
    if resolved_key:
        return resolved_key

    if settings.api_base.startswith("http://") or "localhost" in settings.api_base or "127.0.0.1" in settings.api_base:
        return "local-dev-key"

    return ""


def _infer_with_heuristic(sql_text: str, sql_file_name: str | None) -> SqlBusinessContextSuggestion:
    target_table = _extract_target_table(sql_text)
    source_tables = _extract_source_tables(sql_text, target_table)
    source_count = len(source_tables)
    target_label = target_table or _friendly_name(sql_file_name or "salida_sql")

    if source_count > 1:
        purpose = (
            f"Consolida {source_count} fuentes para poblar {target_label} con cruces, filtros y transformaciones "
            "visibles en el SQL."
        )
    elif source_count == 1:
        purpose = (
            f"Transforma la fuente {source_tables[0]} para poblar {target_label} con reglas y filtros visibles "
            "en el SQL."
        )
    else:
        purpose = f"Prepara {target_label} a partir de la logica declarada en el SQL para dejar una salida procesada."

    non_goals = [
        "No describe reglas ni catalogos fuera de lo visible en el SQL.",
        "No cubre reportes, pantallas ni consumos finales.",
    ]
    if target_table:
        non_goals.append(f"No actualiza otras tablas distintas a {target_table}.")

    return _normalize_suggestion(
        SqlBusinessContextSuggestion(
            purpose=purpose,
            non_goals=non_goals,
            provider="heuristic",
        )
    )


def _extract_target_table(sql_text: str) -> Optional[str]:
    match = TARGET_PATTERN.search(sql_text)
    return match.group(1) if match else None


def _extract_source_tables(sql_text: str, target_table: str | None) -> List[str]:
    seen: List[str] = []
    target_lower = (target_table or "").lower()
    for source in SOURCE_PATTERN.findall(sql_text):
        normalized = source.strip()
        if not normalized:
            continue
        if normalized.lower() == target_lower:
            continue
        if normalized not in seen:
            seen.append(normalized)
    return seen


def _friendly_name(value: str) -> str:
    stem = re.sub(r"\.sql$", "", value, flags=re.IGNORECASE)
    clean = re.sub(r"[_-]+", " ", stem).strip()
    return clean or "la salida objetivo"


def _normalize_suggestion(suggestion: SqlBusinessContextSuggestion) -> SqlBusinessContextSuggestion:
    suggestion.purpose = _clip_words(_single_line(suggestion.purpose), 50)
    suggestion.non_goals = [_clip_words(_single_line(item), 16) for item in suggestion.non_goals if item and item.strip()]
    suggestion.non_goals = suggestion.non_goals[:3]
    if not suggestion.non_goals:
        suggestion.non_goals = ["No agrega alcance fuera de lo visible en el SQL."]
    return suggestion


def _single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clip_words(value: str, max_words: int) -> str:
    words = value.split()
    if len(words) <= max_words:
        return value
    return " ".join(words[:max_words]).rstrip(".,;:") + "."


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    output = getattr(response, "output", None) or []
    for item in output:
        for content in getattr(item, "content", None) or []:
            text = getattr(content, "text", None)
            if text:
                return text
    raise ValueError("La respuesta del modelo no contiene texto util.")


def _extract_chat_completion_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("La respuesta del modelo no contiene choices.")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    raise ValueError("La respuesta del modelo no contiene contenido util.")


def _build_prompt_messages(masked_sql: str, sql_file_name: Optional[str]) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Eres analista funcional de pipelines SQL. "
                "Responde en espanol claro y muy conciso. "
                "Devuelve JSON valido con las llaves 'purpose' y 'non_goals'. "
                "purpose debe ser un parrafo de maximo 50 palabras. "
                "non_goals debe ser una lista de 1 a 3 lineas, cada una muy breve. "
                "Basate solo en lo visible en el SQL. No inventes negocio no evidente."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Archivo: {sql_file_name or 'consulta_web.sql'}\n\n"
                "Resume este SQL para documentacion funcional.\n\n"
                f"{masked_sql}"
            ),
        },
    ]
