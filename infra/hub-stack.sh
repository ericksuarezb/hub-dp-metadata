#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCGEN_DIR="$ROOT_DIR/apps/docgen-sql"
DOCGEN_WEB_DIR="$DOCGEN_DIR/web"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$RUN_DIR/logs"

BACKEND_LOG_FILE="$LOG_DIR/docgen-api.log"
FRONTEND_LOG_FILE="$LOG_DIR/docgen-web.log"

DOCGEN_API_LABEL="local.hub.docgen.api"
DOCGEN_WEB_LABEL="local.hub.docgen.web"
DOCGEN_PYTHON="$DOCGEN_DIR/.venv/bin/python"
NODE_BIN="/usr/local/bin/node"
VITE_BIN="$DOCGEN_WEB_DIR/node_modules/vite/bin/vite.js"

mkdir -p "$LOG_DIR"

info() {
  printf '[hub] %s\n' "$*"
}

warn() {
  printf '[hub] WARNING: %s\n' "$*" >&2
}

fail() {
  printf '[hub] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

port_is_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_port() {
  local port="$1"
  local attempts="${2:-20}"

  for ((i = 0; i < attempts; i += 1)); do
    if port_is_listening "$port"; then
      return 0
    fi
    sleep 1
  done

  return 1
}

pid_is_running() {
  local pid="$1"
  kill -0 "$pid" >/dev/null 2>&1
}

launchctl_has_job() {
  local label="$1"
  launchctl list | rg -F "$label" >/dev/null 2>&1
}

launchctl_remove_job() {
  local label="$1"
  launchctl remove "$label" >/dev/null 2>&1 || true
}

submit_launchctl_job() {
  local label="$1"
  local command="$2"

  launchctl_remove_job "$label"
  launchctl submit -l "$label" -- /bin/zsh -lc "$command"
}

terminal_run() {
  local command="$1"
  osascript - "$command" <<'EOF'
on run argv
tell application "Terminal"
  activate
  do script (item 1 of argv)
end tell
end run
EOF
}

start_docgen_api() {
  if port_is_listening 8316; then
    info "DocGen API already listening on 8316"
    return 0
  fi

  [[ -x "$DOCGEN_DIR/.venv/bin/python" ]] || fail "Missing DocGen virtualenv at $DOCGEN_DIR/.venv"

  info "Starting DocGen API on 8316"
  : >"$BACKEND_LOG_FILE"
  terminal_run "cd \"$DOCGEN_DIR\" && \"$DOCGEN_PYTHON\" -m uvicorn src.web_api:app --host 127.0.0.1 --port 8316 | tee -a \"$BACKEND_LOG_FILE\""

  if ! wait_for_port 8316 20; then
    warn "DocGen API did not start on 8316. Check $BACKEND_LOG_FILE"
  fi
}

start_docgen_web() {
  if port_is_listening 8310; then
    info "DocGen Web already listening on 8310"
    return 0
  fi

  [[ -d "$DOCGEN_WEB_DIR/node_modules" ]] || fail "Missing node_modules in $DOCGEN_WEB_DIR"
  [[ -x "$NODE_BIN" ]] || fail "Missing node runtime at $NODE_BIN"
  [[ -f "$VITE_BIN" ]] || fail "Missing Vite entrypoint at $VITE_BIN"

  info "Starting DocGen Web on 8310"
  : >"$FRONTEND_LOG_FILE"
  terminal_run "cd \"$DOCGEN_WEB_DIR\" && \"$NODE_BIN\" \"$VITE_BIN\" --host 0.0.0.0 --port 8310 | tee -a \"$FRONTEND_LOG_FILE\""

  if ! wait_for_port 8310 20; then
    warn "DocGen Web did not start on 8310. Check $FRONTEND_LOG_FILE"
  fi
}

stop_docgen() {
  launchctl_remove_job "$DOCGEN_API_LABEL"
  launchctl_remove_job "$DOCGEN_WEB_LABEL"

  pkill -f "uvicorn src.web_api:app --host 127.0.0.1 --port 8316" >/dev/null 2>&1 || true
  pkill -f "vite --host 0.0.0.0 --port 8310" >/dev/null 2>&1 || true
  pkill -f "/usr/local/bin/node .*vite.* --host 0.0.0.0 --port 8310" >/dev/null 2>&1 || true
}

start_supabase() {
  require_cmd npx
  info "Ensuring Supabase local stack is up"
  if ! (
    cd "$DOCGEN_DIR"
    npx supabase start
  ); then
    warn "Supabase did not reach healthy state. The rest of the hub will still start."
  fi
}

stop_supabase() {
  require_cmd npx
  info "Stopping Supabase local stack"
  if ! (
    cd "$DOCGEN_DIR"
    npx supabase stop
  ); then
    warn "Supabase stop reported an issue. Continuing with the rest of the shutdown."
  fi
}

start_hub_docker() {
  require_cmd docker
  info "Starting Docker services for hub"
  (
    cd "$ROOT_DIR"
    docker compose --profile hub --profile answer --profile redash up -d
  )
}

stop_hub_docker() {
  require_cmd docker
  info "Stopping Docker services for hub"
  (
    cd "$ROOT_DIR"
    docker compose --profile hub --profile answer --profile redash down
  )
}

print_status() {
  info "Docker compose status"
  (
    cd "$ROOT_DIR"
    docker compose ps
  )

  info "Supabase containers"
  docker ps --format '{{.Names}}\t{{.Status}}' | rg '^supabase_' || true

  info "DocGen local ports"
  lsof -nP -iTCP:8310 -sTCP:LISTEN || true
  lsof -nP -iTCP:8316 -sTCP:LISTEN || true

  info "Fixed routes"
  cat <<'EOF'
http://localhost/
http://docgen.localhost/
http://answer.localhost/
http://redash.localhost/
http://editor.localhost/
http://entropy.localhost/
http://mail.localhost/
Supabase Studio: http://127.0.0.1:55423/
Supabase REST:   http://127.0.0.1:55421/rest/v1
EOF
}

start_all() {
  start_hub_docker
  start_supabase
  start_docgen_api
  start_docgen_web
  info "Hub stack started"
}

stop_all() {
  stop_docgen
  stop_supabase
  stop_hub_docker
  info "Hub stack stopped"
}

restart_all() {
  stop_docgen
  stop_hub_docker
  stop_supabase
  start_all
}

usage() {
  cat <<'EOF'
Usage: infra/hub-stack.sh <start|stop|restart|status>
EOF
}

main() {
  local action="${1:-}"

  case "$action" in
    start)
      start_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      restart_all
      ;;
    status)
      print_status
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
