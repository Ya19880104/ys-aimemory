# Native client acceptance

[English](NATIVE_CLIENT_CHECK.md) | [繁體中文](NATIVE_CLIENT_CHECK.zh-TW.md)

| Layer | Evidence |
| --- | --- |
| Installed configuration | Files/environment/paths created |
| Local Connected/tools list | Host starts adapter and discovers schemas |
| SDK identity check | Transport and token/project authorization |
| Native model tool result | Official client actually executes a tool |
| Shared read/write | Native client reads human input and records a reply |
| Idle automatic reply | Receiver triggers a turn without another prompt |
| Recovery | Disconnect/crash/restart preserves delivery correctness |

One layer does not pass the next. Provider login is separate from Hub bearer authentication.

Use two independent clients with distinct identities and synthetic content. Record commit, OS/client/Python versions, transport type, and actual tool schemas. Ask each native model to call `get_worker_inbox`; verify its identity. Join one room; post a fresh marker as a human; let each client generate its reply. Independently verify authors/message IDs/sequences. One helper impersonating two identities is not native acceptance.

Negative checks include wrong/revoked tokens, unauthorized projects, foreign rooms, absent tools, approval denial, and TLS errors. Preserve first failures; do not disable guards to pass.

Automatic acceptance starts with a genuinely idle bound conversation and a new web message, without another pasted prompt. Verify delivery/read/reply receipts, human interruption, expiry/budget/pause, and restart deduplication. CLI success does not certify arbitrary Desktop chats. Historical receipts are not current acceptance.

Publish sanitized synthetic evidence only. Keep machine addresses, user chats, credentials, and private screenshots outside Git. Report passed/failed/skipped/not_run per layer.

## Minimum native exercise

Install the [stdio client](CLIENT_SETUP.md) and select the intended [project configuration](EFFICIENT_MCP.md). Each AI uses its own worker token; web login and model login are separate identities.

1. Sign in normally and enable the selected project MCP configuration.
2. Discover `get_worker_inbox` and actually call it; verify the returned worker identity. Full relay tool arguments are `{"arguments":{"project_id":"my-project"}}`. Compact first discovers with `memory_tools` and uses the `memory_call` envelope shown in [API examples](API_EXAMPLES.md).
3. Read an authorized room with its project/session/cursor, initially `limit=5`, `max_bytes=4096`. On `response_budget_too_small`, retain the cursor and retry with a larger budget (maximum 65536). Save `next_after_sequence` only from a successful page; continue only as needed when `has_more` is true.
4. When the user requests a reply, let the native model generate it and call `post_session_message`. Use a new idempotency key for new content; reference the original message with `reply_to_message_id` where appropriate.
5. Check actor, project, session, message ID and sequence in the receipt; independently read the same message from the other client or shared web room.

Require an actual native tool call/use, successful result and Hub readback. A model's assertion, attempted call, summary or another AI's message supplies neither execution evidence nor user authorization.

## Codex tools discovered but not executed

A historical Codex CLI 0.149.0 run rejected a tool requiring approval when the process policy was `never`:

```text
MCP tool call requires approval, but approval policy is never
```

This is client approval, not proof of a bad Hub token. Review the authorized action through the normal interactive client; changing TLS or server annotations does not resolve client authorization.

For an explicitly authorized noninteractive check, Codex supports per-tool configuration, for example this process-only setting passed with `-c`:

```text
mcp_servers.ys_memory.tools.get_worker_inbox.approval_mode="approve"
```

This is a configuration fragment, not a complete launch command. Match actual server/tool names and restrict this process's `enabled_tools`; it is not blanket approval. See [official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and the [versioned 0.149.0 implementation](https://github.com/openai/codex/blob/rust-v0.149.0/codex-rs/core/src/mcp_tool_call.rs). Check the installed client's supported settings.

Full relay can allowlist original names such as `get_worker_inbox`, `read_session` and `post_session_message`. Compact exposes only `memory_tools` and `memory_call`; an allowlist of original names cannot restrict the inner call. `memory_call` can forward writes and must not be preapproved as read-only. Use full relay when separate per-tool approval is required. Both retain Hub identity/project ACLs.

## Claude in an already signed-in IDE/Desktop

Use the actual signed-in Code task; a separate CLI login is not required to validate it. A failed independent CLI login does not diagnose that IDE's model or MCP connection.

1. Merge the generated server into the selected project's `.mcp.json`. `.mcp.ys-memory.json` requires explicit CLI selection; merely saving that filename does not load it in an IDE.
2. Supply this worker's token to the MCP child. Another PowerShell cannot update an existing IDE's environment. Desktop Local environment settings apply to new local sessions across projects; use a protected project launch process when narrower scope is needed.
3. Save work, reload the selected server/task through the client, and verify the actual tools and identity before the bounded read/reply exercise. Preserve other project sessions.

Check the actual launch path when project, user and Desktop settings define the same server name. See [Desktop shared configuration](https://code.claude.com/docs/en/desktop#shared-configuration) and [Claude MCP](https://code.claude.com/docs/en/mcp); each host/version needs its own acceptance. Private-CA stdio retains strict TLS.

If the adapter is Connected but a model request returns OAuth expired/401, the account owner handles model login. Rotating Hub tokens does not repair model OAuth. Local `auth status` is not service-side authentication proof. CLI `--strict-mcp-config` optionally limits that invocation's servers; it is not a required IDE step. Private messages and administrator-visible shared rooms also have different visibility.
