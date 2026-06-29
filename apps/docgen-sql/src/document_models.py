from __future__ import annotations

from typing import Dict, List

from src.models import (
    FlowModuleConfig,
    ModuleSequenceItem,
    OutputTableConfig,
    ProjectConfig,
    SqlAnalysis,
    StepDocumentModel,
    StructuralDocumentModel,
)


def build_structural_document_model(
    config: ProjectConfig,
    final_analysis: SqlAnalysis,
) -> StructuralDocumentModel:
    ficha = config.seccion_1.ficha_producto

    module_sequence = []
    for module in config.flujo.modulos:
        module_sequence.append(
            ModuleSequenceItem(
                module_id=module.id,
                module_name=module.nombre,
                module_intention=module.intencion,
                sql_path=module.sql,
                depends_on=module.depende_de,
                output_tables=[
                    _resolve_config_variables(table, config.variables)
                    for table in module.salida_tablas
                ],
                tags=module.tags,
                document_role="PRINCIPAL" if _is_principal_module(module, config) else "STEP",
                document_status="Principal" if _is_principal_module(module, config) else "Secundario",
            )
        )

    output_tables = config.seccion_1.tablas_salida or [
        OutputTableConfig(
            tabla=_resolve_config_variables(config.tabla_final_pipeline or final_analysis.target_table, config.variables),
            descripcion="Tabla final del pipeline con el resultado funcional del proceso.",
        )
    ]
    quick_reference = {
        "Cuantas fuentes usa": f"{len(final_analysis.sources)} fuentes logicas identificadas.",
        "Cuantos pasos tiene": f"{len(final_analysis.steps)} pasos estandarizados del proceso.",
        "Cuantos campos produce": (
            f"{len(final_analysis.transformations)} campos finales: "
            f"{sum(1 for item in final_analysis.transformations if item.field_type == 'D')} directos + "
            f"{sum(1 for item in final_analysis.transformations if item.field_type == 'T')} transformados."
        ),
        "Cuantas reglas lo rigen": f"{len(final_analysis.rules)} reglas RN documentadas.",
        "Que no hace": "; ".join(
            config.seccion_1.referencia_rapida.que_no_hace
            or ["No documenta SQL literal ni dependencias externas no visibles en el script."]
        ),
    }
    product_sheet = {
        "Producto": config.producto_funcional,
        "Dominio": ficha.dominio or "Dominio funcional por confirmar",
        "Responsable": ficha.responsable or "Por definir por el equipo funcional.",
        "Frecuencia": ficha.frecuencia or config.frecuencia,
        "Dia de actualizacion": ficha.dia_actualizacion or "Periodicidad definida por la configuracion del pipeline.",
        "Horario esperado": ficha.horario_esperado or "Disponibilidad operativa posterior a la corrida diaria.",
        "Granularidad": ficha.granularidad or f"Una fila por registro final publicado en {final_analysis.target_table}.",
        "Proposito": ficha.proposito or f"Consolidar el resultado final que sera publicado en {final_analysis.target_table}.",
        "Salida": ficha.salida_tipo or "Tabla fisica actualizada por pipeline SQL.",
        "Consumidores objetivo": ", ".join(
            ficha.consumidores_objetivo or ["Equipos de analitica", "Procesos downstream", "Consumo operativo"]
        ),
    }
    navigation_notes = [
        "Quiero saber como se transforma un campo -> Seccion 5",
        "Quiero saber en que pasos participa un campo -> Seccion 4",
        "Quiero saber que campos genera una tabla insumo -> Seccion 2",
        "Quiero entender una regla de negocio -> Seccion 6",
        "Quiero entender un paso del proceso -> Seccion 7",
        "Quiero saber que modulos forman el producto -> Seccion 3",
    ]
    layer_identification_notes = [
        "Las tablas que inician con cd_ pertenecen a la capa Crystal y se identifican como insumos origen ya procesados.",
        "Las tablas que inician con rd_ pertenecen a la capa Raw.",
        "Las tablas que inician con cu_ pertenecen a la capa Curada.",
    ]
    mapped_variables = [
        f"{token[2:-1] if token.startswith('${') and token.endswith('}') else token} = {value}"
        for token, value in sorted(config.variables.items())
    ]

    return StructuralDocumentModel(
        title=config.flujo.documento_principal.nombre or "Documentacion Funcional Estructural",
        product_name=config.producto_funcional,
        target_table=final_analysis.target_table,
        product_sheet=product_sheet,
        output_tables=output_tables,
        quick_reference=quick_reference,
        layer_identification_notes=layer_identification_notes,
        mapped_variables=mapped_variables,
        module_sequence=module_sequence,
        global_sources=final_analysis.sources,
        global_steps=final_analysis.steps,
        final_transformations=final_analysis.transformations,
        global_rules=final_analysis.rules,
        navigation_notes=navigation_notes,
    )


def build_step_document_model(
    module_config: FlowModuleConfig,
    sql_analysis: SqlAnalysis,
    config: ProjectConfig,
) -> StepDocumentModel:
    acceptance_criteria = [
        f"El SQL {sql_analysis.file_name} debe publicar la tabla destino esperada.",
        "Las fuentes, joins, filtros y reglas del modulo deben quedar documentados sin pegar SQL literal.",
        "Las transformaciones del modulo deben conservar trazabilidad hacia sus fuentes fisicas.",
    ]
    if sql_analysis.compute_stats_tables:
        acceptance_criteria.append(
            "Las operaciones de estadisticas posteriores a la publicacion deben quedar registradas en el documento."
        )

    output_tables = _merge_unique(
        [
            _resolve_config_variables(table, config.variables)
            for table in module_config.salida_tablas
        ],
        [publication.target_table for publication in sql_analysis.publications],
    ) or [sql_analysis.target_table]

    return StepDocumentModel(
        module_id=module_config.id,
        module_name=module_config.nombre,
        module_intention=module_config.intencion,
        product_name=config.producto_funcional,
        sql_path=module_config.sql,
        target_table=sql_analysis.target_table,
        depends_on=module_config.depende_de,
        output_tables=output_tables,
        publications=sql_analysis.publications,
        tags=module_config.tags,
        sources=sql_analysis.sources,
        process_steps=sql_analysis.steps,
        joins=sql_analysis.joins,
        filters=sql_analysis.filters,
        transformations=sql_analysis.transformations,
        rules=sql_analysis.rules,
        acceptance_criteria=acceptance_criteria,
    )


def _resolve_config_variables(text: str, variables: Dict[str, str]) -> str:
    resolved = text
    for token, value in variables.items():
        resolved = resolved.replace(token, value)
    return resolved


def _is_principal_module(module: FlowModuleConfig, config: ProjectConfig) -> bool:
    if module.es_principal:
        return True

    resolved_outputs = [_resolve_config_variables(table, config.variables) for table in module.salida_tablas]
    final_target = _resolve_config_variables(config.tabla_final_pipeline, config.variables)
    return final_target in resolved_outputs


def _merge_unique(*groups: List[str]) -> List[str]:
    seen: List[str] = []
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.append(item)
    return seen
