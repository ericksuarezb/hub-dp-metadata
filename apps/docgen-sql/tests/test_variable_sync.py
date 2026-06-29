from pathlib import Path
import json
import subprocess

import yaml

from src.config import extract_variable_tokens, replace_sql_parameters_block
from src.sync_variables import (
    replace_sql_parameters_block_with_values,
    sync_directory_variables,
    sync_variables_with_project,
    update_yaml_variables_block,
)


def test_extract_variable_tokens_finds_standard_tokens():
    sql = "select * from ${esquema_cu}.tabla where fecha = '${fec_ini_sem}' and base = ${esquema_cd}.x"

    result = extract_variable_tokens(sql)

    assert result == ["${esquema_cd}", "${esquema_cu}", "${fec_ini_sem}"]


def test_replace_sql_parameters_block_writes_all_variables():
    sql = "\n".join(
        [
            "--| @PARAMETROS",
            "--|     #",
            "--\\__________________________________________________________________________________________________/",
            "select * from dual",
        ]
    )

    updated = replace_sql_parameters_block(sql, ["${esquema_cu}", "${fec_ini_sem}"])

    assert "--|     # ${esquema_cu}" in updated
    assert "--|     # ${fec_ini_sem}" in updated
    assert "--\\__________________________________________________________________________________________________/" in updated


def test_replace_sql_parameters_block_with_values_writes_reference_values():
    sql = "\n".join(
        [
            "--| @PARAMETROS",
            "--|     #",
            "--\\__________________________________________________________________________________________________/",
            "select * from dual",
        ]
    )

    updated = replace_sql_parameters_block_with_values(
        sql,
        ["${esquema_cu}", "${fec_ini_sem}"],
        {"${esquema_cu}": "ws_ec_cu_bdclientes", "${fec_ini_sem}": "2026-04-27"},
    )

    assert "--|     # ${esquema_cu} = ws_ec_cu_bdclientes" in updated
    assert "--|     # ${fec_ini_sem} = 2026-04-27" in updated


def test_sync_variables_updates_yaml_and_sql(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_path = tmp_path / "demo.sql"

    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.tabla"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables:",
                '  "${esquema_cu}": "ws_ec_cu_bdclientes"',
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
            ]
        ),
        encoding="utf-8",
    )
    sql_path.write_text(
        "\n".join(
            [
                "--| @PARAMETROS",
                "--|     #",
                "--\\__________________________________________________________________________________________________/",
                "insert overwrite table ${esquema_cu}.demo",
                "select * from ${esquema_cd}.origen where fecha = '${fec_ini_sem}'",
            ]
        ),
        encoding="utf-8",
    )

    result = sync_variables_with_project(sql_path, config_path)

    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sql_text = sql_path.read_text(encoding="utf-8")

    assert result["variables_found"] == ["${esquema_cd}", "${esquema_cu}", "${fec_ini_sem}"]
    assert result["variables_added"] == ["${esquema_cd}", "${fec_ini_sem}"]
    assert "${esquema_cd}" in config_data["variables"]
    assert config_data["variables"]["${esquema_cd}"] == ""
    assert "--|     # ${esquema_cd} = " in sql_text
    assert "--|     # ${fec_ini_sem} = " in sql_text


