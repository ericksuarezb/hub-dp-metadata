from pathlib import Path

from src.sql_business_context import infer_sql_business_context, load_llm_settings, _resolve_api_key, _resolve_api_style


def test_infer_sql_business_context_uses_heuristic_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    sql = """
    insert overwrite table demo.relacion_clientes
    select a.id_cliente, b.id_finacle
    from demo.alnova a
    join demo.finacle b on a.id_cliente = b.id_cliente
    where a.activo = 1
    """

    suggestion = infer_sql_business_context(sql, "03_relacion_clientes.sql")

    assert suggestion.provider == "heuristic"
    assert "demo.relacion_clientes" in suggestion.purpose
    assert len(suggestion.non_goals) >= 2
    assert suggestion.warning is not None


def test_load_llm_settings_reads_yaml(tmp_path):
    config_path = tmp_path / "llm.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  provider: openai",
                "  model: local-model",
                "  api_base: http://127.0.0.1:11434/v1",
                "  api_style: auto",
                "  api_key_env: LOCAL_LLM_KEY",
                "  api_key: ''",
                "  max_input_chars: 8000",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_llm_settings(Path(config_path))

    assert settings.enabled is True
    assert settings.model == "local-model"
    assert settings.api_base == "http://127.0.0.1:11434/v1"
    assert settings.max_input_chars == 8000


def test_resolve_api_style_uses_chat_completions_for_gemini(tmp_path):
    config_path = tmp_path / "llm.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  provider: gemini",
                "  model: gemini-2.5-flash",
                "  api_base: https://generativelanguage.googleapis.com/v1beta/openai/",
                "  api_style: auto",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_llm_settings(Path(config_path))

    assert _resolve_api_style(settings) == "chat_completions"


def test_resolve_api_key_reads_credentials_file(monkeypatch, tmp_path):
    config_path = tmp_path / "llm.yml"
    credentials_path = tmp_path / "config.credentials.json"
    config_path.write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  provider: gemini",
                "  model: gemini-2.5-flash",
                "  api_base: https://generativelanguage.googleapis.com/v1beta/openai/",
                "  api_style: chat_completions",
                "  api_key_env: GEMINI_API_KEY",
                "  api_key: ''",
            ]
        ),
        encoding="utf-8",
    )
    credentials_path.write_text(
        "\n".join(
            [
                "{",
                '  "llm": {',
                '    "gemini_api_key": "gemini-from-json"',
                "  }",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOCGEN_CREDENTIALS_FILE", str(credentials_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    settings = load_llm_settings(config_path)

    assert _resolve_api_key(settings) == "gemini-from-json"
