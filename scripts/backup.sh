#!/usr/bin/env bash
# Run on the operator's VM. Creates a logical backup, without printing secrets.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
umask 077
mkdir -p backups
output="backups/memory-hub-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
trap 'rm -f -- "$output.partial"' EXIT
docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$output.partial"
# Verify the dump archive is readable before accepting the backup.
docker compose exec -T db pg_restore --list < "$output.partial" > /dev/null
mv -- "$output.partial" "$output"
printf 'Backup created: %s\nKeep an encrypted off-VM copy; test restoration before relying on it.\n' "$output"
