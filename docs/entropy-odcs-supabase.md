# Entropy CE + ODCS desde Supabase

## Objetivo

Poblar `Entropy Data CE` con la mayor cantidad posible de metadata ya existente en
`docgen-sql`, sin volver a capturar manualmente información que hoy ya vive en:

- `run_analysis`
- `run_sources`
- `run_transformations`
- `run_modules`
- `run_pipeline_relations`
- `run_workspace_files`
- `run_audit_*`
- `odcs_yaml`

## Lo que ya tenemos listo

La persistencia MVP en Supabase ya guarda casi todo lo necesario para una
primera carga rica hacia Entropy:

- contrato ODCS completo en `run_analysis.odcs_yaml`
- tabla objetivo por corrida en `app_runs.target_table`
- tablas fuente y capa en `run_sources`
- transformaciones y campos físicos de origen en `run_transformations`
- linaje entre módulos y nodos en `run_pipeline_relations`
- inventario de archivos del workspace en `run_workspace_files`
- evidencias de calidad en `run_audit_summary` y `run_audit_findings`

## Estrategia recomendada

### 1. Cargar el Data Product desde ODCS

Primer payload a poblar:

- `data product`
- `schema`
- `fields`
- `tags`
- `domain`
- `purpose / usage / limitations`

Fuente:

- `run_analysis.odcs_yaml`

Esta es la vía más estable porque ya concentra descripción funcional, esquema y
gran parte de la semántica del dataset.

### 2. Crear assets físicos para tablas fuente y destino

Segundo payload a poblar:

- dataset final
- datasets fuente
- columnas principales
- clasificación básica por capa o tipo

Fuentes:

- `app_runs.target_table`
- `run_sources`
- `run_transformations`

Esto permite que Entropy no solo vea el contrato lógico, sino también los
objetos físicos que participan en el flujo.

### 3. Publicar linaje técnico

Tercer payload a poblar:

- relaciones fuente -> destino
- eventos `OpenLineage` por módulo

Fuentes:

- `run_pipeline_relations`
- `run_modules`
- `run_module_sources`

`docgen-sql` ya identifica suficiente estructura como para emitir eventos
OpenLineage mínimos por módulo y relaciones de tabla a tabla.

### 4. Adjuntar evidencia documental y técnica

Cuarto payload a poblar:

- SQL
- DDL
- diccionarios
- DOCX
- diagramas Mermaid / PNG
- otros archivos del workspace

Fuentes:

- `run_workspace_files`
- `app_runs.generated_files`
- `app_runs.storage_objects`

Esto complementa el catálogo con evidencia navegable y ayuda a volver más útil
la ficha del activo.

## Qué puede poblarse ya

- contrato ODCS
- data product
- tabla destino
- tablas fuente
- campos y tipos lógicos/físicos cuando existan
- linaje técnico por módulo
- evidencia documental
- algunos hallazgos de calidad

## Qué requiere una segunda ola

- owners reales desde IAM o CMDB
- freshness / SLA observados desde orquestador
- profiling real por tabla desde base origen
- clasificación PII formal
- usage analytics o downstream consumers

## Exportador inicial incluido

Se agregó un exportador local que construye un bundle intermedio listo para
revisión:

```bash
cd apps/docgen-sql
.venv/bin/python -m src.export_entropy_bundle --run-id <RUN_ID>
```

Salida:

- `output/entropy_bundle/<RUN_ID>/entropy_bundle.json`
- `output/entropy_bundle/<RUN_ID>/data_product.json`
- `output/entropy_bundle/<RUN_ID>/assets.json`
- `output/entropy_bundle/<RUN_ID>/openlineage_events.json`
- `output/entropy_bundle/<RUN_ID>/datacontract.odcs.yaml`

## Orden recomendado de implementación

1. Publicar primero `ODCS + data product`
2. Reconciliar datasets fuente/destino
3. Ingerir `OpenLineage`
4. Adjuntar archivos como evidencia
5. Enriquecer con perfiles, ownership y clasificación

## Nota práctica

La mejor ruta no es modelar Entropy directamente desde SQL crudo. La mejor ruta
es usar `docgen-sql` como capa de normalización y a `Supabase` como staging de
metadata interoperable. Eso reduce duplicidad y hace repetible la carga.
