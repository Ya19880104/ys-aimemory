# Two-party MCP messages

[English](MCP_MESSAGES.md) | [繁體中文](MCP_MESSAGES.zh-TW.md)

These messages are distinct from [shared rooms](SHARED_SESSIONS.md): bodies are visible only to the authenticated sender/recipient. Administrator status does not grant body eavesdropping. Audit can record message IDs and sender/recipient metadata. Both workers must be known/authorized for the project; do not share tokens.

`send_message` takes `project_id`, `recipient_worker_id`, `thread_id`, `body`, `idempotency_key`, and optional `reply_to_message_id`. Sender derives from authentication. Self-send is rejected. Body preserves whitespace/newlines but rejects NUL, all-whitespace, and more than 8,000 UTF-8 bytes. IDs/keys are bounded; discover current schema.

Replies use a new key and the original message ID, within the same project/thread/two participants. Identical retry with the same project/sender/key returns the original result; changed parameters conflict instead of overwriting. Successful send means stored, not read, understood, or accepted as work.

`list_messages` takes project, optional thread, `after_sequence` (default 0), and `limit` (default 20, 1–50). Use returned `next_after_sequence`; sequences can have gaps. Keep cursors per worker/project/thread filter; a narrow-filter cursor must not skip other threads. Empty pages retain the cursor.

For a native two-client exercise send a fresh synthetic marker from A, have B independently read/reply referencing the original ID, and let A read that response. Record both identities/message receipts. One script switching two tokens only proves protocol authorization. Messages do not change project revision/task leases and do not wake clients automatically or replace formal admission/handoff. See [API wrappers](API_EXAMPLES.md).
