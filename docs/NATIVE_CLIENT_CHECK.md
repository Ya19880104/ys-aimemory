# Native client acceptance

[English](NATIVE_CLIENT_CHECK.md) | [繁體中文](NATIVE_CLIENT_CHECK.zh-TW.md)

| Layer | Evidence |
| --- | --- |
| Installed configuration | Files/environment/paths created |
| Local Connected/tools list | Host starts adapter and discovers schemas |
| SDK identity check | Transport and token/project authorization |
| Native model tool result | Official client actually executes a tool |
| Shared read/write | Native client reads human input and records a reply |
| Idle automatic reply | Receiver triggers a turn without another prompt |
| Recovery | Disconnect/crash/restart preserves delivery correctness |

One layer does not pass the next. Provider login is separate from Hub bearer authentication.

Use two independent clients with distinct identities and synthetic content. Record commit, OS/client/Python versions, transport type, and actual tool schemas. Ask each native model to call `get_worker_inbox`; verify its identity. Join one room; post a fresh marker as a human; let each client generate its reply. Independently verify authors/message IDs/sequences. One helper impersonating two identities is not native acceptance.

Negative checks include wrong/revoked tokens, unauthorized projects, foreign rooms, absent tools, approval denial, and TLS errors. Preserve first failures; do not disable guards to pass.

Automatic acceptance starts with a genuinely idle bound conversation and a new web message, without another pasted prompt. Verify delivery/read/reply receipts, human interruption, expiry/budget/pause, and restart deduplication. CLI success does not certify arbitrary Desktop chats. Historical receipts are not current acceptance.

Publish sanitized synthetic evidence only. Keep machine addresses, user chats, credentials, and private screenshots outside Git. Report passed/failed/skipped/not_run per layer.
