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

## Modulos del hub

Este repositorio arma un hub local de gobierno, documentacion y operacion de data products. La idea general es que `DocGen SQL Web` normaliza SQL operativo y lo convierte en artefactos funcionales; `Supabase` actua como staging interoperable para corridas, contratos y payloads; `Entropy CE Control de ingestion` decide que corridas promover y dispara la importacion; `Entropy Data CE` recibe el resultado como catalogo y capa de gobierno; `Data Contract Editor` permite revisar y ajustar contratos ODCS; `Redash` y `Apache Answer` completan la experiencia con analitica, consulta operativa y conocimiento compartido; `Mailhog` y `Master Wiki` funcionan como soporte transversal del entorno. Todo queda expuesto detras de la misma puerta de entrada local para que el flujo entero se pueda probar de punta a punta en una sola workstation.

### DocGen SQL Web

Herramienta principal para cargar SQL, variables y metadata funcional, y generar `JSON`, `DOCX`, auditoria y contrato ODCS desde una UI web.

- Base de datos: usa `Supabase/Postgres` como persistencia opcional de corridas y `DuckDB` como apoyo tactico para profiles y exploracion local.
- Acceso: `http://docgen.localhost`
- Integracion con el hub: es el punto de entrada del flujo. Produce los artefactos que luego se revisan en el editor, se almacenan en staging y eventualmente se publican hacia Entropy.

### Entropy CE Control de ingestion

Modulo de control para decidir por `run_id` que corridas deben incluirse en la publicacion hacia Entropy y para ejecutar la importacion sin depender directamente de la UI de DocGen.

- Base de datos: consume el staging de `Supabase/Postgres`, donde viven las corridas, bundles y registros auxiliares para importacion.
- Acceso: `http://localhost/entropy-control/`
- Integracion con el hub: desacopla la generacion de artefactos de la promocion al catalogo. Esto permite revisar, filtrar y orquestar que entra a Entropy antes de ejecutar la carga final.

### Data Contract Editor

Editor visual y YAML para crear, corregir, validar y comparar contratos de datos en formato ODCS.

- Base de datos: no mantiene una base de datos propia en este stack; trabaja sobre archivos y puede leer o guardar versiones apoyandose en `Supabase`.
- Acceso: `http://editor.localhost`
- Integracion con el hub: sirve como capa de curacion manual para los contratos generados por DocGen antes de publicarlos o reutilizarlos en otros flujos del ecosistema.

### Entropy Data CE

Catalogo y capa de gobierno donde se publican data products, esquemas, contratos, activos y relaciones de linaje.

- Base de datos: `Postgres` dedicado en `entropy-postgres`, levantado con imagen `pgvector/pgvector:pg16`.
- Acceso: `http://entropy.localhost`
- Integracion con el hub: es el destino de publicacion del flujo. Recibe la metadata curada desde DocGen y el modulo de control, y la convierte en una vista navegable de gobierno y catalogacion.

### Apache Answer

Base de conocimiento y Q&A tecnico para capturar runbooks, decisiones, preguntas frecuentes y soporte operativo alrededor del hub.

- Base de datos: persistencia local en `volumes/answer-data/`, administrada por la propia aplicacion.
- Acceso: `http://answer.localhost`
- Integracion con el hub: complementa el catalogo formal con conocimiento operativo. Es el lugar natural para documentar decisiones, troubleshooting y futuras extensiones tipo plugin de Crystal.

### Redash

Herramienta de consultas, visualizacion y dashboards para exploracion y consumo analitico de datos.

- Base de datos: metadata interna en `redash-postgres` y cola de trabajo en `redash-redis`; los datasets de negocio se consultan desde fuentes externas que Redash tenga configuradas.
- Acceso: `http://redash.localhost`
- Integracion con el hub: aporta observabilidad y consumo analitico sobre los datos ya publicados o disponibles en fuentes operativas, y se complementa con el exportador PDF para distribucion controlada.

### Mailhog

Servidor SMTP y visor de correos para desarrollo local.

- Base de datos: no usa una base relacional dedicada; captura mensajes en memoria para inspeccion local.
- Acceso: `http://mail.localhost`
- Integracion con el hub: centraliza el correo saliente de Entropy, Redash y otros modulos del stack para validar notificaciones sin depender de infraestructura externa.

### Master Wiki

Indice maestro de guias, runbooks, decisiones, accesos y rutas sugeridas dentro del entorno.

- Base de datos: no usa base de datos; es contenido estatico servido desde la landing del hub.
- Acceso: `http://localhost/master-wiki/`
- Integracion con el hub: funciona como capa de orientacion humana. Une las aplicaciones, explica el flujo general y reduce el costo de onboarding para quien entra al stack por primera vez.

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
