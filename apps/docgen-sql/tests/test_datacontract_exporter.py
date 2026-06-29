import sqlite3

import pytest
import yaml

from src.config import load_project_config
from src.datacontract_exporter import build_datacontract, export_datacontract
from src.sql_parser import parse_sql_file


CONFIG_PATH = "config/cd_cap_portafolio_cuentas_activas.yml"
SQL_PATH = "input/sql/02_cd_cap_portafolio_cuentas_activas/06_cd_cap_portafolio_cuentas_activas.sql"


def test_build_datacontract_uses_analysis_and_tabular_profile():
    config = load_project_config(CONFIG_PATH)
    analysis = parse_sql_file(SQL_PATH, config)
    profile = {
        "database": "/tmp/mvp.sqlite",
        "engine": "sqlite",
        "table": "cd_cap_portafolio_cuentas_activas",
        "sample_size": 2,
        "fields": {
            "id_cuenta": {
                "physical_type": "TEXT",
                "logical_type": "string",
                "required": True,
                "example": "00012345",
            }
        },
    }

    contract = build_datacontract(analysis, config, profile)
    schema = contract["schema"][0]
    fields = {item["name"]: item for item in schema["properties"]}

    assert contract["apiVersion"] == "v3.1.0"
    assert contract["kind"] == "DataContract"
    assert "customProperties" not in contract
    assert "servers" not in contract
    assert schema["name"] == "cd_cap_portafolio_cuentas_activas"
    assert fields["id_cuenta"]["logicalType"] == "string"
    assert fields["id_cuenta"]["required"] is True
    assert fields["id_cuenta"]["examples"] == ["00012345"]
    assert "customProperties" not in fields["id_cuenta"]
    assert "partitioned" not in fields["id_cuenta"]


def test_export_datacontract_profiles_matching_sqlite_table(tmp_path):
    db_path = tmp_path / "mvp.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE cd_cap_portafolio_cuentas_activas (
                id_cuenta TEXT NOT NULL,
                sld_actual REAL,
                id_cliente INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cd_cap_portafolio_cuentas_activas (id_cuenta, sld_actual, id_cliente)
            VALUES ('ABC001', 1520.45, 99)
            """
        )
        connection.commit()

    output_path = tmp_path / "contract.yaml"
    result = export_datacontract(
        sql_path=SQL_PATH,
        config_path=CONFIG_PATH,
        output_path=output_path,
        sqlite_path=db_path,
        sqlite_table="cd_cap_portafolio_cuentas_activas",
    )

    contract = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert result["sqlite_table"] == "cd_cap_portafolio_cuentas_activas"
    assert result["format"] == "odcs"
    assert fields["id_cuenta"]["physicalType"] == "STRING"
    assert fields["id_cuenta"]["required"] is True
    assert fields["id_cuenta"]["examples"] == ["ABC001"]


def test_export_datacontract_profiles_matching_duckdb_table(tmp_path):
    duckdb = pytest.importorskip("duckdb")

    db_path = tmp_path / "mvp.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE cd_cap_portafolio_cuentas_activas (
                id_cuenta VARCHAR NOT NULL,
                sld_actual DOUBLE,
                id_cliente BIGINT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cd_cap_portafolio_cuentas_activas (id_cuenta, sld_actual, id_cliente)
            VALUES ('DUCK001', 1520.45, 99)
            """
        )

    output_path = tmp_path / "contract_duckdb.yaml"
    result = export_datacontract(
        sql_path=SQL_PATH,
        config_path=CONFIG_PATH,
        output_path=output_path,
        profile_path=db_path,
        profile_table="cd_cap_portafolio_cuentas_activas",
        profile_engine="duckdb",
    )

    contract = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert result["profile_engine"] == "duckdb"
    assert result["profile_table"] == "cd_cap_portafolio_cuentas_activas"
    assert result["ddl_path"].endswith("input/ddl/cd_cap_portafolio_cuentas_activas.txt")
    assert fields["id_cuenta"]["physicalType"] == "STRING"
    assert fields["id_cuenta"]["required"] is True
    assert fields["id_cuenta"]["examples"] == ["DUCK001"]


def test_export_datacontract_prefers_ddl_physical_type_and_keeps_duckdb_examples(tmp_path):
    duckdb = pytest.importorskip("duckdb")

    db_path = tmp_path / "mvp.duckdb"
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            """
            CREATE TABLE cd_cap_portafolio_cuentas_activas (
                id_cuenta VARCHAR NOT NULL,
                sld_actual DOUBLE,
                id_cliente BIGINT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO cd_cap_portafolio_cuentas_activas (id_cuenta, sld_actual, id_cliente)
            VALUES ('DUCKDDL001', 1520.45, 99)
            """
        )

    ddl_path = tmp_path / "ddl.txt"
    ddl_path.write_text(
        """
        CREATE TABLE demo.cd_cap_portafolio_cuentas_activas (
          id_cuenta STRING,
          sld_actual DECIMAL(18,2),
          id_cliente BIGINT
        )
        STORED AS PARQUET;
        """,
        encoding="utf-8",
    )

    output_path = tmp_path / "contract_duckdb_ddl.yaml"
    export_datacontract(
        sql_path=SQL_PATH,
        config_path=CONFIG_PATH,
        output_path=output_path,
        profile_path=db_path,
        profile_table="cd_cap_portafolio_cuentas_activas",
        profile_engine="duckdb",
        ddl_path=ddl_path,
    )

    contract = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert fields["id_cuenta"]["physicalType"] == "STRING"
    assert fields["sld_actual"]["physicalType"] == "DECIMAL(18,2)"
    assert fields["id_cuenta"]["examples"] == ["DUCKDDL001"]


