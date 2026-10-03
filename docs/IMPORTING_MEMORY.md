# Import and update memory safely

[English](IMPORTING_MEMORY.md) | [繁體中文](IMPORTING_MEMORY.zh-TW.md)

Select only information authorized for project sharing. Every source has `source_id`, exact `content`, `uri`, and `commit`. The Hub does not fetch URIs or read arbitrary server paths. Whitespace/newlines are preserved; SHA-256 uses content's UTF-8 bytes. Exclude secrets, private keys, personal data, and unnecessary private material.

Administrator `import_sources` requires project, current `expected_revision`, a unique `idempotency_key`, and 1–20 source entries. Total content is limited to 750,000 UTF-8 bytes; the complete escaped JSON body has a separate 1 MiB HTTP limit. Duplicate source IDs within a batch are rejected. Split oversized batches and get a fresh revision/new key for each.

Validation, canonical updates, and index updates occur atomically. Identical retry by the same identity/project/key returns the original result; differing parameters with that key conflict. Keys deduplicate, not authorize. For changed content use a new key/current revision.

`register_source` can omit revision for a new source; changing existing content/provenance requires current revision. Identical upserts report unchanged without duplicate versions. After conflicts reread and evaluate differences rather than blindly retrying.

Source changes invalidate stale task context. Workers reprepare/read/acknowledge/accept/validate before continuing. Admin web import applies the same gates plus CSRF/nonce protection. Read-only users cannot import. There is no automatic repository or folder crawl. See [index](KNOWLEDGE_INDEX.md).
