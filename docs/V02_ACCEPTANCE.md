# Historical v0.2 acceptance scope

[English](V02_ACCEPTANCE.md) | [繁體中文](V02_ACCEPTANCE.zh-TW.md)

This is a historical scope reference for v0.2, not current release acceptance. The original [test report](../TEST_REPORT.zh-TW.md) records that delivery's commands/results; later changes require new exact-commit evidence.

v0.2 added indexed knowledge/search, batch import/CAS/idempotency, source history, additive schema initialization, DB-backed web sessions/nonces/throttling, and guarded recovery. Its historical Python/SQLite regression, static deployment validation, and PostgreSQL single-user SQL checks did not establish full PostgreSQL driver/concurrency/backup restore, Docker runtime/TLS, real browser, or four official Windows clients.

Do not interpret a present test file as a performed runtime test. PostgreSQL tests may skip without the dedicated environment. DB-backed multi-instance design does not certify capacity/production horizontal scaling. Admin recovery does not reopen completed tasks or provide general task editing.

Current shared-room/account/delivery/cloud features belong to later changes; consult [current acceptance](ACCEPTANCE_TESTS.md), [architecture](ARCHITECTURE.md), and the target commit's actual CI. Preserve historical manifests and reports rather than rewriting them to describe the latest source.
