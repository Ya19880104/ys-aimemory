# ChatGPT private Tunnel pilot

[繁體中文](CHATGPT_PRIVATE_TUNNEL.zh-TW.md)

This pilot connects **one dedicated Hub worker to one project and one shared room** through OpenAI Secure MCP Tunnel. It exposes no public listener. The surrounding Platform organization and ChatGPT workspace permissions are its access boundary. Every caller granted access to this tunnel acts as the same configured service worker. This is **not an OAuth, multi-user public plugin**.

Source tests are not ChatGPT acceptance. Record tool discovery, actual cloud tool calls, subscription verification, webhook receipt, model response and Hub write-back separately. A webhook `2xx` is only **received**, not **replied**.

## What is included

- `identity`: verifies the configured worker and room; returns the latest sequence and shared pause state.
- `read_delta`: requires a cursor; reads up to 10 compact events, with an 8 KiB Hub response budget.
- `post_message`: posts up to 4,000 UTF-8 bytes with a caller-supplied idempotency key.
- `message.created`: new messages from other participants in the fixed room, starting when monitoring is enabled. Own messages are excluded.

The gateway does not expose a general Hub tool relay, caller-selected project, room, URL, task claim, administrator action or file access. It offers MCP 2.0 discovery and the three event methods over stdio. It does not provide a legacy MCP 1.x `initialize` interface.

## Prerequisites

1. Install this version of `ys-aimemory` in a dedicated Python environment on a machine that can reach the Hub. Use that environment's absolute Python path for the tunnel command.
2. Provision a dedicated, minimally scoped Hub worker for the pilot. Do not reuse an administrator or another AI's worker.
3. Obtain the public CA file and its SHA-256 fingerprint through a trusted channel. The gateway verifies the CA pin, hostname and TLS chain; it never disables verification.
4. Confirm that the Hub provides authenticated `GET /v1/chat/status?project_id=...&session_id=...` with a boolean `control.paused`. Missing or unavailable control fails closed.
5. Create the appropriate private tunnel, associated only with the intended organization/workspace; keep the runtime credential local. See [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
6. Determine the exact ChatGPT callback hostname from the actual connection. Start with `callback_hosts: []` for tools-only verification if it is not yet known; subscriptions will fail closed. Enable events only after adding the verified exact hostname. No wildcard or guessed hostname is enabled by default.

## Private configuration

Store this outside Git. Replace the example identifiers and fingerprint with the intended fixed room and verified public CA. Paths are relative to this configuration file.

```json
{
  "hub_url": "https://memory.example.internal",
  "ca_file": "public-ca.crt",
  "ca_sha256": "REPLACE_WITH_VERIFIED_64_HEX_SHA256",
  "project_id": "cloud-pilot",
  "session_id": "REPLACE_WITH_32_HEX_ROOM_ID",
  "worker_id": "chatgpt-cloud-pilot",
  "state_path": "private/gateway.sqlite",
  "callback_hosts": ["REPLACE_WITH_EXACT_CALLBACK_HOST"],
  "poll_interval": 5,
  "subscription_ttl": 1800,
  "max_events_per_subscription": 20
}
```

Provide `YS_AIMEMORY_TOKEN` only in the gateway process environment. On Windows, callback URLs, webhook signing secrets and queued event bodies use current-user DPAPI encryption. On other systems, provide `YS_AIMEMORY_GATEWAY_KEY` as a base64-encoded random 32-byte AES-GCM key through the process environment. Retain that key securely for subsequent starts. Do not put either value in a URL, command argument, checked-in profile, report or screenshot.

`CONTROL_PLANE_API_KEY` belongs to `tunnel-client`; it is distinct from the Hub worker Token. Never give an administrative OpenAI key to the long-running runtime.

## Check, connect and test

Run from the installed environment:

```sh
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --check
```

This verifies Hub TLS, worker identity, fixed-room metadata and pause control. It sends no callback and fetches no message body. Its result is `checked_not_native_verified`.

Use the official `sample_mcp_stdio_local` profile. Its command should launch:

```sh
/absolute/venv/python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json
```

Use `tunnel-client doctor` and its supported runtime supervision commands; check health/readiness. In ChatGPT, create a developer-mode connection using **Tunnel**, then select the intended private tunnel. The stdio pilot has no browser OAuth login; access is governed by the tunnel's organization/workspace association. See [Connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt).

Start a **Work** chat on ChatGPT web, or **Work + Cloud** in the desktop app. Invoke the plugin and verify:

1. `identity` returns the expected worker, project and room.
2. `read_delta` retrieves only explicitly requested sequences.
3. `post_message` writes one test message, verified independently in the Hub.
4. Ask ChatGPT to monitor `message.created` and specify how it should respond. Confirm that subscription and signed callback verification succeed.
5. Send a new administrator message in the Hub. Verify webhook receipt **and** an actual cloud model turn and Hub reply; a polling script is not a substitute for this test.
6. Pause automatic chat in the Hub. New callbacks and gateway posts must stop. Resume and verify bounded delivery.
7. Stop monitoring in ChatGPT; verify unsubscribe. Test local stop independently.

Cloud event support uses the [official MCP Events contract](https://developers.openai.com/plugins/build/mcp-events). ChatGPT cloud availability and workspace policy still require actual account verification.

## Stop and observe

```sh
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --status
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --stop
python -m memory_hub.cloud_tunnel_gateway --config /private/pilot.json --resume
```

`--status` reads only local counters. `--stop` persists across restarts, disables subscriptions and cancels queued deliveries. `--resume` permits a new explicit subscription; it does not restore old subscriptions. A request already in flight cannot be recalled.

The Hub room pause is checked immediately before every webhook dispatch and post. No delivery occurs while paused or when that control cannot be verified. One active cloud subscription is allowed. A subscription can receive at most 20 events; refresh does not replenish that budget. After exhaustion, stop monitoring before explicitly starting a new subscription.

## Limits and recovery

- SQLite keeps the event cursor and encrypted outbox across restart. One process may own a state file at a time. Changing its worker/project/room requires a new state file.
- Webhook delivery is at least once. Retries retain event IDs with fresh signatures, use bounded backoff and stop after five attempts. `410` and `413` are not retried. Native message writes require idempotency keys.
- The pilot does not expose protocol replay cursors. Events missed after subscription expiry are not replayed on renewal. Use `read_delta` explicitly to recover any gap.
- Callback hostnames must match the exact allowlist, all DNS answers must be public, and connections use the validated IP while preserving hostname verification. Redirects are refused. Update the allowlist only after verifying a legitimate callback change.
- Signatures and callback verification are implemented; secret rotation has a short overlap. State decryption failure stops processing rather than discarding state.
- Cross-client binding/claim receipts and shared round-budget allocation are not implemented by this adapter. It honors the common room pause and its own bounded event budget. Neither webhook receipt nor these source tests prove native cloud replies.
- No public/plugin marketplace publication, OAuth account linking, provider session-cookie access or automatic global installation is included.
