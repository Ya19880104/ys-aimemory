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
