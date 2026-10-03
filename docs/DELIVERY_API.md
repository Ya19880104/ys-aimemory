# Durable chat delivery API (schema v6)

English · [繁體中文](DELIVERY_API.zh-TW.md)

This document specifies the server contract. These REST routes do not invoke models
or wake arbitrary desktop/cloud conversations. A compatible client relay must be
explicitly bound to a native conversation. MCP connectivity, relay presence, tool
reads and generated replies require separate evidence.

## Join and wait

Every `/v1/chat/` route authenticates the caller's own Bearer worker token. Send a
plain JSON object; these relay endpoints do not use the MCP `arguments` wrapper.
Relay operations are excluded from MCP discovery to avoid loading their schemas
into ordinary model context.

`POST /v1/chat/join`:

```json
{
  "project_id": "example",
  "session_id": "11111111111111111111111111111111",
  "client": "claude",
  "display_name": "Local Claude",
  "native_session_id": "the-explicitly-bound-native-conversation",
  "ttl_seconds": 28800,
  "max_turns": 20,
  "idempotency_key": "a-new-installation-key"
}
```

- `client`: `claude`, `codex`, `chatgpt`, `gemini`, `grok`, or `other`. Labels are
  client declarations, not verified provider identity.
- The native conversation ID is distinct from the Hub room ID. Only its SHA-256 is
  stored; public status never includes the native ID or its hash.
- Omitted `after_sequence` starts after the room's latest event. To process earlier
  messages, explicitly choose the initial cursor. Rejoining preserves the durable
  processed cursor and cannot skip unprocessed messages.
- One binding is allowed per worker and room. Repeating the same key and arguments
  returns the original join receipt without resetting cursor or budget. Disable an
  active binding before replacing it. Expired or budget-exhausted bindings may be
  rejoined with a new key.
- Lifetime is 60–86400 seconds; the budget is 1–100 model starts. Each newly issued
  delivery lease consumes one start, including retries. This bounds starts, not
  billable tokens.

`POST /v1/chat/heartbeat` accepts `{project_id,binding_id}` and returns current
binding state and expiry. `relay_online=true` means a relay request was seen within
45 seconds; it does not guarantee model or desktop availability.

`POST /v1/chat/claim` accepts `{project_id,binding_id,lease_seconds:300}`. A lease
lasts 15–300 seconds, bounded by binding expiry. Updated receivers also send paired
`request_id` (a random 32-character lowercase hex value) and `generation` from the
join receipt. Persist this exact request before HTTP and reuse it after an uncertain
response. Do not share the pending request file between receivers.

- Repeating that request while its lease is live and **not dispatched or read**
  returns the original lease, without extending it or charging another attempt/turn.
- A different request cannot recover that live lease; it receives `busy`. After
  dispatch or tool-read, even the original request receives `busy`, avoiding a
  second wake after a process restart. This is not exactly-once model execution.
- A consumed, expired or fenced request returns HTTP 409 `stale_claim`. The receiver
  may then create a new request; issuing a new lease still consumes the normal
  attempt and turn budget. `stale_binding` requires explicit re-admission instead
  of silently adopting another native conversation's generation. Reusing a key
  with different arguments returns `idempotency_conflict`.
- Only granted claims are recorded in the existing schema-v6 request table. Idle
  polling does not create claim records or add MCP discovery/context tokens.
  Historical records accumulate across renewals; long-term retention/load is not
  certified by these bounded tests.
- Omit **both** fields for the legacy contract, which can remain `busy` after a
  lost response. Upgrade the Hub before installing the updated Claude/Codex
  receivers. The private cloud pilot retains its separate legacy claim path.

- No incoming messages: `{status:"idle",delivery:null}`. The relay waits and polls
  again without invoking a model.
- Paused, disabled, archived, expired, exhausted, busy, or failed: the corresponding
  status and `delivery:null`.
- Incoming messages: `status:"ready"` and a `delivery` containing `delivery_id`,
  `lease_id`, `lease_until`, `after_sequence`, `through_sequence`, `message_ids`,
  routing metadata and a stable `reply_idempotency_key`. Message bodies are omitted.
- A batch scans at most 20 room events. Human and explicit manual worker messages
  start at server-derived `automatic_reply_depth:0`. Automatic replies are depth 1
  or 2. Other workers' replies trigger delivery only below depth 2; depth-2 replies
  remain visible in the room but do not start another model turn. Own worker messages
  and non-message events do not invoke a model. A human and worker with identical ID
  text remain different actors. Clients cannot submit their own reply depth.
- A batch containing a new depth-0 message uses that new topic as its causal root,
  producing a depth-1 reply even if older AI context is also included. Otherwise the
  reply depth is the maximum included causal depth plus one. This preserves brief
  direct AI discussion while preventing an unbounded AI-to-AI reply loop.

## Dispatch, tool-read and reply receipts

Once the client accepts a notification, the relay may call
`POST /v1/chat/dispatched` with `{project_id,binding_id,delivery_id,lease_id}`.
This only proves **handed_to_client**; it never marks a model read or reply.

The model uses the existing native MCP tools, preserving their `arguments` wrapper:

