from pathlib import Path

import pytest
import yaml

from src.web_models import WebGenerationRequest, WebOutputTableInput, WebSqlFileInput, WebVariableInput
from src.web_service import execute_web_generation, preview_request


SQL_PATH = Path("input/sql/02_cd_cap_portafolio_cuentas_activas/06_cd_cap_portafolio_cuentas_activas.sql")


def test_preview_request_counts_payload_sections():
    request = WebGenerationRequest(
        sql_text="select 1 as demo",
        product_name="Producto demo",
        final_table_name="demo.tabla",
        variables=[WebVariableInput(name="${fecha}", value="2026-04-30")],
        output_tables=[WebOutputTableInput(table="demo.tabla", description="Salida final")],
        quick_reference=["No carga historico"],
        ddl_text="CREATE TABLE demo.tabla (id STRING);",
    )

    preview = preview_request(request)

    assert preview["variable_count"] == 1
    assert preview["output_table_count"] == 1
    assert preview["quick_reference_count"] == 1
    assert preview["has_ddl"] is True
    assert preview["has_dictionary"] is False


def test_execute_web_generation_creates_artifacts(monkeypatch, tmp_path):
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")

    request = WebGenerationRequest(
        sql_text=SQL_PATH.read_text(encoding="utf-8"),
        sql_file_name="06_cd_cap_portafolio_cuentas_activas.sql",
        product_name="Portafolio demo web",
        frequency="Diario",
        final_table_name="ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas",
        variables=[
            WebVariableInput(name="${dia_fec_ini_sem}", value="2026-05-03"),
            WebVariableInput(name="${esquema_cd}", value="wc_ec_cd_baz_bdclientes"),
            WebVariableInput(name="${esquema_cu}", value="ws_ec_cu_baz_bdclientes"),
            WebVariableInput(name="${fec_ini_sem}", value="2026-04-27"),
            WebVariableInput(name="${num_periodo_2_sem_atras}", value="202615"),
            WebVariableInput(name="${num_periodo_mes}", value="202604"),
        ],
        output_tables=[
            WebOutputTableInput(
                table="ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas",
                description="Tabla final generada desde la prueba web",
            )
        ],
        quick_reference=["No sustituye reglas no visibles en el SQL"],
        dictionary_text="| Nombre | Descripcion |\n| --- | --- |\n| id_cuenta | Numero de cuenta |\n",
        csv_sample_text="id_cuenta\nABC001\n",
    )

    response = execute_web_generation(request)

    assert response.mode == "structural"
    assert Path(response.output_dir).exists()
    assert Path(response.generated_files["analysis_json"]).exists()
    assert Path(response.generated_files["document_docx"]).exists()
    assert Path(response.generated_files["audit_xlsx"]).exists()
    assert Path(response.generated_files["audit_json"]).exists()
    assert Path(response.generated_files["datacontract_yaml"]).exists()
    assert Path(response.generated_files["datacontract_yaml"]).name == "ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas.odcs.yaml"
    assert response.pipeline_graph["relations"]
    assert response.pipeline_graph["mermaid"]
    assert response.stats["target_table"].endswith(".cd_cap_portafolio_cuentas_activas")


