#!/usr/bin/env bash
# Restores a trusted backup into a NEW database for inspection; never overwrites.
# Keep restored data private. SQL/dump content can execute code; only use trusted dumps.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -ne 2 || ! "$2" =~ ^restore_check_[a-z0-9_]+$ ]]; then
  echo 'Usage: scripts/restore-check.sh trusted-backup.dump restore_check_NAME' >&2; exit 2
fi
[[ -f "$1" ]] || { echo 'Backup file not found' >&2; exit 1; }
target="$2"
# createdb fails if target already exists. A partial restore is retained for inspection.
docker compose exec -T db sh -c 'exec createdb -U "$POSTGRES_USER" --owner=memory_hub "$1"' sh "$target"
# Quote the validated target as an SQL identifier; restrict access before loading data.
docker compose exec -T db sh -c 'exec psql -X -U "$POSTGRES_USER" --dbname="$1" --set=ON_ERROR_STOP=1 --set=target_db="$1"' sh "$target" <<'SQL'
REVOKE CONNECT ON DATABASE :"target_db" FROM PUBLIC;
SQL
docker compose exec -T db sh -c 'exec pg_restore -U "$POSTGRES_USER" --dbname="$1" --role=memory_hub --no-owner --no-acl --exit-on-error --single-transaction' sh "$target" < "$1"
printf 'Restored into isolated database %s. Inspect records and test application queries before recovery.\n' "$target"
echo 'The live database and app configuration have not been changed. Remove the check database manually after review.'
