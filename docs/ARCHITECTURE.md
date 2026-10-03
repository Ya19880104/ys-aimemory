# Architecture and trust boundaries

[English](ARCHITECTURE.md) | [繁體中文](ARCHITECTURE.zh-TW.md)

FastAPI serves REST `/v1/tools/{name}`, MCP Streamable HTTP `/mcp`, health `/healthz`, and human UI routes. They share Hub service logic. REST is not MCP transport. The Hub stores/cooperates; native clients perform model inference. It does not proxy subscriptions, provider cookies, or private chat histories.

PostgreSQL is the deployment target. Project canonical state remains a JSON aggregate with row-lock serialization. Derived knowledge documents/indexes update transactionally. SQLite requires explicit demo/test opt-in. Additive schema initialization refuses unknown future versions; old binaries cannot safely connect to migrated databases.

Bearer tokens determine worker identity, security role, and project grants. Human DB accounts/cookies are separate. Work roles such as coordinator/reviewer grant no additional permission. Versioned snapshots preserve exact content, SHA-256, URI, and declared commit; the Hub neither fetches the URI nor verifies that a Git SHA exists externally.

Task packets bind revision/required sources. Complete reads, acknowledgement, acceptance, valid leases, and current fencing tokens gate work. Source changes and approved knowledge invalidate stale context. Handoff/recovery invalidate old holders. Declared local workspace paths do not enforce filesystem locks; separate worktrees/OS permissions remain necessary.

Shared rooms and two-party messages have different visibility. Durable delivery claims/receipts coordinate bounded receivers; notifications alone do not prove native model reads or replies. See [delivery contract](DELIVERY_API.md).

Remaining capacity risks include aggregate growth, project lock contention, packet/audit/idempotency retention, and query quality. Full-text search is not semantic/vector search. Source implementation, local tests, official-client acceptance, deployment, and public-service readiness are separate gates.
