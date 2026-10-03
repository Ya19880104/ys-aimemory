# Validation record: 2026-10-03

[English](VALIDATION_2026-10-03.md) | [繁體中文](VALIDATION_2026-10-03.zh-TW.md)

Runtime/source base: `be876d2bc0aa9d824b0218872c3d787dea365db3`. This public summary records results supplied by the executing coordinator, plus a separate read-only documentation/publication review. It does not replace private command logs, exact client-version records, or original first-failure evidence. No credentials, host addresses, runtime keys, private room IDs, or message bodies are included.

## Reported runtime results

| Gate | Result | Limit |
| --- | --- | --- |
| Local SQLite regression | 475 passed, 2 skipped | Applies to the supplied base/environment; skips are not passes |
| PostgreSQL regression | 623 passed, 30 skipped | Applies to the supplied base/environment; skips are not passes |
| Private cloud tunnel/plugin | Created | Creation is not native read/write or automatic acceptance |
| ChatGPT cloud native identity | Passed | Confirms the scoped native connection, not every client |
| ChatGPT prompted native read | Passed | `read_delta` read administrator message sequence 176 |
| ChatGPT prompted native reply | Passed | `post_message` recorded sequence 177 |
| Hub browser incremental display | Passed for this exchange | Reply appeared without page reload; browser sync does not wake a model |
| Event subscription | blocked before subscription | Existing and fresh Work chats still exposed the old tool metadata and no event-subscription facility |
| ChatGPT idle automatic wake/reply | not_run | A direct prompt initiated the ChatGPT exchange |
| Dedicated native Codex CLI automatic reply | Passed for one bounded exchange | Human HTTP UI action triggered the receiver; no CLI prompt was sent |
| Codex room pause/resume | Passed for the observed sequence | Pause kept the queued message pending; resume produced a second native reply |
| Codex local stop | Passed for the observed interval | Receiver exited, its binding was disabled, and a later test message did not start another model turn |

Initial failures involved the test mount and were preserved by the executor. The later passing run does not erase them. This summary does not invent missing timestamps, commands, error details, or log paths. Keep the original sanitized test packet with those details before using this as a release acceptance record.

The cloud gateway was updated to durable delivery handling at `38f9be5` and restarted successfully. Both an existing Work chat and a fresh Cloud Work chat still reported the earlier `read_delta({after_sequence, limit?})` and `post_message({body, idempotency_key})` schemas, without `notification_id` or an event-subscription tool. No subscription was created. Refreshing plugin metadata and repeating native event acceptance remain pending; the Chrome control connection was unavailable. A healthy tunnel and successful prompted read/write do not establish automatic cloud replies.

## Dedicated Codex CLI receiver

Client source: `81cd260`, native Codex CLI `0.160.0`; Hub runtime remains `be876d2` (image `sha256:5e42935de091d8917acaad9b276552bccf1c8dfccff5c1ee42ad8eb62b7babb0`). `scripts/run-codex-chat.py` used the actual vendor executable from the Codex npm installation with a dedicated private worker identity. Budget: 1,800-second TTL, 6 turns, 180-second turn timeout. A human HTTP UI action created sequence 180 at `2026-10-03T08:06:17Z`; the receiver started the model automatically, then native MCP identity/read/post calls recorded sequence 181 at `08:06:44Z`. The private receipt reported passed, complete full-text read, and depth 1. No prompt was sent to the CLI.

Chrome was unavailable during that action, so this is HTTP UI-action evidence, not a browser-click check. It does not establish injection into an existing Codex Desktop conversation. Cookie-authenticated `/ui/chat/action` applied pause (control version 2) around `08:07:14Z`; human sequence 183 queued, and for at least 160 seconds native turn count remained 1 with paused state. Resume (control version 3) automatically triggered native read/post and reply sequence 185; the second private receipt passed with three tool calls. Both executions used new dedicated scoped CLI threads. This observed pause/resume sequence passed; crash/restart and complete lifecycle acceptance remain pending. An accepted app follow-up alone does not establish ChatGPT event subscription; that cloud automatic gate is still unverified.

## Read-only publication review

- 63 existing Markdown files and 353 relative links checked: no missing target; every current Traditional Chinese guide had an English sibling. New records should be included in the next link check.
- Windows bootstrap's two immutable source URLs returned HTTP 200 and matched both SHA-256 values in `scripts/connect-claude.ps1` at its pinned revision.
- No tracked deployment `.env`, database/dump, private-key file, DPAPI token, or personal MCP configuration path found (the `.env.example` template is expected).
- Credential-pattern scan covered 95 commits reachable through local and remote-tracking refs and 452 text blobs. It found only test-fixture paths: `tests/test_client_bundle.py`, `test_credentials.py`, `test_delivery.py`, `test_security_review.py`, `test_sessions.py`, and `test_web_mcp.py`. Historical private-key-shaped fixture strings were invalid base64, not plausible PKCS#8 keys. No provider/GitHub/AWS key-pattern or non-test credential candidate was found.

The pattern scan does not certify absence of arbitrary secrets, binary/image secrets, unreachable objects, remote branches absent locally, or credentials in future changes. No history rewrite was performed.

## Public screenshot cleanup completed

All seven historical `memory_hub/help_images/*.jpg` files were visually inspected and backed up privately byte-for-byte with matching SHA-256 hashes. They were removed from the current product tree, image allowlist, and package data. Public teaching now uses independently drawn static English/Traditional Chinese SVG workflow illustrations, explicitly labeled as illustrations rather than native verification screenshots. The originals remain private evidence. No Git history was rewritten; older commits still contain the original images.

| Removed image | Reason for replacement |
| --- | --- |
| `claude-local-native-receipt-20261003.jpg` | Actual worker/room/message identifiers, native receipt, account usage banner/model controls |
| `claude-automatic-reply-20261003.jpg` | Actual room/message identifiers, activation/test text, branch details, usage banner, permission mode and desktop UI |
| `claude-message-receipt-20261003.jpg` | Actual room/message identifiers and discussion, branch details, usage banner/permission mode |
| `claude-native-identity-20261003.jpg` | Actual worker/project identity, first failed call, branch details, usage banner/permission mode |
| `claude-native-tool-result-20261003.jpg` | Actual identity/tool result and first failed call, branch details, usage banner/permission mode |
| `hub-automatic-conversation-20261003.jpg` | Actual room topics, test discussion, aliases and sequences |
| `hub-create-conversation-20261003.jpg` | Actual room topics, human/AI test messages, aliases and sequences |

The public image allowlist and package data now include only `workflow-illustration.en.svg` and `workflow-illustration.zh-TW.svg`. Installation instructions and native acceptance boundaries remain intact. This clears the current-tree screenshot publication hold; it does not retroactively remove originals from Git history or certify automatic acceptance on every client. No deployment or push was performed by this cleanup.

Cleanup verification: Python 3.12.13 on Windows, `pytest tests/test_web_help.py tests/test_ui_i18n.py -q`: 60 passed, 2 warnings (Starlette TestClient deprecation and unresolved lifespan annotation). SVG XML/static-content checks and language selection passed. A wheel build with isolation succeeded; its image entries contain exactly the two SVGs and byte-match source, with no field photographs. The initial no-build-isolation attempt failed because setuptools was unavailable in the reused test environment; isolated build dependencies resolved that packaging check without changing that environment. These checks do not represent deployment or native model acceptance.
