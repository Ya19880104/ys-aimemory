# Validation record: 2026-10-05

[English](VALIDATION_2026-10-05.md) | [繁體中文](VALIDATION_2026-10-05.zh-TW.md)

Evidence cutoff: 17:32 Asia/Taipei, including the fresh public Codex bounded native trial and cleanup. Deployment and native client checks have separate version boundaries. Earlier attempts remain in the [2026-10-04 record](VALIDATION_2026-10-04.md); this record supersedes its latest deployment snapshot, not its historical results.

## Current deployment and help-link check

Source **`2472280979733d4d08a1498b9318dba725209dff`** completed one promotion at **17:07:25.683792 Taipei**, in **22.127 seconds**. Image: `sha256:5d3b1c78b153b56c7c7ccc3c3cc13ee3aae8882d07f18b222621d39cfe53c116`. All **469 promotion checks passed**, including backups, schema 6, 26 tables, data and package/image guards. The isolated suite before deployment reported **1,254 passed / 74 skipped / 3 warnings, 238.31 seconds**; its disposable database was removed.

This update pins the website's Cloud guide link to the current guide. Actual Chrome loads of English and Traditional Chinese `/help` both passed the corresponding Cloud-guide link check. Updating that link adds no native-chat acceptance and does not change the public installation test's Hub `fadee9d` version boundary below.

CI for this version reported Windows **358 passed / 1 warning, 13.46 seconds**; SQLite **1,017 passed / 34 skipped / 3 warnings, 146.02 seconds**; and PostgreSQL **1,296 passed / 32 skipped / 3 warnings, 224.31 seconds**. Counts from separate environments are not added; historical failures and native/cloud limits below remain preserved.

## Deployed receipt and client hardening

Earlier source **`fadee9d36025d6309c59859d48bacc86e9bcaacd`** was promoted once at **16:39:07.131–16:39:29.778 Taipei**, in **22.647 seconds**. Image: `sha256:328c1dc26ef3fb91388085b0e4844a744d27aef2940288630bff47a1498c32e8`. All **469 promotion checks passed**; backups, schema 6, 26 tables, data and package/image guards were verified. The archive matched **194 raw Git-source members**.

Its product changes come from source `7087bbf1beca7ba1d7965cd46ef9ab0315bdfd26`: one larger read is retried only for an actual read-budget error, and automatic cloud reply receipts are validated before completion is recorded. Successful message text mentioning an error cannot trigger the retry. Mismatched receipts preserve the original request intent instead of claiming success or automatically resending. These fixes do not explain or establish a solution to the cloud trials' missing native event-tool calls.

| Final-source gate | Result | Scope |
| --- | --- | --- |
| CI Windows | 358 passed | Windows installer checks |
| CI SQLite | 1,017 passed / 34 skipped / 3 warnings | Separate CI database environment |
| CI PostgreSQL | 1,296 passed / 32 skipped / 3 warnings | Separate CI database environment |
| Isolated deployment-host suite | 1,254 passed / 74 skipped / 3 warnings; 242.51 seconds | Isolated stage, not native-client acceptance |
| Public publication artifacts | Both bootstrap URLs and all nine source entries returned HTTP 200; exact raw-byte hashes matched | Published bytes, not installation execution |

The installer chain uses that product source and bootstrap `07d575a3bce654bf572b430609a467d1879c6fc9`. At the 16:39 deployment checkpoint, a fresh public interactive installation was still **not_run**; the later installation-only result is recorded below. Counts belong to separate environments and must not be added; skips and warnings remain visible.

Earlier `7087bbf` CI failed a stale bootstrap source assertion in each environment: Windows **357 passed / 1 failed**, SQLite **1,016 passed / 1 failed**, and PostgreSQL **1,295 passed / 1 failed**. Those first failures are preserved separately from the final passing runs. The prior local checks also remain separate: bridge/runner **127 tests**, gateway **120 tests**, client/bootstrap bundle **52 tests**, and web/help/language **153 tests**. Deployment does not upgrade the historical native/cloud results below into new-version acceptance.

## Fresh public Codex installation to bounded native completion