def test_export_datacontract_uses_impala_ddl_and_csv_for_cli_local_server(tmp_path):
    ddl_path = tmp_path / "ddl.txt"
    ddl_path.write_text(
        """
        CREATE TABLE demo.contract_table (
          id_cuenta STRING,
          fec_carga TIMESTAMP,
          sld_actual DECIMAL(32,2)
        )
        PARTITIONED BY (
          cod_titular STRING
        )
        STORED AS PARQUET;
        """,
        encoding="utf-8",
    )

    csv_path = tmp_path / "contract.csv"
    csv_path.write_text(
        "id_cuenta,fec_carga,sld_actual,cod_titular\nABC001,2026-04-24 20:13:24,2421.12,T\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "contract.odcs.yaml"
    export_datacontract(
        sql_path=SQL_PATH,
        config_path=CONFIG_PATH,
        output_path=output_path,
        ddl_path=ddl_path,
        csv_path=csv_path,
    )

    contract = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert contract["servers"][0]["type"] == "local"
    assert contract["servers"][0]["format"] == "csv"
    assert contract["servers"][0]["path"] == str(csv_path)
    assert fields["id_cuenta"]["physicalType"] == "STRING"
    assert fields["fec_carga"]["logicalType"] == "timestamp"
    assert fields["id_cuenta"]["examples"] == ["ABC001"]
    assert "customProperties" not in fields["id_cuenta"]


def test_partition_flags_only_exist_for_partition_columns(tmp_path):
    ddl_path = tmp_path / "ddl.txt"
    ddl_path.write_text(
        """
        CREATE TABLE demo.contract_table (
          id_cuenta STRING,
          fec_carga TIMESTAMP
        )
        PARTITIONED BY (
          cod_titular STRING
        )
        STORED AS PARQUET;
        """,
        encoding="utf-8",
    )

    output_path = tmp_path / "contract.odcs.yaml"
    export_datacontract(
        sql_path=SQL_PATH,
        config_path=CONFIG_PATH,
        output_path=output_path,
        ddl_path=ddl_path,
    )

    contract = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert "partitioned" not in fields["id_cuenta"]
    assert fields["cod_titular"]["partitioned"] is True
    assert fields["cod_titular"]["partitionKeyPosition"] == 1


def test_build_datacontract_uses_dictionary_markdown_descriptions():
    config = load_project_config(CONFIG_PATH)
    analysis = parse_sql_file(SQL_PATH, config)

    dictionary_profile = {
        "path": "input/diccionario/cd_cap_portafolio_cuentas_activas.txt",
        "table_name": "cd_cap_portafolio_cuentas_activas",
        "table_description": None,
        "fields": {
            "id_cuenta": {
                "business_name": "Id Cuenta",
                "description": "Número de cuenta a 14 posiciones",
            },
            "cod_tipo_persona": {
                "business_name": "Cod Tipo Persona",
                "description": "Código para identifica si la cuenta está asociada a una persona física o moral: Valores PF, PM",
            },
        },
    }

    contract = build_datacontract(
        analysis,
        config,
        dictionary_profile=dictionary_profile,
    )
    fields = {item["name"]: item for item in contract["schema"][0]["properties"]}

    assert fields["id_cuenta"]["description"] == "Número de cuenta a 14 posiciones"
    assert fields["cod_tipo_persona"]["description"].startswith("Código para identifica")
    assert "customProperties" not in contract


def test_resolve_table_sidecars_from_conventional_name(tmp_path, monkeypatch):
    from src import datacontract_exporter as exporter

    ddl_dir = tmp_path / "ddl"
    dict_dir = tmp_path / "diccionario"
    ddl_dir.mkdir()
    dict_dir.mkdir()
    (ddl_dir / "mi_tabla.txt").write_text("CREATE TABLE demo.mi_tabla (id STRING);", encoding="utf-8")
    (dict_dir / "mi_tabla.txt").write_text("| Nombre | Descripción |\n| --- | --- |\n| id | Identificador |\n", encoding="utf-8")

    assert exporter._resolve_table_sidecar_path("demo.mi_tabla", ddl_dir) == str(ddl_dir / "mi_tabla.txt")
    assert exporter._resolve_table_sidecar_path("demo.mi_tabla", dict_dir) == str(dict_dir / "mi_tabla.txt")
