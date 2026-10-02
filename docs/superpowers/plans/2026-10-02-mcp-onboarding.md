# MCP onboarding and operating guide

Authorized scope: add hosted Traditional Chinese HTML help, public CA download,
and an administrator MCP generator; deploy and test on the operator-authorized private VM. Preserve
existing environment tokens and project data. No global client settings changes.

1. Add schema v3 credential registry: random tokens, hash-only persistence,
   stable installation owner ID, project scopes, atomic rotation/revocation.
2. Add authenticated `/ui/mcp` with CSRF and one-use forms; create libraries,
   issue per-worker credentials, and display a token only in its POST response.
   Templates reference a process environment variable and contain no raw token.
3. Add `/help` and public CA download; validate the certificate before serving.
   HTTP bootstrap exposes only GET/HEAD help and CA, never login or credentials.
4. Verify SQLite and PostgreSQL tests, additive v2 migration, TLS/auth/scope,
   one-time disclosure, revocation and generated configurations. Independently
   coordinate the user's existing Claude connection-test session.
5. Back up the running v2 database; deploy immutable release, verify live web and
   official MCP clients, preserve evidence and document rollback requirements.

Worktree custody: root writes web.py, web_management.py, web_mcp.py and their
tests in codex/local-hardening. Registry and guide changes are committed in
separate worktrees and integrated after review. No source shared writable tree.

Account model remains one configured web administrator. A stable UUID owner ID
survives username/password changes. Disabling the generator hides management;
issued managed credentials remain active until explicitly revoked. Revocation
does not silently recover existing task leases. Schema v3 rollback requires a
compatible application or restoration of the pre-upgrade backup.
