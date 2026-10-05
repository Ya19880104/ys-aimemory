# Validation record: 2026-10-05

[English](VALIDATION_2026-10-05.md) | [繁體中文](VALIDATION_2026-10-05.zh-TW.md)

Evidence cutoff: 12:45 Asia/Taipei. Deployment and native client checks have separate version boundaries. Earlier attempts remain in the [2026-10-04 record](VALIDATION_2026-10-04.md); this record supersedes its latest deployment snapshot, not its historical results.

## Deployed source and tests

Source `d51a7a312cd72d44eb295bc1f9c6f5b282807888` was promoted at 09:30 Taipei. Image: `sha256:094ffd83f8083b178a61b20c17b7d5247d92d18bed55b75754f8ff3218a13ed3`. The release archive matched all 191 Git-source members byte for byte. Its SHA-256 was `967702ddb835253e7baf12fa52551853a054fee9a19e9a8e68bcf68296b5f832`.

| Gate at this source | Result | Scope |
| --- | --- | --- |
| CI Windows | 334 passed, 1 warning; 18.74 seconds | Windows installer checks |
| CI SQLite | 942 passed, 34 skipped, 3 warnings; 124.08 seconds | Separate CI database environment |
| CI PostgreSQL | 1,203 passed, 32 skipped, 3 warnings; 211.17 seconds | Separate CI database environment |
| Isolated deployment-host suite | 1,163 passed, 72 skipped, 3 warnings; 226.85 seconds | Disposable PostgreSQL database removed afterward |
| Promotion | 462 checks passed, 0 failed; 22.651 seconds | Backup created; schema 6 and 26 tables preserved, allowing only expired web-auth cleanup |
| Independent 09:31 readback | Passed | Exact source/image, healthy container, verified HTTPS and PostgreSQL; zero unexpired enabled bindings and execution leases |

