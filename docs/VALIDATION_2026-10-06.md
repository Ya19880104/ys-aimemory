# Validation: 2026-10-06 continuation

[English](VALIDATION_2026-10-06.md) | [繁體中文](VALIDATION_2026-10-06.zh-TW.md)

This record keeps source, CI, deployment and native evidence separate. At the continuation baseline, public PR18 was `c199d235b0ed34f0dd684d42fbf40655d4bba9a3`; the healthy deployed Hub was `a42630cbe55d7671c680777c3e60d8648d861f6e`. The original handoff's `96177fe` PR and `2472280` deployment were historical. See the [previous deployment record](VALIDATION_2026-10-05.md).

## CI on the continuation baseline

The first attempts of both `c199d23` workflows failed, with cancelled jobs; those records remain intact. Attempt 2 passed all three jobs in each run:

| Workflow | Windows | Linux / SQLite | Linux / PostgreSQL |
| --- | --- | --- | --- |
| [Push, run 37365441050, attempt 2](https://github.com/Ya19880104/ys-aimemory/actions/runs/37365441050/attempts/2) | 438 passed, 2 warnings | 1091 passed, 49 skipped, 3 warnings | 1387 passed, 47 skipped, 3 warnings |
| [PR, run 37365446803, attempt 2](https://github.com/Ya19880104/ys-aimemory/actions/runs/37365446803/attempts/2) | 438 passed, 2 warnings | 1091 passed, 49 skipped, 3 warnings | 1387 passed, 47 skipped, 3 warnings |

These results apply to `c199d23`, not later changes. The three earlier Linux failures on `96177fe` remain failed historical results; later successful runs do not rewrite them. Skipped tests are not passes. The original delivery-manifest verifier still fails against the evolved checkout; its historical manifest is preserved. The separate continuation handoff integrity check matched all 29 recorded files.

## New source changes

Claude disconnect can retry after a partial configuration restoration. An already restored exact original MCP entry is accepted, files already restored are not rewritten, and final binding metadata uses a checked atomic replacement. Edited entries, unknown identities, failed Hub release/readback and active-operation locks still stop the operation. STOP and retry evidence remain intact. The focused local suite passed **92 tests, 2 warnings**; the initial two failing regression cases remain recorded.

Gemini's Windows CLI process is now created suspended inside its owned Job Object in one operation, closing the gap where a parent crash could leave an unassigned child. Cleanup retains and waits on the root process handle, including construction failures. The focused local suite passed **48 tests, 2 warnings** on Windows 11 / Python 3.12. The original orphan reproduction and interim cleanup failure remain failed records. These are synthetic process tests; native Antigravity and other Windows/Python versions are **not_run**.

Integrated source revision: `1cb0e39d72fcd160b32b1fba220a03f44dbfa56a`. Claude bootstrap revision: `aba9a41017a853917e2464611d2a9e05955d9bbc`, SHA-256 `cfaafb60a49e152bad65e05a3b078d38ec435c9a6a2d753e446961957ba8c8b5`. The [paired installation guide](AUTOMATIC_CHAT.md) and generated room command use this bootstrap. Codex's existing immutable source/bootstrap chain is unchanged.

## Remaining gates at this source checkpoint

- Integrated candidate CI and deployment: **not_run**. Baseline CI above cannot authorize a newer candidate by itself.
- Fresh public Codex installation and native MCP lifecycle: **not_run**. A new bounded fixture must prove receipt-based startup, full read, reply, owned-process exit, stop/disconnect and revocation of the same installed Token. Offline helpers and SDK calls cannot satisfy this gate.
- Cloud automatic silent completion, Gemini's complete native lifecycle, and simultaneous three-client conversation/task handoff: **not_run** for these changes. Earlier cloud failures remain failures.
- The specifically rejected Claude adoption operation remains unattempted. Closed/revoked trials, STOP files and journals remain preserved.

Credentials, machine-specific setup, private receipts and process evidence remain outside the public repository.


## Deployment and CI of `38a49cf`

Candidate `38a49cff112dfbe000926041ce680a912ee2fb92` completed both CI runs on their first attempt:

| Workflow | Windows | Linux / SQLite | Linux / PostgreSQL |
| --- | --- | --- | --- |
| [Push, run 37415389253](https://github.com/Ya19880104/ys-aimemory/actions/runs/37415389253) | 448 passed, 2 warnings | 1098 passed, 52 skipped, 3 warnings | 1394 passed, 50 skipped, 3 warnings |
| [PR, run 37415393313](https://github.com/Ya19880104/ys-aimemory/actions/runs/37415393313) | 448 passed, 2 warnings | 1098 passed, 52 skipped, 3 warnings | 1394 passed, 50 skipped, 3 warnings |

The integrated local Windows run passed **1148 tests, 2 skipped, 3 warnings**. A fresh deployment packet passed **1352 tests, 92 skipped, 3 warnings** against a disposable database, then **478 promotion checks**. Deployment finished at **2026-10-06 05:00:33 UTC**. Independent readback confirmed the exact candidate/image, healthy application and PostgreSQL, verified TLS health, paired tutorial URLs pinned to this revision, a readable pre-upgrade backup and retention of the previous image. These results apply to `38a49cf`; they do not validate later source revisions.

## Codex public installer dependency fix

A new bounded public installation on `38a49cf` **failed before the hidden Token prompt**. No Token was entered, client receipt produced, receiver started or room binding created. The installer process tree exited and all owned handles closed. The dedicated issued Token was revoked and a separate verified-TLS request returned HTTP 401. The trial is closed; its failure and diagnostic records are preserved. Installed-Token verification and native MCP lifecycle were **not_run**.

A credential-free reproduction under real base Python 3.12 with `-I -S` failed with `ModuleNotFoundError: httpx`: setup imported the receiver before installing its private environment. Source `3e6166789fa938afc58a78565c625fc73888acb9` defers HTTP imports to runtime receiver/disconnect functions. The initial failing regression remains recorded; the focused local suite passed **217 tests, 1 warning**, including the actual public setup import path with no third-party packages. Existing runtime transport-error and disconnect tests passed.

Codex bootstrap `d688fbfcd132ec8ed9b05937438320ab1c9b94a6`, raw Git SHA-256 `edf5651aaae0a2cdf319d75b1bbdbf370972e7316f5cfa610d3873be518141a4`, pins this source. The paired guide and room command use the same chain. This fix's new CI, deployment, public installation and native acceptance are **not_run** at this source checkpoint; the prior deployment and helper tests cannot substitute for them.

Closed Cloud log diagnostics use independently recorded callback/guard windows and preserve unparsed lines. They do not establish native execution or completion, and do not change earlier failed results. Fresh Cloud automatic receive, Gemini native lifecycle and three-client conversation/task handoff remain **not_run**. The required official host/event controls are unavailable in the current session; this does not establish account-wide unavailability.

## Exact-head CI for the stdlib-safe Codex installer

Candidate `418173134fa1c6cce17e99830a5b5faebbc97475` completed both CI runs on attempt 1, with all three jobs successful:

| Run (attempt 1) | windows-installer | sqlite | postgres |
| --- | --- | --- | --- |
| [Push 37418044541](https://github.com/Ya19880104/ys-aimemory/actions/runs/37418044541) | 449 passed, 2 warnings | 1098 passed, 53 skipped, 3 warnings | 1394 passed, 51 skipped, 3 warnings |
| [PR 37418050461](https://github.com/Ya19880104/ys-aimemory/actions/runs/37418050461) | 449 passed, 2 warnings | 1098 passed, 53 skipped, 3 warnings | 1394 passed, 51 skipped, 3 warnings |

The focused local suite passed **344 tests, 2 warnings**. These are separate environment results, not a combined count. Skipped tests remain skipped. This supersedes only the prior source checkpoint's pending CI status for this candidate; it does not certify public installation, native execution or deployment.

The Codex source/bootstrap chain remains `3e6166789fa938afc58a78565c625fc73888acb9` / `d688fbfcd132ec8ed9b05937438320ab1c9b94a6`, with bootstrap raw Git SHA-256 `edf5651aaae0a2cdf319d75b1bbdbf370972e7316f5cfa610d3873be518141a4`.

[The three `96177fe` Linux failures and successful `a42630c` correction](VALIDATION_2026-10-05.md#test-fixture-fix-ci-and-deployment-of-a42630c), [`c199d23` failed/cancelled first attempts and successful second attempts](#ci-on-the-continuation-baseline), [`38a49cf` deployment](#deployment-and-ci-of-38a49cf), and [the closed public install failure and issued-Token revocation](#codex-public-installer-dependency-fix) remain unchanged. The initial `httpx` regression failure remains failed; its later focused pass has a different source boundary.

### Deployment and fresh public installation at C418

At the post-deployment checkpoint, the local candidate, public PR18 head and independently verified live release were `418173134fa1c6cce17e99830a5b5faebbc97475`. Stage passed **1352 tests, 93 skipped, 3 warnings in 251.18s**; promotion passed **483 checks in 23.432s**, finishing **2026-10-06 05:42:24.336493 UTC**. Readback confirmed the exact image, healthy application/PostgreSQL, verified TLS, paired tutorial URLs pinned to C418, a readable pre-upgrade backup and the retained previous image.

A fresh normal public Codex installation **passed** through the real hidden Token prompt. The public receipt and all eight installed files matched the source/bootstrap/candidate chain and the **3600-second / one-turn / 90-second** limits. The installer process tree exited and its owned handles closed. This validates installation, not a model turn.

The subsequent native guard **failed** with `cannot_hold_owned_process` before room join/receive. STOP was preserved; no binding was created and no human stimulus was sent. Automatic/native receive, complete read, reply and native Job exit are **not_run**; complete held-child exit proof is **failed**. Official stop passed. Later scoped inventories were empty and recorded process identities absent, without upgrading the failed historical exit proof. The same issued and installed Token was revoked (HTTP 303), and strict-TLS authentication with that installed Token returned **HTTP 401**. The fixture is closed and will not be restarted; earlier rate-limited closure readbacks remain recorded.

Fresh Cloud automatic receive/silent completion, Gemini complete native lifecycle, and simultaneous Claude/Codex/Gemini conversation/task handoff remain **not_run**. Required Cloud/Gemini host controls are unavailable in the current tool context; this does not establish account-wide unavailability. Earlier Cloud failures remain failed. The specifically Auto-denied Claude adoption remains unattempted. PR18 remains draft; no overall product acceptance is claimed.

### Second fresh public installation and outer Job closure

A second fresh public installation and its eight-file receipt verification passed on the same C418 release and S/B installer chain. A new external guard created the public receipt process inside an owned Windows Job atomically and retained the root handle. It stopped before join with `HOLD_member_unavailable`; no binding or human stimulus was created. The original fixed error subtype was not recorded, so the cause remains unconfirmed.

The outer Job covered five processes and reached zero active processes, with the held root signaled and owned handles closed. This outer cleanup evidence passed; native receive/full read/reply and the receiver's inner native Job receipt remain **not_run**. Official stop ran inside a separate owned Job and passed. The same issued and installed Token was revoked (HTTP 303) and rejected over verified TLS (HTTP 401). This second fixture is also closed; neither failed fixture will be restarted.

External guard diagnostics are private test-harness work, separate from product CI. Initial deadline/GO races and a final-callback error were preserved before later synthetic corrections. A new source-only packet does not establish another installation or native result.

## Fresh bounded Codex native lifecycle at C418

A third, independent fresh normal public Codex installation passed on `418173134fa1c6cce17e99830a5b5faebbc97475`, using the unchanged S/B installer chain and an eight-file receipt verified against the **3600-second / one-turn / 90-second** limits. One new human question automatically produced **3 native MCP calls**: identity, complete delivery read and one reply. The actual native receipt was `passed/replied`, with `native_containment=windows_job` and verified native tree exit. Independent Hub readback matched the same human/read/reply receipts and the 324-character reply containing the trial marker. No follow-up model prompt or SDK substitute established this result.

The outer owned Job settled all **22 job processes**: zero active processes, the held root signaled, Job and owned handles closed. Metadata identified **16 observed process identities**; unobserved identities remain **not_observed**. Separate official stop and disconnect Jobs also passed and settled their own trees. STOP remains, the binding is disconnected and native-active state is absent. These process and server proofs remain separate from the actual native receipt.

The same issued and installed Token was revoked (HTTP 303); a strict-TLS authentication check with that installed Token returned **HTTP 401**. The fixture is now closed. STOP, journals and all original attempts are preserved; it will not be restarted.

The live Hub and the source/CI/native evidence in this record remain pinned to C418. The accompanying documentation-only change has a separate public/local Git head; it does not represent a new product deployment or another native trial.

This passes only the observed one-question bounded Codex sequence. The earlier first guard failure and second HOLD fixture remain failed/HOLD and closed/revoked; their different cleanup proofs are unchanged. Cloud automatic receive/silent completion, Gemini's complete native lifecycle, simultaneous three-client conversation/task handoff, fresh peer no_reply, receiver restart and indefinite operation remain **not_run** for this candidate. The specifically Auto-denied Claude adoption remains unattempted. No overall product or token-cost acceptance is claimed.
