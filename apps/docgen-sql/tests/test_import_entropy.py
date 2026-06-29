from pathlib import Path

from src.import_entropy import (
    EntropyImportSettings,
    EntropyImporter,
    get_latest_run_id,
    load_entropy_settings,
    overlay_sources_from_registry,
)
from src.run_repository import SupabaseRunRepository, load_supabase_settings


def test_importer_builds_entropy_payload_from_bundle():
    bundle = {
        "source": {"system": "docgen-sql", "run_id": "run-123"},
        "data_product": {
            "name": "Clientes",
            "target_table": "demo.clientes",
            "domain": "captacion",
            "description": {
                "purpose": "Dataset clientes",
                "usage": "Analitica y consumo",
                "limitations": "No incluye historico",
            },
            "status": "active",
            "tags": ["diario"],
            "schema_name": "clientes",
            "schema_physical_name": "demo.clientes",
        },
        "assets": [
            {
                "asset_type": "dataset",
                "qualified_name": "demo.clientes",
                "display_name": "clientes",
                "role": "target",
            },
            {
                "asset_type": "dataset",
                "qualified_name": "raw.personas",
                "display_name": "personas",
                "role": "source",
            },
            {
                "asset_type": "file",
                "qualified_name": "input/sql/clientes.sql",
                "display_name": "clientes.sql",
                "role": "evidence",
            },
        ],
        "lineage": {
            "relations": [{"source_node": "raw.personas", "target_node": "demo.clientes"}],
            "openlineage_events": [
                {
                    "job": {"name": "paso_01"},
                    "inputs": [{"namespace": "raw", "name": "personas"}],
                    "outputs": [{"namespace": "demo", "name": "clientes"}],
                }
            ],
        },
        "quality": {
            "summary": {"passed": True},
            "findings": [{"severity": "warning", "message": "warning"}],
        },
        "datacontract": {
            "external_key": "demo-clientes",
            "file_name": "demo.clientes.odcs.yaml",
            "storage_path": "run-123/demo.clientes.odcs.yaml",
            "yaml": "dataProduct: Clientes\n",
        },
    }

    importer = EntropyImporter()
    payload = importer.build_import_payload(bundle)
    plan = importer.build_operation_plan(payload)

    assert payload["data_product"]["external_key"] == "demo-clientes"
    assert payload["data_product"]["output_port_id"] == "demo-clientes-port"
    assert payload["data_product"]["description"] == (
        "Purpose: Dataset clientes\n\n"
        "Usage: Analitica y consumo\n\n"
        "Limitations: No incluye historico"
    )
    assert payload["data_product"]["description_structured"] == {
        "purpose": "Dataset clientes",
        "usage": "Analitica y consumo",
        "limitations": "No incluye historico",
    }
    assert payload["datacontract"]["external_key"] == "demo-clientes"
    assert len(payload["datasets"]["target"]) == 1
    assert len(payload["datasets"]["sources"]) == 1
    assert len(payload["datasets"]["all"]) == 2
    assert len(payload["evidence_files"]) == 1
    assert plan["create_or_update_data_product"] is True
    assert plan["lineage_relation_count"] == 1
    assert plan["openlineage_event_count"] == 1
    assert payload["lineage"]["openlineage_events"][0]["run"]["facets"]["entropy_data"]["dataProductId"] == "demo-clientes"
    assert payload["lineage"]["openlineage_events"][0]["outputs"][0]["facets"]["entropy_data"]["dataContractId"] == "demo-clientes"


def test_importer_builds_dataproduct_request_body():
    settings = EntropyImportSettings(team_id="team-123", api_token="secret")
    importer = EntropyImporter(settings)
    payload = {
        "source": {"system": "docgen-sql", "run_id": "run-123"},
        "data_product": {
            "external_key": "demo-clientes",
            "name": "Clientes",
            "description": "Dataset clientes",
            "status": "completed",
            "tags": ["diario"],
            "domain": "captacion",
            "schema_name": "clientes",
            "schema_physical_name": "demo.clientes",
            "output_port_id": "demo-clientes-port",
        },
        "datasets": {
            "target": [{"qualified_name": "demo.clientes", "display_name": "clientes", "role": "target"}],
            "sources": [{"qualified_name": "raw.personas", "display_name": "personas", "role": "source"}],
        },
        "datacontract": {
            "external_key": "demo-clientes",
            "file_name": "demo.clientes.odcs.yaml",
            "storage_path": "run-123/demo.clientes.odcs.yaml",
            "yaml": "dataProduct: Clientes\n",
        },
    }

    data_product_id, body, specification = importer.build_dataproduct_request(payload)

    assert data_product_id == "demo-clientes"
    assert specification == "odps"
    assert body["apiVersion"] == "v1.0.0"
    assert body["kind"] == "DataProduct"
    assert body["id"] == "demo-clientes"
    assert body["team"]["name"] == "team-123"
    assert body["status"] == "active"
    assert body["outputPorts"][0]["name"] == "demo-clientes-port"
    assert body["outputPorts"][0]["version"] == "0.1.0"
    assert body["outputPorts"][0]["contractId"] == "demo-clientes"
    assert body["outputPorts"][0]["dataContractId"] == "demo-clientes"
    assert body["outputPorts"][0]["customProperties"][0]["property"] == "displayName"
    assert body["outputPorts"][0]["customProperties"][1]["property"] == "location"
    assert body["customProperties"][0]["property"] == "schema_name"


