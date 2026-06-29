from src.config import resolve_variables
from src.config import load_project_config, resolve_config_path

CONFIG_PATH = "config/cd_cap_portafolio_cuentas_activas.yml"


def test_resolve_variables_from_config_and_date_fallback():
    sql = (
        "select * from ${esquema_cu}.tabla_cu "
        "join ${esquema_cd}.tabla_cd on 1=1 "
        "where fecha = '${fec_ini_sem}' and x = ${faltante};"
    )
    result = resolve_variables(
        sql,
        {
            "${esquema_cu}": "ws_ec_cu_bdclientes",
            "${esquema_cd}": "ws_ec_cd_bdclientes",
        },
    )

    assert "ws_ec_cu_bdclientes.tabla" in result.resolved_sql
    assert "ws_ec_cd_bdclientes.tabla_cd" in result.resolved_sql
    assert "${fec_ini_sem}" not in result.resolved_sql
    assert "${faltante}" in result.unresolved_variables
    assert "var_faltante" in result.masked_sql


def test_load_project_config_supports_section_one_schema():
    config = load_project_config(CONFIG_PATH)

    assert config.seccion_1.ficha_producto.dominio == "Captacion"
    assert config.seccion_1.ficha_producto.responsable == "Equipo de datos de Captacion"
    assert config.seccion_1.tablas_salida[0].tabla == "ws_ec_cd_bdclientes.cd_cap_portafolio_cuentas_activas"
    assert isinstance(config.seccion_1.referencia_rapida.que_no_hace, list)


def test_load_project_config_supports_flujo_modulos_schema():
    config = load_project_config(CONFIG_PATH)
    modules = {module.id: module for module in config.flujo.modulos}

    assert config.flujo.tipo_documentacion == "modular"
    assert config.flujo.documento_principal.nombre == "Documentacion Funcional Estructural"
    assert len(config.flujo.modulos) >= 1
    assert all(module.id for module in config.flujo.modulos)
    assert all(isinstance(module.depende_de, list) for module in config.flujo.modulos)
    assert all(isinstance(module.salida_tablas, list) for module in config.flujo.modulos)
    assert set(modules) == {module.id for module in config.flujo.modulos}


def test_resolve_config_path_supports_bare_filename():
    resolved = resolve_config_path("cd_cap_portafolio_cuentas_activas.yml")

    assert resolved.name == "cd_cap_portafolio_cuentas_activas.yml"
    assert resolved.parent.name == "config"
