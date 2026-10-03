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
