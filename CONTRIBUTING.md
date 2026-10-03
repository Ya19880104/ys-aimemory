# Contributing to ys-aimemory

[English](CONTRIBUTING.md) | [繁體中文](CONTRIBUTING.zh-TW.md)

Issues, proposals, and pull requests are welcome. Read README, AGENTS, and relevant guides first. This project coordinates memory and handoffs; it does not proxy model-provider logins.

## Report a problem

Include commit, OS/Python/client versions, minimal reproduction, expected/actual behavior, and the first relevant error. Distinguish SDK checks from native model calls. Connected alone is insufficient evidence.

Use synthetic data. Do not attach tokens, cookies, `.env`, SSH/TLS private keys, real databases/backups, private chats, full host settings, or personal paths. Use GitHub private vulnerability reporting if available; otherwise request a private contact without publishing exploit details or credentials.

## Develop and validate

```sh
git clone https://github.com/Ya19880104/ys-aimemory.git
cd ys-aimemory
git switch -c docs/your-change
python -m venv .venv
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m pytest -q
.venv/bin/python scripts/test-deployment.py
```

Use `feat/`, `fix/`, or `docs/` as appropriate. Windows uses `.venv\Scripts\python.exe`. Preserve uncommitted work and other workers' branches. PostgreSQL tests require a dedicated disposable database. Skipped tests are not passes; Windows checks do not replace Linux/PostgreSQL/browser acceptance.

## Submit a PR

Describe the concrete problem and resulting behavior, compatibility, actual verification, and limitations. Include passed/failed/skipped/not_run tied to the commit. Inspect `git diff --cached`; `.gitignore` does not remove secrets already in history. Do not rewrite the historical manifest to conceal changes.

English is the default public language. Maintain useful Traditional Chinese counterparts and reciprocal links. API field names and idempotency/revision/lease/fence requirements must agree. Label old plans archival. PR submission does not authorize deployment or changes to user data.
