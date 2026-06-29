# docgen-sql

Generador de especificaciones funcionales a partir de SQL.

## Integracion segura

Si vas a mover este proyecto a otra integracion, la opcion mas estable es **copiar o clonar la carpeta completa** e instalarla como aplicacion desde la raiz con `pip install -e .` o `pip install -e .[web]`.

Si el entorno de destino no tiene salida a internet, usa `pip install -e . --no-build-isolation`; y si el tooling es mas viejo, `python setup.py develop --no-deps`.

Antes de correr el pipeline o la API, valida el entorno con:

```bash
docgen-sql-doctor
```

Guia detallada:

- [INSTALL.md](INSTALL.md)

## MVP web

Ya existe un scaffold inicial para llevar el pipeline a web sin depender de `input/` como captura manual.

- Backend adapter: [src/web_service.py](src/web_service.py)
- API FastAPI: [src/web_api.py](src/web_api.py)
- Frontend React/Vite: [web/src/App.jsx](web/src/App.jsx)

### Enfoque

La web recibe manualmente:

- SQL
- variables `${...}`
- ficha de producto
- tablas de salida
- reglas de referencia rapida
- metadata STEP
- DDL, diccionario y CSV de muestra opcionales
- plantillas `.docx` opcionales

Con esos datos, el backend construye un workspace temporal por corrida en `output/web_runs/` y genera los mismos artefactos principales del pipeline.

### Arranque local del MVP

Backend:

```bash
./.venv/bin/pip install -r requirements-web.txt
./.venv/bin/python -m uvicorn src.web_api:app --reload --port 8000
```

Frontend:

```bash
cd web
npm install
npm run dev
```

Configuracion opcional del LLM para inferir `Proposito` y `Que no hace` desde la UI:

- edita [config/llm.yml](config/llm.yml)
- coloca los tokens locales en `../../config.credentials.json`
- para OpenAI, deja `provider: openai`, `api_base: https://api.openai.com/v1` y define `llm.openai_api_key` o `OPENAI_API_KEY`
- para un modelo local compatible con OpenAI, cambia `model` y `api_base`, por ejemplo `http://127.0.0.1:11434/v1`
- si el LLM esta desactivado o sin credenciales, la app cae a inferencia local

Ejemplo para OpenAI:

```yaml
llm:
  enabled: true
  provider: openai
  model: gpt-4.1-mini
  api_base: https://api.openai.com/v1
  api_key_env: OPENAI_API_KEY
  api_key: ""
  max_input_chars: 12000
```

Ejemplo para endpoint local compatible:

```yaml
llm:
  enabled: true
  provider: openai
  model: llama3.1
  api_base: http://127.0.0.1:11434/v1
  api_key_env: LOCAL_LLM_KEY
  api_key: ""
  max_input_chars: 12000
```

## MVP Supabase

Ya existe una integracion opcional para persistir corridas de la app en Supabase.

Archivos clave:

- esquema SQL: [sql/supabase_mvp.sql](sql/supabase_mvp.sql)
- configuracion: [config/supabase.yml](config/supabase.yml)
- adaptador: [src/run_repository.py](src/run_repository.py)

Esta primera version guarda:

- una fila por corrida en `app_runs`
- `analysis_json` completo en `run_analysis`
- tablas fuente usadas en `run_sources`
- transformaciones finales en `run_transformations`
- resumen de auditoria y findings en `run_audit_summary` y `run_audit_findings`

Activacion:

1. Ejecuta el esquema `sql/supabase_mvp.sql` en tu proyecto Supabase.
2. Edita `config/supabase.yml`.
3. Define la service role key en `../../config.credentials.json` o via `SUPABASE_SERVICE_ROLE_KEY`.

Ejemplo:

```yaml
supabase:
  enabled: true
  url: https://tu-proyecto.supabase.co
  service_role_key_env: SUPABASE_SERVICE_ROLE_KEY
  service_role_key: ""
  timeout_seconds: 10
```

Cuando Supabase esta apagado o no configurado, la app sigue funcionando normal y solo marca `supabase_persisted: false` en el resultado.

Opcional para profiles persistidos de muestras:

```bash
docker compose --profile duckdb up -d
```

Carpetas compartidas:

- `data/duckdb/`: bases `.duckdb` persistidas para profile
- `data/samples/`: muestras CSV o insumos tabulares persistidos

El proyecto toma scripts SQL de `input/sql`, resuelve variables declaradas en `config/proyecto.yml`, parsea el SQL con `sqlglot` y genera tres salidas por archivo:

