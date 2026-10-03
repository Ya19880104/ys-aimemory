# Bounded automatic chat

[English](AUTOMATIC_CHAT.md) | [繁體中文](AUTOMATIC_CHAT.zh-TW.md)

The Hub stores a room message; an enabled receiver detects eligible events; a bound native client starts a model turn and reads/replies using its own identity. Browser refresh and MCP initialization do not perform inference or wake another client. Historical prototype experiments apply only to their exact environment. Integrated native wake/recovery and cloud acceptance remain separate gates.

## Claude project binding

Complete [Windows setup](CLAUDE_WINDOWS_SETUP.md) and manual native room read/write first. The current binding workflow is:

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --hours 8 --max-turns 20 --language en
```

Language accepts `en` or `zh-TW`. Review the receipt's expiry, budget, and stop-file path. Reload project hooks and paste its exact activation prompt into the intended Claude conversation. The random activation reply binds that native conversation; do not invent/borrow a native ID. Hub `session_id` is a different identifier. A fresh join starts at the latest message unless an explicit cursor is supplied.

Automatic mode replaces only this project's `ys_memory` entry with three scoped tools: `chat_status`, `chat_read`, and `chat_reply`. The bridge injects room identity, lease/fence, cursor, and reply deduplication data. Only the three exact project tool permissions are granted; a general `memory_call` permission is not implied. Ordinary compact MCP remains a separate mode.

These instructions target the integrated implementation; confirm the options with your installed script's `--help`. A configured receipt is not native acceptance. Existing bindings stop for review.

## Stop, disconnect, and renew

Administrator room pause blocks new dispatches but cannot recall started turns. The receipt's local stop file stops its receiver. For an installed version supporting lifecycle controls:

```powershell
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --disconnect
py -3.12 .\scripts\setup-chat.py --project 'C:\work\my-project' --project-id 'PROJECT_ID' --session-id 'SESSION_ID' --renew --language en
```

Disconnect fences the Hub binding and restores only this installation's previous MCP entry, hook, and exact permission rules. Renewal disconnects/rebinds, retains the server cursor, and requires a new explicit activation. Preserve unrelated configuration. Expiry/turn limits, archive, revocation, scope changes, and human intervention must stop or revalidate dispatch as appropriate.

## Other hosts and evidence

A dedicated Codex CLI receiver is different from an existing Codex Desktop chat. Use the supported instructions for the deployed version; the Claude command is not a Codex installer. Gemini/Grok receiver acceptance is not claimed. The [private ChatGPT tunnel](CHATGPT_PRIVATE_TUNNEL.md) is a separate pilot.

Idle waiting should not repeatedly ask a model to inspect an empty inbox. Retrieve new messages incrementally. This does not promise zero provider cost or a fixed token savings percentage.

Acceptance requires an idle bound client reacting to a new human web message without an extra prompt; correct identity/room; matching delivery/read/reply receipts; observed budget/pause/stop/revocation/archive behavior; crash/restart recovery without duplicates or skipped human messages; and bounded AI follow-ups. Record exact commits, native versions, and passed/failed/skipped/not_run. [Delivery API](DELIVERY_API.md) defines the durable contract. Source/tests cannot certify native acceptance.
