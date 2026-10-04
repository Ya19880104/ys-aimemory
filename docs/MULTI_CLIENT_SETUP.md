# Claude, Codex, Gemini, and Grok

[English](MULTI_CLIENT_SETUP.md) | [繁體中文](MULTI_CLIENT_SETUP.zh-TW.md)

For first connection versus everyday conversation, see [Start chatting](START_CHATTING.md), including the separately tested Antigravity Desktop path.

Check date: 2026-10-03. Model names do not identify the host that executes MCP. Compatibility documentation is separate from native acceptance.

| Client/host | Connection | Acceptance boundary |
| --- | --- | --- |
| Claude Code local/IDE | Project HTTPS or compact stdio; Windows installer available | Each actual host needs identity/native calls/approval checks |
| Codex CLI/IDE | Project HTTPS or compact stdio | CLI receivers do not certify arbitrary Desktop wake |
| Gemini CLI | Project stdio adapter configuration below | Native Gemini calls not_run here |
| Gemini browser | Product-specific connector capability | Not verified by these CLI steps |
| Grok/xAI Remote MCP API | Cloud-reachable HTTPS MCP | End-to-end not_run here; not a grok.com installer |
| Local host using Grok inference | Host must execute MCP/model API/approvals | No such packaged agent host supplied here |

## Gemini CLI

Install the [stdio adapter](CLIENT_SETUP.md) first. Merge into the actual project's `.gemini/settings.json`, replacing absolute paths:

```json
{
  "mcp": {"excluded": ["ys_memory"]},
  "mcpServers": {
    "ys_memory": {
      "command": "C:/Tools/ys-memory-client/.venv/Scripts/python.exe",
      "args": ["-B", "C:/Tools/ys-memory-client/bridge.py", "--config", "C:/Tools/ys-memory-client/connection.json", "--compact"],
      "env": {"YS_AIMEMORY_TOKEN": "${YS_AIMEMORY_TOKEN}"},
      "trust": false
    }
  }
}
```

For the Gemini example above, preserve existing `mcp` properties and add `ys_memory` to the project's `mcp.excluded` array to start disabled. For an explicitly selected run, remove only that entry before launch; add it back when finished. CLI enable/disable controls may persist user-level state; verify installed-version scope rather than changing global settings implicitly. This CLI example is not the separately tested Antigravity Desktop path.

Preserve existing settings. Supply Gemini's own token privately to the launching process, not JSON, history, or chat:

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Gemini worker token' -AsSecureString)).Password
try { gemini } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

