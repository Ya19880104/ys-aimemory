# Experimental Gemini native host queue

## Current bounded acceptance — 2026-10-04 evening

On live source `7652f1d7f04ef4c00e8860217a0f732f98dcb58e`, Gemini passed two consecutive fresh Hub messages B and C using actual native `chat_read` and `chat_reply`: human sequence 55 → reply 56, then human 57 → reply 58, each on attempt 1. There was no manual model prompt between either website send and response. This is bounded continuous native delivery evidence, separate from the earlier queue experiment and historical snapshot below. See [validation record](VALIDATION_2026-10-04.md) for source and acceptance boundaries.

Same-binding idle receiver restart **failed / incomplete**. Changing a filesystem `enabled` setting did not live-reload the host plugin; after the owned receiver exited, no replacement appeared before expiry. The official host lifecycle control still requires live verification. Treat the restart steps below as an unaccepted test protocol, not a proven restart procedure; no one-command restart is established.

The expired permission-wait fixture and the later bounded fixture are closed. STOP and disabled binding state override conversational statements such as “waiting for the next message”: that wording does not prove an online receiver or a valid lease. A later test requires a new explicit, scoped run and verified host startup, not replay of the expired fixture, clearing STOP or extending its expiry. Preserve old journals and receipts. Formal Gemini task/source/artifact/attachment handoff and simultaneous three-client acceptance remain **not_run**.


`memory_hub.client_antigravity_receiver` includes an explicitly selected
`official_host_queue` admission mode for a dedicated, bounded Antigravity test
conversation. Ordinary installers and default native-idle admission are unchanged.

In one native experiment, the official sidecar waited 200 ms after the first
command returned before submitting the second synthetic message. The UI showed the first complete response followed by the second
system notification and its response. This is evidence for that observed native
queue sequence only. That early experiment did not certify continuous Hub chat, receiver restart,
general busy-session safety or three-party acceptance; later bounded continuous
delivery evidence is recorded above.

The installed official CLI provides `get-conversation-metadata` and
`send-message`. Queue admission queries metadata for the exact configured native
conversation and verifies its local workspace URI and native project before each
notification. Metadata establishes scope; it does not establish idle. Only native
MCP read/reply receipts establish delivery completion. First-use native tool
permissions still require the user's normal client approval.

## Module integration

The caller provisions the protected HTTP transport and chat-only MCP bridge,
explicitly joins a fixed Hub room, and supplies the returned binding ID,
generation, fixed expiry and budgets. The receiver does not join or rebind itself.

```python
from memory_hub.client_antigravity_receiver import (
    run, official_metadata_admission,
)

# Explicit reviewed opt-in; all remaining scope and budget fields are required.
config["admission_mode"] = "official_host_queue"
config["native_project_id"] = reviewed_native_project_id

state = run(config, protected_client, private_state_directory, official_agentapi,
    lambda: official_metadata_admission(config, official_agentapi))
```

Use only the official sidecar host's executable/environment. Do not discover
provider tokens, guess an internal server address, or access transcripts. The
notification contains instructions and no Hub message bodies. Chat content does
not authorize source work, commands, deployment or other destinations.

An OS lock excludes concurrent receivers. A durable journal records intent before
dispatch. Unknown, returned or interrupted attempts are reconciled with the exact
Hub delivery receipt before another claim. They are never automatically resent.
An expired unresolved delivery returns `unresolved`; preserve its journal and use
explicit recovery. A transport return code is not native completion or idle.

## Controlled receiver restart

1. Record the exact binding, generation, expiry, latest delivery and journal.
2. For an idle-process crash test, stop only the owned receiver process without
   disconnecting the Hub binding or changing STOP/journal/admission files.
3. Using the supported official host lifecycle control, start the same reviewed
   sidecar with the same private state directory and verify the replacement process.
   Editing filesystem configuration alone does not establish host reload.
   Never clear an existing STOP file to revive an old run.
4. Verify status reconciliation precedes claim. If a send was uncertain, the
   receiver waits for its exact replied receipt or returns `unresolved`; it must
   not send the same delivery again.
5. For an in-flight crash test, preserve intent and lease. Expiry, generation
   change, pause, disconnect or exhausted budget requires an explicit new test or
   normal recovery; do not extend expiry or reset attempts to obtain a pass.

The focused source suite recorded 16 passed and two dependency warnings in a
Windows Python 3.12 run. It includes a real FastAPI/SQLite REST-contract check and
offline error/recovery tests. These results are distinct from native acceptance;
the documented restart protocol has not yet passed a native test.

Official references: [Sidecars](https://antigravity.google/docs/sidecars),
[Lifecycle hooks](https://antigravity.google/docs/hooks).

## Historical controlled acceptance snapshot — earlier 2026-10-04 run

The installed receiver source was `523c0c3be59860e3373475d69042962a626d4c09`.
The subsequent documentation HEAD was
`11458de0b108b5e458408a15007480cccdaccc6d`; the server remained on
`66db7e17ad53da019be90bbc705238ac0a3493cf`. These are separate version identities.

In the bounded native test, Codex and Claude each read and replied to two fresh
human broadcasts and completed one peer follow-up. Exact Hub deliveries recorded
native read/reply timestamps and one attempt each. Both stopped at their server
budget of three turns.

The dedicated **official Codex CLI** also passed a controlled idle receiver
process crash/restart: the same binding, generation, configuration, expiry,
journal, server cursor and remaining budget were retained. A second human
broadcast was read and replied to after restart. The restarted process's local
turn counter reset, while the server's cumulative budget did not. This verifies
that controlled CLI path; it does not establish automatic wake-up in an arbitrary
Codex Desktop conversation or an in-flight restart.

Gemini's official host accepted one automatic notification, but its native
`chat_read` permission prompt awaited user approval beyond the delivery lease.
The receiver recorded `unresolved` at **2026-10-04 09:07:32 UTC**; the delivery
lease expired at 09:07:29 UTC, before the binding's 09:13:21 UTC expiry. Its
delivery had no read/reply receipt, and the journal retained the single returned
attempt without an automatic resend. Native acceptance was `not_run`; this is a
preserved incomplete run, not a completed delivery or a general source failure.
At this historical cutoff, Gemini continuous reception and restart, full
three-party acceptance, network recovery, artifacts and formal task handoff
remained unverified. Later bounded continuous delivery is recorded above. CLI return code zero is not a native acceptance result.

For a first test, join only the intended dedicated conversation and review the
native client's conversation-only permissions before starting the bounded
acceptance window. Allowing `chat_status` does not approve `chat_read` or
`chat_reply`; the client may ask separately for each tool. Use the client's
normal approval UI for those requests. If a pending request outlasts its delivery
lease or test expiry, preserve the journal and receipt and use explicit recovery.
Do not automatically resend, clear attempt history, or extend an expired test
merely because approval arrived later.
