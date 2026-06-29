from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.runtime_paths import get_project_root


def credentials_file_candidates() -> Iterable[Path]:
    explicit_path = os.getenv("DOCGEN_CREDENTIALS_FILE", "").strip()
    if explicit_path:
        yield Path(explicit_path).expanduser()
        return

    root = get_project_root().resolve()
    for candidate_root in [root, *root.parents]:
        yield candidate_root / "config.credentials.json"


def find_credentials_file() -> Optional[Path]:
    for candidate in credentials_file_candidates():
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_credentials() -> Dict[str, Any]:
    path = find_credentials_file()
    if path is None:
        return {}
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return {}
    data = json.loads(raw_text)
    return data if isinstance(data, dict) else {}


def get_credential(*path: str, default: str = "") -> str:
    if not path:
        return default

    current: Any = load_credentials()
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    if current is None:
        return default
    if isinstance(current, str):
        return current.strip()
    return str(current).strip()


def first_non_empty(*values: str) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized:
            return normalized
    return ""
