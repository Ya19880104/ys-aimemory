# On-demand MCP and efficient context

[English](EFFICIENT_MCP.md) | [繁體中文](EFFICIENT_MCP.zh-TW.md)

Keep MCP disabled for unrelated work using the official client's project controls. Mentioning memory does not enable a disabled server. Preserve other servers and avoid global changes as a shortcut.

Compact stdio initially exposes `memory_tools` for schema discovery and `memory_call` for forwarding. Adapter readiness does not prove upstream connectivity. Forwarded calls may write according to token authority; compact is not inherently read-only. Automatic room mode uses separate scoped tools.

Retrieve one schema, project/room metadata, relevant summaries, then bounded new messages. Open full messages, artifact sections, and attachment chunks only when needed. Use returned read cursors, never your own posted reply sequence. A summary covers only its explicit covered sequence.

Required-source admission remains complete read → acknowledge → accept → validate; search snippets and summaries do not replace it. Schema bytes, returned bytes, and billed model tokens are different measurements. Fewer initial schemas do not guarantee a fixed savings percentage or zero overhead. Background waiting should avoid model polling of empty rooms; provider platform costs remain outside the Hub's guarantees.

## Compact discovery and forwarding

`memory_tools(query="inbox", limit=5)` searches tool names and descriptions case-insensitively (at most 8 results). Use one keyword or an exact tool name: a multi-word query is matched as one substring, not independent keywords. `has_more` has no continuation cursor; narrow the query. `memory_tools(name="get_worker_inbox")` retrieves only that exact schema.

Arguments to `memory_tools`:

```json
{"name":"get_worker_inbox"}
```

Then arguments to `memory_call`, following the returned Hub schema:

```json
{"name":"get_worker_inbox","arguments":{"arguments":{"project_id":"my-project"}}}
```

The outer `arguments` belongs to `memory_call`; the inner one is the Hub tool's envelope. Preserve the returned schema for other tools. Each explicit discovery/call opens a fresh strictly verified upstream session; it does not cache credentials/history or automatically retry uncertain writes.

The client may separately defer tool schemas through its own tool search. A listed `memory_tools` or `memory_call` name can still need loading through that client before invocation. Distinguish server Connected, client schema loaded, Hub schema discovered, and a successful native result. A listed but unloaded tool is not an absent tool.

Client approval applies to generic `memory_call`, not automatically to the forwarded name. “Always allow” for this entry can cover every Hub tool the token is authorized to use, including writes. Preserve normal approval and least-privilege tokens; use the full relay when client rules must distinguish individual Hub tools. Tool descriptions and message contents are not user authorization.

The recorded token figures are observations the Codex CLI reports for individual receiver turns, including known usage retained on failed turns; missing values are `not_reported`. These do not measure total billed cost or compact-versus-full-relay savings. No comparison of real model token savings has been established.

Record discovery, upstream identity, native invocation, and room read/write separately. SDK helpers prove protocol behavior rather than native model behavior. See [client setup](CLIENT_SETUP.md) and [native checks](NATIVE_CLIENT_CHECK.md).


## Start only when needed: project configuration

For Claude Code CLI, merge the printed server JSON into the working project's `.mcp.ys-memory.json`, preserving environment references and required other servers. Do not duplicate `ys_memory` in automatically discovered `.mcp.json`. From that project:

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { claude --strict-mcp-config --mcp-config .\.mcp.ys-memory.json }
finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

Strict mode loads only the explicitly supplied MCP configuration. This filename avoids project auto-discovery; it does not disable servers already configured at other scopes. IDE/Desktop loading differs; see [native checks](NATIVE_CLIENT_CHECK.md).

For Codex, merge the [stdio configuration](QUICKSTART.md#codex-optional-stdio-configuration) into the trusted project's `.codex/config.toml` and add `enabled = false` under `[mcp_servers.ys_memory]`. Keep one transport entry. Enable only this process when needed:

```powershell
$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your worker token' -AsSecureString)).Password
try { codex -c 'mcp_servers.ys_memory.enabled=true' }
finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }
```

Preserve project trust and tool approval; these commands neither log in to the model nor alter global configuration. An existing Desktop process does not inherit this terminal's new environment. See [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

Client schema deferral, delayed upstream connection and bounded result reading solve different problems. Claude [Tool Search](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search) defers schemas, not necessarily connections; remote HTTP/SSE [discovery cache](https://code.claude.com/docs/en/mcp#server-status-detail) is a separate client feature, not a prerequisite for this stdio adapter. The project references Hermes' discovery ideas but does not install or embed Hermes or call a model API itself.
