from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

import duckdb


running = True


def _handle_signal(signum, frame) -> None:  # pragma: no cover - signal handling
    del signum, frame
    global running
    running = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mantiene viva una instancia local de DuckDB UI.")
    parser.add_argument("--db-path", required=True, help="Ruta a la base DuckDB.")
    parser.add_argument("--port", type=int, default=4213, help="Puerto local del DuckDB UI.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    db_path = Path(args.db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    extension_dir = Path(os.environ.get("DUCKDB_EXTENSION_DIRECTORY", db_path.parent / ".duckdb_extensions")).resolve()
    extension_dir.mkdir(parents=True, exist_ok=True)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    connection_args = {}
    if db_path.exists():
        # The UI is used as an exploration surface, so read-only access avoids
        # writer locks when another process is preparing or refreshing the file.
        connection_args["read_only"] = True

    connection = duckdb.connect(str(db_path), **connection_args)
    try:
        connection.execute(f"SET extension_directory = '{extension_dir.as_posix()}';")
        extension_binary = _find_ui_extension_binary(extension_dir)
        if extension_binary is not None:
            connection.execute(f"LOAD '{extension_binary.as_posix()}';")
        else:
            try:
                connection.execute("LOAD ui;")
            except duckdb.Error:
                connection.execute("INSTALL ui;")
                connection.execute("LOAD ui;")
        connection.execute(f"SET ui_local_port = {int(args.port)};")
        connection.execute("CALL start_ui_server();")
        while running:
            time.sleep(1)
    finally:
        try:
            connection.execute("CALL stop_ui_server();")
        except Exception:
            pass
        connection.close()


def _find_ui_extension_binary(extension_dir: Path) -> Path | None:
    matches = sorted(extension_dir.glob("**/ui.duckdb_extension"))
    if matches:
        return matches[0]
    return None


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - CLI fail path
        print(str(exc), file=sys.stderr)
        raise
