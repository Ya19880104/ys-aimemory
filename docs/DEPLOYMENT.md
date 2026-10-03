# Ubuntu/PVE deployment and recovery

[English](DEPLOYMENT.md) | [繁體中文](DEPLOYMENT.zh-TW.md)

Follow [quickstart](QUICKSTART.md) for a new authorized VM, private configuration, certificate files, preflight, and startup. PVE resources, DNS, firewall, certificate trust, backup destination, and RPO/RTO are operator decisions. A public GitHub repository is not deployment authorization.

## Defaults and credentials

Compose keeps database ports private and application access on loopback; TLS publication needs an explicitly chosen authorized interface. Application containers use non-root/read-only restrictions. Database administrator and application passwords differ. Workers have distinct scoped tokens; human passwords use scrypt hashes. Never publish `.env`, keys, databases, backups, or full `docker compose config` output.

HTTP bootstrap exposes only help/public CA GET/HEAD. Stdio ZIP downloads require HTTPS and valid public CA material; the TLS private key belongs only in nginx. Verify certificate SAN/expiry/DER fingerprint independently. Do not skip TLS or bind all interfaces to solve access problems.

## Validate the actual runtime

```bash
bash scripts/preflight.sh --tls
docker compose --profile tls up -d --build
docker compose --profile tls ps
curl --fail http://127.0.0.1:8000/healthz
```

Static validators do not prove image build/startup, network trust, browser usability, or native clients. Record exact commit/image/environment and negative checks separately. Database-backed web sessions/nonces/throttling support shared application state; that design does not certify multi-worker capacity. Update every runtime instance together after policy/schema changes.

## Backup and upgrade

```bash
bash scripts/backup.sh
bash scripts/restore-check.sh /absolute/path/to/trusted.dump restore_check_YYYYMMDD
```

Verify the trusted actual dump and a new isolated DB name. Restore checking must not overwrite live data. Preserve deployment environment and stable owner ID alongside protected backups. Test Unicode sources, task/hand-off state, chat attachments, audit, search, and current account grants after restore.

Migration is additive and version checked. Old applications reject newer schemas. Rollback requires coordinated write stop and a matching older backup restored to a separate database, followed by controlled switching; merely running an old image against the migrated DB is unsafe. Never use `docker compose down -v` to repair authentication.

## Remaining operations work

Measure canonical aggregate size, lock contention, retention, index quality, storage/capacity, and dependency/image reproducibility. Public-service readiness additionally needs identity lifecycle, trustworthy proxy/IP handling, DNS/TLS renewal, boundary rate limits, monitoring/incident procedures, and restore drills. The fixed-room [private tunnel pilot](CHATGPT_PRIVATE_TUNNEL.md) does not complete those gates.


## Documentation mirrors and offline help

`HUB_DOCS_BASE_URL` controls server-rendered Hub guide links. Unset or empty keeps `https://github.com/Ya19880104/ys-aimemory/blob/main/docs`. Set an HTTPS directory such as `https://docs.example.com/ys-memory`, or a root-relative directory such as `/mirror/docs`; links append the selected English or Traditional Chinese Markdown filename. Supply the mirror files and web-server mapping yourself; the Hub does not download, host or validate mirror contents. Wheels do not bundle the Markdown guides.

For a disconnected LAN, set `HUB_DOCS_BASE_URL=/help`: links open the existing localized built-in help landing page (`/help?lang=en` or `/help?lang=zh-TW`), rather than nonexistent per-guide routes. This is a summarized local manual, not a copy of every full guide.

Only HTTPS or root-relative directory URLs are accepted. Credentials, query/fragment, percent escapes, backslashes, control/non-ASCII characters, repeated path separators and dot traversal are rejected; use ASCII/punycode URLs. Invalid values safely fall back to local `/help` without breaking UI requests. Trailing slashes are normalized. Compose passes this setting to the app. Restart the configured runtime after changing deployment settings. Pinned installer downloads and upstream vendor references remain independent; this setting neither rewrites nor trusts installer sources.

An invalid `HUB_DOCS_BASE_URL` falls back to localized `/help` and emits one warning per application middleware startup. The rejected value is not logged.
