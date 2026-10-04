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
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install --no-deps .
test ! -e .env && (umask 077; cp .env.example .env)
```

Edit your new `.env` locally. Never overwrite an existing installation. Use independent random database passwords of at least 24 characters. There is no built-in administrator password. Generate separate secrets for the database administrator, application database user, and bootstrap worker:

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

The first human account is bootstrapped from the environment; later account creation, disabling, permissions and password management use Settings → User management. Account-management permission is separate from project access. Shared rooms are project-visible; private messages are two-party. See [web accounts](WEB_DASHBOARD.md).

Before upgrading:

```bash
bash scripts/backup.sh
bash scripts/restore-check.sh /absolute/path/to/trusted.dump restore_check_YYYYMMDD
```

Use the actual backup path and a new isolated database name. Never remove volumes to repair login problems. See [deployment](DEPLOYMENT.md) for schema rollback.

## Install and connect clients

Use an existing Hub without redeploying it. Install and sign in to your own official Claude Code or Codex client; this repository supplies MCP wiring, not model subscriptions or login. Each AI needs a distinct worker token. Merge settings into the actual project, preserving other servers; example configurations reference `YS_AIMEMORY_TOKEN`, never its value.

### Codex: direct HTTPS

Merge into the chosen, trusted project's `.codex/config.toml`:

```toml
[mcp_servers.ys_memory]
url = "https://hub.example.test:8443/mcp"
bearer_token_env_var = "YS_AIMEMORY_TOKEN"
```

Replace the origin. For a private CA, set `CODEX_CA_CERTIFICATE` to the independently verified public CA's absolute path before launch. A system-trusted CA needs no extra setting. See [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and [custom CA bundles](https://learn.chatgpt.com/docs/auth#custom-ca-bundles).

### Claude Code: stdio bundle

Get the HTTPS bundle through `/help#clients` or `/ui/mcp`. Follow the guarded [Windows installation commands](MULTI_CLIENT_SETUP.md#windows-client-installation): verify the public CA, use a new directory, check each command, create Python 3.12 venv, install `requirements.lock`, then run:

```powershell
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

This prints local absolute-path configuration offline, without a token. Check `connection.json`'s CA DER pin. Merge the generated `mcpServers.ys_memory` entry into the project's `.mcp.json`, preserving `${YS_AIMEMORY_TOKEN}` and other servers. Moving the adapter requires regenerating its paths. For project-specific on-demand use, see [efficient MCP](EFFICIENT_MCP.md); mentioning memory in a prompt does not enable a disabled server.

### Codex: optional stdio configuration

After installing the same bundle, choose this transport or direct HTTPS, with one `ys_memory` entry:

```toml
[mcp_servers.ys_memory]
command = 'C:\Tools\ys-memory-client\.venv\Scripts\python.exe'
args = ['-B', 'C:\Tools\ys-memory-client\bridge.py', '--config', 'C:\Tools\ys-memory-client\connection.json', '--compact']
env_vars = ['YS_AIMEMORY_TOKEN']
startup_timeout_sec = 60
```

Replace all three absolute paths. TOML literal strings preserve backslashes; the bridge validates its pinned CA. There is no `--print-codex-config` bridge command; this guide uses manual project configuration, not `codex mcp add --scope project`. Configuration support does not certify every native host.

### Launch and acceptance

From the configured project in a new PowerShell:

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { codex } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

For Claude, replace `codex` with `claude`. An already running Desktop process does not inherit another terminal's newly set environment. Handle model login, project trust and tool approvals in that client.

Ask the native model to discover and call `get_worker_inbox` for your project, reporting the actual worker/project without creating a task or sending a message. In compact mode, discover one schema with `memory_tools`, then call through `memory_call` using its documented envelope. Follow [native acceptance](NATIVE_CLIENT_CHECK.md), then the [two-party exercise](MCP_MESSAGES.md). Compact's two local entries differ from the upstream catalog; Connected, SDK success and native tool execution are separate evidence.

| Symptom | Check |
| --- | --- |
| Hub 401 | Own worker token reaches this process and has not been revoked; model OAuth 401 is separate |
| 403 / project not authorized | Actual granted project ID; selecting another room does not bypass scope |
| TLS / name constraints | CA, SAN and fingerprint; the stdio bridge preserves TLS validation |
| Tool approval required | Review in the normal interactive client; `never` is not automatic approval |
| ZIP 404 | Valid public CA in `nginx/public`, and HTTPS download |

## Ask an AI to help install

Fill only non-secret fields; this template becomes an instruction when you explicitly give it to your AI:

```text
Read README, AGENTS.md and docs/QUICKSTART.md first.
Scope: [new authorized Ubuntu VM deployment / connect a client to an existing Hub].
OS and project directory: [fill in]. Client: [Claude Code / Codex].
Hub HTTPS origin, project ID and my worker ID: [non-secret identifiers].
Public CA file and independently verified DER fingerprint: [if needed].
Work only in that project, merge settings and preserve existing MCP/data.
Do not change global settings. I enter secrets privately on this computer.
Check versions and existing state; preserve TLS validation and tool approvals.
Verify actual get_worker_inbox identity, then use my designated second AI for a fresh message exercise.
Report commands, versions and passed/failed/skipped/not_run without secrets.
```

Report problems through [Issues](https://github.com/Ya19880104/ys-aimemory/issues) with commit, OS and sanitized reproduction. Development uses branches, PRs and tests; see [CONTRIBUTING](../CONTRIBUTING.md).
