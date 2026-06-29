from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from src.runtime_paths import get_project_root, project_path

REPO_ROOT = get_project_root()
DEFAULT_DUCKDB_PATH = project_path("data", "duckdb", "docgen_profiles.duckdb")
RUNTIME_DIR = project_path("output", "runtime")
DUCKDB_HOME = RUNTIME_DIR / "duckdb-home"
DUCKDB_EXTENSIONS = RUNTIME_DIR / "duckdb-extensions"
DUCKDB_UI_PID = RUNTIME_DIR / "duckdb-ui.pid"
DUCKDB_UI_LOG = RUNTIME_DIR / "duckdb-ui.log"


def ensure_duckdb_ui_server(
    db_path: str | Path | None = None,
    port: int = 4213,
) -> Dict[str, Any]:
    target_db = Path(db_path or DEFAULT_DUCKDB_PATH).resolve()
    target_db.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    DUCKDB_HOME.mkdir(parents=True, exist_ok=True)
    DUCKDB_EXTENSIONS.mkdir(parents=True, exist_ok=True)
    # DuckDB UI writes extension state under HOME/.duckdb/extension_data.
    (DUCKDB_HOME / ".duckdb" / "extension_data").mkdir(parents=True, exist_ok=True)

    current_pid = _read_pid()
    if current_pid and _process_alive(current_pid):
        return {
            "status": "running",
            "url": f"http://localhost:{port}/",
            "db_path": str(target_db),
            "pid": current_pid,
            "log_path": str(DUCKDB_UI_LOG),
        }

    if current_pid:
        _clear_pid()

    env = os.environ.copy()
    env["HOME"] = str(DUCKDB_HOME)
    env["DUCKDB_EXTENSION_DIRECTORY"] = str(DUCKDB_EXTENSIONS)

    with DUCKDB_UI_LOG.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "src.duckdb_ui_server",
                "--db-path",
                str(target_db),
                "--port",
                str(port),
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    DUCKDB_UI_PID.write_text(str(process.pid), encoding="utf-8")
    return {
        "status": "started",
        "url": f"http://localhost:{port}/",
        "db_path": str(target_db),
        "pid": process.pid,
        "log_path": str(DUCKDB_UI_LOG),
    }


def _read_pid() -> int | None:
    if not DUCKDB_UI_PID.exists():
        return None
    raw = DUCKDB_UI_PID.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _clear_pid() -> None:
    if DUCKDB_UI_PID.exists():
        DUCKDB_UI_PID.unlink()


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