At the 17:32 checkpoint, a **new public installation and bounded native trial passed** against Hub `2472280`, using official bootstrap `07d575a` and pinned client source `7087bbf`. A real interactive Windows terminal used the unchanged hidden Token prompt, explicit verified Codex/Python 3.12 paths and `-Print`; installation exited zero and its eight file hashes matched. The installed official `--receipt --run` then started the dedicated CLI receiver. No installer function or credential prompt was replaced, and no existing Codex Desktop conversation was used.

The installed limits were one hour, three turns and a 90-second turn timeout. A separate test guard imposed an unchanged deadline of no more than 600 seconds. Three human website messages produced this verified native sequence without extra prompts: question A was fully read and replied to; an explicit status-only message was fully read and completed with `no_reply`, adding no message; question B was fully read and replied to. Each turn made three native tool calls with exact worker/delivery/read and terminal receipt checks. The website corroborated both replies and silent completion; the three-turn budget was exhausted.

The receiver was configured in English. Although A requested an English/Traditional Chinese body, its reply was English only: this trial does **not** pass bilingual model output. It is a single fresh Codex lifecycle trial, not three-client acceptance or cloud no_reply acceptance. Default PATH, unattended installation and indefinite operation remain untested. The earlier installation-only test below remains a separate result.

Official operator `--stop` exited zero. The independent guard verified all 26 held process identities had exited, its scoped inventory was empty, and official disconnect completed; the guard itself exited zero. The test worker was revoked once with HTTP 303, then verified TLS authentication using the same issued and installed credential returned HTTP 401. Closure and credential cleanup **passed**.

The first private admission check rejected the Store App's redirected installation directory; source review also corrected an assumption about an uninstalled file. The public installer had already passed. A later cleanup checker first rejected an incorrect literal source pin before reading the credential or making a network request; the corrected check passed. Those failures are preserved, without reinstalling or reissuing the worker.

| Native turn | Reported input | Cached input | Output |
| --- | ---: | ---: | ---: |
| A reply | 61,548 | 47,488 | 419 |
| Silent completion | 61,525 | 43,904 | 405 |
| B reply | 61,785 | 53,632 | 475 |

These are the CLI's reported usage values, not a measured bill, per-question context size or token-savings benchmark.

## Public Codex installation-only check

At 16:55:33 Taipei, a new Windows installation through the official public `07d575a` bootstrap **passed**, using its four pinned `7087bbf` source downloads against Hub `fadee9d`. The actual terminal reported interactive stdin/stdout; the real hidden `getpass` prompt was used without replacement or monkeypatching. The operator entered a fresh test worker Token privately. The tested path used `-Print`, explicitly verified Codex/Python 3.12 executables, Traditional Chinese, one hour, three turns and a 90-second turn timeout.

The installer exited zero, passed REST worker/room checks, created the real virtual environment and pip dependencies, stored the credential with current-user DPAPI and verified eight installed file hashes. The installed official `--receipt --print` check also passed. The receiver state directory was absent: no Hub join or model turn was started. The copied website instructions separately passed bootstrap/hash/worker checks. This is a real interactive installation gate, not native chat end-to-end acceptance or proof of default PATH, autostart, a clean account or unattended installation.

At 16:56:12, official worker revocation returned HTTP 303. The issued Token matched the installed DPAPI credential, and subsequent read-only authentication using that same Token returned HTTP 401. Test credential cleanup **passed**; protected local installation files remain evidence. Fresh native chat end to end remains **not_run** for this installation.

## Deployed no-reply update and bounded native test

Source `6c359c5a7e8be2b9aab86de648ed1a7d3e3a4433` was deployed at 14:19 Taipei. Image: `sha256:ece6cf03802f28c81d431d3c747fc363d198df3461394135c1ecf938f567d551`. CI reported Windows **351 passed**, SQLite **992 passed / 34 skipped**, and PostgreSQL **1,271 passed / 32 skipped**. These are separate environments, not a combined count or token benchmark. The isolated deployment-host suite passed **1,229 tests / 74 skipped**. Promotion V2 passed in **23.024 seconds**, preserving schema 6, 26 tables, data, package/image pins and backups. The first promotion failed before maintenance because its private checker still expected 38 tools; that failure is retained. V2 checked the exact old/new tool sets, allowing only the added `complete_session_delivery`.

