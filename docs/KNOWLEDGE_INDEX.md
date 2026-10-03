# Knowledge search, versions, and index health

[English](KNOWLEDGE_INDEX.md) | [繁體中文](KNOWLEDGE_INDEX.zh-TW.md)

`search_knowledge` uses PostgreSQL simple-tokenizer full-text search/GIN, or SQLite FTS5 in test mode. CJK queries use an explicitly marked literal substring fallback. It is not vector/semantic search. Query text is not executable SQL/FTS syntax; inspect the response's search mode.

Supply the authorized `project_id`, query, limit (default 50, maximum 100), and offset (maximum 10000). Continue with returned `next_offset`. Results include provenance, bounded snippets, index revision, and decision status. Pending proposals remain non-authoritative; snippets cannot replace required-source admission.

Canonical project JSON is authoritative. Derived documents and synchronous transactional index work update with source/decision changes. There is no independent background indexing worker. First access can rebuild existing project indexes without deleting history/tasks/packets/audit.

`index_health` compares revisions and row counts, not every content byte. Administrator `reindex_project(project_id, expected_revision)` rebuilds derived data from canonical state, not external repositories.

`list_sources`/`list_tasks` use `after_id`, limit, and returned `next_after_id`; `get_source_metadata` lists versions without full content. `get_project_summary` provides revisions/counts/index state; `get_worker_inbox` exposes the authenticated worker's tasks. Large aggregate growth, retention, contention, and CJK search quality still need measurement.
