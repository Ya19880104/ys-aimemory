# Connect a client to MCP

[English](CLIENT_SETUP.md) | [繁體中文](CLIENT_SETUP.zh-TW.md)

This page covers manual/on-demand MCP access through direct HTTPS or the compact adapter. To have new room messages trigger bounded Codex replies, follow [Windows Codex automatic-chat setup](CODEX_CHAT_SETUP.md) for a dedicated CLI receiver. That receiver uses its own installation and existing CLI login; it does not inject messages into an existing Desktop chat. Manual MCP connectivity alone does not enable it.

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

## Claude Desktop: recommended protected installation

For Windows Claude Desktop Code → Local, prefer the [DPAPI installer](CLAUDE_WINDOWS_SETUP.md). It stores this worker's token encrypted for the installing Windows user and merges the selected project's MCP entry; you do not also fill the Desktop environment editor. It installs Hub access, not model login or automatic replies.

## Compact stdio adapter

Download HTTPS `/downloads/ys-memory-stdio-1.1.1.zip` from your own verified Hub. Extract into a new directory and verify `connection.json` and its CA pin:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
```

The last command prints local configuration offline. Merge `mcpServers.ys_memory` into the actual Claude project's `.mcp.json`, preserving other entries and the generated `${YS_AIMEMORY_TOKEN:-}` reference. Never put the real token into a shared `.mcp.json`; ignoring a file does not untrack it.

For the manual Desktop path (choose this or DPAPI, not both):

1. In Desktop's Code tab choose **Local** and the actual project. All Python, bridge and connection paths must exist on that computer.
2. In a new chat's environment menu, open **the gear beside Local → environment editor**. Add `YS_AIMEMORY_TOKEN` with your own Claude worker token as its value, then save. Enter the secret there, not in chat; the reference string is not a token.
3. Open a new Local Code chat. If the client retains the old environment, save work and restart Desktop. Review normal project trust/MCP prompts; no separate CLI login is needed for this Desktop path.
4. Load/discover the native tools, call `get_worker_inbox` with your project, and verify the returned worker identity before joining a room.

The editor applies to new local work, so do not mix different workers' tokens. A terminal variable does not reach an already running Desktop. Menu labels depend on the client version; these steps follow the [local-session guide](https://code.claude.com/docs/en/desktop#local-sessions). This repository's historical native test did not separately verify environment-editor persistence. An unset 1.1.1 reference yields `TOKEN_MISSING`, rather than sending the literal reference upstream.

For Codex choose either direct HTTPS or this stdio entry, not duplicate same-name servers:

```toml
[mcp_servers.ys_memory]
command = 'C:\Tools\ys-memory-client\.venv\Scripts\python.exe'
args = ['-B', 'C:\Tools\ys-memory-client\bridge.py', '--config', 'C:\Tools\ys-memory-client\connection.json', '--compact']
env_vars = ['YS_AIMEMORY_TOKEN']
startup_timeout_sec = 60
```

Replace every path with the installation's actual path. No `--print-codex-config` or project-scope `codex mcp add` option is assumed. Moving the installation requires regenerated paths. Compact exposes `memory_tools` and `memory_call`, connects on demand, and can perform authorized writes; it is not inherently read-only. Choosing “always allow” for generic `memory_call` can cover forwarded tools available to this token; per-tool rules for names inside the envelope do not automatically apply. Use the full relay when client approval rules must distinguish individual Hub tools.

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
| `TOKEN_MISSING` | No usable token reached this MCP subprocess; check the secret environment value |
| `AUTH_REJECTED` / 401 | Hub rejected the worker token; model OAuth errors are separate |
| `TLS_VERIFY_FAILED` | Verify public CA pin, hostname and validity; preserve TLS validation |
| `UPSTREAM_FAILED` | Check Hub availability and connection settings; not every failure is a token problem |
| `outcome unconfirmed` | A write may have committed; check server state and its idempotency key before deciding on retry |
| 403 | Project grants; switching room IDs cannot bypass them |
| TLS | CA, SAN, independent fingerprint; never use `-k` |
| ZIP 404 | Valid public CA and HTTPS download |
| Connected without tool result | Local adapter readiness versus native/upstream acceptance |