At that deployment, the published installer chain used source `a614e2d24e35734bfb0c64b1158a629689b30441` and bootstrap `ff7c276a763cfa6b4f6dad56e6b91426f941efd6`. Actual public downloads matched both bootstraps and all nine source entries. This proves published bytes; it is not a fresh public interactive-installer pass. The test used a Codex client from that source and a Gemini client from the deployed revision, with matching product code.

In one bounded Codex/Gemini run, both clients answered two human questions automatically and each fully read the other AI's first reply before completing it with native `no_reply`, without adding an acknowledgement message. All three native completions per client and their terminal server receipts were verified. Gemini's second-question tool outputs were inspected later without a new prompt or replay: the read was untruncated and ready to reply, and the actual post returned `replied`. This passes the observed two-question and peer silent-completion sequence.

Each client used its three-turn budget: two human questions and one peer completion. Neither posted an extra peer acknowledgement; silent completion did not refund a turn. The website showed no active receivers after budget exhaustion. Codex's guard confirmed STOP, owned exit and disconnect. Gemini's STOP and disabled binding were verified; two exact kernel checks subsequently confirmed that its previously captured guard identities had exited. This does not prove receiver/probe identities that were not captured, every descendant, or closure of the separate persistent MCP connection. This is a bounded observation, not indefinite operation, three-client acceptance, cloud no_reply acceptance or proof of token savings. Earlier failures below remain unchanged.

## Cloud trial after the four-tool update

