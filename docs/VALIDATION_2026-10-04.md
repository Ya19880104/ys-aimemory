# Validation record: 2026-10-04

[English](VALIDATION_2026-10-04.md) | [繁體中文](VALIDATION_2026-10-04.zh-TW.md)

This report retains separate version boundaries for source checks, deployment and native/browser acceptance. The earlier candidate `6ea3ca51a8863b38d0c8d85c1beb2c1f7392858f`, based on `ee21c2dfccba1d7f60b44563880c8b6a864bf971`, was deployed during the earlier checks below. Later results follow in the next section. Earlier native evidence remains in [2026-10-03 validation](VALIDATION_2026-10-03.md).


## Current deployed source and installer chain

Live source: `7652f1d7f04ef4c00e8860217a0f732f98dcb58e`; image: `sha256:d4d2f2800c9f9c090f631aed807e7882aa7cbdfc1b15cc2b13765c1d81d2cab4`. Isolated deployment-host suite: **1,010 passed, 63 skipped, 3 warnings in 232.17 seconds**. Promotion: **454 checks passed**, 2026-10-04T11:45:02.755408Z–11:45:26.279132Z. Schema 6 was preserved; the 26-table comparison allowed only expired `web_auth_entries` cleanup. Backup headers/hashes were checked; restore and off-VM acceptance were **not_run**. Candidate CI: Windows **268 passed, 1 warning**; SQLite **817 passed, 32 skipped, 3 warnings**; PostgreSQL **1,043 passed, 30 skipped, 3 warnings**. Results remain separate by environment; skips are not passes.

Current Codex bootstrap: `31a1db36e04d304c3e2823b31d5b175ab17e87e2`; four source files pinned to `bd25c375bc6046c1cfbe488c859cde2c7e8a3421`; raw bootstrap SHA-256: `1a03b5a79ef9242f197962527320f5146ebdbb52b3619273afe44c2d94906e7c`. Actual public raw bytes and all four hashes matched; the published runner checks unresolved native state before join. Deployed guide/clipboard URL/hash pins matched and activation remains explicit. The Python `setup.install` native-client preparation path was tested, but the downloaded PowerShell bootstrap was **not_run end to end**. Neither hash verification nor preparation proves native model delivery. Current Claude chain remains separate: bootstrap `5f9400802ecdfe98f350a25a1f6848e1cf5ba1d0`, source `b168876f00f85ccb37e97bb11c3678d8cb9e6ae4`, as pinned by the deployed Claude guide; no new Claude end-to-end acceptance is inferred.

Coordinator-supplied native evidence at 2026-10-04 20:17 Taipei: an actual official Codex CLI reached the tool_read gate while its child remained alive. The actual receiver was killed; restarting with the same arguments and state exited with code 1 at the unresolved-native guard. Binding, delivery, generation, turns (1 of 3) and attempt (1) remained unchanged. Owned Job processes were stopped and the fresh binding disabled with no cleanup errors. The bounded real-provider in-flight fence is **passed**; post-commit-unknown and full automatic resume are **not_run**. Independent review confirmed identical before/after state, all six preserved state-file hashes and owned-process identity evidence. Preparation used programmatic setup.install; the PowerShell bootstrap was not executed. Gemini native permission/continuation remains pending. Keep PR18 draft and issue #12 open; no overall product PASS is claimed. Later native results require a separate exact-version addendum.

## Later source checks and final cloud acceptance: 2026-10-04

The first broader CI/staging run at `bd25c375bc6046c1cfbe488c859cde2c7e8a3421` failed the installer source-pin check: the fixed receiver no longer matched the old bootstrap hash. That failure was preserved, and the candidate was not promoted. The bootstrap now pins the four source files from `bd25c37`; the web generator and both setup guides pin immutable bootstrap `31a1db36e04d304c3e2823b31d5b175ab17e87e2` and its SHA-256. The filesystem-based integrity test remains usable in shallow checkouts and Git-free release archives. The corrected bootstrap, generated command and help checks recorded **70 passed, 2 warnings in 47.32 seconds**; final 7652 CI/deployment results are recorded above.