- un JSON intermedio estructurado
- un documento Word `.docx`
- una auditoria en `.xlsx`

El objetivo es convertir SQL operativo en una especificacion funcional legible, reusable y auditable.

## Flujo recomendado

### 1. Sincronizar variables del proyecto

Antes de generar documentos, se recomienda sincronizar las variables `${...}` encontradas en los SQL.

Para todos los SQL del proyecto:

```bash
python3 -m src.sync_variables --dir input/sql
```

Este comando:

- recorre todos los `.sql` dentro de `input/sql`
- detecta variables con patron `${...}`
- pide un valor una sola vez por variable
- actualiza `config/proyecto.yml`
- actualiza el bloque `@PARAMETROS` dentro de cada SQL con formato:

```sql
--| @PARAMETROS
--|     # ${esquema_cu} = ws_ec_cu_bdclientes
--|     # ${fec_ini_sem} = 2026-04-27
```

Si no quieres preguntas interactivas:

```bash
python3 -m src.sync_variables --dir input/sql --no-prompt
```

Tambien puedes sincronizar un solo SQL:

```bash
python3 -m src.sync_variables --sql input/sql/02_detalle_cuenta_alnova.sql
```

### 2. Sincronizar modulos del flujo funcional

Una vez sincronizadas las variables, se recomienda sincronizar `flujo.modulos` en `config/proyecto.yml`.

Para todos los SQL del proyecto:

```bash
.venv/bin/python -m src.sync_modules --dir input/sql
```

Este comando:

- recorre los `.sql`
- lee metadatos del encabezado SQL
- actualiza `flujo.modulos` en `config/proyecto.yml`
- usa `@ARCHIVO` para `nombre`
- usa `@DESCRIPCION` para `intencion`
- si alguno viene vacio, permite captura manual por terminal

Ejemplo de lectura desde encabezado:

```sql
--| @ARCHIVO: Detalle cuenta ALNOVA
--| @DESCRIPCION: Obtener el universo de cuentas ALNOVA excluyendo cuentas ya identificadas en Finacle
```

Si no quieres captura manual:

```bash
.venv/bin/python -m src.sync_modules --dir input/sql --no-prompt
```

Tambien puedes sincronizar un solo SQL:

```bash
.venv/bin/python -m src.sync_modules --sql input/sql/02_detalle_cuenta_alnova.sql --no-prompt
```

### 3. Ejecutar el pipeline de generacion

El pipeline requiere las dependencias del entorno virtual.

Ejemplo:

```bash
.venv/bin/python -m src.run_pipeline --sql input/sql/02_detalle_cuenta_alnova.sql
```

Este comando genera:

- `output/json/DA_REQ_CD_IT_02_detalle_cuenta_alnova.json`
- `output/docx/DA_REQ_CD_IT_02_detalle_cuenta_alnova.docx`
- `output/audit/DA_REQ_CD_IT_02_detalle_cuenta_alnova.xlsx`

Para generar un documento modular STEP para un solo modulo:

```bash
.venv/bin/python -m src.run_pipeline --module paso_02_detalle_cuenta_alnova --mode step
```

Para generar todos los documentos STEP definidos en `flujo.modulos` en una sola corrida:

```bash
.venv/bin/python -m src.run_pipeline --mode step --all-steps
```

Este modo:

- recorre todos los modulos definidos en `config/proyecto.yml`
- toma el `sql` asociado a cada modulo
- genera JSON, DOCX STEP y auditoria por modulo
- devuelve un resumen consolidado en consola
- si un modulo no coincide con el arquetipo soportado por el parser, lo reporta en `errors` sin detener toda la corrida

## Estructura del proyecto

```text
docgen-sql/
├── config/
│   └── proyecto.yml
├── input/
│   ├── prompts/
│   │   └── Prompt_Especificacion_Funcional_v7.md
│   ├── sql/
│   │   └── *.sql
│   └── templates/
│       ├── DA_REQ_CD_IT_plantilla.docx
│       └── DA_REQ_CD_IT_STEP_plantilla.docx
├── output/
│   ├── audit/
│   ├── docx/
│   └── json/
├── src/
│   ├── audit.py
│   ├── config.py
│   ├── document.py
│   ├── models.py
│   ├── run_pipeline.py
│   ├── sql_parser.py
│   ├── sync_modules.py
│   └── sync_variables.py
└── tests/
```

## Rol de cada archivo importante

### `config/proyecto.yml`

Es la configuracion principal del proyecto.

