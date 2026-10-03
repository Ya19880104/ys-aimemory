# API contract and executable examples

[English](API_EXAMPLES.md) | [繁體中文](API_EXAMPLES.zh-TW.md)

Use `memory_hub/models.py`, session/delivery schemas, and target MCP `tools/list` as the field contract. Tool count changes with version; discover it rather than assuming a fixed count. Public OpenAPI routes are disabled.

## Wrappers

REST: `POST /v1/tools/get_worker_inbox`, Bearer authentication, JSON body:

```json
{"arguments":{"project_id":"sandbox"}}
```

MCP tools themselves accept an object named `arguments`, inside the protocol's arguments envelope:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_worker_inbox","arguments":{"arguments":{"project_id":"sandbox"}}}}
```

Client SDKs handle initialize/initialized and protocol headers. Do not substitute REST URLs for `/mcp`.

## Task fields

Administrators create project → register sources → create task with `goal`, `allowed_paths`, `acceptance_criteria`, and `source_ids`. No general task-definition editor/reopen tool is promised.

- Prepare: `project_id`, `task_id`, `workspace`, `branch`, `commit`.
- Claim: project/task, `lease_seconds` (30–3600, default 300).
- Packet operations: project/`packet_id`; source read adds `source_id`.
- Gated mutations: project/packet/`fence` and their tool-specific fields.
- Evidence: `{source_id, sha256}` from current packet required sources.
- Handoff: `summary`, `evidence`, `to_worker`, `changed_artifacts`, `result_commit`, nonempty `test_results`, `blockers`, and nonempty `next_steps`.
- TestResult: `command`, `status` (`passed`, `failed`, `not_run`), `details`. Preserve skipped observations explicitly in details; do not invent a schema status.
- Recovery: admin only; project/task, `expected_revision`, `expected_generation`, `expected_fence`, nonempty `reason`, optional `to_worker`.

URI/commit are declared provenance, not proof of externally fetched/verified Git state. See [runbook](FOUR_AGENT_RUNBOOK.md).

## Two-party message example

```json
{"arguments":{"project_id":"sandbox","recipient_worker_id":"worker-b","thread_id":"check-001","body":"Please reply to synthetic marker CHECK-001.","idempotency_key":"send-check-001","reply_to_message_id":null}}
```

Sender derives from the token. Repeat an uncertain send with the same key and identical parameters; changed parameters conflict. Replies use a new key and the original message ID. `list_messages` accepts project, optional thread, `after_sequence`, and `limit`; use returned `next_after_sequence`. See [messages](MCP_MESSAGES.md).

## Sandbox workflow

`docs/demo_workflow.py` creates test records on its target Hub. Use only a dedicated sandbox with administrator/worker credentials explicitly authorized for the same project. Securely set `HUB_URL`, `HUB_PROJECT`, `HUB_ADMIN_TOKEN`, `HUB_WORKER_A_TOKEN`, `HUB_WORKER_B_TOKEN`, and `HUB_WORKER_B_ID` in the current shell, then:

```sh
python docs/demo_workflow.py
```

It accepts HTTPS or loopback HTTP, does not delete records, modify worktrees, deploy, or call a model. Native acceptance is separate. Shared rooms use [session tools](SHARED_SESSIONS.md); automatic delivery uses the separately documented [contract](DELIVERY_API.md).