Coordinator-supplied evidence at `07ff550c25dd0f8beb44338f943c56621762e78c` includes cloud trace `fd8d627c7b5856a9e03e63d5b2c826dd5e62a87e`, hard-crash fixture `a96ee30d68e54fd5e17a87b80ab374f25ff3ca24` and unresolved-native admission guard `07ff550`. The scoped suite (`tests/test_codex_receiver_crash.py`, `tests/test_codex_chat_runner.py`, `tests/test_codex_chat_setup.py`, `tests/test_cloud_tunnel_gateway.py`) recorded **208 passed, 1 existing Starlette warning in 12.46 seconds**. Independent source review: **GO** for this scope. At that earlier source-check cutoff the live VM was `af79c01a24e96898125de42e8be0d596f869fb16`; the later 7652 promotion above supersedes that deployment snapshot.

The synthetic hard-crash test kills the receiver parent while a fake CLI child remains alive and verifies the unresolved-native fence before Hub join. Prior native Codex idle restart passed within its observed scope; broader real-provider in-flight recovery remains pending beyond the bounded fence verified above. Preserve `native-active.json` and the delivery journal, confirm the old child has exited, and reconcile server delivery/binding state before an authorized retry. Deleting the marker alone is not recovery.

Final fresh cloud acceptance: the first callback attempt received HTTP 200 at **2026-10-04 19:17:16 Taipei (11:17:16 UTC)**; the native task UI reported last_run at 19:17:17, which is not execution proof. No gateway native read/post ingress was observed through 19:20:20 before the manual prompt. Automatic event read/reply **failed for this run**. An explicit manual diagnostic prompt then produced native `read_delta` with `tool_read` at 19:20:36 and native `post_message` with `replied` at 19:20:42. Manual native read/write **passed**, separately from the failed automatic gate. Trace timestamps and matching fingerprints made the callback, first native ingress and receipt milestones distinguishable without publishing message content or private identifiers.

The task was paused at 19:20:45, unsubscribed at 19:20:50, and the runtime was stopped after 19:21 with process exit confirmed. A second event and restart acceptance were **not_run**. Native UI tool-metadata refresh failed during this run, while manual native tools remained available. The root cause remains unresolved between automated task context and its first tool call; no external cause is confirmed. Historical native cloud evidence retains its original version boundary.

## Historical changes and contract

The four P2 follow-ups keep legacy Claude bootstrap sources reachable in main history; permit ordinary manual posting after expiry while enforcing pause/disable/archive/revocation; recover lost committed claim responses using persisted receiver-specific request IDs and binding generations; and allow validated documentation mirrors or the real localized `/help` landing page. Claude/Codex installers, hashes, UI instructions and paired guides were updated together.

Replay recovers only the original still-live lease before dispatch or any recorded full-message read, without extending it or charging another attempt/turn. Partial batch reads also block a second ready response. Different receivers cannot obtain that live lease. Generation, payload and administrative fences remain enforced. This is not exactly-once model execution. Claim memos contain metadata, not message bodies; idle/busy/paused polling does not create memos, but historical records accumulate across renewals. The private cloud pilot retains its legacy claim path.

## Historical recorded verification

