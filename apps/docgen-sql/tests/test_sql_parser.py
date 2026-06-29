from src.models import ProjectConfig
from src.sql_parser import get_column_lineage, parse_sql_file


def _demo_config() -> ProjectConfig:
    return ProjectConfig(
        producto_funcional="demo",
        frecuencia="Diario",
        tabla_final_pipeline="demo.tabla_salida",
        prefijo_archivo="DA_REQ_CD_IT_",
        variables={
            "${esquema_cu}": "ws_ec_cu_baz_bdclientes",
            "${esquema_cd}": "ws_ec_cd_baz_bdclientes",
            "${esquema_rd}": "rd_baz_bdclientes",
        },
        template="input/templates/DA_REQ_CD_IT_plantilla.docx",
    )


def test_parse_sql_extracts_core_artifacts():
    analysis = parse_sql_file("input/sql/02_cd_cap_portafolio_cuentas_activas/02_detalle_cuenta_alnova.sql", _demo_config())

    assert analysis.target_table == "ws_ec_cu_baz_bdclientes.cu_cap_universo_cuentas"
    assert analysis.compute_stats_tables == ["ws_ec_cu_baz_bdclientes.cu_cap_universo_cuentas"]
    assert analysis.transformations
    assert any(item.field_name == "id_cuenta" for item in analysis.transformations)
    assert any(join.join_type == "LEFT ANTI" for join in analysis.joins)
    assert not analysis.unresolved_variables
    assert analysis.metadata["parse_archetype"] == "insert_overwrite_curated_table_with_enrichment_with_preparation_layers"
    assert "id_cuenta" in analysis.column_lineage
    assert analysis.column_lineage["id_cuenta"].functions == ["CONCAT"]
    assert any(
        source.base_table == "rd_baz_bdclientes.rd_pedt008" and source.source_column == "num_account"
        for source in analysis.column_lineage["id_cuenta"].physical_sources
    )


def test_insert_overwrite_detects_target_table():
    analysis = parse_sql_file("input/sql/02_cd_cap_portafolio_cuentas_activas/01_finacle_saldos_decrypt.sql", _demo_config())

    assert analysis.target_table == "ws_ec_cu_baz_bdclientes.cu_finacle_saldos_decrypt"


def test_final_select_detects_all_output_fields():
    analysis = parse_sql_file("input/sql/02_cd_cap_portafolio_cuentas_activas/01_finacle_saldos_decrypt.sql", _demo_config())

    expected_fields = {
        "id_cliente",
        "id_cuenta",
        "cta_encrypt",
        "fechaapertura",
        "fechacancelacion",
        "centrocontable",
        "fechaultimomovimiento",
        "personalidad",
        "estatuscuenta",
        "moneda",
        "saldototal",
        "saldodisponible",
        "plazodeposito",
        "producto",
    }
    parsed_fields = {item.field_name for item in analysis.transformations}

    assert parsed_fields == expected_fields


def test_get_column_lineage_resolves_direct_and_derived_sources():
    analysis = parse_sql_file("input/sql/02_cd_cap_portafolio_cuentas_activas/02_detalle_cuenta_alnova.sql", _demo_config())
    lineage = analysis.column_lineage

    assert "ID_CUENTA" not in lineage
    assert lineage["id_cuenta"].display_name == "ID_CUENTA"
    assert lineage["id_sucursal_apertura"].lineage_type == "direct"
    assert lineage["id_sucursal_apertura"].physical_sources[0].base_table == "rd_baz_bdclientes.rd_pedt008"
    assert lineage["id_cuenta"].lineage_type == "derived"
    assert {item.source_column for item in lineage["id_cuenta"].physical_sources} >= {"brn_open", "cod_prodserv", "num_account"}


def test_used_in_steps_is_derived_from_ast_and_lineage():
    analysis = parse_sql_file("input/sql/02_cd_cap_portafolio_cuentas_activas/02_detalle_cuenta_alnova.sql", _demo_config())
    sources = {source.alias: source for source in analysis.sources}

    assert sources["cta"].used_in_steps == ["Paso 1", "Paso 2", "Paso 3", "Paso 4", "Paso 5", "Paso 6"]
    assert sources["ctainf"].used_in_steps == ["Paso 1", "Paso 3", "Paso 5", "Paso 6"]
    assert sources["fechas"].used_in_steps == ["Paso 3", "Paso 5", "Paso 6"]
    assert sources["fin"].used_in_steps == ["Paso 3"]


def test_create_table_as_select_detects_target_table(tmp_path):
    sql_path = tmp_path / "ctas.sql"
    sql_path.write_text(
        "\n".join(
            [
                "CREATE TABLE ${esquema_cu}.demo_salida STORED AS PARQUET AS",
                "SELECT 1 AS id, 'demo' AS tipo",
            ]
        ),
        encoding="utf-8",
    )

    analysis = parse_sql_file(sql_path, _demo_config())

    assert analysis.target_table == "ws_ec_cu_baz_bdclientes.demo_salida"
    assert analysis.metadata["statement_type"] == "create_table_as_select"
    assert analysis.metadata["parse_archetype"] == "create_table_as_select_published_table"