def test_sync_variables_cli_module(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_path = tmp_path / "demo.sql"

    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.tabla"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables: {}",
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
            ]
        ),
        encoding="utf-8",
    )
    sql_path.write_text(
        "\n".join(
            [
                "--| @PARAMETROS",
                "--|     #",
                "--\\__________________________________________________________________________________________________/",
                "select * from ${esquema_cd}.origen where fecha = '${fec_ini_sem}'",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "src.sync_variables",
            "--sql",
            str(sql_path),
            "--config",
            str(config_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert payload["variables_found"] == ["${esquema_cd}", "${fec_ini_sem}"]
    assert "${fec_ini_sem}" in config_data["variables"]


def test_update_yaml_variables_block_can_capture_values_before_writing():
    config_text = "\n".join(
        [
            'producto_funcional: "Demo"',
            "variables:",
            '  "${esquema_cu}": "ws_ec_cu_bdclientes"',
            'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
            "",
        ]
    )
    answers = iter(["ws_ec_cu_bdclientes_real", "2026-04-27"])

    updated, added, values = update_yaml_variables_block(
        config_text,
        ["${esquema_cu}", "${fec_ini_sem}"],
        prompt_for_values=True,
        input_fn=lambda _: next(answers),
    )

    assert added == ["${fec_ini_sem}"]
    assert values["${esquema_cu}"] == "ws_ec_cu_bdclientes_real"
    assert values["${fec_ini_sem}"] == "2026-04-27"
    assert '"${esquema_cu}": "ws_ec_cu_bdclientes_real"' in updated
    assert '"${fec_ini_sem}": "2026-04-27"' in updated


def test_sync_directory_variables_prompts_once_and_updates_all_sql(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()

    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.tabla"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables:",
                '  "${esquema_cu}": "ws_ec_cu_bdclientes"',
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sql_dir / "a.sql").write_text(
        "\n".join(
            [
                "--| @PARAMETROS",
                "--|     #",
                "--\\__________________________________________________________________________________________________/",
                "select * from ${esquema_cu}.a where fecha = '${fec_ini_sem}'",
            ]
        ),
        encoding="utf-8",
    )
    (sql_dir / "b.sql").write_text(
        "\n".join(
            [
                "--| @PARAMETROS",
                "--|     #",
                "--\\__________________________________________________________________________________________________/",
                "select * from ${esquema_cd}.b",
            ]
        ),
        encoding="utf-8",
    )
    answers = iter(["ws_ec_cd_bdclientes", "ws_ec_cu_bdclientes_real", "2026-04-27"])

    result = sync_directory_variables(
        sql_dir,
        config_path,
        prompt_for_values=True,
        input_fn=lambda _: next(answers),
    )

    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    a_sql = (sql_dir / "a.sql").read_text(encoding="utf-8")
    b_sql = (sql_dir / "b.sql").read_text(encoding="utf-8")

    assert result["variables_found"] == ["${esquema_cd}", "${esquema_cu}", "${fec_ini_sem}"]
    assert config_data["variables"]["${esquema_cd}"] == "ws_ec_cd_bdclientes"
    assert config_data["variables"]["${esquema_cu}"] == "ws_ec_cu_bdclientes_real"
    assert config_data["variables"]["${fec_ini_sem}"] == "2026-04-27"
    assert "--|     # ${esquema_cu} = ws_ec_cu_bdclientes_real" in a_sql
    assert "--|     # ${fec_ini_sem} = 2026-04-27" in a_sql
    assert "--|     # ${esquema_cd} = ws_ec_cd_bdclientes" in b_sql


def test_sync_variables_cli_directory_mode(tmp_path):
    config_path = tmp_path / "proyecto.yml"
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()

    config_path.write_text(
        "\n".join(
            [
                'producto_funcional: "Demo"',
                'frecuencia: "Diario"',
                'tabla_final_pipeline: "demo.tabla"',
                'prefijo_archivo: "DA_REQ_CD_IT_"',
                "variables: {}",
                'template: "input/templates/DA_REQ_CD_IT_plantilla.docx"',
            ]
        ),
        encoding="utf-8",
    )
    (sql_dir / "demo.sql").write_text(
        "\n".join(
            [
                "--| @PARAMETROS",
                "--|     #",
                "--\\__________________________________________________________________________________________________/",
                "select * from ${esquema_cd}.origen where fecha = '${fec_ini_sem}'",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "python3",
            "-m",
            "src.sync_variables",
            "--dir",
            str(sql_dir),
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
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert payload["variables_found"] == ["${esquema_cd}", "${fec_ini_sem}"]
    assert payload["files_updated"][0]["sql_path"].endswith("demo.sql")
    assert "${esquema_cd}" in config_data["variables"]