Contiene:

- datos del producto
- variables `${...}` y sus valores
- plantilla `.docx`
- informacion estatica de la Seccion 1 del documento
- definicion del flujo modular en `flujo.modulos`

Ejemplo de responsabilidades:

- `variables`: valores para sustituir en SQL
- `seccion_1.ficha_producto`: datos funcionales del producto
- `seccion_1.tablas_salida`: tablas de salida y descripcion
- `seccion_1.referencia_rapida`: limitaciones o notas de negocio
- `flujo.documento_principal`: configuracion del documento estructural principal
- `flujo.modulos`: secuencia funcional de SQL del proceso

### `input/prompts/Prompt_Especificacion_Funcional_v7.md`

Es la especificacion conceptual del documento:

- estructura esperada
- reglas de redaccion
- reglas visuales
- contenido por seccion

No se ejecuta directamente, pero sirve como referencia funcional.

### `input/templates/DA_REQ_CD_IT_plantilla.docx`

Es la base visual del documento final.

El renderer la usa como referencia de:

- secciones
- estilo
- colores
- tablas
- estructura editorial

### `output/json/*.json`

Es la fuente intermedia estructurada.

El renderer DOCX toma el contenido desde aqui de forma conceptual, aunque en tiempo de ejecucion se genera primero en memoria desde el parser.

### `src/sync_variables.py`

Utilidad de sincronizacion de variables.

Se puede ejecutar con `python3` del sistema porque fue implementada sin dependencias externas.

### `src/sync_modules.py`

Utilidad para construir o actualizar `flujo.modulos` en `config/proyecto.yml`.

Responsabilidades:

- leer encabezados SQL
- tomar `@ARCHIVO` como `nombre`
- tomar `@DESCRIPCION` como `intencion`
- capturar manualmente valores faltantes
- registrar `sql`, `template`, `salida_tablas` y `tags`
- dejar el flujo funcional del producto en configuracion

### `src/run_pipeline.py`

CLI principal del pipeline.

Se recomienda correrlo con `.venv/bin/python` porque usa librerias como:

- `python-docx`
- `sqlglot`
- `pydantic`
- `openpyxl`

Modos soportados:

- `--sql <ruta>`: genera documento estructural para un SQL
- `--module <id> --mode step`: genera un STEP por modulo
- `--mode step --all-steps`: genera todos los STEP declarados en `flujo.modulos`

### `src/sql_parser.py`

Es el nucleo del parser SQL.

Responsabilidades:

- resolver y enmascarar variables para parseo seguro
- parsear `INSERT OVERWRITE` con dialecto `hive`
- usar `qualify` de SQLGlot
- extraer fuentes, joins, filtros, reglas y transformaciones
- construir linaje fisico por columna
- inferir `used_in_steps` desde AST y linaje

## Estructura de `flujo.modulos`

El proyecto ya soporta una capa de documentacion modular declarada en `config/proyecto.yml`.

Ejemplo conceptual:

```yaml
flujo:
  tipo_documentacion: modular
  documento_principal:
    nombre: Documentacion Funcional Estructural
    template: input/templates/DA_REQ_CD_IT_plantilla.docx
  modulos:
    - id: paso_02_detalle_cuenta_alnova
      nombre: Detalle cuenta ALNOVA
      intencion: Obtener el universo de cuentas ALNOVA excluyendo cuentas ya identificadas en Finacle
      sql: input/sql/02_detalle_cuenta_alnova.sql
      template: input/templates/DA_REQ_CD_IT_STEP_plantilla.docx
      depende_de:
        - paso_01_finacle_saldos_decrypt
      salida_tablas:
        - ws_ec_cu_bdclientes.cu_cap_universo_cuentas
      tags:
        - alnova
        - universo
        - cuentas
```

Campos soportados por modulo:

- `id`: identificador unico y estable
- `nombre`: nombre legible del modulo
- `intencion`: descripcion funcional corta del modulo
- `sql`: SQL fuente del modulo
- `template`: plantilla step asociada
- `depende_de`: modulos previos requeridos
- `salida_tablas`: tablas publicadas por el SQL
- `tags`: clasificacion corta

Regla actual de construccion:

- `nombre` sale de `@ARCHIVO`
- `intencion` sale de `@DESCRIPCION`
- si alguno viene vacio:
  - se conserva el valor existente en `proyecto.yml` si ya estaba
  - si no existe y el comando es interactivo, se pide captura manual
  - si se usa `--no-prompt`, queda la propuesta automatica o vacio

