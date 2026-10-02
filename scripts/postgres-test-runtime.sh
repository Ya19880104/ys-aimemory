#!/usr/bin/env bash
# Execute a command against a disposable PostgreSQL cluster, then stop/delete it.
# Only a private Unix socket is opened; there is no TCP listener or password.
# Example: PG_TEST_RUNTIME_ROOT=/tmp/pg18/root scripts/postgres-test-runtime.sh \
#   .venv/bin/python -m pytest -q
# A normal PostgreSQL install also works: PG_TEST_BINDIR=/usr/lib/postgresql/18/bin
set -euo pipefail
umask 077
[[ $# -gt 0 ]] || { echo 'Usage: scripts/postgres-test-runtime.sh COMMAND [ARGS...]' >&2; exit 2; }
[[ $(id -u) != 0 ]] || { echo 'PostgreSQL tests must run as a non-root user.' >&2; exit 2; }
if [[ -n ${PG_TEST_RUNTIME_ROOT:-} ]]; then
  PG_TEST_BINDIR="$PG_TEST_RUNTIME_ROOT/usr/lib/postgresql/18/bin"
  export LD_LIBRARY_PATH="$PG_TEST_RUNTIME_ROOT/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
: "${PG_TEST_BINDIR:?Set PG_TEST_BINDIR or PG_TEST_RUNTIME_ROOT to your test runtime}"
for binary in postgres initdb pg_ctl createdb dropdb pg_dump pg_restore; do
  [[ -x "$PG_TEST_BINDIR/$binary" ]] || { echo "Missing runtime binary: $binary" >&2; exit 2; }
done
export PATH="$PG_TEST_BINDIR:$PATH"
work=$(mktemp -d "${TMPDIR:-/tmp}/ys-pg-test.XXXXXXXX")
started=0
cleanup() {
  local code=$?
  trap - EXIT INT TERM
  if [[ $started == 1 && -f "$work/data/postmaster.pid" ]]; then
    if ! pg_ctl -D "$work/data" -m immediate -w stop > "$work/stop.log" 2>&1; then
      echo "Unable to stop test server; preserving $work for inspection." >&2
      cat "$work/stop.log" >&2
      exit 1
    fi
  fi
  if [[ $code != 0 ]]; then
    echo 'Disposable PostgreSQL command failed; server log follows:' >&2
    cat "$work/server.log" 2>/dev/null >&2 || true
  fi
  rm -rf -- "$work"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -m 700 "$work/socket"
# Avoid inherited remote/service configuration or production passwords.
unset PGSERVICE PGSERVICEFILE PGPASSWORD PGOPTIONS PGHOSTADDR PGSSLMODE
export PGHOST="$work/socket" PGPORT=5432 PGUSER=hub_runtime_test PGDATABASE=hub_runtime_test
initdb_args=(-D "$work/data" -U "$PGUSER" --encoding=UTF8 --locale=C --auth-local=trust --auth-host=reject)
if [[ -n ${PG_TEST_RUNTIME_ROOT:-} ]]; then
  initdb_args+=(-L "$PG_TEST_RUNTIME_ROOT/usr/share/postgresql/18")
fi
initdb "${initdb_args[@]}" > "$work/initdb.log"
# Set the cleanup flag before startup in case pg_ctl is interrupted.
started=1
if ! pg_ctl -D "$work/data" -l "$work/server.log" \
  -o "-c listen_addresses='' -c unix_socket_directories='$PGHOST' -c unix_socket_permissions=0700 -c port=$PGPORT" \
  -w start > "$work/start.log" 2>&1; then
  cat "$work/start.log" >&2
  exit 1
fi
createdb "$PGDATABASE"
export HUB_TEST_DATABASE_URL="postgresql+psycopg://$PGUSER@/$PGDATABASE?host=$PGHOST&port=$PGPORT"
export HUB_TEST_RUNTIME=1 HUB_TEST_SOCKET_ONLY=1
export HUB_TEST_POSTGRES_MAJOR="${HUB_TEST_POSTGRES_MAJOR:-18}"
postgres --version
"$@"
