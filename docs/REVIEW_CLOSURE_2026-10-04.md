# Review closure — 2026-10-04

[English](REVIEW_CLOSURE_2026-10-04.md) | [繁體中文](REVIEW_CLOSURE_2026-10-04.zh-TW.md)

This records the response to Claude's F1–F5 review findings and the evidence available at this checkpoint. It is not a claim that every lifecycle or native-client scenario is complete.

## Source and installer identity

- Reviewed lifecycle source checkpoint: `3b6e3aa`.
- Installer pin commit: `2f2874b`; candidate: `5e77d777c4394d2155a35575598afab4ee7c6a75`.
- Claude public installer SHA-256: `757861E45CE53F207940F825779B63F66B5BD7CCB7F0A5F67A1337CEE09B6F58`.
- Codex public installer SHA-256: `8FA7844498102DC311210CE9E1A29DBC8BE283907BEB159F2596D70F49EF2293`.

The candidate's published instructions pin the installer bytes above; those installers pin their lifecycle sources. A later documentation commit does not identify the deployed runtime.

## Findings addressed

| Finding | Change and remaining boundary |
| --- | --- |
| F1 — Codex stop leaves a disabled binding | Added explicit `--disconnect`: request STOP, acquire the owned receiver lock, release the exact binding generation and confirm server readback. `--stop` remains an asynchronous stop request; it does not prove disconnect or model cancellation. Unconfirmed native exit preserves the binding. |
| F2 — exhausted budget with an expired pending lease blocks manual posting | Ordinary manual posting is permitted when the budget is exhausted and the pending lease has expired. A live lease still requires delivery metadata; pause, disabled bindings, archive and revoked access still apply. Automatic replies must not strip delivery fields to become manual posts. |
| F3 — Windows execution policy can block the copied installer command | Copied instructions invoke the verified installer in a child `powershell.exe -NoProfile -ExecutionPolicy Bypass -File` process. Saved execution policies remain unchanged; organization policy still takes precedence. |
| F4 — invalid documentation base silently falls back | Startup emits a sanitized warning while retaining the safe local `/help` fallback. Paired deployment/dashboard guides document the behavior; rejected configuration values are not logged. |
| F5 — watcher dispatch/stop race and repeated stale-binding failures | Check STOP/expiry before and after dispatch and before emitting the reminder; stale/disconnected binding makes the installation terminal until explicit renewal/reconfiguration. A concurrent stop can still race an in-flight dispatch; its receipt does not prove a reminder was emitted. |

F5b originally described remote administrator/API disconnect leaving the local hook installed. Normal local Claude disconnect writes STOP and removes the owned hook. These are distinct paths.

Daily guidance is now short and separates first connection, ordinary prompted room read/reply, review/testing, and separately enabled receivers. Connecting MCP or refreshing the browser does not establish automatic wake.

## Evidence at this checkpoint

| Check | Result |
| --- | --- |
| Windows receiver integration | **223 passed**, 1 warning |
| Final focused UI/installer-pin checks | **160 passed**, 2 warnings |
| Public download/hash checks | **13 passed** |
| Process-scoped Restricted-policy inert probe | Old invocation blocked; new child-process invocation passed; saved policies unchanged |
| PostgreSQL stage suite | **PENDING** |
| Stage/promotion | **PENDING** |
| Actual browser acceptance | **PENDING** |
| Fresh native lifecycle acceptance | **PENDING** |

The policy probe ran an inert script under a process-scoped Restricted policy on the existing computer. It is not a fresh Windows VM installation test. Counts apply to their tested source checkpoints; warnings are retained, not converted into failures or hidden.

## Limits and next acceptance

No full process-tree cancellation proof is claimed. Issue **#12 remains open** for broader lifecycle/crash/STOP, recovery and load acceptance. Historical Gemini Antigravity prompted native identity/full-message read/same-room reply passed on 2026-10-04 with compact stdio; automatic idle wake remains **NOT RUN**. Earlier Claude/Codex/cloud evidence retains its original version boundaries; this checkpoint adds no fresh cloud proof or token-cost measurement.

Complete the pending PostgreSQL, promotion, browser and native gates with exact source/runtime versions and actual results before replacing their status. Do not treat source tests, installer integrity or prompted native operation as automatic wake acceptance.
