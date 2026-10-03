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
