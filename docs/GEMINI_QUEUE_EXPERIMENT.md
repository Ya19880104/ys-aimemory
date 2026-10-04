# Experimental Gemini native host queue

`memory_hub.client_antigravity_receiver` includes an explicitly selected
`official_host_queue` admission mode for a dedicated, bounded Antigravity test
conversation. Ordinary installers and default native-idle admission are unchanged.

In one native experiment, the official sidecar waited 200 ms after the first
command returned before submitting the second synthetic message. The UI showed the first complete response followed by the second
system notification and its response. This is evidence for that observed native
queue sequence only. Continuous Hub chat, receiver restart, general busy-session
safety, and three-party acceptance are not certified by this experiment.

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
3. Start the same reviewed official sidecar with the same private state directory.
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
