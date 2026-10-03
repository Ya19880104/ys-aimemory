# Acceptance and failure scenarios

[English](ACCEPTANCE_TESTS.md) | [繁體中文](ACCEPTANCE_TESTS.zh-TW.md)

Tie each result to exact commit, time, OS/runtime/client versions, command, exit code, and sanitized evidence. Report passed/failed/skipped/not_run separately. A fixture, historical report, validator, or SDK success cannot substitute for the environment being accepted.

| Gate | Positive and negative checks |
| --- | --- |
| Source/import | Exact UTF-8/hash preservation; CAS conflicts; atomic rollback; identical/different idempotency retry |
| Admission | Competing claim single winner; complete required reads; stale revision rejected; acceptance/validation required |
| Lease/handoff | Renew, expiry, old fence rejection, explicit recipient admission, offline administrator recovery |
| Permissions | Invalid/revoked token, cross-project denial, role escalation denied, private-message isolation |
| Search | Mode marked, CJK literal fallback, pagination, index revision/count health/rebuild |
| Web | Login/logout, CSRF/nonce replay, expiry, account grant changes, shared session invalidation |
| PostgreSQL | Actual driver/server concurrency, migration, multi-instance auth, dump/restore into isolated DB |
| Browser | Real UI, keyboard/IME, responsive layout, reload/back/repeated submit, attachment handling |
| Native clients | Identity/tool call/read/reply per real official client; model login and approvals |
| Automatic delivery | Idle wake, correct room/binding, pause/budget/stop, crash/retry/deduplication, bounded AI follow-ups |
| Deployment | Real image build/start/restart, TLS trust, private port exposure, persistence, restore drill |

Use disposable DBs and synthetic projects. Never reset real data or weaken safeguards to pass. Four actual Windows clients require independent identities/worktrees and end-to-end handoff with stale-source/lease/recovery negatives; four simulated Principals are insufficient. Native automatic/cloud pilot acceptance remains pending until its own evidence is recorded. See [native checks](NATIVE_CLIENT_CHECK.md), [delivery API](DELIVERY_API.md), and [deployment](DEPLOYMENT.md).
