from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class OutputTableConfig(BaseModel):
    tabla: str
    descripcion: str


class QuickReferenceConfig(BaseModel):
    que_no_hace: List[str] = Field(default_factory=list)

    @field_validator("que_no_hace", mode="before")
    @classmethod
    def _default_que_no_hace(cls, value):
        return value or []


class ProductSheetConfig(BaseModel):
    dominio: Optional[str] = None
    responsable: Optional[str] = None
    frecuencia: Optional[str] = None
    dia_actualizacion: Optional[str] = None
    horario_esperado: Optional[str] = None
    granularidad: Optional[str] = None
    proposito: Optional[str] = None
    salida_tipo: Optional[str] = None
    consumidores_objetivo: List[str] = Field(default_factory=list)

    @field_validator("consumidores_objetivo", mode="before")
    @classmethod
    def _default_consumidores_objetivo(cls, value):
        return value or []


class SectionOneConfig(BaseModel):
    ficha_producto: ProductSheetConfig = Field(default_factory=ProductSheetConfig)
    tablas_salida: List[OutputTableConfig] = Field(default_factory=list)
    referencia_rapida: QuickReferenceConfig = Field(default_factory=QuickReferenceConfig)

    @field_validator("tablas_salida", mode="before")
    @classmethod
    def _default_tablas_salida(cls, value):
        return value or []


class MainDocumentConfig(BaseModel):
    nombre: Optional[str] = None
    template: Optional[str] = None


class FlowModuleConfig(BaseModel):
    id: str
    nombre: str
    intencion: str
    sql: str
    template: Optional[str] = None
    depende_de: List[str] = Field(default_factory=list)
    salida_tablas: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    es_principal: bool = False

    @field_validator("depende_de", "salida_tablas", "tags", mode="before")
    @classmethod
    def _default_module_lists(cls, value):
        return value or []


class FlowConfig(BaseModel):
    tipo_documentacion: str = "modular"
    documento_principal: MainDocumentConfig = Field(default_factory=MainDocumentConfig)
    modulos: List[FlowModuleConfig] = Field(default_factory=list)

    @field_validator("modulos", mode="before")
    @classmethod
    def _default_modulos(cls, value):
        return value or []


class ProjectConfig(BaseModel):
    producto_funcional: str
    frecuencia: str
    tabla_final_pipeline: str
    prefijo_archivo: str
    variables: Dict[str, str] = Field(default_factory=dict)
    template: str
    seccion_1: SectionOneConfig = Field(default_factory=SectionOneConfig)
    flujo: FlowConfig = Field(default_factory=FlowConfig)

    @field_validator("variables", mode="before")
    @classmethod
    def _default_variables(cls, value):
        return value or {}


class VariableResolution(BaseModel):
    resolved_sql: str
    unresolved_variables: List[str] = Field(default_factory=list)
    auto_resolved_variables: Dict[str, str] = Field(default_factory=dict)
    masked_sql: Optional[str] = None
    masked_variables: Dict[str, str] = Field(default_factory=dict)


class SourceDetail(BaseModel):
    alias: str
    table_name: str
    layer: str
    fields_generated: List[str] = Field(default_factory=list)
    contains_description: str
    used_in_steps: List[str] = Field(default_factory=list)
    destination_table: str
    source_kind: str = "table"


class JoinDetail(BaseModel):
    source_alias: str
    source_name: str
    join_type: str
    condition_text: str
    meaning: str
    step: str = "Paso 3"
    rule_id: Optional[str] = None


class FilterDetail(BaseModel):
    scope: str
    condition_text: str
    step: str
    rule_id: Optional[str] = None


class TransformationDetail(BaseModel):
    index: int
    field_name: str
    expression_name: str
    field_type: str
    subtype: str
    origin: str
    source_fields: List[str] = Field(default_factory=list)
    description: str
    step: str
    rule_id: Optional[str] = None
    participates_in_steps: List[str] = Field(default_factory=list)
    physical_source_fields: List[str] = Field(default_factory=list)


class LineageSource(BaseModel):
    base_table: str
    source_column: str
    source_table_alias: Optional[str] = None
    reference_name: str


