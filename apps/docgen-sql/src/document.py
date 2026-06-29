from __future__ import annotations

from pathlib import Path
from src.document_models import build_structural_document_model
from src.document_renderer import render_structural_docx
from src.models import DocumentArtifact, ProjectConfig, SqlAnalysis


def render_document(
    analysis: SqlAnalysis,
    config: ProjectConfig,
    output_path: str | Path,
) -> DocumentArtifact:
    model = build_structural_document_model(config, analysis)
    return render_structural_docx(model, config.template, output_path)
