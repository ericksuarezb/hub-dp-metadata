from pathlib import Path

from src.audit import audit_outputs
from src.models import (
    DocumentArtifact,
    FilterDetail,
    ProcessStep,
    RuleDetail,
    SqlAnalysis,
    TransformationDetail,
)


def _sample_analysis() -> SqlAnalysis:
    transformation = TransformationDetail(
        index=1,
        field_name="id_cliente",
        expression_name="column",
        field_type="D",
        subtype="—",
        origin="A",
        source_fields=["A.id_cliente"],
        description="Se traslada sin cambios el campo A.id_cliente hacia id_cliente.",
        step="Paso 5",
        rule_id=None,
        participates_in_steps=["Paso 2", "Paso 5"],
    )
    return SqlAnalysis(
        file_name="demo.sql",
        sql_path="input/sql/demo.sql",
        target_table="ws_ec_cu_bdclientes.demo",
        raw_sql="select 1",
        resolved_sql="select 1",
        unresolved_variables=[],
        auto_resolved_variables={},
        compute_stats_tables=[],
        ctes=[],
        subqueries=[],
        sources=[],
        joins=[],
        filters=[],
        transformations=[transformation],
        rules=[RuleDetail(id="RN-01", description="Regla valida.", applies_in="Paso 4")],
        steps=[
            ProcessStep(
                number=1,
                title="Paso demo",
                objective="Objetivo demo.",
                depends_on="Ninguno",
                tables_involved=["tabla_demo"],
                join_criteria=[],
                join_type=[],
                meaning=[],
                selection_criteria=[],
                extracted_fields=["id_cliente"],
                rule_ids=[],
                result="Resultado demo.",
            )
        ],
        metadata={},
    )


def _sample_document() -> DocumentArtifact:
    return DocumentArtifact(
        path="output/docx/DA_REQ_CD_IT_demo.docx",
        section_titles=[
            "1. Referencia rapida y ficha del producto",
            "2. Fuentes de datos",
            "3. Flujo general del proceso",
            "4. Matriz de trazabilidad",
            "5. Transformaciones",
            "6. Reglas de negocio",
            "7. Proceso paso a paso detallado",
            "8. Convenciones y navegacion",
        ],
        section4_fields=["id_cliente"],
        section5_fields=["id_cliente"],
        referenced_rule_ids=[],
        document_text="Documento funcional sin codigo pegado.",
    )


def test_audit_fails_if_any_section_is_missing(tmp_path):
    analysis = _sample_analysis()
    document = _sample_document()
    document.section_titles = document.section_titles[:-1]

    result = audit_outputs(analysis, document, tmp_path / "audit_missing_section.json")

    assert result.passed is False
    assert any("Faltan secciones obligatorias" in error for error in result.errors)


def test_audit_fails_if_final_field_is_missing_from_section_5(tmp_path):
    analysis = _sample_analysis()
    document = _sample_document()
    document.section5_fields = []

    result = audit_outputs(analysis, document, tmp_path / "audit_missing_field.json")

    assert result.passed is False
    assert any("Faltan campos finales en Seccion 5" in error for error in result.errors)


def test_audit_fails_if_document_contains_sql_keywords(tmp_path):
    analysis = _sample_analysis()
    document = _sample_document()
    document.document_text = "Este DOCX pega SELECT x FROM y WHERE z = 1 con un JOIN extra."

    result = audit_outputs(analysis, document, tmp_path / "audit_sql_text.json")

    assert result.passed is False
    assert any("patrones de SQL literal" in error for error in result.errors)


def test_audit_allows_explanatory_mentions_without_sql_clause_shape(tmp_path):
    analysis = _sample_analysis()
    document = _sample_document()
    document.document_text = "El proceso selecciona clientes y aplica filtros de negocio sin pegar SQL literal."

    result = audit_outputs(analysis, document, tmp_path / "audit_explanatory_text.json")

    assert not any("patrones de SQL literal" in error for error in result.errors)


def test_audit_validates_output_prefix(tmp_path):
    analysis = _sample_analysis()
    document = _sample_document()
    document.path = "output/docx/reporte_demo.docx"

    result = audit_outputs(analysis, document, tmp_path / "audit_prefix.json")

    assert result.passed is False
    assert any("debe iniciar con DA_REQ_CD_IT_" in error for error in result.errors)
