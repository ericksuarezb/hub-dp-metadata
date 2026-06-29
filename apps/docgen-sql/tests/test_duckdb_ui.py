from pathlib import Path

from src import duckdb_ui


def test_ensure_duckdb_ui_server_creates_duckdb_extension_state(monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime"
    duckdb_home = runtime_dir / "duckdb-home"
    duckdb_extensions = runtime_dir / "duckdb-extensions"
    db_path = tmp_path / "data" / "mock.duckdb"

    class FakeProcess:
        pid = 43210

    def fake_popen(*args, **kwargs):
        assert kwargs["env"]["HOME"] == str(duckdb_home)
        assert kwargs["env"]["DUCKDB_EXTENSION_DIRECTORY"] == str(duckdb_extensions)
        return FakeProcess()

    monkeypatch.setattr(duckdb_ui, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(duckdb_ui, "DUCKDB_HOME", duckdb_home)
    monkeypatch.setattr(duckdb_ui, "DUCKDB_EXTENSIONS", duckdb_extensions)
    monkeypatch.setattr(duckdb_ui, "DUCKDB_UI_PID", runtime_dir / "duckdb-ui.pid")
    monkeypatch.setattr(duckdb_ui, "DUCKDB_UI_LOG", runtime_dir / "duckdb-ui.log")
    monkeypatch.setattr(duckdb_ui, "_read_pid", lambda: None)
    monkeypatch.setattr(
        duckdb_ui,
        "subprocess",
        type("SubprocessModule", (), {"Popen": fake_popen, "STDOUT": object()}),
    )

    result = duckdb_ui.ensure_duckdb_ui_server(db_path=db_path, port=4321)

    assert result["status"] == "started"
    assert result["url"] == "http://localhost:4321/"
    assert (duckdb_home / ".duckdb" / "extension_data").is_dir()
    assert Path(result["db_path"]) == db_path.resolve()
