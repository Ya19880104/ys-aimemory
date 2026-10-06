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
