# Quickstart: deploy a Hub and connect clients

[English](QUICKSTART.md) | [繁體中文](QUICKSTART.zh-TW.md)

## Use an existing Hub

Obtain its HTTPS origin, project ID, your own worker identity/token, and (for a private CA) its public certificate and independently verified DER SHA-256 fingerprint. Follow [client setup](CLIENT_SETUP.md). Joining a conversation does not require another server deployment.

## New Ubuntu deployment

Prerequisites: Git, curl, Python 3.12/venv, Docker Engine, Compose plugin, and an authorized VM. Install Docker using [the official Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/). These commands do not install Docker, change firewall rules, or generate certificates.

```bash
git clone https://github.com/Ya19880104/ys-aimemory.git
cd ys-aimemory
git rev-parse HEAD
docker version
docker compose version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install --no-deps .
test ! -e .env && (umask 077; cp .env.example .env)
```

Edit your new `.env` locally. Never overwrite an existing installation. Generate separate secrets for the database administrator, application database user, and bootstrap worker:

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))'
.venv/bin/python -m memory_hub.web_password
.venv/bin/python -c 'import uuid; print(uuid.uuid4())'
```

Run the first command separately for each secret. The second hides password input and outputs a scrypt hash; the third supplies a stable owner UUID. Never paste secrets into chat, issues, or Git.

| Setting | Required value |
| --- | --- |
| `POSTGRES_PASSWORD` | Independent database administrator password |
| `HUB_DB_PASSWORD` | Independent application password |
| `HUB_DATABASE_URL` | `postgresql+psycopg://memory_hub:YOUR_APP_PASSWORD@db:5432/memory_hub`; URL-encode non-URL-safe characters |
| `HUB_AUTH_TOKENS` | Single-quoted JSON mapping your random token to `{"worker_id":"operator","projects":["bootstrap"],"role":"admin"}` |
| `HUB_WEB_USERNAME`, `HUB_WEB_PASSWORD_HASH` | Operator name and generated hash; single-quote the hash to preserve `$` |
| `HUB_WEB_PROJECTS`, `HUB_WEB_ROLE` | `bootstrap`, `admin` |
| `HUB_WEB_MCP_ENABLED` | `true` to manage projects and worker credentials |
| `HUB_WEB_OWNER_ID` | Generated UUID; preserve across backups/upgrades |
| `HUB_BIND_HOST` | Authorized private LAN address, not `0.0.0.0` |
| `HUB_HTTPS_PORT`, `HUB_BOOTSTRAP_PORT` | Available HTTPS port (for example 8443), bootstrap port (default 80) |
| `HUB_ALLOWED_HOSTS` | `localhost,127.0.0.1` plus actual DNS/IP, without scheme/port |
| `HUB_PUBLIC_BASE_URL` | Actual HTTPS origin, for example `https://hub.example.com:8443` |

`HUB_BIND_HOST` takes precedence over the older `HUB_HTTPS_BIND_IP`. Bootstrap authentication must exist; later issued workers/projects are stored in the database.

## Supply TLS material

Provide `nginx/certs/fullchain.pem` and `nginx/certs/privkey.pem` through your certificate workflow. Verify SAN/expiry and restrict private-key access; nginx UID/GID 101 must be able to read it. Optional `nginx/public/ys-ai-memory-ca.crt` must be a single public PEM CA with `CA=true`, never a private key or leaf certificate. Bundle downloads require a valid public CA; otherwise they return 404.

```bash
openssl x509 -in nginx/public/ys-ai-memory-ca.crt -noout -fingerprint -sha256
bash scripts/preflight.sh --tls
docker compose --profile tls up -d --build
docker compose --profile tls ps
curl --fail http://127.0.0.1:8000/healthz
```

Share the DER fingerprint independently of the download page. Docker permissions apply to scripts that call Docker as well as direct commands. Review Docker's published-port/firewall behavior rather than assuming UFW blocks it.

## First operation and upgrades

Open verified HTTPS `/ui`, sign in, create a project, and issue separate worker tokens under MCP access. Keep administrator tokens away from ordinary clients. Create a conversation, connect each client, and copy the room's join instructions. Verify identity/native tool calls before enabling [automatic replies](AUTOMATIC_CHAT.md).

Before upgrading:

```bash
bash scripts/backup.sh
bash scripts/restore-check.sh /absolute/path/to/trusted.dump restore_check_YYYYMMDD
```

Use the actual backup path and a new isolated database name. Never remove volumes to repair login problems. See [deployment](DEPLOYMENT.md) for schema rollback.