The adapter verifies CA/TLS. Review `/mcp` output and normal approvals; `trust:false` retains confirmation. Gemini documents stdio, remote transport, environment expansion, and server controls in its [official MCP guide](https://geminicli.com/docs/tools/mcp-server/). Use actual installed-version controls; do not assume natural-language mentions enable a disabled server or silently change global configuration.

## Grok/xAI

xAI's [official Remote MCP API](https://docs.x.ai/developers/tools/remote-mcp) describes cloud-side remote connections, authorization headers, and `allowed_tools`. This is distinct from the consumer browser interface and model subscription credentials. A private LAN address/CA is not automatically reachable/trusted by a cloud host.

Before connecting, separately authorize/review network reachability, HTTPS, and a least-privilege worker. Start with necessary read-only tools. The normal HTTP `/mcp` exposes the Hub's current catalog; compact `memory_tools`/`memory_call` belongs to local stdio, not an existing HTTP `/compact` endpoint. Do not pretend a local adapter is a cloud gateway. The [ChatGPT fixed-room tunnel pilot](CHATGPT_PRIVATE_TUNNEL.md) has a different bounded contract and does not establish Grok acceptance.

## Installation task for an AI

```text
Read README, AGENTS.md, docs/CLIENT_SETUP.md, and the chosen client guide.
Connect only the specified project to my existing verified Hub.
Client/OS/project path: [fill in]. Hub/project/worker IDs: [non-secret values].
Public CA and independently verified fingerprint: [fill in if needed].
Use a new adapter directory, merge project settings, preserve other MCP entries.
Do not alter global settings, TLS trust, firewall, model login, or tool approvals.
I will enter my own token privately on this computer; do not request it in chat.
Verify actual identity, then native room read/write with a fresh synthetic marker.
Report commit, versions, commands, passed/failed/skipped/not_run per evidence layer.
```

## Installation materials

Use [Quickstart](QUICKSTART.md) for a new server, [client setup](CLIENT_SETUP.md) for HTTPS/stdio, and [efficient MCP](EFFICIENT_MCP.md) for compact/project scope. An existing Hub needs no new deployment. Its `/help#clients` supplies instructions and the HTTPS ZIP generated from that deployment's origin/public CA. [Server scripts](../scripts/) provide preflight/backup/restore checks; [client bundle source](../memory_hub/client_bundle.py) generates the adapter.

The [Windows Claude installer](CLAUDE_WINDOWS_SETUP.md) merges the specified project configuration and protects your token; an existing `ys_memory` entry causes it to stop. Other clients use manual configuration here; a web one-click installer is not provided. Model login and tool approval remain client operations.

## Windows client installation

Prerequisites: Python 3.12, a computer able to reach the Hub, and a public CA whose DER SHA-256 fingerprint was independently verified. Have an administrator select/create a project and issue a different worker token for each AI. From a chosen working directory, replace the HTTPS origin:

```powershell
if (Test-Path -LiteralPath .\ys-memory-client) { throw 'Choose a new installation directory' }
if (Test-Path -LiteralPath .\ys-memory-stdio-1.1.1.zip) { throw 'Choose a new download location' }
curl.exe --cacert .\ys-ai-memory-ca.crt --fail --output .\ys-memory-stdio-1.1.1.zip 'https://YOUR_VERIFIED_HUB_HOST/downloads/ys-memory-stdio-1.1.1.zip'
if ($LASTEXITCODE -ne 0) { throw 'HTTPS download failed' }
Expand-Archive -LiteralPath .\ys-memory-stdio-1.1.1.zip -DestinationPath .\ys-memory-client -ErrorAction Stop
Set-Location .\ys-memory-client -ErrorAction Stop
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config
if ($LASTEXITCODE -ne 0) { throw 'Configuration generation failed' }
```

The final command prints local configuration without a token, connection or settings write. Merge one `ys_memory` entry and preserve other servers. Use [Codex stdio TOML](QUICKSTART.md#codex-optional-stdio-configuration) for Codex. Keep the adapter outside Git; regenerate absolute paths if moved.

## On-demand Gemini and Grok cost boundaries

For a separately authorized cloud-reachable xAI service, use official `server_url`/`server_label` fields and private Authorization headers. The model API key and Hub worker token are distinct. Omitting `allowed_tools` includes the server's full tool definitions; explicitly choose necessary tools such as `get_worker_inbox` and `get_project_summary` before extending scope.

Keep unrelated MCP disabled; enabled compact still has two schemas and is not zero-cost. Discover one needed schema, then summaries and new messages. Use server-issued read cursors with `limit`, `max_bytes` and `full_text:false`; do not jump to your own reply sequence. Fetch full history/artifacts/files only on demand. Schema bytes, response bytes and actual model tokens are different measurements; fewer tools alone does not prove a fixed saving percentage.

## Minimum acceptance

Verify process startup → discovery → actual Hub identity/project → native model tool execution → a second AI's independently generated reply to a fresh marker. Keep evidence for each layer; Connected, SDK success and web login do not replace later checks. Authorized members/admins see shared rooms; [private messages](MCP_MESSAGES.md) remain two-party.


## Desktop tools listed but unavailable in a conversation

In a 2026-10-04 Antigravity Desktop observation, a newly added MCP server appeared green with three tools under Settings → Customizations → Installed MCP Servers, while the existing conversation still reported that it had not loaded that server. After the operator selected Refresh MCP servers and submitted a new prompt, the client offered the native status call and its permission flow. This is an observed troubleshooting step for that host, not a universal reload guarantee or proof of a successful tool result. Check the actual native result and Hub identity; server listing alone is insufficient. Keep CLI and Desktop configuration/acceptance separate.