## Como esta estructurado el JSON intermedio

Ejemplo de salida:

```text
output/json/DA_REQ_CD_IT_02_detalle_cuenta_alnova.json
```

Campos principales del JSON:

- `file_name`: nombre del SQL
- `sql_path`: ruta del archivo SQL
- `target_table`: tabla destino detectada en `INSERT OVERWRITE`
- `raw_sql`: SQL original
- `resolved_sql`: SQL con variables resueltas
- `unresolved_variables`: variables no resueltas si existen
- `auto_resolved_variables`: variables inferidas automaticamente
- `compute_stats_tables`: tablas detectadas en `COMPUTE STATS`
- `ctes`: nombres de CTEs
- `subqueries`: aliases de subconsultas
- `sources`: fuentes logicas detectadas
- `joins`: cruces detectados
- `filters`: filtros `WHERE`
- `transformations`: columnas finales y su clasificacion
- `column_lineage`: linaje fisico por columna final
- `rules`: reglas de negocio inferidas
- `steps`: pasos del proceso
- `metadata`: metadatos del parseo

### `sources`

Cada fuente incluye:

- `alias`
- `table_name`
- `layer`
- `fields_generated`
- `contains_description`
- `used_in_steps`
- `destination_table`
- `source_kind`

`used_in_steps` ya no es una lista fija. Ahora se calcula segun:

- si la fuente aparece en `FROM`
- si vive dentro de `CTE` o `subquery`
- si participa en `JOIN`
- si participa en `WHERE`
- si alimenta columnas del `SELECT` final

Esto significa que `used_in_steps` ya no depende de reglas editoriales fijas, sino de la participacion real de la fuente en el AST del SQL.

### `transformations`

Cada transformacion representa una columna final del `SELECT`.

Campos clave:

- `field_name`
- `field_type`
- `subtype`
- `origin`
- `source_fields`
- `physical_source_fields`
- `description`
- `step`
- `rule_id`

### `column_lineage`

Es el bloque de linaje detallado por columna.

Cada entrada usa una clave canonica en minusculas, por ejemplo:

```json
"id_cuenta": {
  "column_name": "id_cuenta",
  "display_name": "ID_CUENTA",
  "expression_sql": "CONCAT(CTA.BRN_OPEN ,CTA.ACC) AS ID_CUENTA",
  "lineage_type": "derived",
  "source_aliases": ["CTA"],
  "source_columns": ["CTA.BRN_OPEN", "CTA.ACC"],
  "physical_sources": [
    {
      "base_table": "rd_baz_bdclientes.rd_pedt008",
      "source_column": "brn_open",
      "source_table_alias": "rd_pedt008",
      "reference_name": "rd_pedt008.brn_open"
    }
  ],
  "functions": ["CONCAT"]
}
```

Notas:

- `column_name`: nombre canonico
- `display_name`: alias original del SQL
- `lineage_type`: `direct` o `derived`
- `physical_sources`: tabla fisica original y columna fuente
- `functions`: funciones detectadas en la expresion, por ejemplo `CONCAT`, `COALESCE`, `IF`

### `metadata`

Metadatos actuales:

- `statement_count`
- `source_count`
- `field_count`
- `parse_archetype`
- `masked_variables`

Ejemplo de `parse_archetype`:

- `insert_overwrite_curated_table_with_enrichment_with_preparation_layers`

## Como se genera el DOCX

El proceso documental sigue esta secuencia:

1. `sync_variables` deja los SQL con variables claras y valores capturados
2. `sync_modules` actualiza `flujo.modulos` con la secuencia funcional del proceso
3. `run_pipeline` parsea el SQL
4. se construye el modelo `SqlAnalysis`
5. `document.py` renderiza el `.docx`
6. `audit.py` valida el documento generado

El DOCX conserva la estructura funcional esperada:

- Portada
- Seccion 1
- Seccion 2
- Seccion 3
- Seccion 4
- Seccion 5
- Seccion 6
- Seccion 7
- Seccion 8

## Auditoria

La auditoria valida, entre otros puntos:

- presencia de secciones obligatorias
- que los campos finales aparezcan en Seccion 4 y 5
- que las reglas referenciadas existan
- que no haya SQL pegado en el documento
- que el nombre del archivo empiece con `DA_REQ_CD_IT_`

La salida principal de auditoria es `.xlsx`, y tambien se deja un respaldo `.json`.

## Comandos utiles

### Generar contrato ODCS YAML

La utilidad `src/export_datacontract.py` genera un contrato en formato ODCS v3 usando:

