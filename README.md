# Document Hub

Base inicial para montar un hub de aplicaciones orientadas a gestion documental,
data contracts y metadata.

## Incluye

- Landing central en `http://localhost`
- Master Wiki inicial en `http://localhost/master-wiki/`
- DocGen SQL Web en `http://docgen.localhost`
- Data Contract Editor en `http://editor.localhost`
- Entropy Data CE en `http://entropy.localhost`
- Apache Answer en `http://answer.localhost`
- Redash en `http://redash.localhost`
- Mailhog en `http://mail.localhost`
- Exportador PDF de Redash en `apps/redash-email` con salida en `volumes/redash-reports`

## Estructura

```text
.
├── apps/
│   └── landing/
│       └── site/
├── docs/
├── infra/
│   └── caddy/
├── volumes/
├── .env.example
└── docker-compose.yml
```

## Primer arranque

1. Copia `.env.example` a `.env`
2. Ejecuta `docker compose up -d`
3. Abre `http://localhost`

Bootstrap sugerido para una clonacion nueva:

```bash
./scripts/bootstrap.sh
```

Credenciales locales:

- infraestructura Docker: `.env`
- integraciones externas y tokens de la app: `config.credentials.json`
- plantilla segura: `config.credentials.json.example`

## Arranque de Redash

Redash queda como stack opcional:

1. Completa `REDASH_SECRET_KEY` y `REDASH_COOKIE_SECRET` en `.env`
2. Inicializa su base: `docker compose --profile redash run --rm redash-server create_db`
3. Levanta Redash: `docker compose --profile redash up -d redash-server redash-scheduler redash-scheduled-worker redash-adhoc-worker redash-worker redash-postgres redash-redis`
4. Abre `http://redash.localhost`

## Arranque de Apache Answer

Apache Answer queda integrado como pieza del hub para centralizar Q&A tecnico y
servir como base de la futura experiencia Crystal.

1. Levanta el servicio: `docker compose --profile answer up -d apache-answer`
2. Si tambien quieres exponerlo por la landing del hub: `docker compose --profile hub --profile answer up -d gateway landing apache-answer`
3. Abre `http://answer.localhost`

Persistencia:

- los datos de Answer quedan en `volumes/answer-data/`
- la siguiente evolucion recomendada es un plugin `/crystal` dentro de Answer, segun `docs/vista-crystal-integration-evaluation.md`

## Exportar dashboard de Redash a PDF

Se integro un servicio opcional `redash-exporter` basado en `StarfishStorage/redash-email`.

1. Define en `.env` el API key de Redash con `REDASH_EXPORT_API_KEY`
2. Ajusta si hace falta `REDASH_EXPORT_DASHBOARD`, por defecto `BAZ | CAPTACION MOCK`
3. Ejecuta una prueba sin enviar correo:
   `docker compose --profile redash-export run --rm redash-exporter`
5. El PDF quedara en `volumes/redash-reports/<timestamp>/`

Para enviar el correo real en lugar de solo validar el render:

`docker compose --profile redash-export run --rm redash-exporter /tmp/report.yaml --verbose`

Notas:

- El `CMD` por defecto del exportador corre con `--dry-run --verbose`
- `Mailhog` sigue siendo el SMTP local por defecto
- Este enfoque usa el link publico del dashboard, asi que falla si el tablero depende de parametros `Text` no compartibles en Redash

## Ruta de datos recomendada

- `Redash` debe conectarse principalmente a `SQL Server`, que es la fuente oficial objetivo.
- `DuckDB` puede seguir existiendo como via temporal de analisis rapido.
- `DuckDB` no es una fuente nativa de Redash, asi que no debe asumirse como integracion directa de dashboards.

## Publicacion en GitHub

Para que otras personas puedan clonar y replicar este proyecto, **no conviene subir el estado vivo de `volumes/` ni los outputs generados**. La estrategia recomendada es:

- versionar codigo, configuracion, `docker-compose.yml`, scripts de bootstrap, migraciones SQL y ejemplos de configuracion
- excluir `.env`, tokens, llaves, bases de datos locales, `output/`, `node_modules/` y logs
- recrear bases y servicios con `docker compose`, migraciones y seeds sanitizados

Guia detallada:

- [docs/github-readiness.md](docs/github-readiness.md)

Chequeo rapido antes de publicar:

```bash
./scripts/repo-doctor.sh
```

## Notas

- `entropy-data-ce` requiere Postgres y por eso se incluye `entropy-postgres`.
- `mailhog` se deja como SMTP local para desarrollo.
- `apache-answer` queda como capa de Q&A y punto natural para alojar la integracion Crystal.
- La estructura esta pensada para sumar mas apps manteniendo una sola puerta de entrada.

## Referencias

- [Data Contract Editor](https://github.com/datacontract/datacontract-editor)
- [Entropy Data CE](https://github.com/entropy-data/entropy-data-ce)
- [Apache Answer](https://github.com/apache/answer)
- [Redash](https://github.com/getredash/redash)
