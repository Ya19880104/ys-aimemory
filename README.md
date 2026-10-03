# ys-aimemory

[English](README.md) | [繁體中文](README.zh-TW.md)

Shared project memory, conversations, and explicit task handoffs for human operators and AI clients. Built with Python, FastAPI, the official MCP SDK, and PostgreSQL. Clients use MCP Streamable HTTP or a local stdio adapter; model inference stays in the user's chosen client.

## Start here

1. **Use an existing Hub:** [Client setup](docs/CLIENT_SETUP.md) or [Windows Claude installation](docs/CLAUDE_WINDOWS_SETUP.md).
2. **Run your own Hub:** [Quickstart](docs/QUICKSTART.md) and [deployment](docs/DEPLOYMENT.md).
3. **Discuss with humans and AI:** [Operation manual](docs/OPERATION_MANUAL.md) and [shared conversations](docs/SHARED_SESSIONS.md).
4. **Enable bounded automatic replies:** [Automatic chat](docs/AUTOMATIC_CHAT.md). MCP connectivity alone does not start a receiver or wake an idle model.
5. **Choose a client:** [Claude, Codex, Gemini, and Grok](docs/MULTI_CLIENT_SETUP.md).
6. **Browse all guides:** [Bilingual documentation index](docs/README.md).

The normal flow is **create/select a project → create/select a conversation → issue a separate worker token for each AI → connect MCP → join that room → optionally enable a bounded receiver**. Chat does not require a task lease. When discussion becomes source work, use formal task admission.

## Capabilities and boundaries

- Versioned sources, SHA-256 evidence, revisions, search, import, and audit.
- Task admission: prepare → claim → read required sources → acknowledge → accept → validate. Leases, renewal, fencing, checkpoints, explicit handoff, and guarded administrator recovery.
- Shared conversations, incremental reads, immutable artifacts, scoped attachments, and separate two-party messages.
- Human administrator/member/read-only accounts, explicit project grants, CSRF/nonce protection, and database-backed sessions.
- Dedicated worker identities; compact stdio discovery through `memory_tools` and `memory_call`.
- Durable automatic-delivery state and room pause controls. Native receiver integration and cloud/private-tunnel acceptance must be verified against the deployed commit; this README does not certify those gates as passed.

Receipts prove the operation recorded by the server. They do not prove understanding, model execution, continuous presence, or independent acceptance. Browser refresh, native IDE MCP calls, CLI receivers, SDK checks, and cloud transports need different evidence. See [native-client acceptance](docs/NATIVE_CLIENT_CHECK.md) and [delivery API](docs/DELIVERY_API.md).

The [private ChatGPT tunnel pilot](docs/CHATGPT_PRIVATE_TUNNEL.md) uses a fixed worker and one room. It is not a public multi-user OAuth service. Publishing this repository does not publish a deployed Hub.

## Local development

Clone into a new directory; run from the root containing `pyproject.toml`:

```sh
git clone https://github.com/Ya19880104/ys-aimemory.git
cd ys-aimemory
git rev-parse HEAD
python -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/test-deployment.py
```

Windows: replace `.venv/bin/python` with `.venv\Scripts\python.exe`; activation is optional. Python 3.11+ is required; Windows installers use 3.12. `requirements-tested.txt` records tested versions, not a hash-locked artifact. PostgreSQL tests require a disposable database; skips are not passes.

After privately configuring `HUB_DATABASE_URL` and `HUB_AUTH_TOKENS`:

```sh
.venv/bin/python -m uvicorn memory_hub.app:create_app --factory --host 127.0.0.1 --port 8000
```

There is no built-in administrator password or usable token. PostgreSQL is the deployment target; SQLite opt-in is for isolated demos/tests. `/healthz` is health, `/mcp` is MCP, `/v1/tools/{tool_name}` is REST.

## Contributing and agent rules

[Contributing](CONTRIBUTING.md) · [Issues](https://github.com/Ya19880104/ys-aimemory/issues) · [Actions](https://github.com/Ya19880104/ys-aimemory/actions)

Read [AGENTS.md](AGENTS.md) and the relevant [Skills](skills/) before source work. Workers use separate clones/worktrees, identities, and branches. Task roles do not grant security permissions. Do not commit tokens, passwords, cookies, private keys, real databases/backups, personal client settings, or private acceptance evidence.

Existing help screenshots preserve historical test material, not current native acceptance. Review their identifiers and sharing scope before redistribution.

`MANIFEST.sha256.json` and [the original report](TEST_REPORT.zh-TW.md) preserve historical delivery evidence, not current CI results or a manifest of later additions. Record passed, failed, skipped, and not_run separately with the exact commit/environment. Distribution: `ys-ai-memory-hub`; import: `memory_hub`.

Latest scoped evidence: [2026-10-03 validation](docs/VALIDATION_2026-10-03.md). Prompted ChatGPT identity/read/write and browser synchronization are distinct from event subscription and idle automatic wake.
