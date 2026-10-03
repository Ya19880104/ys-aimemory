# Validation record: 2026-10-03

[English](VALIDATION_2026-10-03.md) | [繁體中文](VALIDATION_2026-10-03.zh-TW.md)


## Latest round-two verification

Runtime source: `24f317310ea6fdd66ca78da8cea3003a413d226c`, promoted **2026-10-03T15:16:07Z**, image `sha256:2ebd766dc9aad165adccb21526651b4835c39a575d248cb0530f9920e7aa1f90`. This section records sanitized executor-supplied results, not an independent rerun by the documentation reviewer. Native evidence below used watcher `e24b13c418bad9705f86b589b1ac212145d06a71` with the earlier `c4fe0f1` Hub, before promotion; do not assign that native evidence to the new runtime.

| Gate | Result | Scope |
| --- | --- | --- |
| PostgreSQL VM stage | passed: 779 tests, 56 skipped, 3 warnings; 180.82 seconds | Skips are not passes |
| Focused Windows checks | passed: 104 tests | Scoped source checks, not full candidate CI |
| Promotion | passed: 427 checks in 22.332 seconds | Applies to this runtime/environment |
| Public bootstrap | passed: all six URLs HTTP 200, declared hashes and Git blobs matched | Artifact integrity, not every client installation |
| Claude idle automatic exchange | passed: approximately 16.646 seconds | Exact activation, idle listener, human browser message; ToolSearch plus native chat_read/chat_reply; no extra Claude prompt |
| Claude pause/resume | passed for observed sequence | Queued human message remained unanswered while paused; resume produced native read/reply after approximately 6.808 seconds |
| Claude controlled application outage | passed for observed sequence | About 12 seconds stopped; watcher reconnecting then idle with same binding/expiry; next human message produced native reply after approximately 6.119 seconds |
| Claude three-turn budget | passed for observed interval | Exhausted at 3/3; later human message caused no fourth turn for at least 37 seconds |
| Explicit disconnect | passed | Owned watcher stopped; no remaining owned Python watcher process or global configuration change. Independent STOP-case not tested because budget was already exhausted |
| New-runtime Chrome logout/deep-link/login | passed | Selected project and conversation preserved; this does not certify all GUI surfaces |
| GUI language switching | pending / not_run | HTTP language checks remain a separate earlier gate |
| ChatGPT event discovery | passed | Tunnel restored, plugin refreshed, updated notification schemas and message.created visible; fresh Work identity passed |
| ChatGPT native subscription / idle automatic action | not_run; no subscription established | Model reported unable to subscribe; root cause unresolved. Missing deferred tool names do not prove platform feature absence; events/subscribe is a protocol method |