def test_execute_web_generation_creates_step_artifacts_for_uploaded_sequence(monkeypatch, tmp_path):
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")

    sql_text = SQL_PATH.read_text(encoding="utf-8")
    request = WebGenerationRequest(
        sql_text=sql_text,
        sql_file_name="06_cd_cap_portafolio_cuentas_activas.sql",
        sql_files=[
            WebSqlFileInput(
                sql_file_name="01_relacion_clientes_alnova.sql",
                sql_text=sql_text,
                is_step=True,
            ),
            WebSqlFileInput(
                sql_file_name="02_relacion_clientes_finacle.sql",
                sql_text=sql_text,
                is_step=True,
            ),
            WebSqlFileInput(
                sql_file_name="03_relacion_clientes.sql",
                sql_text=sql_text,
                is_step=False,
            ),
        ],
        product_name="Portafolio demo web",
        frequency="Diario",
        final_table_name="ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas",
        variables=[
            WebVariableInput(name="${dia_fec_ini_sem}", value="2026-05-03"),
            WebVariableInput(name="${esquema_cd}", value="wc_ec_cd_baz_bdclientes"),
            WebVariableInput(name="${esquema_cu}", value="ws_ec_cu_baz_bdclientes"),
            WebVariableInput(name="${fec_ini_sem}", value="2026-04-27"),
            WebVariableInput(name="${num_periodo_2_sem_atras}", value="202615"),
            WebVariableInput(name="${num_periodo_mes}", value="202604"),
        ],
        quick_reference=["No sustituye reglas no visibles en el SQL"],
    )

    response = execute_web_generation(request)

    assert Path(response.generated_files["document_docx"]).name.endswith("03_relacion_clientes.docx")
    assert Path(response.generated_files["step_docx__01_relacion_clientes_alnova"]).exists()
    assert Path(response.generated_files["step_docx__02_relacion_clientes_finacle"]).exists()
    assert response.stats["sql_files_uploaded"] == 3
    assert response.stats["step_documents_generated"] == 2


