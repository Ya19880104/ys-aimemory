# MCP Messages Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. The user has authorized implementation, VM deployment and coordination with remote Claude.

**Goal:** Codex and remote Claude exchange real, persisted messages through authenticated MCP calls.

**Architecture:** Add a separate message table and two tools under existing project authorization and serialized transactions. The authenticated principal supplies the sender. Keep task leases, knowledge revision and message conversations independent.

**Tech Stack:** Python, Pydantic, SQLAlchemy, PostgreSQL, official MCP SDK; existing FastAPI/HTTPS deployment.

**Spec:** The current user request asks both agents to test and improve MCP so they can converse directly. The concrete contract below implements that request.

## Contract and constraints

- `send_message(project_id,recipient_worker_id,thread_id,body,idempotency_key,reply_to_message_id=null)`.
- `thread_id`: nonempty safe identifier, maximum 128 characters. Body: preserve whitespace, reject whitespace-only, maximum 8000 UTF-8 bytes. Key: nonempty, maximum 128 characters.
- `list_messages(project_id,thread_id=null,after_sequence=0,limit=20)`; limit 1–50. Sender/recipient only; admin has no implicit read-all override.
- Replies must reference the same project/thread and exact participant pair. Unknown and inaccessible parents produce the same error.
- Recipients must currently be active and project-authorized; sender is never accepted from caller arguments. No self messaging.
- Persist messages and audit atomically. Unique `(project,sender,key)`; identical retry returns the existing message, changed payload conflicts. Audit excludes body.
- Use project-serialized committed sequence ordering. `next_after_sequence` is last returned sequence or the input cursor; `has_more` uses an extra matching row. Reset cursor when changing filters.
- Do not change knowledge revision, task lease/fence or knowledge index. Messages are untrusted content, not authorization.
- No automatic model wakeup, provider login borrowing, global Codex changes, secret-bearing reports, or impersonating Claude agent-b.
- Source base: `021fcea303e8b6662fd9af60eb6c40250d14eda0`; existing main and old worktrees preserved.

## Task 1: Message tools and persistence

Owner: core_inventory in isolated `worktrees/mcp-messages`; files: models.py, service.py, store.py, app.py, new message_store.py, message tests and schema/tool-count compatibility tests.

- [ ] Write failing behavior tests, retain RED output, then implement the contract.
- [ ] Verify both directions, third-person/admin exclusion, spoofed sender, scope/recipient denial, reply isolation, whitespace/UTF-8 limits, retry conflicts, pagination with hidden rows and audit gaps.
- [ ] Verify transaction rollback, concurrent duplicate requests, restart persistence, v3 migration preservation, and task-context validity before/after chat on SQLite and PostgreSQL.
- [ ] Commit tested changes; independent review before integration.

## Task 2: Discoverability and instructions

Owner: test_scope_review in isolated `worktrees/mcp-message-docs`; files: README, client/API/generator docs, web_help.py and help tests, new MCP_MESSAGES.zh-TW.md.

- [ ] Document concrete send/list/reply payloads using the MCP `arguments` wrapper, polling cursor and separate identities.
- [ ] Explain persisted messaging versus model execution, native versus SDK verification, and unchanged task authorization.
- [ ] Add the HTML manual section and verify accessible links/content; commit and review.

## Task 3: Deployment and live two-agent conversation

Owner: root; reviewer: hardening_review. Evidence is outside Git under `verification/messages-20261002`.

- [ ] Integrate reviewed commits, run full PostgreSQL regression, and retain exact commit/environment/results.
- [ ] Create a private pre-migration DB backup; stage a source archive from the clean commit, validate a candidate with isolated PG, then promote on authorized VM.
- [ ] Validate HTTPS CA/hostname, health schema v4, 28 tools, runtime source hashes and authenticated authorization through official MCP.
- [ ] Send a fresh agent-a question. Remote Claude agent-b must read it via MCP and independently author a reply. Agent-a reads and responds via MCP; verify at least two round trips with reply IDs and message bodies.
- [ ] Verify third identity cannot read the conversation and task context remains unchanged. Record native client status separately.
- [ ] Publish a concise evidence report and update CURRENT_STATUS without altering historical receipts.

## Review ledger

Task 1 and Task 2 share the tool contract but no implementation files. Task 3 consumes both commits; all backend and docs changes are reviewed before deployment. No existing Hub-managed task is being claimed for this new local development work.

Decision: use dedicated messages rather than cyclic task handoffs, because conversation should not transfer work ownership. Keep evidence and old worktrees for custody.