- el `SqlAnalysis` actual como fuente principal de campos, reglas y linaje
- una base tabular opcional, preferentemente DuckDB, para enriquecer tipos, `required` y ejemplos
- una DDL de Impala opcional para fijar `physicalType` y columnas particionadas
- un CSV de muestra opcional para ejemplos y para generar `servers.local_csv`
- un diccionario opcional y automatico en `input/diccionario/<tabla>.txt` para descripciones de campos

Ejemplo basico:

```bash
python3 -m src.export_datacontract \
  --sql input/sql/02_cd_cap_portafolio_cuentas_activas/06_cd_cap_portafolio_cuentas_activas.sql \
  --config config/cd_cap_portafolio_cuentas_activas.yml
```

Ejemplo recomendado con DuckDB:

```bash
python3 -m src.export_datacontract \
  --sql input/sql/02_cd_cap_portafolio_cuentas_activas/06_cd_cap_portafolio_cuentas_activas.sql \
  --config config/cd_cap_portafolio_cuentas_activas.yml \
  --profile-db data/duckdb/docgen_profiles.duckdb \
  --profile-table cd_cap_portafolio_cuentas_activas \
  --profile-engine duckdb
```

Compatibilidad con SQLite:

```bash
python3 -m src.export_datacontract \
  --sql input/sql/02_cd_cap_portafolio_cuentas_activas/06_cd_cap_portafolio_cuentas_activas.sql \
  --config config/cd_cap_portafolio_cuentas_activas.yml \
  --sqlite-db /ruta/al/mvp.sqlite \
  --sqlite-table cd_cap_portafolio_cuentas_activas
```

Ejemplo orientado a Data Contract CLI local:

```bash
python3 -m src.export_datacontract \
  --sql input/sql/02_cd_cap_portafolio_cuentas_activas/06_cd_cap_portafolio_cuentas_activas.sql \
  --config config/cd_cap_portafolio_cuentas_activas.yml \
  --ddl /ruta/ddl.txt \
  --csv-sample /ruta/cd_cap_portafolio_cuentas_activas.csv
```

La salida usa `apiVersion: v3.1.0`, `kind: DataContract` y `schema/properties`, que es la
estructura esperada por ODCS. La metadata tecnica del parser se conserva dentro de
`customProperties` a nivel contrato, objeto y campo.

Si se informa `--csv-sample`, el contrato agrega un bloque `servers.local_csv` compatible con
`datacontract test --server local_csv`.

Si existe un archivo como `input/diccionario/cd_cap_portafolio_cuentas_activas.txt`, el exportador
lo usa automaticamente para poblar las descripciones de las columnas por nombre de campo.

Si existe un archivo como `input/ddl/cd_cap_portafolio_cuentas_activas.txt`, el exportador
lo usa automaticamente para poblar `physicalType`, `logicalType` y columnas particionadas,
sin necesidad de pasar `--ddl`, pero solo cuando no se informa una base de profile.

El nombre de salida por default es `output/datacontract/<sql_stem>.yaml`.

### Instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install python-docx sqlglot sqlparse pydantic pandas openpyxl pyyaml pytest
pip install duckdb
```

### Sincronizar variables de todos los SQL

```bash
python3 -m src.sync_variables --dir input/sql
```

### Sincronizar variables sin preguntas

```bash
python3 -m src.sync_variables --dir input/sql --no-prompt
```

### Sincronizar modulos del flujo

```bash
.venv/bin/python -m src.sync_modules --dir input/sql
```

### Sincronizar modulos sin preguntas

```bash
.venv/bin/python -m src.sync_modules --dir input/sql --no-prompt
```

### Generar documento para un SQL

```bash
.venv/bin/python -m src.run_pipeline --sql input/sql/02_detalle_cuenta_alnova.sql
```

### Ejecutar pruebas

```bash
.venv/bin/pytest -q
```

## Estado actual del parser

El parser actual ya incluye:

- parseo con `sqlglot` usando dialecto `hive`
- `qualify` para analisis estructural
- AST walk para columnas, joins y filtros
- linaje fisico de columnas finales
- clasificacion de columnas directas y derivadas
- identificacion de funciones
- inferencia real de `used_in_steps`

El proyecto tambien incluye:

- sincronizacion automatica de variables `${...}`
- sincronizacion de modulos funcionales desde encabezados SQL
- definicion del flujo funcional de N SQL en `proyecto.yml`

## Recomendaciones de uso

- Ejecutar primero `sync_variables`
- Ejecutar despues `sync_modules`
- Mantener `config/proyecto.yml` como fuente maestra de valores estaticos
- Mantener `flujo.modulos` como fuente maestra del orden funcional del proceso
- Ejecutar `run_pipeline` con `.venv/bin/python`
- Revisar siempre el JSON intermedio antes de ajustar el renderer DOCX
- Usar la auditoria como control de calidad minimo

## Troubleshooting

### `ModuleNotFoundError: No module named 'openpyxl'`

Esto pasa cuando ejecutas `src.run_pipeline` con el `python3` del sistema en vez del entorno virtual.

Usa:

```bash
.venv/bin/python -m src.run_pipeline --sql input/sql/02_detalle_cuenta_alnova.sql
```

Si falta el entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install python-docx sqlglot sqlparse pydantic pandas openpyxl pyyaml pytest
```