def test_importer_builds_datacontract_request_body_from_yaml_id():
    importer = EntropyImporter()
    payload = {
        "data_product": {
            "external_key": "demo-clientes",
            "name": "Clientes",
        },
        "datacontract": {
            "external_key": "fallback-id",
            "yaml": "\n".join(
                [
                    "apiVersion: v3.1.0",
                    "kind: DataContract",
                    "id: contract-from-yaml",
                    "dataProduct: Clientes",
                    "schema:",
                    "  - name: clientes",
                ]
            ),
        },
    }

    contract_id, contract_object, normalized_yaml = importer.build_datacontract_request(payload)

    assert contract_id == "contract-from-yaml"
    assert contract_object["id"] == "contract-from-yaml"
    assert contract_object["kind"] == "DataContract"
    assert "id: contract-from-yaml" in normalized_yaml


def test_importer_publish_datacontract_falls_back_between_endpoint_variants():
    settings = EntropyImportSettings(
        base_url="http://127.0.0.1:8082",
        api_token="secret",
        team_id="team-123",
    )
    importer = EntropyImporter(settings)
    calls = []

    def fake_request(method, path, payload, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            raise RuntimeError("Entropy devolvio HTTP 404 en intento inicial")
        return {"ok": True}

    importer._request = fake_request

    result = importer.publish_datacontract(
        {
            "data_product": {"external_key": "demo-clientes", "name": "Clientes"},
            "datacontract": {
                "yaml": "\n".join(
                    [
                        "apiVersion: v3.1.0",
                        "kind: DataContract",
                        "id: contract-from-yaml",
                        "dataProduct: Clientes",
                    ]
                )
            },
        }
    )

    assert calls[0][1] == "/api/datacontracts/contract-from-yaml?specification=odcs"
    assert calls[1][1] == "/api/datacontracts/contract-from-yaml"
    assert result["status"] == "published"
    assert result["contract_id"] == "contract-from-yaml"
    assert result["request_format"] == "json"


def test_importer_filters_non_physical_source_datasets():
    importer = EntropyImporter()

    payload = importer.build_import_payload(
        {
            "data_product": {"name": "Clientes", "target_table": "demo.clientes"},
            "assets": [
                {"asset_type": "dataset", "qualified_name": "demo.clientes", "display_name": "clientes", "role": "target"},
                {"asset_type": "dataset", "qualified_name": "raw.personas AS p", "display_name": "personas", "role": "source", "source_kind": "table"},
                {"asset_type": "dataset", "qualified_name": "CTE _tmp_clientes_ (derivada de raw.personas)", "display_name": "_tmp_clientes_", "role": "source", "source_kind": "cte"},
                {"asset_type": "dataset", "qualified_name": "raw.a AS a, raw.b AS b (subconsulta mix)", "display_name": "mix", "role": "source", "source_kind": "subquery"},
                {"asset_type": "dataset", "qualified_name": "_logical_tmp_ AS l", "display_name": "_logical_tmp_", "role": "source", "source_kind": "table"},
            ],
            "lineage": {
                "relations": [
                    {"source_node": "stg.orders", "source_kind": "table", "source_group": "stg"},
                    {"source_node": "cte_union_orders", "source_kind": "process", "source_group": "process"},
                ]
            },
            "quality": {},
            "datacontract": {},
        }
    )

    assert [item["qualified_name"] for item in payload["datasets"]["sources"]] == ["raw.personas", "stg.orders"]
    assert [item["display_name"] for item in payload["datasets"]["sources"]] == ["personas", "orders"]


def test_importer_execute_calls_data_product_and_lineage_endpoints():
    settings = EntropyImportSettings(
        base_url="http://127.0.0.1:8082",
        api_token="secret",
        team_id="team-123",
    )
    importer = EntropyImporter(settings)
    captured_calls = []

    def fake_request_json(method, path, payload):
        captured_calls.append((method, path, payload))
        return {"ok": True}

    importer._request_json = fake_request_json

    result = importer.execute(
        {
            "source": {"system": "docgen-sql", "run_id": "run-123"},
            "data_product": {
                "external_key": "demo-clientes",
                "name": "Clientes",
                "description": "Dataset clientes",
                "status": "active",
                "tags": ["diario"],
                "domain": "captacion",
                "schema_name": "clientes",
                "schema_physical_name": "demo.clientes",
                "output_port_id": "demo-clientes-port",
            },
            "datasets": {
                "target": [{"qualified_name": "demo.clientes", "display_name": "clientes", "role": "target"}],
                "sources": [{"qualified_name": "raw.personas", "display_name": "personas", "role": "source"}],
            },
            "lineage": {
                "openlineage_events": [
                    {
                        "job": {"name": "paso_01"},
                        "run": {"runId": "run-123::paso_01"},
                    }
                ]
            },
            "datacontract": {},
        }
    )

    assert captured_calls[0][0] == "PUT"
    assert captured_calls[0][1] == "/api/dataproducts/demo-clientes?specification=odps"
    assert captured_calls[1][0] == "POST"
    assert "dataProductId=demo-clientes" in captured_calls[1][1]
    assert "outputPortId=demo-clientes-port" in captured_calls[1][1]
    assert result["status"] == "executed"
    assert result["results"]["lineage_events_sent"] == 1


def test_importer_execute_publishes_datacontract_before_dataproduct():
    settings = EntropyImportSettings(
        base_url="http://127.0.0.1:8082",
        api_token="secret",
        team_id="team-123",
    )
    importer = EntropyImporter(settings)
    captured_calls = []

    def fake_request(method, path, payload, headers=None):
        captured_calls.append((method, path, payload, headers))
        return {"ok": True}

    importer._request = fake_request

    result = importer.execute(
        {
            "source": {"system": "docgen-sql", "run_id": "run-123"},
            "data_product": {
                "external_key": "demo-clientes",
                "name": "Clientes",
                "description": "Dataset clientes",
                "status": "active",
                "tags": ["diario"],
                "domain": "captacion",
                "schema_name": "clientes",
                "schema_physical_name": "demo.clientes",
                "output_port_id": "demo-clientes-port",
            },
            "datasets": {
                "target": [{"qualified_name": "demo.clientes", "display_name": "clientes", "role": "target"}],
                "sources": [],
            },
            "lineage": {
                "openlineage_events": []
            },
            "datacontract": {
                "external_key": "contract-from-yaml",
                "yaml": "\n".join(
                    [
                        "apiVersion: v3.1.0",
                        "kind: DataContract",
                        "id: contract-from-yaml",
                        "dataProduct: Clientes",
                    ]
                ),
            },
        }
    )

    assert captured_calls[0][1] == "/api/datacontracts/contract-from-yaml?specification=odcs"
    assert captured_calls[1][1] == "/api/dataproducts/demo-clientes?specification=odps"
    assert result["results"]["datacontract"]["status"] == "published"


def test_importer_discovers_team_id_by_name():
    settings = EntropyImportSettings(
        base_url="http://127.0.0.1:8082",
        api_token="secret",
        team_name="captacion",
    )
    importer = EntropyImporter(settings)

    def fake_request_json(method, path, payload):
        assert method == "GET"
        return {
            "items": [
                {"id": "team-1", "name": "plataforma", "teamType": "Platform Team"},
                {"id": "team-2", "name": "captacion", "teamType": "Team"},
            ]
        }

    importer._request_json = fake_request_json

    assert importer.discover_team_id() == "team-2"


def test_importer_discovers_single_candidate_team_id():
    settings = EntropyImportSettings(
        base_url="http://127.0.0.1:8082",
        api_token="secret",
    )
    importer = EntropyImporter(settings)

    importer._request_json = lambda method, path, payload: [
        {"id": "team-2", "name": "captacion", "teamType": "Team"}
    ]

    assert importer.discover_team_id() == "team-2"


def test_get_latest_run_id_returns_most_recent_entry():
    settings = load_supabase_settings(Path("/tmp/does-not-exist.yml"))
    settings.enabled = True
    settings.url = "https://demo.supabase.co"
    settings.service_role_key = "secret"
    repository = SupabaseRunRepository(settings)

    repository._fetch_json = lambda endpoint, headers: [
        {"run_id": "run-new", "created_at": "2026-05-20T12:00:00Z"}
    ]

    assert get_latest_run_id(repository) == "run-new"


def test_overlay_sources_from_registry_replaces_bundle_sources(monkeypatch):
    class FakeClient:
        def is_enabled(self):
            return True

        def fetch_rows(self, table_or_view, filters=None):
            assert table_or_view == "entropy_source_registry_ready"
            assert filters == {"run_id": "eq.run-123"}
            return [
                {
                    "source_table": "rd_baz_bdclientes.rd_clientes",
                    "source_object_name": "rd_clientes",
                    "source_schema_type": "RAW",
                    "source_kind": "table",
                }
            ]

    monkeypatch.setattr("src.import_entropy.SupabaseTableClient", lambda: FakeClient())

    bundle = {
        "source": {"run_id": "run-123"},
        "assets": [
            {"asset_type": "dataset", "qualified_name": "demo.target", "role": "target"},
            {"asset_type": "dataset", "qualified_name": "dirty.cte_name", "role": "source"},
            {"asset_type": "file", "qualified_name": "sql/query.sql", "role": "evidence"},
        ],
    }

    updated = overlay_sources_from_registry(bundle)

    dataset_assets = [item for item in updated["assets"] if item.get("asset_type") == "dataset"]
    assert [item["qualified_name"] for item in dataset_assets] == ["demo.target", "rd_baz_bdclientes.rd_clientes"]
    assert updated["source"]["registry_controlled_sources"] is True


def test_importer_registry_controlled_sources_do_not_backfill_from_relations():
    importer = EntropyImporter()

    payload = importer.build_import_payload(
        {
            "source": {
                "run_id": "run-123",
                "registry_controlled_sources": True,
            },
            "data_product": {"name": "Clientes", "target_table": "demo.clientes"},
            "assets": [
                {"asset_type": "dataset", "qualified_name": "demo.clientes", "display_name": "clientes", "role": "target"},
                {"asset_type": "dataset", "qualified_name": "raw.personas", "display_name": "personas", "role": "source"},
            ],
            "lineage": {
                "relations": [
                    {"source_node": "tmp.step_table", "source_kind": "table", "source_group": "tmp"},
                ]
            },
            "quality": {},
            "datacontract": {},
        }
    )

    assert [item["qualified_name"] for item in payload["datasets"]["sources"]] == ["raw.personas"]


def test_importer_dry_run_returns_planned_payload():
    importer = EntropyImporter()

    result = importer.run(
        {
            "data_product": {"name": "Clientes", "target_table": "demo.clientes"},
            "assets": [],
            "lineage": {},
            "quality": {},
            "datacontract": {},
        },
        dry_run=True,
    )

    assert result["mode"] == "dry-run"
    assert result["status"] == "planned"
    assert result["plan"]["create_or_update_data_product"] is True


def test_load_entropy_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("ENTROPY_BASE_URL", "https://entropy.local/api")
    monkeypatch.setenv("ENTROPY_API_TOKEN", "secret-token")
    monkeypatch.setenv("ENTROPY_TEAM_ID", "team-abc")
    monkeypatch.setenv("ENTROPY_TEAM_NAME", "captacion")

    settings = load_entropy_settings()

    assert settings.base_url == "https://entropy.local/api"
    assert settings.api_token == "secret-token"
    assert settings.team_id == "team-abc"
    assert settings.team_name == "captacion"


def test_load_entropy_settings_reads_local_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ENTROPY_BASE_URL", raising=False)
    monkeypatch.delenv("ENTROPY_API_TOKEN", raising=False)
    monkeypatch.delenv("ENTROPY_TEAM_ID", raising=False)
    monkeypatch.delenv("ENTROPY_TEAM_NAME", raising=False)
    monkeypatch.setattr("src.import_entropy.project_path", lambda *parts: tmp_path.joinpath(*parts))

    (tmp_path / ".env.local").write_text(
        "\n".join(
            [
                "ENTROPY_BASE_URL=http://127.0.0.1:8082",
                "ENTROPY_API_TOKEN='token-from-file'",
                "ENTROPY_TEAM_ID=team-from-file",
                "ENTROPY_TEAM_NAME=governance",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_entropy_settings()

    assert settings.base_url == "http://127.0.0.1:8082"
    assert settings.api_token == "token-from-file"
    assert settings.team_id == "team-from-file"
    assert settings.team_name == "governance"


def test_load_entropy_settings_reads_credentials_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ENTROPY_BASE_URL", raising=False)
    monkeypatch.delenv("ENTROPY_API_TOKEN", raising=False)
    monkeypatch.delenv("ENTROPY_TEAM_ID", raising=False)
    monkeypatch.delenv("ENTROPY_TEAM_NAME", raising=False)
    credentials_path = tmp_path / "config.credentials.json"
    credentials_path.write_text(
        "\n".join(
            [
                "{",
                '  "entropy": {',
                '    "base_url": "https://entropy.local/api",',
                '    "api_token": "token-from-json",',
                '    "team_id": "team-json",',
                '    "team_name": "governance-json"',
                "  }",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOCGEN_CREDENTIALS_FILE", str(credentials_path))

    settings = load_entropy_settings()

    assert settings.base_url == "https://entropy.local/api"
    assert settings.api_token == "token-from-json"
    assert settings.team_id == "team-json"
    assert settings.team_name == "governance-json"
