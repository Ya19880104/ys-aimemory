# Connect a client to MCP

[English](CLIENT_SETUP.md) | [繁體中文](CLIENT_SETUP.zh-TW.md)

## Identity and trust

Install and sign into your own official client. Hub web login, model-provider login, and worker bearer token are different credentials. Each AI gets a separate project-scoped token. A room URL contains identifiers, not credentials.

For a private CA obtain its public file and independently verified DER SHA-256 fingerprint. Preserve existing project MCP entries; do not bypass certificate validation or change global settings.

## Codex direct HTTPS

Merge into the trusted project's `.codex/config.toml`:

```toml
[mcp_servers.ys_memory]
url = "https://memory.example.internal:8443/mcp"
bearer_token_env_var = "YS_AIMEMORY_TOKEN"
```

Replace the origin. For a private CA set `CODEX_CA_CERTIFICATE` to its verified absolute path before launch; system-trusted certificates need no override. References: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [custom CA](https://learn.chatgpt.com/docs/auth#custom-ca-bundles).

## Compact stdio adapter

Download HTTPS `/downloads/ys-memory-stdio-1.1.1.zip` from your own verified Hub. Extract into a new directory and verify `connection.json` and its CA pin:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

The last command prints local configuration offline. Merge `mcpServers.ys_memory` into the actual Claude project's `.mcp.json`, retaining `${YS_AIMEMORY_TOKEN}`. The [Windows installer](CLAUDE_WINDOWS_SETUP.md) is an alternative using DPAPI.

For Codex choose either direct HTTPS or this stdio entry, not duplicate same-name servers:

```toml
[mcp_servers.ys_memory]
command = 'C:\Tools\ys-memory-client\.venv\Scripts\python.exe'
args = ['-B', 'C:\Tools\ys-memory-client\bridge.py', '--config', 'C:\Tools\ys-memory-client\connection.json', '--compact']
env_vars = ['YS_AIMEMORY_TOKEN']
startup_timeout_sec = 60
```

Replace every path with the installation's actual path. No `--print-codex-config` or project-scope `codex mcp add` option is assumed. Moving the installation requires regenerated paths. Compact exposes `memory_tools` and `memory_call`, connects on demand, and can perform authorized writes; it is not inherently read-only.

## Launch and verify

In the selected project's new PowerShell:

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { codex } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

Use `claude` instead of `codex` for Claude Code. Existing Desktop processes do not inherit a new terminal's environment. Review ordinary client trust/tool prompts; do not disable guards for a green check.

Ask the native model to discover/call `get_worker_inbox` with your project and report the returned identity. In compact mode discover the single schema, then forward the original arguments through `memory_call`. Do not claim a task merely to test connectivity. Join a room and perform [native read/write acceptance](NATIVE_CLIENT_CHECK.md).

| Failure | Check |
| --- | --- |
| 401 | Token propagation/revocation; model OAuth errors are separate |
| 403 | Project grants; switching room IDs cannot bypass them |
| TLS | CA, SAN, independent fingerprint; never use `-k` |
| ZIP 404 | Valid public CA and HTTPS download |
| Connected without tool result | Local adapter readiness versus native/upstream acceptance |