All six jobs in the [PR run](https://github.com/Ya19880104/ys-aimemory/actions/runs/37231666006) and [push run](https://github.com/Ya19880104/ys-aimemory/actions/runs/37231661568) succeeded. Counts belong to separate environments and must not be added. Skips remain skips. Existing warnings concern Starlette/httpx, Pydantic lifespan resolution and per-request cookies; the recorded warning count depends on the suite. Backup restoration and off-host recovery remain **not_run**.

The prior `7c2f0f6` CI failures remain recorded. The final correction replaced two stale expected-hash literals with independent shipped-bootstrap hashes; it did not change product behavior. The public bootstrap chain remains revision `cf1ac9956681a36146fdf83b3a9c7bb1961d16b1`, source `b2c193e12988bcaacd07423e2aeac17b0442c455`. Public download checks covered 10 unique files and all 11 manifest entries. Integrity does not establish an end-to-end downloaded-bootstrap installation.

## Live browser checks

On the deployed release, the English and Traditional Chinese chat page showed **0 current receivers / 0 online**, with **12 inactive records collapsed separately**. Expanding the English history and refreshing preserved its open state; it could then be collapsed again. Both languages clearly distinguish receiver heartbeat from a model read or reply. Private screenshots retain the actual browser evidence.

The deployed help page rendered both languages, the project-installer/manual-stdio distinction, the short daily chat request, and the bounded cloud setup/stop instructions. This is live page evidence, not automatic message delivery, public installer execution or an acceptance of every client path. No new test message was sent during these checks.

Actual copied setup instructions passed all four English/Traditional Chinese × Claude/Codex combinations: immutable revision and SHA-256 matched the independently read Git bootstrap bytes, the selected language and one-hour/three-turn budget matched, the installation line remained commented, and no `undefined` appeared. These commands were copied and inspected, not executed. The new bilingual compact documentation examples also passed offline validation against the shipped target input model; flattened target input was rejected and both languages used identical JSON.

## Fresh native client preparation

These ordinary native checks used installed clients and Hub source `bda71b26c7f6ed4d4532050167731373d284d3d0`, before the new deployment:

- **Codex passed native identity and an empty incremental room read**, with actual MCP receipts and owned process exit. Earlier failed attempts and the separate SDK catalog check remain distinct.
- **Gemini passed native pre-join status**, reporting inactive. Its subsequent bounded automatic trial is recorded separately below.
- **Claude passed an ordinary native identity call in a new Local Code conversation**, with the expected worker and project. Its first flattened `memory_call` input failed schema validation; the second call preserved both `arguments` layers and succeeded. This is not a first-attempt pass, room read/write or automatic-chat acceptance. The earlier conversation retained a closed MCP connection; it was not treated as a current connection.

Claude's shorter-path official installation completed, but the private test wrapper then rejected a logical-versus-physical Windows Store path comparison. Read-only review verified the installed receipt, source/configuration pins and resolved same-file identity. That evidence does not erase the wrapper failure. A separately reviewed metadata-adoption command was **not_run** because Claude's Auto permission classifier denied it before execution; explicit approval remains pending. No retry, permission relaxation or manual replacement receipt was used.

The documentation now supplies the missing complete [compact dispatcher example](API_EXAMPLES.md#compact-local-dispatcher). This is a guidance correction; it does not change the API or certify that a fresh model will select the correct input on its first attempt.

## Bounded two-client trial and monitor correction

At 12:10, an administrator submitted one marker through the actual chat page after both fresh receivers reported ready. The installed clients were `bda71b26c7f6ed4d4532050167731373d284d3d0`; the deployed Hub was `d51a7a312cd72d44eb295bc1f9c6f5b282807888`. This was a two-client trial; Claude was not included.

- **Gemini automatic native read/reply passed for this one event.** The native conversation woke from the background notification, read the entire message, and posted its own reply. The operator approved the first `chat_read` tool prompt once; no follow-up model prompt was used to trigger the response. Actual expanded native tool outputs, the server delivery receipt and the website reply agreed. This does not establish unattended first-use approval.
- **Codex failed before any native MCP call.** The private test monitor rejected an unrecognized child executable and saved STOP. The runner recorded a stopped/timed-out native turn with zero tool calls; missing token usage remains `not_reported`. The original monitor also failed to prove closure of a late process. A later scoped cleanup verified the previously recorded processes had exited and officially disconnected the binding; it did not erase the failure or establish the unidentified historical child's exact exit.
- **A separate ordinary-call diagnostic reproduced the monitor rejection.** It recorded the exact installed `codex-code-mode-host.exe`, its SHA-256, its direct held Codex parent and hashed arguments before rejecting it. That diagnostic confirmed exit of all processes it had observed and preserved the old STOP. It made no successful MCP call. The correction and fresh trial below address the private monitor; this finding alone does not prove a product-server defect.

The common deadline stopped the Gemini receiver and disabled its binding. Later read-only checks confirmed exit of its recorded receiver/guard identities, and two scoped inventories contained only the separate persistent MCP processes. The native host's actual `GetAllPlugins` output no longer listed the receiver. The repeated metadata-only probe had not recorded its second process identity, so its historical exact-process exit remains unverified; current scoped inventories found no probe. No old attempt, cursor or budget was reset.

The private harness also exposed two setup defects: Windows `Start-Process` can return a virtual-environment launcher PID rather than the interpreter PID in READY, and a repeated metadata probe collided with its exclusive exit evidence file. Both original failures are retained. The actual receiver start used a held interpreter identity check; the old exit file was not reused as proof of the repeated probe's exit.

## Corrected Codex monitor: two automatic replies passed

The corrected private monitor admits only the observed code-mode host with the exact executable hash, single-executable argument list and direct held Codex parent. Other unknown children still stop the trial. It now durably records owned child metadata before rejection and retains those handles for exit verification. Twelve pure admission checks passed, followed by fresh native identity and empty incremental-read calls with owned process exit. No old failed attempt was restarted.

A fresh worker using the same bda client/d51 Hub version boundary then completed two actual automatic turns:

| Event | Human message → native reply | Native MCP calls | CLI input tokens | Cached input tokens | Output tokens |
| --- | --- | --- | --- | --- | --- |
| A | 12:41:22 → 12:41:47 | 3 | 60,105 | 52,608 | 461 |
| B, after returning to idle | 12:42:51 → 12:43:15 | 3 | 60,018 | 52,608 | 440 |

For each event, the administrator sent a new message through the actual website. The dedicated Codex CLI receiver automatically verified its identity, fully read the delivery and posted one reply. Actual native receipts, server `replied` receipts and visible website replies agreed; both deliveries had one attempt. There was no operator catch-up prompt, direct SDK tool-call substitute or receiver restart between messages.

These usage fields are direct `turn.completed.usage` observations, not a controlled comparison or an invoice. Cached input is not additional input to sum into the total. The figures do not establish that token cost is minimal; reducing model round trips remains a separate optimization task.

After the second reply, an operator STOP ended this trial early within its independent ten-minute deadline. The guard verified owned handles had signaled and the scoped process inventory was empty, then performed the official disconnect. Its exit code was zero; independent server readback confirmed the binding was disconnected and local native-active state was absent. This passes bounded continuous receive for two events and orderly stop. It does not test a receiver restart, model crash, simultaneous multi-client conversation or indefinite operation.

## Acceptance still open

Fresh simultaneous Claude/Codex/Gemini automatic conversation and handoff remain **not_run**. The completed two-client attempt above was not an overall pass. Fresh trials must retain their client/Hub version boundary, first failures, bounded lifetime and actual native delivery evidence.

Earlier bounded Gemini and ChatGPT two-event automatic native read/reply and idle receiver/gateway restart passes remain valid only for their recorded `6d0ce27` fixtures, which are closed. The earlier sequential formal handoff and limited Codex in-flight crash fence also retain their original scope. They do not establish simultaneous three-party chat, a live queued-model event, model-crash/unknown-commit recovery, indefinite operation, a fresh-account cloud plugin installation or a controlled token-cost benchmark.

PR #18 remains draft and issue #12 remains open. No overall product acceptance is claimed.
