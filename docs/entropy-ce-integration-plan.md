# Plan de integracion Entropy CE

## Objetivo

Definir una estrategia realista para integrar en `Entropy Data CE` toda la
informacion ya capturada en este hub, aprovechando lo existente en:

- `DocGen SQL Web`
- `Data Contract Editor`
- `Supabase / PostgREST`
- artefactos documentales generados por `docgen-sql`

La meta no es volver a modelar manualmente los mismos activos dentro de
`Entropy`, sino usar el stack actual como capa de normalizacion y publicar hacia
Entropy solo lo necesario para catalogacion, descubrimiento y gobierno.

## Resumen ejecutivo

La mejor ruta es una estrategia mixta:

1. `docgen-sql` sigue siendo la fuente tecnica principal de parseo, linaje,
   tablas, transformaciones y evidencias.
2. `Data Contract Editor` sirve como capa de curacion semantica del contrato
   ODCS cuando se necesiten ajustes manuales o enriquecimiento funcional.
3. `Supabase / PostgREST` se mantiene como staging interoperable y API interna
   del modelo consolidado.
4. `Entropy CE` consume ese staging mediante una ingesta inicial y procesos
   incrementales de enriquecimiento.

La conclusion practica es simple: `Entropy` debe ser consumidor del modelo
consolidado, no el lugar donde recapturamos todo a mano.

## Lo que ya existe

### 1. Hub y aplicaciones base

El repo ya expone:

- `DocGen SQL Web`
- `Data Contract Editor`
- `Entropy Data CE`

Referencias:

- [README.md](../README.md)
- [docs/architecture.md](architecture.md)

### 2. Persistencia normalizada en Supabase

`docgen-sql` ya persiste metadata util para integracion en tablas como:

- `app_runs`
- `run_analysis`
- `run_sources`
- `run_transformations`
- `run_modules`
- `run_module_sources`
- `run_module_transformations`
- `run_pipeline_relations`
- `run_workspace_files`
- `run_audit_summary`
- `run_audit_findings`

Referencias:

- [apps/docgen-sql/src/run_repository.py](../apps/docgen-sql/src/run_repository.py)
- [apps/docgen-sql/sql/supabase_mvp.sql](../apps/docgen-sql/sql/supabase_mvp.sql)

### 3. Contrato ODCS ya disponible

La corrida ya puede conservar el contrato en `run_analysis.odcs_yaml`, y
tambien exponerlo como version recuperable del lado web/API.

Referencias:

- [apps/docgen-sql/src/run_repository.py](../apps/docgen-sql/src/run_repository.py)
- [apps/docgen-sql/src/web_api.py](../apps/docgen-sql/src/web_api.py)

### 4. Bundle intermedio orientado a Entropy

Ya existe un exportador para construir un bundle de interoperabilidad a partir
de una corrida persistida. Ese bundle produce:

- `entropy_bundle.json`
- `data_product.json`
- `assets.json`
- `openlineage_events.json`
- `datacontract.odcs.yaml`

Referencias:

- [docs/entropy-odcs-supabase.md](entropy-odcs-supabase.md)
- [apps/docgen-sql/src/export_entropy_bundle.py](../apps/docgen-sql/src/export_entropy_bundle.py)

## Hallazgo clave

La parte de extraccion, normalizacion y empaquetado ya esta bastante avanzada.

Lo que no aparece aun en este repo es un importador que publique directamente
ese bundle dentro de `Entropy CE`. Es decir:

- si tenemos `bundle listo para revision`
- no tenemos todavia `push automatico a Entropy`

Ese es el hueco tecnico principal.

## Arquitectura objetivo

```text
SQL / Hive / fuentes fisicas
          |
          v
    DocGen SQL Web
    - parseo SQL
    - linaje
    - tabla destino
    - tablas fuente
    - evidencias
          |
          v
  Data Contract Editor
  - curacion ODCS
  - enrichment funcional
          |
          v
   Supabase / PostgREST
   - staging interoperable
   - versionado operativo
   - API interna
          |
          v
 Entropy Importer Adapter
 - mapeo a modelo Entropy
 - carga inicial
 - upsert incremental
          |
          v
      Entropy CE
```

## Estrategia recomendada

### Fase 1. Alta del data product desde ODCS

Publicar primero en Entropy:

- data product
- schema
- fields
- tags
- domain
- descripcion funcional

Fuente principal:

- `run_analysis.odcs_yaml`

Razon:

- el ODCS ya concentra semantica estable
- evita reconstruir significado desde SQL crudo

### Fase 2. Reconciliacion de datasets fisicos

Publicar o reconciliar:

- dataset destino
- datasets fuente
- columnas fisicas principales
- capa o clasificacion tecnica basica

Fuentes:

- `app_runs.target_table`
- `run_sources`
- `run_transformations`

Razon:

- Entropy necesita visibilidad del activo fisico, no solo del contrato logico

### Fase 3. Carga de linaje tecnico

Publicar:

