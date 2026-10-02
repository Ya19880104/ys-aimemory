# Shared workspace implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement and independently review each deliverable.

**Goal:** A human administrator and independently authenticated AI workers share conversations, documents, proposals and files in named Sessions, with efficient on-demand retrieval.

**Architecture:** Add project-scoped collaboration records independent of private worker messages and formal task leases. Persist human accounts and resolve current permissions on every browser request. Clients explicitly select a Session and cursor; browser refresh does not call a model. Existing full MCP remains compatible; an optional compact/on-demand client profile avoids advertising every schema.

**Tech stack:** Existing FastAPI, SQLAlchemy, SQLite/PostgreSQL, MCP SDK, server-rendered HTML and vanilla JavaScript; no new framework.

**Spec:** User requests in this task: shared live chat with administrator participation, direct AI conversation, handoff/task/plan documents and attachments; account management; single MCP then Session selection; mention-triggered access and minimal history tokens. Hermes Agent research must be distinguished from implemented behavior.

## Global constraints

- Public base commit: 8272c1ba48ff69c57bbe0c7801644dcb345ef9a1. Separate writable worktrees per worker. Never publish previous local history or credentials.
- Preserve old private message visibility and all formal task context/lease/fence gates. Chat or draft artifacts do not grant authority.
- Shared Sessions are visible to explicitly scoped project members and administrators; human/worker identities are server-derived and distinct. Account-management permission alone does not confer project visibility.
- Every read is bounded. Default history is incremental and compact; summary/search return source IDs and watermarks, never silently claim to cover later events. Full artifacts/files require explicit reads. No provider API or automatic model calls.
- Attachment MVP: at most 512 KiB per file and 25 MiB per Session, stored in DB and covered by backups. Treat content as untrusted, download only, no execution/extraction/remote URL fetch. Public upload within shared Session is disclosed.
- Additive schema migration; refuse future schema; retain v4 data and invalidate legacy anonymous browser cookies on account migration. Existing worker tokens stay independent.
- Test SQLite and actual PostgreSQL separately. Report passed/failed/skipped/not_run. Native model acceptance is separate from SDK transport success.

## 1. Shared Session service

Owner: core implementer in `worktrees/shared-session-core`.

Files: new `memory_hub/session_store.py`, `memory_hub/session_service.py`, `memory_hub/session_models.py`; integrate `store.py`, `service.py`, `models.py`, `app.py` only where needed; `tests/test_sessions.py` and runtime backup/migration tests.

Contract: `hub.sessions.call(name, arguments, actor)` for browser and MCP. `actor` has `kind`, `id`, `display_name`, `projects`, `role`; browser must derive it from current validated human account. MCP uses validated Principal. Methods include list/create/read/post/search Sessions, create/get artifacts, upload/read attachments, archive/reopen. Explicit project/session IDs on every operation except scoped discovery. Return stable event sequence, next cursor and has_more. List/search omit full bodies; reads default 20 events with bounded bytes and explicit full option. Store source references and summary coverage as immutable artifacts.

- [ ] Add failing tests for real A/B/human conversation, scope/actor isolation, old private-message privacy.
- [ ] Implement transactional sequence/idempotency/quota with project lock and separate event tables.
- [ ] Add attachment hash/chunk/pagination/rollback and exact-limit tests.
- [ ] Verify SQLite and integrate additive schema version and backup coverage.
- [ ] Commit isolated deliverable; independent review before integration.

## 2. Database human accounts

Owner: accounts implementer in `worktrees/web-accounts`.

Files: new `memory_hub/web_users.py`, `memory_hub/web_accounts.py`; modify `web.py`, `web_auth.py`, `web_management.py`, `web_mcp.py`, `web_store.py`; tests `test_web_accounts.py` and existing web security tests. Coordinate `store.py` migration/`app.py` allowlist registration with root.

Contract: `auth.principal(current_session)` returns live human identity (`user_id`, username/display_name, role, projects, can_manage_users, security_version); route code must stop relying on global config scope/role. Initial configured account imports once with stable owner UUID and explicit grants including currently owned projects. Future restarts must not overwrite online changes. New project creation grants creator scope transactionally. Root session UI consumes this contract.

- [ ] Write failing bootstrap/restart/version/revocation/scope/last-admin tests.
- [ ] Add DB accounts, explicit grants, serialized management and audit, password bounds and persistent bootstrap marker.
- [ ] Add account CRUD, enable/disable/reset/self-password pages with CSRF/nonces/CAS. No deletion of historical identity.
- [ ] Convert existing browser paths to live principal; maintain worker bearer separation.
- [ ] Run full web regression; commit isolated deliverable; independent review.

## 3. Browser workspace and efficient client access

Owner: root integrator. Files: `memory_hub/web_sessions.py`, precise app routes, navigation/help/client generator, `clients/`, docs and focused tests.

- [ ] Verify official Hermes and client lazy-discovery support; document deferred schema vs server activation vs history reads accurately.
- [ ] Implement responsive Session list, actor-labelled timeline, safe text rendering, human composer, documents/files and task links. Poll incremental events about once per second, back off hidden tabs, stop on auth loss; preserve draft/scroll.
- [ ] Provide scoped JSON reads/mutations with CSRF; download attachments with authorization and safe headers. CSP permits only same-origin room fetch.
- [ ] Provide compact optional MCP discovery/dispatch or explicit activation profile with project-local configuration; keep legacy tools interoperable. No implicit remote reads during ordinary conversation.
- [ ] Explain single connection -> Session selection -> incremental conversation -> explicit artifact/handoff workflow and exact token controls.
- [ ] Test account/chat integration, browser acceptance and two independent client identities; separately record native model limitations.

## 4. Delivery

- [ ] Run all regression and deployment validators; review diff/secrets and exact source identity.
- [ ] Publish feature branch/PR and verify exact-commit GitHub SQLite/PostgreSQL CI. Attach PR to task.
- [ ] Back up authorized VM, deploy only verified candidate, smoke-test browser and MCP; keep rollback evidence private and report any unverified gates accurately.

## Work ledger

- Public source baseline: pushed main, SQLite and PostgreSQL CI success on 2026-10-02, run 36967375187.
- Native worktree creation unavailable because chat opens outer non-Git handoff folder; isolated Git worktrees created through Git in inner repository.
- Implementation and deployment below this baseline remain pending until their evidence is recorded.