class ColumnLineage(BaseModel):
    column_name: str
    display_name: str
    expression_sql: str
    lineage_type: str
    source_aliases: List[str] = Field(default_factory=list)
    source_columns: List[str] = Field(default_factory=list)
    physical_sources: List[LineageSource] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)


class RuleDetail(BaseModel):
    id: str
    description: str
    applies_in: str


class ProcessStep(BaseModel):
    number: int
    title: str
    objective: str
    depends_on: str
    tables_involved: List[str] = Field(default_factory=list)
    join_criteria: List[str] = Field(default_factory=list)
    join_type: List[str] = Field(default_factory=list)
    meaning: List[str] = Field(default_factory=list)
    selection_criteria: List[str] = Field(default_factory=list)
    extracted_fields: List[str] = Field(default_factory=list)
    rule_ids: List[str] = Field(default_factory=list)
    result: str


class PublicationDetail(BaseModel):
    sequence: int
    statement_type: str
    target_table: str
    role: str
    has_compute_stats: bool = False


class ModuleSequenceItem(BaseModel):
    module_id: str
    module_name: str
    module_intention: str
    sql_path: str
    depends_on: List[str] = Field(default_factory=list)
    output_tables: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    document_role: str = "STEP"
    document_status: str = "Secundario"


class SqlAnalysis(BaseModel):
    file_name: str
    sql_path: str
    target_table: str
    raw_sql: str
    resolved_sql: str
    unresolved_variables: List[str] = Field(default_factory=list)
    auto_resolved_variables: Dict[str, str] = Field(default_factory=dict)
    compute_stats_tables: List[str] = Field(default_factory=list)
    publications: List[PublicationDetail] = Field(default_factory=list)
    ctes: List[str] = Field(default_factory=list)
    subqueries: List[str] = Field(default_factory=list)
    sources: List[SourceDetail] = Field(default_factory=list)
    joins: List[JoinDetail] = Field(default_factory=list)
    filters: List[FilterDetail] = Field(default_factory=list)
    transformations: List[TransformationDetail] = Field(default_factory=list)
    column_lineage: Dict[str, ColumnLineage] = Field(default_factory=dict)
    rules: List[RuleDetail] = Field(default_factory=list)
    steps: List[ProcessStep] = Field(default_factory=list)
    metadata: Dict[str, object] = Field(default_factory=dict)


class StructuralDocumentModel(BaseModel):
    title: str
    product_name: str
    target_table: str
    product_sheet: Dict[str, str] = Field(default_factory=dict)
    output_tables: List[OutputTableConfig] = Field(default_factory=list)
    quick_reference: Dict[str, str] = Field(default_factory=dict)
    layer_identification_notes: List[str] = Field(default_factory=list)
    mapped_variables: List[str] = Field(default_factory=list)
    module_sequence: List[ModuleSequenceItem] = Field(default_factory=list)
    global_sources: List[SourceDetail] = Field(default_factory=list)
    global_steps: List[ProcessStep] = Field(default_factory=list)
    final_transformations: List[TransformationDetail] = Field(default_factory=list)
    global_rules: List[RuleDetail] = Field(default_factory=list)
    navigation_notes: List[str] = Field(default_factory=list)


class StepDocumentModel(BaseModel):
    module_id: str
    module_name: str
    module_intention: str
    product_name: str
    sql_path: str
    target_table: str
    depends_on: List[str] = Field(default_factory=list)
    output_tables: List[str] = Field(default_factory=list)
    publications: List[PublicationDetail] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    sources: List[SourceDetail] = Field(default_factory=list)
    process_steps: List[ProcessStep] = Field(default_factory=list)
    joins: List[JoinDetail] = Field(default_factory=list)
    filters: List[FilterDetail] = Field(default_factory=list)
    transformations: List[TransformationDetail] = Field(default_factory=list)
    rules: List[RuleDetail] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)


class DocumentArtifact(BaseModel):
    path: str
    document_kind: str = "structural"
    section_titles: List[str] = Field(default_factory=list)
    section4_fields: List[str] = Field(default_factory=list)
    section5_fields: List[str] = Field(default_factory=list)
    referenced_rule_ids: List[str] = Field(default_factory=list)
    document_text: str = ""


class AuditResult(BaseModel):
    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    output_path: Optional[str] = None
    output_json_path: Optional[str] = None
