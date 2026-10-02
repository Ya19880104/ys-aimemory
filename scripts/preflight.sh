#!/usr/bin/env bash
# Read-only validation. Never prints resolved credentials; does not deploy.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v docker >/dev/null || { echo 'Docker with Compose v2 is required on the VM.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3 is required for preflight.' >&2; exit 1; }
args=()
if [[ "${1:-}" == --tls ]]; then
  args=(--profile tls)
  for cert in nginx/certs/fullchain.pem nginx/certs/privkey.pem; do
    [[ -s "$cert" ]] || { echo "Missing operator-provided certificate file: $cert" >&2; exit 1; }
  done
elif [[ $# -gt 0 ]]; then
  echo 'Usage: scripts/preflight.sh [--tls]' >&2; exit 2
fi
docker compose "${args[@]}" config --format json | python3 scripts/validate-compose.py
echo 'Configuration checks passed. Runtime, certificate trust, and PostgreSQL restore tests are still required.'
