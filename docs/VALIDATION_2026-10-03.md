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
| Event subscription | not_run | No event-subscription acceptance reported |
| Idle automatic wake/reply | not_run | A direct prompt initiated the native exchange |
| Native Codex/events acceptance | not_run in this record | Await separate exact-version evidence |

Initial failures involved the test mount and were preserved by the executor. The later passing run does not erase them. This summary does not invent missing timestamps, commands, error details, or log paths. Keep the original sanitized test packet with those details before using this as a release acceptance record.

## Read-only publication review

- 63 existing Markdown files and 353 relative links checked: no missing target; every current Traditional Chinese guide had an English sibling. New records should be included in the next link check.
- Windows bootstrap's two immutable source URLs returned HTTP 200 and matched both SHA-256 values in `scripts/connect-claude.ps1` at its pinned revision.
- No tracked deployment `.env`, database/dump, private-key file, DPAPI token, or personal MCP configuration path found (the `.env.example` template is expected).
- Credential-pattern scan covered 95 commits reachable through local and remote-tracking refs and 452 text blobs. It found only test-fixture paths: `tests/test_client_bundle.py`, `test_credentials.py`, `test_delivery.py`, `test_security_review.py`, `test_sessions.py`, and `test_web_mcp.py`. Historical private-key-shaped fixture strings were invalid base64, not plausible PKCS#8 keys. No provider/GitHub/AWS key-pattern or non-test credential candidate was found.

The pattern scan does not certify absence of arbitrary secrets, binary/image secrets, unreachable objects, remote branches absent locally, or credentials in future changes. No history rewrite was performed.

## Screenshot publication hold

All seven tracked `memory_hub/help_images/*.jpg` files were visually inspected. No bearer credential or private key was visible, but they contain actual historical test context and client/account UI. Prefer replacing them with clearly labeled synthetic teaching images before claiming the package contains no private acceptance material.

| Image | Material to replace or redact |
| --- | --- |
| `claude-local-native-receipt-20261003.jpg` | Actual worker/room/message identifiers, native receipt, account usage banner/model controls |
| `claude-automatic-reply-20261003.jpg` | Actual room/message identifiers, activation/test text, branch details, usage banner, permission mode and desktop UI |
| `claude-message-receipt-20261003.jpg` | Actual room/message identifiers and discussion, branch details, usage banner/permission mode |
| `claude-native-identity-20261003.jpg` | Actual worker/project identity, first failed call, branch details, usage banner/permission mode |
| `claude-native-tool-result-20261003.jpg` | Actual identity/tool result and first failed call, branch details, usage banner/permission mode |
| `hub-automatic-conversation-20261003.jpg` | Actual room topics, test discussion, aliases and sequences |
| `hub-create-conversation-20261003.jpg` | Actual room topics, human/AI test messages, aliases and sequences |

All seven are in the image allowlist in `memory_hub/web_quickstart.py`; four are directly displayed by its walkthrough (local receipt, automatic conversation, native tool result, create conversation). `pyproject.toml` packages the entire image glob. Replacing/removing only Markdown references does not remove images from the Python package or public help routes. This review did not modify images/product routes/history; coordinate replacement with the product writer and preserve original private evidence separately.
