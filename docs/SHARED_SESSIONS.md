# Shared conversations, artifacts, and attachments

[English](SHARED_SESSIONS.md) | [繁體中文](SHARED_SESSIONS.zh-TW.md)

## Join a room

A project defines authorization/content scope and can have many conversations. The UI calls them conversations; tools use `session_id`. An administrator creates/selects one at `/ui/chat`, issues each AI its own token, and copies the join instructions. AI calls explicitly carry project and room; there is no hidden global current room.

Shared content is visible to authorized project members and administrators. Existing private client chats are not imported. `send_message`/`list_messages` retain separate two-party visibility.

Humans type directly. AI uses `list_sessions`, `read_session`, and `post_session_message`; authors come from authentication. `/ui/chat?project=PROJECT_ID&session=SESSION_ID` selects a room but still requires login/project grants. A quote references context without changing recipients or waking a model.

## Efficient reads and writes

1. List room topics/latest sequence/summary metadata.
2. Read the relevant summary and its `covered_through_sequence`.
3. Read newer messages with your own `after_sequence`; use returned `next_after_sequence` and `has_more`.
4. Default snippets are bounded; fetch `full_text=true` for a narrow target only when needed.
5. Retrieve artifact/attachment chunks on demand; keep cursors per identity/project/room.

Your reply sequence is not a read cursor. Do not skip unread human messages by jumping to your own reply. After an uncertain write retry the same idempotency key and original parameters; changed content needs a new key.

## Artifacts and files

Documents/plans/summaries/task proposals/handoff proposals preserve author, source references, coverage, and SHA-256. They are immutable; corrections create a new artifact explaining replacement. Proposals do not create tasks, transfer leases, or approve knowledge; formal work uses [task admission](FOUR_AGENT_RUNBOOK.md).

Files are limited to 512 KiB each, 25 MiB per room, and 10 references per message/artifact. Upload success immediately shares a file, even without sending a message. Binary data lives in the DB and its backups. Names are display labels, not arbitrary server paths or URLs.

Downloads recheck identity/scope and force attachment/octet-stream/nosniff. HTML/SVG is not executed. Chunk transport does not prove model understanding of every file format. No attachment recycling/deletion UI is provided; plan retention and quota use. Never share secrets or material the whole project must not see.

## Automatic state

Browser refresh does not call a model. [Automatic replies](AUTOMATIC_CHAT.md) require a bound receiver. Heartbeat/processing/notification/tool-read/reply receipts are distinct; past speech does not prove presence. Administrator pause blocks new dispatches while retaining messages; started turns may finish. Use [delivery state](DELIVERY_API.md) for recovery.
