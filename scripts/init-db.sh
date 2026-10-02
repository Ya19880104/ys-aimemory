#!/usr/bin/env bash
# Official postgres image runs this only during first initialization of an empty volume.
set -euo pipefail
: "${HUB_DB_PASSWORD:?Application database password is required}"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 --set=app_password="$HUB_DB_PASSWORD" <<'SQL'
CREATE ROLE memory_hub LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER DATABASE memory_hub OWNER TO memory_hub;
REVOKE CONNECT ON DATABASE memory_hub FROM PUBLIC;
GRANT CONNECT ON DATABASE memory_hub TO memory_hub;
SQL