| Source / gate | Result | Boundary |
| --- | --- | --- |
| Historical candidate 1422187: full local Windows | 748 passed, 2 skipped, 3 known warnings; 377.87 seconds | Does not certify later changes |
| Historical candidate 1422187: isolated VM PostgreSQL | 898 passed, 56 skipped, 3 warnings; 199.84 seconds | Separate from local Windows; skips are not passes |
| Historical candidate 1422187: promotion | 431 checks passed in 22.2 seconds; 2026-10-03T17:15:20Z–17:15:42Z | Schema v6 and 26 tables preserved |
| Historical candidate 1422187: browser help notes | English/Traditional Chinese passed | New upgrade/expiry notes displayed; copied instructions subsequently failed |
| Catalog repair 8dfa278 | 149 passed, 2 warnings; 101.24 seconds | Actual generated translation catalog exercised; initial two regression failures preserved |
| Claim cleanup repair 4ed9877 | 70 passed, 1 warning | Covers absent pending file after idle/stale response; permission errors still fail closed |
| Bootstrap/runner checks at bd8d4e6 | 76 passed, 1 warning; 7.03 seconds | Source-scoped receiver/installer checks, not native model execution |
| Final copied-command checks before 6ea3ca5 | 4 passed, 2 warnings; 5.32 seconds | Generated command checks, not final browser clipboard acceptance |
| Public pins at 6ea3ca5 | 13 checks passed | Public download/hash/source consistency; not native installation acceptance |
| Independent Sol 6.1 read-only audit | GO for inspected scope | Ownership/fences/docs and immutable pin consistency; no complete native acceptance claim |

The initial browser copied-instruction failure produced `# undefined`. The old harness substituted a fake translation function and missed the defect; two new regression cases failed before the minimal literal-call repair in 8dfa278. The corrected harness uses the real generated catalog for both languages and clients. Those passing source checks do not erase the browser failure or replace final browser replay.

CodeRabbit completed the 1422187 review with one minor pending-file cleanup finding, fixed at 4ed9877 with three targeted cases. Subsequent review was rate-limited. Codex review quota was unavailable. Review status alone is not independent full acceptance.

## Historical public installer chain: earlier 6ea3 checks

| Client | Installer revision | Verified source revision |
| --- | --- | --- |
| Claude | 7b666c6dae39d49fbc700540ad2248829c133b80 | 5b54867a4204e8218a541b7d87039a2700bf22ac |
| Codex | bd8d4e684e0f510312cf491e015dbd1d3944fff4 | 4ed987759e3d83e8caa5788831de3544438172db |

Codex installer SHA-256: `F5E622AC3BC21CA06B311238C4B49491324FDD01C40F84FC97081913A4EBFDD7`. At that earlier cutoff, both [Codex setup](CODEX_CHAT_SETUP.md) guide languages and UI pins matched; [Claude setup](AUTOMATIC_CHAT.md) retains its separately verified chain. Existing installations do not self-update. Upgrade the Hub, stop the owned receiver, and follow the explicit installer/renewal procedure; preserve old state and evidence.

## Historical candidate verification: 6ea3

- Final 6ea3ca5 isolated VM suite: **901 passed, 57 skipped, 3 known warnings**, 199.64 seconds. The disposable database was removed.
- Promotion: **433 checks passed**, 22.22 seconds; 2026-10-03T17:37:27Z–17:37:49Z (2026-10-04 01:37 Taipei). Schema v6 and 26 tables remain unchanged. Image: `sha256:9b78fdb4574b50391b9147ea15ca13b41f239fe7aa5caf22280634f4c3667a4f`.
- Final 6ea3ca5 CI: all six push/PR Windows-installer, SQLite and PostgreSQL jobs passed ([push](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140841102), [PR](https://github.com/Ya19880104/ys-aimemory/actions/runs/37140843688)).
- Actual Chrome English/Traditional Chinese × Claude/Codex: **all four copied-instruction combinations passed**. Rendered textarea and clipboard match, with no `undefined`; installer URLs, SHA-256 values and language/client-specific guide links are correct. Language switching preserves the selected project and conversation. These checks generated and copied instructions only; it does not run an installer or wake a model.

## Remaining acceptance boundaries

Issue #12 remains open for broader lifecycle/capacity work. Full native model crash/restart and independent STOP lifecycle, legacy cloud lost-claim recovery, long-running subscription/expiry/offline/revocation/duplicate/burst cases, memo retention/load and controlled cost benchmarks remain pending. The bounded native crash-fence pass at 7652 above does not cover these pending gates; automatic cloud events have not passed.

The historical promotions above created backups and verified their headers/hashes; restore and off-host acceptance were not run. Historical manifests identify the original delivery and do not validate these later source changes. Public reports omit credentials, host addresses, private identities, message bodies and private screenshots.
