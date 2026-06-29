# GitHub Readiness

Esta guia deja claro que se debe publicar y que se debe reconstruir al clonar.

## Recomendacion

No publiques una copia literal del entorno local. Publica una **receta reproducible**.

La receta correcta para este repo es:

1. Codigo fuente y configuracion versionada.
2. `docker-compose.yml` para infraestructura local.
3. `.env.example` sin secretos.
4. Migraciones SQL y seeds sanitizados.
5. Scripts de bootstrap y diagnostico.

## Si conviene subir

- `README.md`
- `docker-compose.yml`
- `infra/`
- `docs/`
- `sql/`
- `apps/` con codigo fuente, plantillas y configuracion ejemplo
- `apps/docgen-sql/supabase/migrations/`
- `.env.example`
- `config.credentials.json.example`
- `scripts/`

## No conviene subir

- `.env`
- `config.credentials.json`
- credenciales embebidas en YAML, TOML o Markdown
- `volumes/` con Postgres, SQLite, DuckDB o archivos en caliente
- `apps/docgen-sql/output/`
- `.run/`
- `node_modules/`
- entornos virtuales
- archivos `.DS_Store`

## Bases de datos

### No subir

No subas carpetas de datos como:

- `volumes/entropy-postgres/`
- `volumes/redash-postgres/`
- `volumes/answer-data/`
- `volumes/dashboard-duckdb/`

Esas carpetas contienen estado local, archivos bloqueados, PIDs, configuracion generada y potencialmente datos sensibles.

### Si subir

Sube la definicion de las bases:

- migraciones
- scripts SQL de inicializacion
- seeds pequenos y sanitizados
- instrucciones de restauracion

## Que falta para una replicacion 100% completa

Hoy el repo ya puede recrear infraestructura y parte de la configuracion, pero faltaria definir de forma explicita:

- seeds sanitizados para Redash si se quieren dashboards prearmados
- seed o dump sanitizado para Apache Answer si se quiere contenido inicial
- estrategia de datos demo para DuckDB y cualquier fuente externa
- un origen replicable para cualquier conexion a SQL Server corporativo

## Regla practica

Si un archivo cambia por ejecutar el sistema, casi seguro no debe ir al repo.

Si un archivo explica como crear el sistema desde cero, casi seguro si debe ir al repo.
