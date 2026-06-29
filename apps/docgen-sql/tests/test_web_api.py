from src import web_api
from src.sql_business_context import SqlBusinessContextSuggestion


def test_sql_business_context_endpoint(monkeypatch):
    monkeypatch.setattr(
        web_api,
        "infer_sql_business_context",
        lambda sql_text, sql_file_name=None: SqlBusinessContextSuggestion(
            purpose="Resume el objetivo funcional del SQL.",
            non_goals=["No cubre reportes finales."],
            provider="heuristic",
            warning=None,
        ),
    )

    response = web_api.infer_business_context(
        web_api.SqlBusinessContextRequest(
            sql_text="select 1",
            sql_file_name="demo.sql",
        )
    )

    assert response["purpose"] == "Resume el objetivo funcional del SQL."
    assert response["non_goals"] == ["No cubre reportes finales."]


def test_list_latest_datacontracts_endpoint(monkeypatch):
    class FakeRepository:
        def is_enabled(self):
            return True

        def list_latest_datacontracts(self, search="", limit=100):
            assert search == "clientes"
            assert limit == 5
            return [{"run_id": "run-1", "table_name": "demo.clientes"}]

    monkeypatch.setattr(web_api, "SupabaseRunRepository", lambda settings: FakeRepository())
    monkeypatch.setattr(web_api, "load_supabase_settings", lambda: object())

    response = web_api.list_latest_datacontracts(search="clientes", limit=5)

    assert response["items"] == [{"run_id": "run-1", "table_name": "demo.clientes"}]


def test_get_datacontract_endpoint(monkeypatch):
    class FakeRepository:
        def is_enabled(self):
            return True

        def get_datacontract_version(self, run_id):
            assert run_id == "run-1"
            return {"run_id": "run-1", "yaml_text": "version: 1"}

    monkeypatch.setattr(web_api, "SupabaseRunRepository", lambda settings: FakeRepository())
    monkeypatch.setattr(web_api, "load_supabase_settings", lambda: object())

    response = web_api.get_datacontract("run-1")

    assert response == {"run_id": "run-1", "yaml_text": "version: 1"}
