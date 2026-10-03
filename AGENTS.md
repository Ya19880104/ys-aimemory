# ys-aimemory collaboration rules

[English](AGENTS.md) | [繁體中文](AGENTS.zh-TW.md)

This independent memory/MCP project is separate from ERP and AIOps. Read README and relevant docs before changes; do not modify unrelated repositories.

For Hub-managed work follow `skills/hub-task-start/SKILL.md`: prepare → claim → read required sources → acknowledge → accept → validate. Use only your own worker identity, a valid lease, and the current fence. Work roles do not grant security permissions.

Every worker uses a separate clone/worktree, branch, and explicit path scope. Never share a writable worktree. Stop new writes when sources are stale, leases expire, or scopes conflict; preserve work and revalidate context. Renew long-running leases. After handoff the previous holder stops writing.

Use `skills/hub-task-handoff/SKILL.md` for delivery and `skills/hub-review-accept/SKILL.md` for review/testing. Report exact commits, actual tests, untested items, evidence, and next steps. Pending proposals are not authoritative sources.

Never store passwords, login cookies, API keys, or real tokens in Git, Hub knowledge, or handoff logs. Credential configuration, deployment, external publication, and permission changes require explicit authorization.

Skills are agreements. The server gates operations sent through it; it cannot prevent direct local file changes. If the Hub is unavailable, report that honestly. Never claim validated context, a claimed task, or an acquired lock without evidence.