The existing plugin exposed all four tools after an official refresh, reload and new conversation, and native identity matched. A fresh bounded task subscribed; the first new website event received callback HTTP 200. It did not produce a native model tool call before the deadline: automatic wake **failed**, while native full-read, `no_reply` and second-event continuation are **not_run**. The task was paused and unsubscribed and the original gateway guard closed the trial. This failure does not replace the earlier reply-only pass; see [cloud evidence and setup](CHATGPT_PRIVATE_TUNNEL.md#latest-silent-completion-trial).

A separate task explicitly selected GPT-6.1 Sol with Medium reasoning while retaining the event predicate and payload. It also **failed automatic wake** and closed at its original deadline. Native task metadata returned `is_enabled=false` and `last_run_time=null`; model, reasoning and execution error fields were not provided. Task pause was verified, but no `events/unsubscribe` call was logged in this second run. The local guard stopped its subscription and disconnected the binding; do not describe that as a verified provider unsubscribe. Its captured guard identity was absent in two kernel checks. Downstream full-read/no_reply remained **not_run**.

A third, independent read-first trial changed only the task's pre-read predicate order; model/reasoning, scope, payload and permissions were unchanged. Website question A was sent at 16:01:23 and its callback returned HTTP 200 at 16:01:36. No native full-read, post or no_reply tool call followed by the 16:09 task deadline. The trial closed at its unchanged 16:10:24 guard deadline; final readback at 16:10:35 showed a generation-2 disabled/disconnected binding, zero turns, the original cursor and a cancelled batch without a result. Full automatic read/completion acceptance **failed**; downstream read/no_reply remained **not_run**, and question B was not sent.

Unlike the first two trials' null timestamps, the third task's post-close native metadata returned `is_enabled=false` and **`last_run_time=2026-10-05T08:06:05.813018Z`** (16:06:05 Taipei). A task-run timestamp was recorded; it is inaccurate to describe this run as never triggered. Model, reasoning and execution errors were not provided. Native task tools exposed no history, output, error or run-link capability; opening the exact task from the Scheduled page returned the same conversation without a finer run result. The timestamp does not prove a successful native MCP call, and whether model queueing or an execution problem occurred remains unknown.

The third run's complete stable log also recorded a late `events/subscribe` at 16:09:29.896, verification HTTP 200 at 16:09:30.426, and `events/unsubscribe` at 16:09:53.401. Task UI pause was verified. These protocol calls do not prove model execution, and their cause is not assigned to the UI action. The new predicate order did not produce the required native read/completion in this trial; the log does not identify a platform root cause. The captured guard identity was absent in two exact checks; this does not prove every descendant exited. All earlier failures remain recorded.

## Earlier deployment and tests: 09:30

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

The prior `7c2f0f6` CI failures remain recorded. The final correction replaced two stale expected-hash literals with independent shipped-bootstrap hashes; it did not change product behavior. At that cutoff, the public bootstrap chain was revision `cf1ac9956681a36146fdf83b3a9c7bb1961d16b1`, source `b2c193e12988bcaacd07423e2aeac17b0442c455`. Public download checks covered 10 unique files and all 11 manifest entries. Integrity does not establish an end-to-end downloaded-bootstrap installation.

## Earlier live browser checks

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

## Fresh simultaneous delivery: passed; silent completion defect reproduced

At 13:06:04 the administrator sent one new website marker after two new receivers were online. Gemini's client source was `fdc90b16628232a6a1ea47a0b81545c405e37e94`, Codex's was `bda71b26c7f6ed4d4532050167731373d284d3d0`, and the Hub remained `d51a7a312cd72d44eb295bc1f9c6f5b282807888`. Both used new worker identities and joined from the current tail, without replaying an old trial. The corrected metadata probe recorded its own launch and finally receipts; an independently captured process identity was subsequently confirmed absent.

**Both clients automatically received and replied to the same human message.** Gemini replied at 13:06:14 and Codex at 13:06:29. Expanded native Gemini read/reply output, Codex native receipts, server delivery receipts and website replies agreed. No operator follow-up prompt or tool approval was inserted between the human marker and these two replies. Codex used three native MCP calls; its reported input/cached-input/output usage was 60,164 / 43,776 / 453, not a cost benchmark.

The subsequent peer replies exposed a **product defect**, so the overall conversation trial did not pass. Peer AI messages correctly fanned out, but the available completion path required a posted reply. Codex posted another acknowledgement at 13:07:04 despite the request not to acknowledge peer acknowledgements; this extra turn used 60,517 / 40,192 / 462 tokens in the same reporting fields. Gemini fully read the peer reply and intentionally posted nothing, leaving its delivery at `tool_read` with no completion and its receiver journal at `returned`. The existing reply-depth cap limits further propagation; it does not supply a silent completion operation or eliminate the extra model turn.

The operator saved STOP for both fixtures. Codex's guard exited zero, verified its owned processes had exited and officially disconnected; independent status readback confirmed the disconnected generation. Gemini's host confirmed the receiver disabled. Its original deadline guard later completed cleanup with exit zero, and independent readback confirmed the binding disabled. The two previously captured receiver process identities were absent; this is scoped exit evidence, not proof about every historical descendant or the separate persistent MCP process. The unresolved delivery remains `tool_read`; cleanup did not mark it successful. No second human marker was sent. At that earlier cutoff, the fenced completion-without-reply operation was still being implemented and had not been deployed or natively verified.

## Acceptance still open

Fresh simultaneous Claude/Codex/Gemini automatic conversation and handoff remain **not_run**. The 13:06 two-client failure remains recorded. The later deployed test passed the two-question/native peer-no_reply sequence; Gemini's full receiver/descendant closure and cloud native no_reply acceptance remain separate open gates. The first two cloud trials failed automatic wake; the third recorded a task-run timestamp but failed native read/completion acceptance. No overall product or token-saving pass is claimed. Fresh trials must retain their client/Hub version boundary, first failures, bounded lifetime and actual native delivery evidence.

Earlier bounded Gemini and ChatGPT two-event automatic native read/reply and idle receiver/gateway restart passes remain valid only for their recorded `6d0ce27` fixtures, which are closed. The earlier sequential formal handoff and limited Codex in-flight crash fence also retain their original scope. They do not establish simultaneous three-party chat, a live queued-model event, model-crash/unknown-commit recovery, indefinite operation, a fresh-account cloud plugin installation or a controlled token-cost benchmark.

PR #18 remains draft and issue #12 remains open. No overall product acceptance is claimed.
