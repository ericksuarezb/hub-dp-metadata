#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCGEN_DIR="$ROOT_DIR/apps/docgen-sql"
DOCGEN_WEB_DIR="$DOCGEN_DIR/web"

info() {
  printf '[bootstrap] %s\n' "$*"
}

warn() {
  printf '[bootstrap] WARNING: %s\n' "$*" >&2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[bootstrap] ERROR: missing command: %s\n' "$1" >&2
    exit 1
  }
}

copy_if_missing() {
  local src="$1"
  local dst="$2"
  if [[ ! -e "$dst" ]]; then
    cp "$src" "$dst"
    info "Created $(basename "$dst") from template"
  fi
}

require_cmd docker
require_cmd python3
require_cmd npm

mkdir -p \
  "$ROOT_DIR/.run/logs" \
  "$ROOT_DIR/volumes/entropy-postgres" \
  "$ROOT_DIR/volumes/redash-postgres" \
  "$ROOT_DIR/volumes/redash-reports" \
  "$ROOT_DIR/volumes/answer-data" \
  "$ROOT_DIR/volumes/dashboard-duckdb"

copy_if_missing "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
copy_if_missing "$ROOT_DIR/config.credentials.json.example" "$ROOT_DIR/config.credentials.json"

if [[ ! -d "$DOCGEN_DIR/.venv" ]]; then
  info "Creating Python virtualenv for docgen-sql"
  python3 -m venv "$DOCGEN_DIR/.venv"
fi

info "Installing docgen-sql Python dependencies"
"$DOCGEN_DIR/.venv/bin/pip" install -U pip
"$DOCGEN_DIR/.venv/bin/pip" install -e "$DOCGEN_DIR[web,dev]"

info "Installing docgen-sql web dependencies"
(
  cd "$DOCGEN_WEB_DIR"
  npm install
)

info "Bootstrap complete"
info "Next steps:"
printf '  1. Review %s/.env and %s/config.credentials.json\n' "$ROOT_DIR" "$ROOT_DIR"
printf '  2. Start infra with: cd %s && docker compose up -d\n' "$ROOT_DIR"
printf '  3. Optionally run: cd %s && ./.venv/bin/docgen-sql-doctor\n' "$DOCGEN_DIR"

warn "This script does not restore real business data. Use migrations and sanitized seeds for shareable demo data."
