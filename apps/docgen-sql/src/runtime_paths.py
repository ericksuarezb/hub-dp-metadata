from __future__ import annotations

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    candidates = []

    env_root = os.getenv("DOCGEN_SQL_HOME")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    cwd = Path.cwd()
    candidates.append(cwd)
    candidates.extend(cwd.parents)
    candidates.append(PACKAGE_ROOT)

    seen = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if _looks_like_project_root(resolved):
            return resolved

    return PACKAGE_ROOT


def project_path(*parts: str) -> Path:
    return get_project_root().joinpath(*parts)


def _looks_like_project_root(path: Path) -> bool:
    return (path / "src").is_dir() and (path / "config").is_dir() and (path / "input").is_dir()
