import json
import subprocess
from pathlib import Path

import yaml

from src.sync_modules import extract_header_metadata, sync_module_from_sql


def test_extract_header_metadata_reads_archivo_and_descripcion():
    sql = "\n".join(
        [
            "--| @ARCHIVO: Detalle cuenta ALNOVA",
            "--| @DESCRIPCION:",
            "--|     # Construir universo curado de cuentas",
        ]
    )

    metadata = extract_header_metadata(sql)

    assert metadata["ARCHIVO"] == "Detalle cuenta ALNOVA"
    assert metadata["DESCRIPCION"] == "Construir universo curado de cuentas"


def test_sync_module_from_sql_prompts_if_descripcion_is_empty(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_path = tmp_path / "02_detalle_cuenta_alnova.sql"
    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.tabla"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables: {}",
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "flujo:",
                "  tipo_documentacion: modular",
                "  documento_principal:",
                '    nombre: "Documentacion Funcional Estructural"',
                '    template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "  modulos: []",
            ]
        ),
        encoding="utf-8",
    )
    sql_path.write_text(
        "\n".join(
            [
                "--| @ARCHIVO: Detalle cuenta ALNOVA",
                "--| @DESCRIPCION:",
                "INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_universo_cuentas",
            ]
        ),
        encoding="utf-8",
    )

    result = sync_module_from_sql(
        sql_path,
        config_path=config_path,
        prompt_for_values=True,
        input_fn=lambda _: "Construir el universo curado de cuentas ALNOVA",
    )
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    module = config_data["flujo"]["modulos"][0]

    assert result["module_id"] == "paso_02_detalle_cuenta_alnova"
    assert module["nombre"] == "Detalle cuenta ALNOVA"
    assert module["intencion"] == "Construir el universo curado de cuentas ALNOVA"
    assert module["salida_tablas"] == ["${esquema_cu}.cu_cap_universo_cuentas"]


def test_sync_modules_cli_for_single_sql(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_path = tmp_path / "02_detalle_cuenta_alnova.sql"
    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.tabla"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables: {}",
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "flujo:",
                "  tipo_documentacion: modular",
                "  documento_principal:",
                '    nombre: "Documentacion Funcional Estructural"',
                '    template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "  modulos: []",
            ]
        ),
        encoding="utf-8",
    )
    sql_path.write_text(
        "\n".join(
            [
                "--| @ARCHIVO: Detalle cuenta ALNOVA",
                "--| @DESCRIPCION: Universo curado de cuentas",
                "INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_universo_cuentas",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.sync_modules",
            "--sql",
            str(sql_path),
            "--config",
            str(config_path),
            "--no-prompt",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["nombre"] == "Detalle cuenta ALNOVA"
    assert payload["intencion"] == "Universo curado de cuentas"


def test_sync_module_marks_principal_when_output_matches_final_table(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_path = tmp_path / "06_final.sql"
    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.salida_final"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables: {}",
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "flujo:",
                "  tipo_documentacion: modular",
                "  documento_principal:",
                '    nombre: "Documentacion Funcional Estructural"',
                '    template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "  modulos: []",
            ]
        ),
        encoding="utf-8",
    )
    sql_path.write_text(
        "\n".join(
            [
                "--| @ARCHIVO: Final",
                "--| @DESCRIPCION: Publicar salida final",
                "INSERT OVERWRITE TABLE demo.salida_final",
                "SELECT 1 AS id",
            ]
        ),
        encoding="utf-8",
    )

    sync_module_from_sql(sql_path, config_path=config_path, prompt_for_values=False)
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    module = config_data["flujo"]["modulos"][0]

    assert module["es_principal"] is True


def test_sync_module_collects_multiple_output_tables(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_path = tmp_path / "04_multi.sql"
    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.final"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables: {}",
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "flujo:",
                "  tipo_documentacion: modular",
                "  documento_principal:",
                '    nombre: "Documentacion Funcional Estructural"',
                '    template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "  modulos: []",
            ]
        ),
        encoding="utf-8",
    )
    sql_path.write_text(
        "\n".join(
            [
                "--| @ARCHIVO: Multi",
                "--| @DESCRIPCION: Publica dos tablas",
                "CREATE TABLE demo.prev STORED AS PARQUET AS SELECT 1 AS id;",
                "INSERT OVERWRITE TABLE demo.final SELECT id FROM demo.prev;",
            ]
        ),
        encoding="utf-8",
    )

    sync_module_from_sql(sql_path, config_path=config_path, prompt_for_values=False)
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    module = config_data["flujo"]["modulos"][0]

    assert module["salida_tablas"] == ["demo.prev", "demo.final"]
