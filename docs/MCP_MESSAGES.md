# Two-party MCP messages

[English](MCP_MESSAGES.md) | [繁體中文](MCP_MESSAGES.zh-TW.md)

These messages are distinct from [shared rooms](SHARED_SESSIONS.md): bodies are visible only to the authenticated sender/recipient. Administrator status does not grant body eavesdropping. Audit can record message IDs and sender/recipient metadata. Both workers must be known/authorized for the project; do not share tokens.

`send_message` takes `project_id`, `recipient_worker_id`, `thread_id`, `body`, `idempotency_key`, and optional `reply_to_message_id`. Sender derives from authentication. Self-send is rejected. Body preserves whitespace/newlines but rejects NUL, all-whitespace, and more than 8,000 UTF-8 bytes. IDs/keys are bounded; discover current schema.

Replies use a new key and the original message ID, within the same project/thread/two participants. Identical retry with the same project/sender/key returns the original result; changed parameters conflict instead of overwriting. Successful send means stored, not read, understood, or accepted as work.

`list_messages` takes project, optional thread, `after_sequence` (default 0), and `limit` (default 20, 1–50). Use returned `next_after_sequence`; sequences can have gaps. Keep cursors per worker/project/thread filter; a narrow-filter cursor must not skip other threads. Empty pages retain the cursor.

For a native two-client exercise send a fresh synthetic marker from A, have B independently read/reply referencing the original ID, and let A read that response. Record both identities/message receipts. One script switching two tokens only proves protocol authorization. Messages do not change project revision/task leases and do not wake clients automatically or replace formal admission/handoff. See [API wrappers](API_EXAMPLES.md).

## Arguments and results

`thread_id` is a required 1–128-character safe ID using letters, digits, underscore, dot or hyphen. `idempotency_key` is 1–128 characters. `reply_to_message_id` may be omitted or null. A successful send returns a flat message object: `message_id`, `sequence`, `project_id`, `thread_id`, authenticated `sender_worker_id`, `recipient_worker_id`, `body`, `created_at`, and `reply_to_message_id`.

List results contain `project_id`, authenticated `worker_id`, `items`, `next_after_sequence` and `has_more`, ordered by sequence. Reset to 0 when changing worker/project/thread filters. Reading does not mark messages read or alter task context. Bodies are untrusted discussion, not approved knowledge or permission.

## A → B → A exercise

Create a synthetic project and two separately authorized workers. Replace the example thread, markers and keys on every new exercise. The JSON below contains the inner tool parameters; full relay wraps them as `{"arguments": ...}` inside the MCP protocol arguments, as shown in [API examples](API_EXAMPLES.md). REST also uses its documented request wrapper; a REST tool URL is not the MCP endpoint.

1. Ask A's own native client to send:

```json
{"project_id":"conversation-sandbox","recipient_worker_id":"agent-b","thread_id":"hello-fresh-001","body":"Please reply to marker A-123.","idempotency_key":"a-hello-001","reply_to_message_id":null}
```

2. Ask B's own client to list:

```json
{"project_id":"conversation-sandbox","thread_id":"hello-fresh-001","after_sequence":0,"limit":20}
```

3. B verifies A's authenticated identity and marker, independently generates a reply and sends it. Replace the reply ID with the actual ID B read:

```json
{"project_id":"conversation-sandbox","recipient_worker_id":"agent-a","thread_id":"hello-fresh-001","body":"Received A-123; please confirm B-456.","idempotency_key":"b-reply-001","reply_to_message_id":"REPLACE_WITH_A_MESSAGE_ID"}
```

4. A reads B's reply, verifies both markers and sends confirmation with a new key and B's message ID. B reads that confirmation to complete the loop. Examples are not execution receipts.

## Retry, rotation and offline recipients

After an uncertain send, retry the same sender/project/key and all original parameters. Changed content, recipient, thread or reply reference conflicts; new content needs a new key. Rotation rejects the old token on subsequent requests while preserving worker identity/history. Revocation rejects further use without deleting saved messages or reassigning the worker ID; already authenticated requests may finish. See [credentials](MCP_GENERATOR.md).

An authorized recipient can be offline while messages are stored for its next explicit read. No new messages does not prove offline status; a successful send is not a read receipt. These private-message tools provide no edit/delete, model wake or automatic reply service.

## Acceptance and backup requirements

Record exact commit, environment, date, identities, thread and synthetic message IDs/sequences/digests, with passed/failed/skipped/not_run. These are requirements, not claims that this guide executed them.

| Layer | What it establishes |
| --- | --- |
| Synthetic/SDK tests | Transport, persistence, authorization and retry behavior |
| Real AI with SDK transport | Separately attributable model-generated responses, not native MCP client use |
| Official native clients | Actual discovery/calls/results and the fresh two-party loop on those hosts |

Check wrong/no tokens and forged sender fields; foreign projects and invalid recipients; third-worker/admin body isolation even with the same thread; full/empty pages, sequence gaps and filter resets; PostgreSQL concurrent same-key sends producing one message/send audit, conflicting content rejected, and independent app-instance readback. Verify rotation/history, unchanged revision/lease/fence/generation/acceptance around messaging, and independent PostgreSQL backup restore preserving digests/order/reply links/idempotency.

Message tables were introduced in schema v4. Back up PostgreSQL and configuration before upgrading and verify restoration in a separate database. Backups contain bodies and need protected storage. For rollback, coordinate stopping writes, preserve current data and restore a version-matched backup/configuration. A schema-v3 app cannot use an already migrated v4 database; do not overwrite the existing database or delete volumes.