def test_execute_web_generation_uses_final_table_name_for_duckdb_examples_and_ddl_for_physical_type(monkeypatch, tmp_path):
    duckdb = pytest.importorskip("duckdb")
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")

    db_path = tmp_path / "profiles.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE cd_cap_portafolio_cuentas_activas (
                id_cuenta VARCHAR NOT NULL,
                sld_actual DOUBLE
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cd_cap_portafolio_cuentas_activas (id_cuenta, sld_actual)
            VALUES ('WEBDUCK001', 1520.45)
            """
        )

    ddl_text = """
    CREATE TABLE demo.cd_cap_portafolio_cuentas_activas (
      id_cuenta STRING,
      sld_actual DECIMAL(18,2)
    )
    STORED AS PARQUET;
    """

    request = WebGenerationRequest(
        sql_text=SQL_PATH.read_text(encoding="utf-8"),
        sql_file_name="06_cd_cap_portafolio_cuentas_activas.sql",
        product_name="Portafolio demo web",
        frequency="Diario",
        final_table_name="demo.cd_cap_portafolio_cuentas_activas",
        profile_db_path=str(db_path),
        profile_engine="duckdb",
        ddl_text=ddl_text,
    )

    response = execute_web_generation(request)

    contract = yaml.safe_load(Path(response.generated_files["datacontract_yaml"]).read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert fields["id_cuenta"]["physicalType"] == "STRING"
    assert fields["sld_actual"]["physicalType"] == "DECIMAL(18,2)"
    assert fields["id_cuenta"]["examples"] == ["WEBDUCK001"]


def test_execute_web_generation_falls_back_to_home_schema_db_for_duckdb_examples(monkeypatch, tmp_path):
    duckdb = pytest.importorskip("duckdb")
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")
    monkeypatch.setattr(web_service, "DEFAULT_DUCKDB_PATH", tmp_path / "missing.duckdb")
    monkeypatch.setattr(web_service.Path, "home", staticmethod(lambda: tmp_path))

    db_path = tmp_path / "cd_baz_bdclientes.db"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE cd_cap_relacion_cliente (
                id_master BIGINT,
                id_cliente_alnova VARCHAR
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cd_cap_relacion_cliente (id_master, id_cliente_alnova)
            VALUES (123, 'ALNOVA001')
            """
        )

    request = WebGenerationRequest(
        sql_text=Path("input/sql/01_cd_cap_relacion_cliente/02_relacion_clientes.sql").read_text(encoding="utf-8"),
        sql_file_name="03_relacion_clientes.sql",
        product_name="Relacion clientes",
        frequency="Diario",
        final_table_name="cd_baz_bdclientes.cd_cap_relacion_cliente",
        profile_engine="duckdb",
        ddl_text="""
        CREATE TABLE demo.cd_cap_relacion_cliente (
          id_master BIGINT,
          id_cliente_alnova STRING
        ) STORED AS PARQUET;
        """,
    )

    response = execute_web_generation(request)

    contract = yaml.safe_load(Path(response.generated_files["datacontract_yaml"]).read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert fields["id_master"]["examples"] == [123]
    assert fields["id_cliente_alnova"]["examples"] == ["ALNOVA001"]


def test_execute_web_generation_keeps_working_when_supabase_is_disabled(monkeypatch, tmp_path):
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")

    request = WebGenerationRequest(
        sql_text=SQL_PATH.read_text(encoding="utf-8"),
        sql_file_name="06_cd_cap_portafolio_cuentas_activas.sql",
        product_name="Portafolio demo web",
        frequency="Diario",
        final_table_name="ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas",
    )

    response = execute_web_generation(request)

    assert response.stats["supabase_persisted"] is False


def test_execute_web_generation_persists_principal_and_step_modules(monkeypatch, tmp_path):
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")

    captured = {}

    class FakeRepository:
        def __init__(self, settings):
            self.settings = settings

        def is_enabled(self):
            return True

        def persist_run(
            self,
            run_id,
            request_payload,
            response_payload,
            analysis,
            audit,
            odcs_yaml_text,
            config_snapshot,
            module_results,
            pipeline_graph,
            workspace_inventory,
        ):
            captured["run_id"] = run_id
            captured["module_results"] = module_results
            captured["pipeline_graph"] = pipeline_graph
            captured["workspace_inventory"] = workspace_inventory
            return {}

    monkeypatch.setattr(web_service, "SupabaseRunRepository", FakeRepository)
    monkeypatch.setattr(web_service, "load_supabase_settings", lambda: object())

    sql_text = SQL_PATH.read_text(encoding="utf-8")
    request = WebGenerationRequest(
        sql_text=sql_text,
        sql_file_name="03_relacion_clientes.sql",
        sql_files=[
            WebSqlFileInput(
                sql_file_name="01_relacion_clientes_alnova.sql",
                sql_text=sql_text,
                is_step=True,
            ),
            WebSqlFileInput(
                sql_file_name="02_relacion_clientes_finacle.sql",
                sql_text=sql_text,
                is_step=True,
            ),
            WebSqlFileInput(
                sql_file_name="03_relacion_clientes.sql",
                sql_text=sql_text,
                is_step=False,
            ),
        ],
        product_name="Relacion clientes",
        frequency="Diario",
        final_table_name="demo.cd_cap_relacion_cliente",
    )

    response = execute_web_generation(request)

    assert response.stats["supabase_persisted"] is True
    assert captured["run_id"] == response.run_id
    assert [item["sql_file_name"] for item in captured["module_results"]] == [
        "03_relacion_clientes.sql",
        "01_relacion_clientes_alnova.sql",
        "02_relacion_clientes_finacle.sql",
    ]
    assert captured["module_results"][0]["is_principal"] is True
    assert captured["module_results"][0]["is_step"] is False
    assert captured["module_results"][1]["is_step"] is True
    assert captured["module_results"][2]["is_step"] is True
    assert captured["pipeline_graph"]["mermaid"]
    assert any(item["relative_path"] == "config.yml" for item in captured["workspace_inventory"])
    assert any(item["file_category"] == "sql" for item in captured["workspace_inventory"])
    assert all("local_path" not in item for item in response.workspace_inventory)


def test_execute_web_generation_returns_workspace_inventory_without_zip(monkeypatch, tmp_path):
    from src import web_service

    monkeypatch.setattr(web_service, "WEB_RUNS_ROOT", tmp_path / "web_runs")

    request = WebGenerationRequest(
        sql_text=SQL_PATH.read_text(encoding="utf-8"),
        sql_file_name="06_cd_cap_portafolio_cuentas_activas.sql",
        product_name="Portafolio demo web",
        frequency="Diario",
        final_table_name="ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas",
    )

    response = execute_web_generation(request)

    assert "workspace_zip" not in response.generated_files
    assert any(item["relative_path"] == "config.yml" for item in response.workspace_inventory)