- relaciones fuente -> destino
- ejecuciones o eventos minimos de `OpenLineage` por modulo

Fuentes:

- `run_pipeline_relations`
- `run_modules`
- `run_module_sources`
- `openlineage_events.json`

Razon:

- ya existe suficiente estructura para construir una primera vista de lineage

### Fase 4. Adjuntar evidencia documental

Adjuntar o referenciar:

- SQL
- DDL
- diccionarios
- DOCX
- Mermaid
- PNG
- otros archivos del workspace

Fuentes:

- `run_workspace_files`
- `app_runs.generated_files`
- `app_runs.storage_objects`

Razon:

- la ficha del activo se vuelve util para exploracion y soporte operativo

### Fase 5. Enriquecimiento incremental

Agregar despues:

- owners reales
- stewardship
- freshness observada
- SLA
- clasificacion PII
- profiling real
- consumo downstream

Razon:

- estos atributos no deben bloquear la primera carga

## Que se puede poblar ya

- contrato ODCS
- data product
- tabla destino
- tablas fuente
- parte del schema y campos
- tags y dominio cuando existan en ODCS
- linaje tecnico basico
- evidencias documentales
- hallazgos minimos de calidad

## Que no conviene modelar manualmente en Entropy

- descripciones ya presentes en ODCS
- tablas y columnas ya inferidas por `docgen-sql`
- relaciones que ya existen en `run_pipeline_relations`
- archivos ya inventariados en `run_workspace_files`

Si se recaptura esto manualmente dentro de Entropy, se introduce:

- duplicidad
- drift semantico
- mas costo operativo
- menos trazabilidad

## Backlog tecnico recomendado

### Bloque A. Importador a Entropy

1. Crear un servicio o script `entropy_importer` dentro del repo.
2. Leer el payload desde `SupabaseRunRepository.get_run_export_payload(...)` o
   desde `entropy_bundle.json`.
3. Traducir `data_product`, `assets` y `lineage` al modelo de carga requerido
   por Entropy CE.
4. Implementar `upsert` idempotente para evitar duplicados.
5. Registrar resultados de importacion por `run_id`.

### Bloque B. Modelo de reconciliacion

1. Definir claves estables para assets.
2. Usar `qualified_name` como base para datasets.
3. Resolver colisiones entre nombre logico y nombre fisico.
4. Separar claramente `data product` de `dataset asset`.

### Bloque C. Incrementales

1. Detectar cambios por `run_id`, `target_table` o hash de contrato.
2. Reimportar solo cuando cambie ODCS, linaje o inventario relevante.
3. Marcar obsolescencia o supersesion de versiones anteriores.

### Bloque D. Evidencia navegable

1. Exponer ligas a storage para artefactos persistidos.
2. Normalizar categorias de archivo.
3. Decidir que evidencia se adjunta y cual solo se referencia.

### Bloque E. Gobierno

1. Definir fuente maestra para owners y dominios.
2. Incorporar clasificacion y glosario en una segunda ola.
3. Alinear la semantica del ODCS con taxonomias corporativas.

## MVP sugerido

Un MVP razonable no intenta cargar todo. Solo hace esto:

1. recibe `run_id`
2. obtiene `get_run_export_payload(run_id)`
3. genera el bundle interoperable
4. publica en Entropy:
   - data product
   - dataset destino
   - datasets fuente
   - lineage minimo
5. guarda bitacora de exito o error

Con eso ya se valida:

- que el modelo actual alcanza para una integracion real
- que la captura manual en Entropy puede reducirse al minimo

## Orden recomendado de ejecucion

1. Consolidar el contrato en `DocGen SQL Web` y `Data Contract Editor`.
2. Persistir corrida y artefactos en `Supabase`.
3. Generar `entropy bundle`.
4. Cargar `ODCS + data product`.
5. Reconciliar assets fisicos.
6. Cargar lineage.
7. Adjuntar evidencias.
8. Enriquecer con ownership, clasificacion y profiling.

## Siguiente implementacion sugerida

La siguiente pieza de trabajo con mejor retorno es construir el importador
faltante hacia `Entropy CE`, no rehacer el modelo de metadata.

Eso implica:

- confirmar el mecanismo de importacion soportado por Entropy CE
- mapear el bundle actual al payload esperado por Entropy
- dejar un comando reproducible del tipo:

```bash
.venv/bin/python -m src.import_entropy --run-id <RUN_ID>
```

## Referencias

- [docs/entropy-odcs-supabase.md](entropy-odcs-supabase.md)
- [docs/architecture.md](architecture.md)
- [README.md](../README.md)
- [apps/docgen-sql/src/export_entropy_bundle.py](../apps/docgen-sql/src/export_entropy_bundle.py)
- [apps/docgen-sql/src/run_repository.py](../apps/docgen-sql/src/run_repository.py)
- [apps/docgen-sql/sql/supabase_mvp.sql](../apps/docgen-sql/sql/supabase_mvp.sql)
