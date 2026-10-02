#!/usr/bin/env bash
# Extract a pinned official PGDG PostgreSQL 18.6 runtime. No sudo, service setup,
# host package installation, or maintainer scripts. For Debian 13 amd64 only.
# Provenance: https://www.postgresql.org/download/linux/debian/
# PostgreSQL package SHA256 values were checked against the signed trixie-pgdg
# InRelease/Packages index on 2026-09-30 (key fingerprint:
# B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8).
# liburing checksum: https://packages.debian.org/trixie/amd64/liburing2/download
set -euo pipefail
umask 077
if [[ $# != 1 ]]; then
  echo 'Usage: scripts/postgres-test-fetch-pgdg.sh EMPTY_OUTPUT_DIRECTORY' >&2
  exit 2
fi
[[ $(uname -m) == x86_64 ]] || { echo 'This pinned runtime requires amd64.' >&2; exit 2; }
[[ ! -e "$1" ]] || { echo 'Output directory must not already exist.' >&2; exit 2; }
mkdir -p "$1"
output=$(cd "$1" && pwd)
mkdir "$output/packages" "$output/root"
fetch() {
  local base=$1 package=$2 checksum=$3
  curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
    --connect-timeout 15 --max-time 120 "$base/$package" -o "$output/packages/$package"
  printf '%s  %s\n' "$checksum" "$output/packages/$package" | sha256sum --check -
  dpkg-deb --extract "$output/packages/$package" "$output/root"
}
base=https://apt.postgresql.org/pub/repos/apt/pool/main/p/postgresql-18
fetch "$base" libpq5_18.6-1.pgdg13+2_amd64.deb c6cc459bb499db4697686533e50bf5943f7e7d6929c04ef55eec184d5436859b
fetch "$base" postgresql-18_18.6-1.pgdg13+2_amd64.deb bf4062a44757c3f7a207a1b9e20c2bf93f9847257516c2ce0befc1257d3dcf8e
fetch "$base" postgresql-client-18_18.6-1.pgdg13+2_amd64.deb 9af40c99f7074f8ff3798155af2f07f1a4e1e3bd4edce44ef928c1e03aea620e
fetch https://deb.debian.org/debian/pool/main/libu/liburing liburing2_2.9-1_amd64.deb 4b589c00c7a51172aace2cb2fb3d3ff32daf86c644023126dcfcaa840cc941ea
export LD_LIBRARY_PATH="$output/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$output/root/usr/lib/postgresql/18/bin/postgres" --version
printf 'Run with: PG_TEST_RUNTIME_ROOT=%q scripts/postgres-test-runtime.sh COMMAND [ARGS...]\n' "$output/root"
