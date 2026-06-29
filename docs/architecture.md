# Arquitectura inicial

## Objetivo

Tener un "hub" local que permita:

- una landing central para entrar a todas las herramientas;
- cada aplicacion aislada como servicio independiente;
- una estructura preparada para agregar nuevas apps sin reordenar todo;
- persistencia y configuracion separadas de la capa de presentacion.

## Decision de estructura

Se propone un monorepo de infraestructura y experiencia de acceso:

- `apps/landing/`: landing page y futura UI de acceso comun;
- `infra/caddy/`: proxy reverso y reglas de enrutamiento;
- `docs/`: decisiones de arquitectura, onboarding y runbooks;
- `volumes/`: persistencia local de servicios stateful;
- `docker-compose.yml`: orquestacion local del stack.

## Topologia actual

- `http://localhost`: landing principal;
- `http://editor.localhost`: Data Contract Editor;
- `http://entropy.localhost`: Entropy Data CE;
- `http://answer.localhost`: Apache Answer para Q&A tecnico y futura experiencia Crystal;
- `http://redash.localhost`: Redash para dashboards y exploracion SQL;
- `http://mail.localhost`: Mailhog para pruebas locales.

## Estrategia de datos

Separamos claramente la capa de aplicaciones del camino de acceso a datos:

- `SQL Server` es la fuente oficial objetivo para visualizacion y consumo analitico;
- `DuckDB` se considera una via temporal y tactica para exploracion rapida;
- `Entropy` mantiene su propia persistencia operativa en `Postgres`;
- `Redash` se incorpora como capa BI del hub, idealmente apuntando a `SQL Server`.

### Implicacion importante

Redash soporta `Microsoft SQL Server` de forma nativa, pero `DuckDB` no es una
fuente soportada de forma nativa dentro de Redash. Por eso:

- el camino recomendado para Redash es `SQL Server`;
- DuckDB queda como herramienta temporal de trabajo rapido, fuera del flujo
  principal de dashboards;
- si se quisiera mostrar informacion originada en DuckDB dentro de Redash,
  haria falta exportarla o replicarla a una fuente compatible.

## Criterios para agregar nuevas apps

1. Crear un servicio nuevo en `docker-compose.yml`.
2. Agregar una regla de host en `infra/caddy/Caddyfile`.
3. Añadir una tarjeta en la landing.
4. Si la app requiere estado, crear su carpeta bajo `volumes/`.
5. Si la app necesita configuracion especial, documentarla en `docs/`.

## Integracion de Apache Answer

Apache Answer se incorpora como stack complementario para conversaciones
tecnicas, FAQs y navegacion hacia catalogos curados.

- Host sugerido: `answer.localhost`
- Puerto local directo: `9080`
- Persistencia: `volumes/answer-data`
- Rol dentro del hub: capa de Q&A y base de integracion para Crystal

La decision derivada de `docs/vista-crystal-integration-evaluation.md` es no
importar el HTML de Crystal tal cual en la landing del hub. En cambio, el hub
expone Apache Answer como nueva app y deja la experiencia Crystal para una fase
posterior dentro de Answer mediante un plugin de ruta tipo `/crystal`.

## Integracion de Redash

Redash se integra con perfil opcional `redash` para no cargar el arranque base.
El stack incluye:

- `redash-server`
- `redash-scheduler`
- `redash-scheduled-worker`
- `redash-adhoc-worker`
- `redash-worker`
- `redash-postgres`
- `redash-redis`

Esto mantiene el hub modular y permite activar dashboards solo cuando se
necesiten.

## Escalado recomendado

Cuando el hub crezca, la siguiente evolucion natural seria:

- separar `compose` base y `compose.override` por entorno;
- mover secretos a un manejador seguro;
- sustituir la landing estatica por una app ligera propia;
- incorporar autenticacion comun delante del gateway si hiciera falta.
