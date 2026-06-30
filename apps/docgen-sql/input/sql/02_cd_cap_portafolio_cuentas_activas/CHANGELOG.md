# Changelog

Todos los cambios notables de este proyecto serán documentados en este archivo.

El formato está basado en Keep a Changelog.

## [Unreleased]

### Fixed
- `apps/docgen-sql/src/sql_parser.py`
  - Se corrigió la detección de publicaciones soportadas para reconocer sentencias `CREATE TABLE ... AS WITH ... SELECT`.
  - El parser ahora usa el AST de `sqlglot` para distinguir `INSERT` y `CREATE TABLE AS SELECT`, evitando falsos negativos cuando el `SELECT` final viene precedido por CTEs.

### Added
- `apps/docgen-sql/tests/test_sql_parser.py`
  - Se agregó cobertura para CTAS con bloque `WITH`.
  - Se ajustó la expectativa de publicaciones múltiples para reflejar tablas intermedias detectadas correctamente.

## [1.0.0] - 2026-04-29

### Added
- `01_finacle_saldos_decrypt.sql`
  - Se agregó el campo `plazodeposito` al resultado final de la tabla `cu_finacle_saldos_decrypt`.
  - Se agregaron sentencias comentadas para `DROP TABLE` y `CREATE TABLE ... STORED AS PARQUET`.

- `02_detalle_cuenta_alnova.sql`
  - Se agregó el campo `plazodeposito` como cadena vacía para cuentas provenientes de Alnova.

- `02_detalle_cuenta_finacle.sql`
  - Se agregó el campo `plazodeposito` al detalle de cuentas Finacle.
  - Se incluye `plazodeposito` desde `cu_finacle_saldos_decrypt`.

### Changed
- `03_familia_producto_cat.sql`
  - Se modificó la generación de `cod_producto_nivel_07`.
  - Para los productos `PF-0022` y `PF-0002`, ahora se concatena la descripción del producto con el plazo de depósito en días.
  - Para el resto de productos, se mantiene el valor original de `fcnuevo_producto_nivel_07`.

### Fixed
- Se homologó la estructura entre cuentas Alnova y Finacle agregando el campo `plazodeposito`, evitando diferencias de esquema en procesos posteriores.

## [1.0.0] - 2026-04-29

### Added
- Versión inicial de los scripts SQL:
  - `01_finacle_saldos_decrypt.sql`
  - `02_detalle_cuenta_alnova.sql`
  - `02_detalle_cuenta_finacle.sql`
  - `03_familia_producto_cat.sql`
  - `04_saldo_disponible_ctas.sql`
  - `05_identificador_ctes.sql`
  - `06_cd_cap_portafolio_cuentas_activas.sql`