### `ModuleNotFoundError: No module named 'yaml'`

Esto suele pasar al usar comandos que dependen de `src.config` con el `python3` del sistema.

Casos:

- `src.run_pipeline` requiere `.venv/bin/python`
- `src.sync_variables` no depende de `pyyaml`, por lo que si se ejecuta directo con `python3` del sistema debe funcionar

Si un comando falla por dependencias, usa el Python del entorno virtual:

```bash
.venv/bin/python -m src.run_pipeline --sql input/sql/02_detalle_cuenta_alnova.sql
```

### `@DESCRIPCION` viene vacia en el SQL

`src.sync_modules` toma:

- `@ARCHIVO` -> `nombre`
- `@DESCRIPCION` -> `intencion`

Si `@DESCRIPCION` esta vacia:

- si ya existe una `intencion` previa en `config/proyecto.yml`, se conserva
- si ejecutas en modo interactivo, el comando te pedira capturarla
- si usas `--no-prompt`, dejara la propuesta automatica o el valor vacio

Modo interactivo:

```bash
.venv/bin/python -m src.sync_modules --sql input/sql/02_detalle_cuenta_alnova.sql
```

Modo no interactivo:

```bash
.venv/bin/python -m src.sync_modules --sql input/sql/02_detalle_cuenta_alnova.sql --no-prompt
```

### El JSON no aparece en `output/json`

Verifica:

1. que corriste `src.run_pipeline`
2. que lo corriste con `.venv/bin/python`
3. que el SQL tenga una sentencia `INSERT OVERWRITE`

Comando correcto:

```bash
.venv/bin/python -m src.run_pipeline --sql input/sql/02_detalle_cuenta_alnova.sql
```

### El SQL no actualiza el bloque `@PARAMETROS`

Verifica que el archivo tenga el marcador:

```sql
--| @PARAMETROS
```

Luego vuelve a correr:

```bash
python3 -m src.sync_variables --dir input/sql
```

El bloque se actualizará con formato:

```sql
--| @PARAMETROS
--|     # ${variable} = valor
```

### `flujo.modulos` no refleja un SQL nuevo

Después de agregar o cambiar SQL en `input/sql`, vuelve a ejecutar:

```bash
.venv/bin/python -m src.sync_modules --dir input/sql
```

Si el encabezado del SQL no trae `@ARCHIVO` o `@DESCRIPCION`, el módulo puede quedar incompleto y requerirá captura manual.

### `used_in_steps` parece diferente a lo esperado

`used_in_steps` ya no es una lista fija. Ahora se infiere desde el AST del SQL y el linaje real.

Se calcula según:

- fuente principal del `FROM`
- participación en `JOIN`
- uso en `WHERE`
- uso en columnas del `SELECT`
- existencia dentro de `CTE` o `subquery`

Si el resultado parece extraño, revisa primero el SQL parseado y el bloque `sources` del JSON intermedio.

### El nombre de columna aparece diferente entre SQL y JSON

En `column_lineage`:

- la clave del diccionario es canónica y va en minúsculas
- el nombre original del SQL se conserva en `display_name`

Ejemplo:

```json
"id_cuenta": {
  "column_name": "id_cuenta",
  "display_name": "ID_CUENTA"
}
```

Eso es normal y evita duplicidades en el JSON.

## Estado de pruebas

Actualmente la suite automatizada valida:

- deteccion de `INSERT OVERWRITE`
- extraccion de columnas finales
- resolucion de variables
- enmascaramiento seguro de variables no resueltas
- auditoria documental
- sincronizacion de variables
- sincronizacion de modulos
- linaje por columna
- inferencia de `used_in_steps`
