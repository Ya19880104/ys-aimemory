# Web dashboard and human accounts

[English](WEB_DASHBOARD.md) | [繁體中文](WEB_DASHBOARD.zh-TW.md)

Login leads to shared conversations `/ui/chat`. `/ui` exposes project/task/source/audit management. Chat does not require task admission; source execution does. Human cookies are not MCP bearer credentials.

## Language

English is the default. `HUB_WEB_LANGUAGE` accepts only `en` or `zh-TW`; unsupported values fail configuration validation. The interface language switch uses `?lang=en` or `?lang=zh-TW` and a language preference cookie. It changes interface text, not stored user messages, worker identity, project grants, or token permissions. Keep API identifiers and source content unchanged when switching.

## Bootstrap

No default password exists. Configure `HUB_WEB_USERNAME`, generated `HUB_WEB_PASSWORD_HASH`, comma-separated explicit `HUB_WEB_PROJECTS`, and `HUB_WEB_ROLE` (default read_only; admin is an explicit choice). Generate hashes with `python -m memory_hub.web_password` and single-quote them in Compose `.env` to preserve `$`. `HUB_WEB_COOKIE_SECURE=true` requires HTTPS; false is only for isolated loopback tests. `HUB_WEB_SESSION_TTL` is 300–28800 seconds, default 3600.

Initial accounts are imported once into DB. Thereafter online account data is authoritative; old environment values do not reset disabled users or overwrite password/role/grant changes. Follow upgrade guidance before removing bootstrap variables; partial bootstrap configuration can fail startup.

## Accounts and permissions

`/ui/users` supports names, roles, explicit project grants, reset/disable/enable; login names are stable, history retains UUIDs, and identity deletion is not provided. Users change their password at `/ui/account/password` using the current password. `can_manage_users` is a separate trusted global capability, not an implicit grant to read all projects. The last enabled account manager cannot be disabled/revoked.

Admin performs allowed project/task operations; member participates in chat; read_only views without posting. Password/role/scope/status changes invalidate prior sessions. Requests recheck DB identity/grants. Project creation records owner/grant atomically; historical ownership does not recreate revoked grants.

## Security and state

DB sessions, CSRF, operation nonces, flash messages, and throttling coordinate across instances. Only hashed cookie keys are stored. Sessions expire at a fixed time. Security-policy changes revoke prior sessions/nonces and require coordinated worker updates. Login limits use direct peer IP; proxy users may share limits, and arbitrary forwarded headers are not trusted.

Configured MCP identities/recent activity are observations, not permanent online/model-running status. Automatic receiver states are separate from MCP activity. No OAuth/SSO or forgotten-password email flow is supplied. Preserve a second trusted account manager and protected recovery process. See [deployment](DEPLOYMENT.md) and [shared chat](SHARED_SESSIONS.md).


## Documentation mirrors and offline help

`HUB_DOCS_BASE_URL` controls server-rendered Hub guide links. Unset or empty keeps `https://github.com/Ya19880104/ys-aimemory/blob/main/docs`. Set an HTTPS directory such as `https://docs.example.com/ys-memory`, or a root-relative directory such as `/mirror/docs`; links append the selected English or Traditional Chinese Markdown filename. Supply the mirror files and web-server mapping yourself; the Hub does not download, host or validate mirror contents. Wheels do not bundle the Markdown guides.

For a disconnected LAN, set `HUB_DOCS_BASE_URL=/help`: links open the existing localized built-in help landing page (`/help?lang=en` or `/help?lang=zh-TW`), rather than nonexistent per-guide routes. This is a summarized local manual, not a copy of every full guide.

Only HTTPS or root-relative directory URLs are accepted. Credentials, query/fragment, percent escapes, backslashes, control/non-ASCII characters, repeated path separators and dot traversal are rejected; use ASCII/punycode URLs. Invalid values safely fall back to local `/help` without breaking UI requests. Trailing slashes are normalized. Compose passes this setting to the app. Restart the configured runtime after changing deployment settings. Pinned installer downloads and upstream vendor references remain independent; this setting neither rewrites nor trusts installer sources.