def test_multiple_publications_are_captured_in_analysis():
    analysis = parse_sql_file("input/sql/02_cd_cap_portafolio_cuentas_activas/04_saldo_disponible_ctas.sql", _demo_config())

    assert [item.target_table for item in analysis.publications] == [
        "ws_ec_cu_baz_bdclientes.cu_cap_saldos_disponibles_ctas",
    ]
    assert analysis.publications[0].role == "final"


def test_coalesce_lineage_expands_ctes_and_union_sources():
    analysis = parse_sql_file(
        "input/sql/01_cd_cap_relacion_cliente/02_relacion_clientes.sql",
        _demo_config(),
    )

    id_master = next(item for item in analysis.transformations if item.field_name == "id_master")

    assert analysis.ctes == [
        "_id_master_alnova_",
        "_id_master_finacle_",
        "_id_master_cu_",
        "_id_master_icu_",
    ]
    assert "cd_baz_bdclientes.cd_cte_master_diaria.id_master" in id_master.physical_source_fields
    assert "ws_ec_cu_baz_bdclientes.cu_cap_relacion_cliente_finacle.id_cliente_finacle" in id_master.physical_source_fields
    assert "ws_ec_cu_baz_bdclientes.cu_cap_relacion_cliente_alnova.id_cliente_alnova" in id_master.physical_source_fields
    assert any(
        "CTE _id_master_alnova_" in rule.description and "menor valor de id_master" in rule.description
        for rule in analysis.rules
    )
    assert any(
        rule.applies_in == "Paso 1" and "id_cliente" in rule.description
        for rule in analysis.rules
    )
    step_2 = next(step for step in analysis.steps if step.number == 2)
    assert step_2.title == "Lectura y consolidacion de fuente base"
    assert "ws_ec_cu_baz_bdclientes.cu_cap_relacion_cliente_finacle" in step_2.tables_involved
    assert "ws_ec_cu_baz_bdclientes.cu_cap_relacion_cliente_alnova" in step_2.tables_involved
    assert step_2.join_type == ["UNION ALL"]
    assert any("se apilan los registros" in item.lower() for item in step_2.join_criteria)
    assert any("conserva todos los registros" in item.lower() for item in step_2.meaning)


def test_cte_source_name_is_functional_and_not_embedded_sql():
    analysis = parse_sql_file(
        "input/sql/01_cd_cap_relacion_cliente/02_relacion_clientes.sql",
        _demo_config(),
    )

    cte_source = next(source for source in analysis.sources if source.alias == "_id_master_alnova_")

    assert cte_source.table_name.startswith("CTE _id_master_alnova_")
    assert "SELECT" not in cte_source.table_name.upper()
    assert "cd_baz_bdclientes.cd_cte_master_diaria" in cte_source.table_name


def test_compute_stats_statements_are_ignored_for_main_parse(tmp_path):
    sql_path = tmp_path / "with_stats.sql"
    sql_path.write_text(
        "\n".join(
            [
                "INSERT OVERWRITE TABLE ${esquema_cu}.demo_salida",
                "SELECT id, nombre FROM ${esquema_rd}.demo_fuente",
                ";",
                "",
                "COMPUTE STATS ${esquema_cu}.demo_salida",
                ";",
            ]
        ),
        encoding="utf-8",
    )

    analysis = parse_sql_file(sql_path, _demo_config())

    assert analysis.target_table == "ws_ec_cu_baz_bdclientes.demo_salida"
    assert analysis.compute_stats_tables == ["ws_ec_cu_baz_bdclientes.demo_salida"]
    assert analysis.metadata["ignored_compute_stats_count"] == 1
    assert {item.field_name for item in analysis.transformations} == {"id", "nombre"}


def test_union_query_keeps_transformations_and_source_context(tmp_path):
    sql_path = tmp_path / "union_publish.sql"
    sql_path.write_text(
        "\n".join(
            [
                "INSERT OVERWRITE TABLE ${esquema_cu}.demo_union",
                "SELECT id, nombre, 0 AS bandera FROM ${esquema_cu}.fuente_a",
                "UNION",
                "SELECT id, nombre, 1 AS bandera FROM ${esquema_cu}.fuente_b",
                ";",
            ]
        ),
        encoding="utf-8",
    )

    analysis = parse_sql_file(sql_path, _demo_config())

    assert [item.field_name for item in analysis.transformations] == ["id", "nombre", "bandera"]
    assert {source.table_name for source in analysis.sources} == {
        "ws_ec_cu_baz_bdclientes.fuente_a",
        "ws_ec_cu_baz_bdclientes.fuente_b",
    }
    step_2 = next(step for step in analysis.steps if step.number == 2)
    assert step_2.title == "Lectura y consolidacion de fuente base"
    assert step_2.join_type == ["UNION"]
    assert "ws_ec_cu_baz_bdclientes.fuente_a" in step_2.tables_involved
    assert "ws_ec_cu_baz_bdclientes.fuente_b" in step_2.tables_involved
