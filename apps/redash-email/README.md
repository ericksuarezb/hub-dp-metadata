# Redash Email Export

Integracion local basada en `StarfishStorage/redash-email` para exportar dashboards
de Redash a `PDF` o `PNG` y opcionalmente enviarlos por correo.

## Variables

- `REDASH_EXPORT_API_KEY`: API key de un usuario con acceso al dashboard.
- `REDASH_EXPORT_DASHBOARD`: nombre exacto del tablero. Default: `BAZ | CAPTACION MOCK`.
- `REDASH_EXPORT_RECIPIENTS`: lista separada por comas.
- `REDASH_EXPORT_SENDER`: remitente del correo.
- `REDASH_EXPORT_MAILHOST_URL`: SMTP interno, por defecto `smtp://mailhog:1025`.
- `REDASH_EXPORT_RENDER_DELAY`: segundos extra para esperar el render del dashboard.
- `REDASH_EXPORT_NAVIGATION_TIMEOUT`: timeout del navegador headless.

## Uso

Prueba local sin enviar correo:

```bash
docker compose --profile redash-export run --rm redash-exporter
```

Enviar correo real:

```bash
docker compose --profile redash-export run --rm redash-exporter /tmp/report.yaml --verbose
```

Los archivos quedan en `volumes/redash-reports/<timestamp>/`.
