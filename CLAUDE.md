# Claude Code project entry point

[English](CLAUDE.md) | [繁體中文](CLAUDE.zh-TW.md)

Read [AGENTS.md](AGENTS.md) first; the same workflow and boundaries apply.

Portable Skills are in `skills/`: hub-task-start for admission, hub-task-handoff for delivery, hub-review-accept for review/testing. If discovery is unavailable, read them explicitly by path. Do not assume they were installed or loaded.

The user configures MCP in their own client. Use the authenticated worker identity; coordinator/reviewer roles are not administrator permissions. Follow [the task runbook](docs/FOUR_AGENT_RUNBOOK.md) and the actual tool schemas.