ChatGPT acceptance requires observing the real subscription request, callback verification and stored subscription, webhook 2xx acknowledgement and native action. See [official MCP Events testing](https://developers.openai.com/plugins/build/mcp-events#test-in-chatgpt). Discovery and prompted identity/read/write cannot substitute for these steps.

Source/automatic expiry, full crash/restart, parent/orphan handling, load and revocation acceptance remain pending. No old-history replay was seen after the observed fresh join; other cursor/rejoin cases remain unverified. Earlier OAuth-expired, Chrome-offline and stale-metadata statements below describe their original snapshots and are superseded only within the scoped evidence above. Private identifiers, message bodies, hosts, evidence paths and screenshots are omitted.


## Latest deployed candidate: `c4fe0f1`

Candidate source: `c4fe0f1ecedbe186cc4b80f195e47dc606fe9470`. Promotion completed at **2026-10-03T09:45:32Z**. These are version- and environment-specific results, not acceptance for every client. The executor supplied deployment/HTTP results; this document update independently checked the CI totals and sanitized native receipt fields. No private IDs, credentials, host addresses, or evidence paths are published.

| Gate | Result | Scope |
| --- | --- | --- |
| GitHub CI: Windows | 211 passed | All three candidate CI jobs passed |
| GitHub CI: SQLite | 599 passed, 32 skipped | Skips are not passes |
| GitHub CI: PostgreSQL | 787 passed, 30 skipped, 3 warnings | Separate from VM stage |
| VM stage | 761 passed, 56 skipped, 3 warnings | Candidate runtime/environment |
| Promotion | 417 checks passed in 22.147 seconds | All 26 tables, schema v6 data, permissions, and backup-header reads passed |
| Fresh HTTP checks | Passed | Language switching preserved the selected room; English/Traditional Chinese automatic-setup panel, trusted CA and installer pin checks passed |
| Public Codex installer `49fb77a` | TTY reinstallation passed | Immutable source dependencies at `3577118`; no clone required |
| Fresh dedicated Codex native automatic exchange | Passed | One new human message triggered three native MCP identity/read/reply calls; reply after 26.6066 seconds, actor shown as Codex, receiver stopped at one-turn budget |
| Cloud tunnel | Healthy / ready after restoration | Transport health does not establish event subscription |
| ChatGPT prompted native identity/read/write | Observed passed | Earlier prompted exchange; cloud automatic subscription remains not_run due stale plugin metadata |
| Claude hook automatic replies | not_run | Provider OAuth login remains expired |
| Chrome GUI acceptance | not_run | Control connection remains offline; HTTP actions are not browser clicks |

The earlier `e1d71f8` CI run had one failure: the bootstrap source pin was stale after the receiver changed. That failure remains part of the record. For `c4fe0f1`, the public `49fb77ae3c64a6da61c4d4175d32b9f71e32d001` installer returned HTTP 200 and matched SHA-256 `3A9DC4603260D40E39FC04A3B639F35DF72533B53C809CAC3D6E317E0AC22B81`; all four dependencies at `35771181eeceba4375de631859eac270504103bc` returned HTTP 200, matched the declared hashes, and byte-matched their Git blobs. Candidate CI subsequently passed all three jobs. Earlier deployment-helper first failures remain preserved despite service recovery.

### Observed token usage; optimization remains under investigation

| Reported counters for observed exchange | Input tokens | Cached input tokens (included in input) | Output tokens |
| --- | ---: | ---: | ---: |
| Initial installer pilot | 71,711 | 58,880 | 436 |
| Scoped `skills.max_context_tokens=1` experiment at `ab1f20a` | 59,287 | 49,024 | 410 |
| Final candidate native exchange | 59,520 | 51,584 | 467 |

These are reported cumulative session/tool-exchange counters, not one prompt or billed usage; they are not a controlled benchmark or a guaranteed saving. The scoped skills override was followed by lower observed input, but these small samples do not establish causality, billing savings, or complete low-token optimization. The inspected inbox was only 126 bytes and was not the large-cost cause in this exchange; the new chat-scoped identity projection limits future inflation from unrelated task inboxes. Cost investigation continues.

The copied-installation guidance safety fix has source-scoped acceptance: 28 tests passed with two existing warnings, including real PowerShell parser coverage for both languages/clients and hostile `;` / `$()` worker values. Complete-guide paste performs download/hash verification/review only; installation stays commented until explicitly selected after review. The fresh HTTP panel check confirms rendered deployment behavior, while the parser check covers generated command safety. Neither substitutes for GUI clicks or cloud automatic acceptance.

Historical snapshots below retain their original version boundaries; their pending-at-the-time statements do not override the deployed candidate evidence above.

## Earlier verification snapshot (before final candidate deployment)

This update separates the tested/deployed `0e8ca5e76fd5bb5f186e3294d32e56d353bdcd94` candidate from later source changes. The executing coordinator supplied runtime results; this documentation review independently checked the three CI log totals and the sanitized fields of the private Codex native receipt. Private IDs, credentials, host addresses, and evidence paths are omitted.

| Gate / source | Result | Boundary |
| --- | --- | --- |
| GitHub CI at `0e8ca5e`: Windows | 157 passed | All three CI jobs passed for this commit |
| GitHub CI at `0e8ca5e`: SQLite | 546 passed, 17 skipped | Skips are not passes |
| GitHub CI at `0e8ca5e`: PostgreSQL | 725 passed, 15 skipped | Separate from the VM stage run |
| VM deployment stage at `0e8ca5e` | PostgreSQL 701 passed, 39 skipped; 429 checks reported | Applies to this stage/environment, not later source |
| Deployment helpers | Two first failures preserved; service subsequently restored | Recovery does not erase the original failures |
| HTTPS UI language switching | Bug found on `0e8ca5e`; source fix `63c9` awaiting deployment at this snapshot | Source correction is not deployed acceptance |
| Public immutable Codex installer at `78c37ad` | TTY installation passed | Uses the published installer; installation alone is not model acceptance |
| Codex dedicated CLI automatic exchange after this installation | Passed: one new human message triggered three native identity/read/reply tool calls | Private receipt passed; one-turn budget stopped the receiver |
| ChatGPT cloud prompted identity/read/write | Passed for the observed exchange | Directly prompted; not automatic wake |
| ChatGPT event subscription / idle automatic replies | not_run; stale plugin metadata blocked subscription | No subscription established |
| Claude hook automatic replies | not_run; provider OAuth login expired | Configuration does not establish model-provider authentication |
| Chrome GUI checks | not_run; control connection offline | HTTP and native CLI evidence are separate from GUI clicks |
| Copied installation instructions at source `e571031` | Scoped tests: 28 passed, 2 existing warnings | Real PowerShell parser checked both languages and clients with hostile `;` / `$()` worker values |

The clipboard fix comments every explanatory/worker line and the installation command. Pasting the complete guide performs download, SHA-256 verification, and opens the review file; installation requires explicitly removing the command's leading comment after review. The parser verified that the complete payload has no additional executable command and that the separately selected Codex installation command keeps the worker as one literal argument. It does not represent a deployed browser check. The test harness's initial Windows command-length and stdin UTF-8 failures were preserved before the corrected harness passed.

The tested Codex exchange reported **71,711 input tokens, including 58,880 cached input tokens, and 436 output tokens**. The usage is higher than intended and its cause remains under investigation; this is not low-token acceptance. Source `ab1f20a` adds the scoped `skills.max_context_tokens=1` override; a new one-turn experiment was underway when this snapshot was written. No cost improvement is claimed yet.

Later source includes the automatic-reply setup panel and safety fixes, but this snapshot does **not** certify that the fresh final release was deployed. Preserve exact version/environment gates and first failures when adding subsequent acceptance evidence.

## Historical baseline

Runtime/source base: `be876d2bc0aa9d824b0218872c3d787dea365db3`. This public summary records results supplied by the executing coordinator, plus a separate read-only documentation/publication review. It does not replace private command logs, exact client-version records, or original first-failure evidence. No credentials, host addresses, runtime keys, private room IDs, or message bodies are included.

## Reported runtime results

| Gate | Result | Limit |
| --- | --- | --- |
| Local SQLite regression | 475 passed, 2 skipped | Applies to the supplied base/environment; skips are not passes |
| PostgreSQL regression | 623 passed, 30 skipped | Applies to the supplied base/environment; skips are not passes |
| Private cloud tunnel/plugin | Created | Creation is not native read/write or automatic acceptance |
| ChatGPT cloud native identity | Passed | Confirms the scoped native connection, not every client |
| ChatGPT prompted native read | Passed | `read_delta` read the administrator test message |
| ChatGPT prompted native reply | Passed | `post_message` recorded the test reply |
| Hub browser incremental display | Passed for this exchange | Reply appeared without page reload; browser sync does not wake a model |
| Event subscription | blocked before subscription | Existing and fresh Work chats still exposed the old tool metadata and no event-subscription facility |
| ChatGPT idle automatic wake/reply | not_run | A direct prompt initiated the ChatGPT exchange |
| Dedicated native Codex CLI automatic reply | Passed for one bounded exchange | Human HTTP UI action triggered the receiver; no CLI prompt was sent |
| Codex room pause/resume | Passed for the observed sequence | Pause kept the queued message pending; resume produced a second native reply |
| Codex local stop | Passed for the observed interval | Receiver exited, its binding was disabled, and a later test message did not start another model turn |

Initial failures involved the test mount and were preserved by the executor. The later passing run does not erase them. This summary does not invent missing timestamps, commands, error details, or log paths. Keep the original sanitized test packet with those details before using this as a release acceptance record.

The cloud gateway was updated to durable delivery handling at `38f9be5` and restarted successfully. Both an existing Work chat and a fresh Cloud Work chat still reported the earlier `read_delta({after_sequence, limit?})` and `post_message({body, idempotency_key})` schemas, without `notification_id` or an event-subscription tool. No subscription was created. Refreshing plugin metadata and repeating native event acceptance remain pending; the Chrome control connection was unavailable. A healthy tunnel and successful prompted read/write do not establish automatic cloud replies.

## Dedicated Codex CLI receiver

Client source: `81cd260`, native Codex CLI `0.160.0`; Hub runtime remains `be876d2` (image `sha256:5e42935de091d8917acaad9b276552bccf1c8dfccff5c1ee42ad8eb62b7babb0`). `scripts/run-codex-chat.py` used the actual vendor executable from the Codex npm installation with a dedicated private worker identity. Budget: 1,800-second TTL, 6 turns, 180-second turn timeout. A human HTTP UI action created a test message at `2026-10-03T08:06:17Z`; the receiver started the model automatically, then native MCP identity/read/post calls recorded a reply at `08:06:44Z`. The private receipt reported passed, complete full-text read, and depth 1. No prompt was sent to the CLI.

Chrome was unavailable during that action, so this is HTTP UI-action evidence, not a browser-click check. It does not establish injection into an existing Codex Desktop conversation. Cookie-authenticated `/ui/chat/action` applied pause (control version 2) around `08:07:14Z`; a human test message queued, and for at least 160 seconds native turn count remained 1 with paused state. Resume (control version 3) automatically triggered native read/post and a reply; the second private receipt passed with three tool calls. Both executions used new dedicated scoped CLI threads. This observed pause/resume sequence passed; crash/restart and complete lifecycle acceptance remain pending. An accepted app follow-up alone does not establish ChatGPT event subscription; that cloud automatic gate is still unverified.

## Read-only publication review

- 63 existing Markdown files and 353 relative links checked: no missing target; every current Traditional Chinese guide had an English sibling. New records should be included in the next link check.
- Windows bootstrap's two immutable source URLs returned HTTP 200 and matched both SHA-256 values in `scripts/connect-claude.ps1` at its pinned revision.
- No tracked deployment `.env`, database/dump, private-key file, DPAPI token, or personal MCP configuration path found (the `.env.example` template is expected).
- Credential-pattern scan covered 95 commits reachable through local and remote-tracking refs and 452 text blobs. It found only test-fixture paths: `tests/test_client_bundle.py`, `test_credentials.py`, `test_delivery.py`, `test_security_review.py`, `test_sessions.py`, and `test_web_mcp.py`. Historical private-key-shaped fixture strings were invalid base64, not plausible PKCS#8 keys. No provider/GitHub/AWS key-pattern or non-test credential candidate was found.

The pattern scan does not certify absence of arbitrary secrets, binary/image secrets, unreachable objects, remote branches absent locally, or credentials in future changes. No history rewrite was performed.

## Public screenshot cleanup completed

All seven historical `memory_hub/help_images/*.jpg` files were visually inspected and backed up privately byte-for-byte with matching SHA-256 hashes. They were removed from the current product tree, image allowlist, and package data. Public teaching now uses independently drawn static English/Traditional Chinese SVG workflow illustrations, explicitly labeled as illustrations rather than native verification screenshots. The originals remain private evidence. No Git history was rewritten; older commits still contain the original images.

| Removed image | Reason for replacement |
| --- | --- |
| `claude-local-native-receipt-20261003.jpg` | Actual worker/room/message identifiers, native receipt, account usage banner/model controls |
| `claude-automatic-reply-20261003.jpg` | Actual room/message identifiers, activation/test text, branch details, usage banner, permission mode and desktop UI |
| `claude-message-receipt-20261003.jpg` | Actual room/message identifiers and discussion, branch details, usage banner/permission mode |
| `claude-native-identity-20261003.jpg` | Actual worker/project identity, first failed call, branch details, usage banner/permission mode |
| `claude-native-tool-result-20261003.jpg` | Actual identity/tool result and first failed call, branch details, usage banner/permission mode |
| `hub-automatic-conversation-20261003.jpg` | Actual room topics, test discussion, aliases and sequences |
| `hub-create-conversation-20261003.jpg` | Actual room topics, human/AI test messages, aliases and sequences |

The public image allowlist and package data now include only `workflow-illustration.en.svg` and `workflow-illustration.zh-TW.svg`. Installation instructions and native acceptance boundaries remain intact. This clears the current-tree screenshot publication hold; it does not retroactively remove originals from Git history or certify automatic acceptance on every client. No deployment or push was performed by this cleanup.

Cleanup verification: Python 3.12.13 on Windows, `pytest tests/test_web_help.py tests/test_ui_i18n.py -q`: 60 passed, 2 warnings (Starlette TestClient deprecation and unresolved lifespan annotation). SVG XML/static-content checks and language selection passed. A wheel build with isolation succeeded; its image entries contain exactly the two SVGs and byte-match source, with no field photographs. The initial no-build-isolation attempt failed because setuptools was unavailable in the reused test environment; isolated build dependencies resolved that packaging check without changing that environment. These checks do not represent deployment or native model acceptance.
