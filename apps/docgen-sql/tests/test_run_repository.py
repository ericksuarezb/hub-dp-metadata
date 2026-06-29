from pathlib import Path

from src.run_repository import SupabaseRunRepository, load_supabase_settings


def test_load_supabase_settings_reads_yaml(tmp_path):
    config_path = tmp_path / "supabase.yml"
    config_path.write_text(
        "\n".join(
            [
                "supabase:",
                "  enabled: true",
                "  url: https://demo.supabase.co",
                "  service_role_key_env: SUPABASE_SERVICE_ROLE_KEY",
                "  service_role_key: secret-value",
                "  timeout_seconds: 5",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_supabase_settings(Path(config_path))

    assert settings.enabled is True
    assert settings.url == "https://demo.supabase.co"
    assert settings.service_role_key == "secret-value"
    assert settings.timeout_seconds == 5


def test_supabase_repository_is_disabled_without_required_settings():
    repository = SupabaseRunRepository(load_supabase_settings(Path("/tmp/does-not-exist.yml")))

    assert repository.is_enabled() is False


def test_supabase_repository_reads_service_role_key_from_credentials_file(monkeypatch, tmp_path):
    credentials_path = tmp_path / "config.credentials.json"
    credentials_path.write_text(
        "\n".join(
            [
                "{",
                '  "supabase": {',
                '    "service_role_key": "secret-from-json"',
                "  }",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOCGEN_CREDENTIALS_FILE", str(credentials_path))

    settings = load_supabase_settings(Path("/tmp/does-not-exist.yml"))
    settings.enabled = True
    settings.url = "https://demo.supabase.co"
    repository = SupabaseRunRepository(settings)

    assert repository.service_role_key == "secret-from-json"
    assert repository.is_enabled() is True


def test_workspace_zip_is_not_treated_as_regular_artifact():
    settings = load_supabase_settings(Path("/tmp/does-not-exist.yml"))
    repository = SupabaseRunRepository(settings)

    assert repository._should_upload_artifact("/tmp/workspace.zip") is False


def test_list_latest_datacontracts_returns_latest_per_table():
    settings = load_supabase_settings(Path("/tmp/does-not-exist.yml"))
    settings.enabled = True
    settings.url = "https://demo.supabase.co"
    settings.service_role_key = "secret"
    repository = SupabaseRunRepository(settings)

    def fake_fetch_json(endpoint, headers):
        if "app_runs" in endpoint:
            return [
                {
                    "run_id": "run-new",
                    "created_at": "2026-05-12T11:00:00Z",
                    "product_name": "Clientes",
                    "sql_file_name": "clientes_v2.sql",
                    "final_table_name": "demo.clientes",
                    "target_table": "demo.clientes",
                    "storage_objects": {"datacontract_yaml": "run-new/demo.clientes.odcs.yaml"},
                },
                {
                    "run_id": "run-old",
                    "created_at": "2026-05-11T11:00:00Z",
                    "product_name": "Clientes",
                    "sql_file_name": "clientes_v1.sql",
                    "final_table_name": "demo.clientes",
                    "target_table": "demo.clientes",
                    "storage_objects": {"datacontract_yaml": "run-old/demo.clientes.odcs.yaml"},
                },
                {
                    "run_id": "run-other",
                    "created_at": "2026-05-10T11:00:00Z",
                    "product_name": "Cuentas",
                    "sql_file_name": "cuentas.sql",
                    "final_table_name": "demo.cuentas",
                    "target_table": "demo.cuentas",
                    "storage_objects": {},
                },
            ]
        return [
            {"run_id": "run-new", "odcs_yaml": "version: 1"},
            {"run_id": "run-old", "odcs_yaml": "version: 0"},
            {"run_id": "run-other", "odcs_yaml": "version: 2"},
        ]

    repository._fetch_json = fake_fetch_json

    items = repository.list_latest_datacontracts()

    assert [item["run_id"] for item in items] == ["run-new", "run-other"]
    assert [item["table_name"] for item in items] == ["demo.clientes", "demo.cuentas"]


def test_get_datacontract_version_returns_inline_yaml_and_metadata():
    settings = load_supabase_settings(Path("/tmp/does-not-exist.yml"))
    settings.enabled = True
    settings.url = "https://demo.supabase.co"
    settings.service_role_key = "secret"
    repository = SupabaseRunRepository(settings)

    def fake_fetch_json(endpoint, headers):
        if "app_runs" in endpoint:
            return [
                {
                    "run_id": "run-1",
                    "created_at": "2026-05-12T11:00:00Z",
                    "product_name": "Clientes",
                    "sql_file_name": "clientes.sql",
                    "final_table_name": "demo.clientes",
                    "target_table": "demo.clientes",
                    "storage_objects": {"datacontract_yaml": "run-1/demo.clientes.odcs.yaml"},
                }
            ]
        return [{"run_id": "run-1", "odcs_yaml": "version: 1"}]

    repository._fetch_json = fake_fetch_json

    item = repository.get_datacontract_version("run-1")

    assert item["run_id"] == "run-1"
    assert item["file_name"] == "demo.clientes.odcs.yaml"
    assert item["yaml_text"] == "version: 1"


def test_get_datacontract_version_falls_back_to_storage_download():
    settings = load_supabase_settings(Path("/tmp/does-not-exist.yml"))
    settings.enabled = True
    settings.url = "https://demo.supabase.co"
    settings.service_role_key = "secret"
    settings.storage_bucket = "docgen-artifacts"
    repository = SupabaseRunRepository(settings)

    def fake_fetch_json(endpoint, headers):
        if "app_runs" in endpoint:
            return [
                {
                    "run_id": "run-1",
                    "created_at": "2026-05-12T11:00:00Z",
                    "product_name": "Clientes",
                    "sql_file_name": "clientes.sql",
                    "final_table_name": "demo.clientes",
                    "target_table": "demo.clientes",
                    "storage_objects": {"datacontract_yaml": "run-1/demo.clientes.odcs.yaml"},
                }
            ]
        return [{"run_id": "run-1", "odcs_yaml": ""}]

    repository._fetch_json = fake_fetch_json
    repository.download_object = lambda bucket, path: (b"version: storage\n", "application/yaml")

    item = repository.get_datacontract_version("run-1")

    assert item["yaml_text"] == "version: storage\n"
