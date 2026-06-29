#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

section() {
  printf '\n[%s]\n' "$1"
}

show_matches() {
  local pattern="$1"
  shift
  rg -n --hidden --glob '!.git' "$pattern" "$@" 2>/dev/null || true
}

section "Large local state"
du -sh volumes apps/docgen-sql/output .run 2>/dev/null || true

section "Files that should stay out of GitHub"
find . -maxdepth 3 \( -name '.env' -o -name '.env.local' -o -name 'config.credentials.json' -o -path './volumes/*' -o -path './apps/docgen-sql/output/*' \) 2>/dev/null | head -n 200

section "Possible absolute paths"
show_matches '/Users/|/private/|[A-Za-z]:\\\\' . \
  --glob '!apps/docgen-sql/output/**' \
  --glob '!apps/datacontract-editor/dist/**'

section "Possible inline secrets"
show_matches '(API_KEY|TOKEN|SECRET|PASSWORD)[^[:alnum:]]*[:=][^[:space:]]+' . \
  --glob '!.env.example' \
  --glob '!config.credentials.json' \
  --glob '!**/*.md' \
  --glob '!**/tests/**' \
  --glob '!apps/datacontract-editor/dist/**'

section "Done"
printf 'Review the findings above before publishing the repository.\n'