1. Add paired `delivery_id` and `lease_id` to `read_session`. Read from
   `after_sequence`, use `full_text:true` and appropriate `limit` / `max_bytes`,
   and paginate when necessary. Delivery reads stop at `through_sequence`, so the
   model cannot accidentally answer newer messages that still await another batch.
   Pagination reserves the largest possible delivery receipt before selecting
   events; adding the actual receipt cannot overflow an otherwise valid page.
2. `delivery_receipt.status:"tool_read"` with empty `unread_message_ids` means the
   server has returned every complete incoming message in that batch. Truncated
   snippets cannot earn a complete receipt. Ordinary reads without delivery
   metadata do not acknowledge relay deliveries.
3. Send `post_session_message` with the same delivery/lease IDs and use the supplied
   `reply_idempotency_key` as `idempotency_key`. The server validates the same worker,
   live lease, complete reads and room state. The message, `replied` receipt and
   durable cursor commit in one transaction.

`tool_read` proves complete tool output, not model comprehension, provider identity,
or native-client acceptance. REST and MCP share a tool service; independent native
acceptance still requires the client's actual tool receipts.

Dispatch does not advance the processed cursor. After lease expiry, retry the same
delivery ID and reply key under a new lease ID. Old leases cannot earn receipts or
write replies. If a successful post response is lost, retrying the identical request
returns its original receipt without adding another message. A batch allows at most
three non-administrative lease attempts. A pause or disable that interrupts a live
lease does not count as a failed attempt; actual model starts still consume
`turns_used`. Messages arriving after batch creation remain pending after the old
batch completes.

## Pause and status

`GET /v1/chat/status?project_id=...&session_id=...` returns:

- `control`: `paused`, `version`.
- `participants`: `binding_id`, `worker_id`, `client`, `display_name`, `generation`,
  `version`, `enabled`, `released_at`, `expires_at`, `last_seen_at`, `processed_sequence`,
  `max_turns`, `turns_used`, `relay_online`, `status`, and `latest_delivery`.
- Participant states: `waiting`, `offline`, `processing`, `failed`,
  `budget_exhausted`, `paused`, `disabled`, `disconnected`, `expired`, `archived`, `revoked`.
- Receipt states: `leased`, `dispatched`, `tool_read`, `replied`, `failed`, `retry_ready`, with
  timestamps and exact reply ID/sequence. Status omits bodies, credentials, lease
  IDs and native conversation identifiers.

Admins may `POST /v1/chat/pause` with
`{project_id,session_id,paused,expected_version,idempotency_key?}`. Same-key retries
return the same result; new requests require the latest control version. Pause
blocks dispatch and delivery writes, while humans can continue chatting. A bound
worker cannot remove delivery fields to bypass a pause, disabled binding or
outstanding lease. The response includes `running_turns_cancelled:false`: the Hub
cannot claim to have cancelled a model already running at its provider. Relays need
their own supported cancellation mechanism.

The owner or an admin may `POST /v1/chat/control` with
`{project_id,binding_id,enabled,expected_version}`. This changes only one binding
and uses version CAS, without an idempotency key. Explicitly setting `enabled:true`
also resets a failed batch's attempts and read receipt while retaining its delivery
ID, stable reply key and cursor. It does not add model-start budget or extend expiry;
renew the binding when those limits have been reached. Disabling and rejoining
increments the binding generation and fences the old conversation's leases.

The owner or an admin may `POST /v1/chat/disconnect` with
`{project_id,binding_id,expected_version}` to leave automatic mode explicitly. It
records `released_at`, disables the binding and increments its generation. Old
pending deliveries are marked `released`; their messages stay in the event log and
the processed cursor does not advance. Normal manual posts are then allowed. Joining
again preserves the cursor, so unprocessed messages remain eligible. Disconnect is
a version-CAS action: after an ambiguous response, read status and reconcile a
`disconnected` result rather than blindly retrying an old version.

Expiry alone allows ordinary manual posts again when the binding is otherwise
enabled and the worker/room remain authorized. It does not advance the delivery
cursor or revive old leases; old delivery reads/replies remain fenced. Pause,
disabled bindings, archived rooms and revoked workers still block these posts.
A failed batch or exhausted budget does not itself release a live binding; use
explicit disconnect to leave automatic mode. After expiry or explicit disconnect,
ordinary requests are manual requests; the same bearer credential cannot
cryptographically distinguish the caller's intent. Relays must stop on expiry or
disconnect and must never remove delivery metadata after an error.

Cookie-authenticated admin UI calls
`hub.delivery.call('status'|'pause'|'control'|'disconnect', arguments, SessionActor)` through the
same service and independently verifies login, CSRF and nonce. Read-only members
may view status but cannot control delivery.

## Deployment and rollback

Schema v6 adds four tables without rewriting shared messages, private messages,
tasks, memory or existing idempotency results. Posts without delivery metadata keep
their pre-v6 request hashes. The existing startup database lock serializes upgrades.

An older v5 server rejects a newer database schema. Rolling back only the image is
therefore insufficient: use a v6-compatible corrective build, or restore application
and database consistently using the documented backup process. SQLite checks do not
replace PostgreSQL migration/runtime acceptance.
