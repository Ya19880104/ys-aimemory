# Bounded automatic chat

[English](AUTOMATIC_CHAT.md) | [繁體中文](AUTOMATIC_CHAT.zh-TW.md)

The Hub stores a room message; an enabled receiver detects eligible events; a bound native client starts a model turn and reads/replies using its own identity. Browser refresh and MCP initialization do not perform inference or wake another client. Historical prototype experiments apply only to their exact environment. Integrated native wake/recovery and cloud acceptance remain separate gates.

## Windows: connect Claude to one room without cloning

This path installs project-local MCP and prepares automatic replies in one selected room. Use an existing local Claude Code project and Python 3.12. In the Hub, choose the project and room, obtain a **separate Claude worker Token**, and copy the project ID, room/session ID, HTTPS Hub URL and trusted **CA DER SHA-256 fingerprint**. The room ID is not the Claude conversation ID. Keep the Token for the private prompt; it never belongs in a URL or the following command.

Download this immutable installer in PowerShell, check its hash and review it:

```powershell
$Installer = Join-Path $env:TEMP ('ys-memory-chat-' + [Guid]::NewGuid().ToString('N') + '.ps1')
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/7b666c6dae39d49fbc700540ad2248829c133b80/scripts/connect-chat.ps1' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne 'BBE80FCE04A2707C84C4F0501DE1DA8359205EDC89D00A179EF4AE7851A28E89') { throw 'Installer hash mismatch' }
notepad $Installer
```

After review, run it with your values. The project directory must already exist and be the same directory opened by local Claude:

```powershell
& $Installer -Url 'https://YOUR-HUB' -ExpectedCa 'TRUSTED_CA_DER_SHA256' -Project 'C:\work\my-project' -ProjectId 'YOUR_PROJECT_ID' -SessionId 'YOUR_ROOM_ID' -Language en -Hours 8 -MaxTurns 20
```

If Python is not detected, append `-PythonPath 'C:\Python312\python.exe'`. `Language` supports `en` and `zh-TW`; `Hours` is 1–8 and `MaxTurns` is 1–100. English, 8 hours and 20 starts are the defaults. A room must already exist; this installer does not create accounts or rooms.

1. On a first install, enter the Claude worker Token at the hidden terminal prompt. No characters appear. The installer stores it under Windows current-user DPAPI; it is absent from project settings and the receipt. A verified existing install reuses its encrypted credential without requesting or decrypting it during setup.
2. The receipt reports `configured_waiting_for_native_hook`, expiry, turn budget, a stop-file path and **`activation_prompt`**. Open a new local Claude conversation in the same project, or reload that project's MCP and hooks in your client. Paste the receipt's complete `activation_prompt` into the intended conversation. Claude must reply with the exact generated `YS_MEMORY_JOIN_...` line; do not substitute a conversation ID or simply paste that line yourself.
3. After the reply, check the Hub room for the participant/receiver state. Send a new human message in the Hub and leave Claude idle. Acceptance requires an actual native `chat_read` and `chat_reply` with matching delivery/read/reply receipts, visible in the room. A successful installer or online receiver alone is **not** native acceptance. New joins start from the latest message; send the test message after activation.

The bootstrap downloads exactly five SHA-256-checked files from source revision `5b54867a4204e8218a541b7d87039a2700bf22ac`, preserving `scripts/` and `memory_hub/`. It then verifies the Hub bundle through the pinned CA. No clone or source checkout is required. It changes only this project's `ys_memory` entry, its bounded Stop hook and the three exact `chat_status`, `chat_read`, `chat_reply` permissions. It does not change global configuration, CA trust, Claude login or permission mode.

An existing `ys_memory` entry is reused only when its complete config hash, installer receipt, launcher, Hub/CA and verified bundle match. Unknown, edited or active-chat configurations are preserved and rejected; do not delete them to bypass the check. Review the configuration or use the original receipt's disconnect procedure first. If MCP installation completes but the chat step fails, that MCP installation remains available for inspection; no model turn is started by the installer.

The receipt is also saved as `chat-bootstrap-receipt.json` in the printed `bootstrap_sources` directory. Keep that directory. For stop/renew without a clone, use the receipt's exact `lifecycle_python` and `lifecycle_script` paths:

```powershell
$Receipt = Get-Content -LiteralPath 'PASTE_BOOTSTRAP_SOURCES\chat-bootstrap-receipt.json' -Raw | ConvertFrom-Json
& $Receipt.lifecycle_python $Receipt.lifecycle_script --project 'C:\work\my-project' --disconnect
# To reconnect after disconnect, run the same installed script and activate its NEW prompt:
& $Receipt.lifecycle_python $Receipt.lifecycle_script --project 'C:\work\my-project' --project-id 'YOUR_PROJECT_ID' --session-id 'YOUR_ROOM_ID' --hours 8 --max-turns 20 --language en
```

Use `--renew` on the last command if the binding is still present and you want to disconnect and renew in one operation. The installed environment is used because disconnect needs its verified dependencies. This bootstrap is for local Claude; it does not install a Codex receiver or a ChatGPT cloud plugin.

## Claude project binding from a checkout

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

For a dedicated Codex CLI receiver, follow the [Codex chat installation guide](CODEX_CHAT_SETUP.md). Its own installer provisions a separate worker credential, verified Hub bundle and private runtime, and prints exact start/stop commands. Default `--print` performs installation and a REST identity/room check; explicit `--run` starts the bounded receiver. It does not inject an existing Codex Desktop chat or use Claude's credential. Gemini/Grok receiver acceptance is not claimed. The [private ChatGPT tunnel](CHATGPT_PRIVATE_TUNNEL.md) is a separate pilot.

Idle waiting should not repeatedly ask a model to inspect an empty inbox. Retrieve new messages incrementally. This does not promise zero provider cost or a fixed token savings percentage.

Acceptance requires an idle bound client reacting to a new human web message without an extra prompt; correct identity/room; matching delivery/read/reply receipts; observed budget/pause/stop/revocation/archive behavior; crash/restart recovery without duplicates or skipped human messages; and bounded AI follow-ups. Record exact commits, native versions, and passed/failed/skipped/not_run. [Delivery API](DELIVERY_API.md) defines the durable contract. Source/tests cannot certify native acceptance.

## Upgrade and lost-response recovery

Upgrade the Hub first, then stop the old receiver and use this page's current pinned installer. Existing installations do not update themselves. Do not overwrite a running receiver or delete its state. Use Claude's disconnect/renew flow; for Codex, confirm the old receiver stopped, then create a new dedicated installation with an explicit budget.

Updated receivers persist the claim request before HTTP and retry transient failures with bounded backoff within their expiry and stop controls. The same request recovers the original notification only while its lease is valid, dispatch has not started, and no full-message read has been recorded, without another delivery attempt or turn charge. Restarting after dispatch does not immediately launch the same model turn again; a genuinely expired lease may be redelivered at normal budget cost. This is not an exactly-once model guarantee or full native crash-lifecycle acceptance.

Expiry alone permits ordinary manual posts again; room pause, disabled bindings, archiving and revoked permissions still apply. An expired automatic reply must never strip its delivery fields and resend as a manual post. See the [delivery API](DELIVERY_API.md).
