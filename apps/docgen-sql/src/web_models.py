from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class WebVariableInput(BaseModel):
    name: str
    value: str = ""


class WebOutputTableInput(BaseModel):
    table: str
    description: str


class WebModuleInput(BaseModel):
    id: str = "paso_web_01"
    name: str = "Paso web"
    intention: str = "Paso generado desde la interfaz web"
    depends_on: List[str] = Field(default_factory=list)
    output_tables: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_main: bool = True


class WebProductSheetInput(BaseModel):
    domain: Optional[str] = None
    owner: Optional[str] = None
    frequency: Optional[str] = None
    update_day: Optional[str] = None
    expected_schedule: Optional[str] = None
    granularity: Optional[str] = None
    purpose: Optional[str] = None
    output_type: Optional[str] = None
    target_consumers: List[str] = Field(default_factory=list)


class WebTemplateInput(BaseModel):
    file_name: str
    content_base64: str


class WebSqlFileInput(BaseModel):
    sql_file_name: str
    sql_text: str
    is_step: bool = False


class WebGenerationRequest(BaseModel):
    mode: Literal["structural", "step"] = "structural"
    sql_text: str
    sql_file_name: str = "consulta_web.sql"
    sql_files: List[WebSqlFileInput] = Field(default_factory=list)
    product_name: str = "Producto generado desde web"
    frequency: str = "Diario"
    final_table_name: str = "demo.tabla_resultado"
    file_prefix: str = "DA_REQ_CD_IT_"
    document_title: str = "Documentacion Funcional Estructural"
    generate_datacontract: bool = True
    variables: List[WebVariableInput] = Field(default_factory=list)
    product_sheet: WebProductSheetInput = Field(default_factory=WebProductSheetInput)
    output_tables: List[WebOutputTableInput] = Field(default_factory=list)
    quick_reference: List[str] = Field(default_factory=list)
    module: Optional[WebModuleInput] = None
    profile_db_path: Optional[str] = None
    profile_table: Optional[str] = None
    profile_engine: Optional[Literal["duckdb", "sqlite"]] = None
    ddl_text: Optional[str] = None
    dictionary_text: Optional[str] = None
    csv_sample_text: Optional[str] = None
    structural_template: Optional[WebTemplateInput] = None
    step_template: Optional[WebTemplateInput] = None


class WebGenerationResponse(BaseModel):
    run_id: str
    mode: str
    sql_file: str
    config_file: str
    output_dir: str
    generated_files: dict
    audit_passed: bool
    audit_errors: List[str] = Field(default_factory=list)
    audit_warnings: List[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)
    pipeline_graph: dict = Field(default_factory=dict)
    workspace_inventory: List[dict] = Field(default_factory=list)
