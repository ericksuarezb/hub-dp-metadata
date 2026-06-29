from pathlib import Path

from src.sync_entropy_registry import (
    build_entropy_source_registry_rows,
    infer_is_temporary,
    load_schema_catalog_csv,
    normalize_schema_type,
)


def test_normalize_schema_type_maps_empty_and_unknown():
    assert normalize_schema_type("") == "NO CLASIFICADO"
    assert normalize_schema_type("raw") == "RAW"
    assert normalize_schema_type("algo-raro") == "OTRO"


def test_infer_is_temporary_uses_type_and_name():
    assert infer_is_temporary("stg_baz_clientes", "RAW") is True
    assert infer_is_temporary("cd_baz_clientes_tmp", "CRYSTAL") is True
    assert infer_is_temporary("cu_baz_clientes", "TEMPORAL") is True
    assert infer_is_temporary("rd_baz_clientes", "RAW") is False


def test_load_schema_catalog_csv_maps_rows(tmp_path):
    csv_path = tmp_path / "schemas.csv"
    csv_path.write_text(
        "\n".join(
            [
                "esquema,descripcion,proposito",
                "rd_baz_bdclientes,Raw clientes,RAW",
                "stg_baz_bdclientes,Stage clientes,TEMPORAL",
                "x_misc,,",
            ]
        ),
        encoding="utf-8",
    )

    rows = load_schema_catalog_csv(Path(csv_path))

    assert rows[0]["schema_name"] == "rd_baz_bdclientes"
    assert rows[0]["schema_type"] == "RAW"
    assert rows[0]["is_temporary"] is False
    assert rows[1]["schema_name"] == "stg_baz_bdclientes"
    assert rows[1]["is_temporary"] is True
    assert rows[2]["schema_type"] == "NO CLASIFICADO"


def test_build_entropy_source_registry_rows_marks_temporary_sources(monkeypatch):
    schema_map = {
        "rd_baz_bdclientes": {"schema_type": "RAW"},
        "stg_baz_bdclientes": {"schema_type": "TEMPORAL"},
    }

    class FakeRepository:
        def is_enabled(self):
            return True

        def get_run_export_payload(self, run_id):
            return {"fake": run_id}

    class FakeImporter:
        def build_import_payload(self, bundle):
            return {
                "datasets": {
                    "target": [{"qualified_name": "cd_baz_bdclientes.cd_target"}],
                    "sources": [
                        {"qualified_name": "rd_baz_bdclientes.rd_source", "source_kind": "table"},
                        {"qualified_name": "stg_baz_bdclientes.tmp_source", "source_kind": "table"},
                    ],
                }
            }

    monkeypatch.setattr("src.sync_entropy_registry.SupabaseRunRepository", lambda settings: FakeRepository())
    monkeypatch.setattr("src.sync_entropy_registry.build_entropy_bundle", lambda payload: payload)
    monkeypatch.setattr("src.sync_entropy_registry.EntropyImporter", lambda: FakeImporter())

    rows = build_entropy_source_registry_rows("run-123", schema_map)

    assert rows[0]["target_table"] == "cd_baz_bdclientes.cd_target"
    assert rows[0]["include_in_entropy"] is True
    assert rows[1]["source_schema_type"] == "TEMPORAL"
    assert rows[1]["include_in_entropy"] is False
