# Windows Codex automatic-chat setup

[English](CODEX_CHAT_SETUP.md) | [繁體中文](CODEX_CHAT_SETUP.zh-TW.md)

This guide installs a dedicated **local Codex CLI receiver** for one YS Memory project and conversation. After you start it, new room messages can trigger bounded native model replies. It creates its own private installation; it does not inject messages into an existing Codex Desktop conversation, configure Claude, or edit global Codex settings.

For ordinary on-demand MCP access, use [client setup](CLIENT_SETUP.md). For room controls and delivery semantics, see [automatic chat](AUTOMATIC_CHAT.md).

## 1. Prepare the CLI and room

Use Windows with Python 3.12. Git is only needed for the optional checkout method. Install the official Codex CLI using the **Windows** instructions on the [official Codex CLI page](https://learn.chatgpt.com/docs/codex/cli), then open a new PowerShell terminal. Check the installation:

```powershell
Get-Command codex -All
codex --version
py -3.12 --version
```

The installer resolves `codex.exe` from `PATH`. For a standard official npm installation that exposes `codex.cmd`, it reads that installation's package metadata and resolves the matching Windows x64/arm64 native dependency automatically; it does not execute the wrapper or require a guessed application-folder path. Package name, alias version, OS and architecture must match. For a nonstandard installation, `--codex` (or bootstrap `-CodexPath`) accepts an explicitly verified native executable. Version/help preflight checks required CLI features without running a model.

Use your existing CLI login. If the CLI is not signed in, complete `codex login` yourself using [official authentication guidance](https://learn.chatgpt.com/docs/auth). The installer does not sign in, copy model credentials, or change your account. The Hub worker Token below is a separate credential.

In the Hub, select/create the project, open a conversation, and issue a dedicated worker Token for this Codex receiver through the MCP generator. Give that worker access to the selected project. Keep each AI's worker identity separate. Collect:

| Value | Where it comes from / meaning |
| --- | --- |
| `--url` | Administrator-verified HTTPS Hub origin, such as `https://memory.example.internal:8443`; no `/mcp`, query, fragment, or Token. |
| `--expected-ca` | Public CA certificate **DER SHA-256** fingerprint obtained through a trusted channel: 64 hexadecimal characters. |
| `--project-id` | The Hub project ID, not a local folder path or display title. |
| `--session-id` | The Hub conversation ID: 32 lowercase hexadecimal characters, not a Codex chat ID. |
| `--worker-id` | The exact dedicated Codex worker identity associated with the Token. |
| Worker Token | The Token issued for that worker; enter it only at the hidden local prompt. |

The machine must reach the Hub's public CA download on HTTP port 80, the verified HTTPS client bundle, and the Python package source used by that bundle. Only the public CA is fetched over HTTP; its trusted fingerprint must match before authenticated HTTPS operations. The installer does not add global CA trust, follow redirects, or use environment proxies for Hub requests.

## 2. Install through a fixed URL (no clone)

Download and review this immutable script. The hash check must pass before execution:

```powershell
$Installer = Join-Path $env:TEMP ('ys-memory-codex-' + [Guid]::NewGuid().ToString('N') + '.ps1')
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/bd8d4e684e0f510312cf491e015dbd1d3944fff4/scripts/connect-codex-chat.ps1' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne 'F5E622AC3BC21CA06B311238C4B49491324FDD01C40F84FC97081913A4EBFDD7') { throw 'Installer hash mismatch' }
notepad $Installer
```

After review, replace the values and install. Use the dedicated Codex worker, never Claude's Token:

```powershell
& $Installer -Url 'https://YOUR-HUB' -ExpectedCa 'TRUSTED_CA_DER_SHA256' -ProjectId 'YOUR_PROJECT_ID' -SessionId 'YOUR_32_LOWERCASE_HEX_ROOM_ID' -WorkerId 'YOUR_CODEX_WORKER_ID' -Language en -Hours 1 -MaxTurns 20 -Print
```

`-Print` is the default: it performs installation and authorization checks without starting a model. Enter the Token at the hidden prompt, then continue at **Start the dedicated receiver** below using the receipt's exact `start_command`. Explicit `-Run` instead installs and immediately starts the bounded receiver. Do not combine both switches. `-PythonPath` can select an existing Python 3.12; `-TurnTimeout` defaults to 90 seconds. No local project-directory argument is needed: the receiver creates a private empty working directory for its conversational turns.

The bootstrap verifies four source files from revision `4ed987759e3d83e8caa5788831de3544438172db`, preserving their `scripts/` and `memory_hub/` layout. The shared `setup-claude.py` file supplies only verified bundle/CA primitives; this workflow does not call its Claude installer or write `.mcp.json`. Read the installation details and limits below, or skip the checkout commands if you used the URL installer.

### Alternative: install from a checkout

Clone into a **new** directory and use the checkout containing `scripts/setup-codex-chat.py`:

```powershell
git clone https://github.com/Ya19880104/ys-aimemory.git 'C:\src\ys-aimemory'
Set-Location -LiteralPath 'C:\src\ys-aimemory'
git checkout --detach 4ed987759e3d83e8caa5788831de3544438172db
git rev-parse HEAD
Test-Path -LiteralPath '.\scripts\setup-codex-chat.py'
```

Record the commit shown. If you already have a checkout, preserve its work and use its actual path. If the script is absent, obtain the release containing it; do not substitute a Claude installer or a guessed download command.

Replace the example values, then run this in the interactive PowerShell terminal:

```powershell
py -3.12 .\scripts\setup-codex-chat.py `
  --url 'https://memory.example.internal:8443' `
  --expected-ca 'YOUR_64_HEX_DER_SHA256' `
  --project-id 'YOUR_PROJECT_ID' `
  --session-id 'YOUR_32_LOWERCASE_HEX_ROOM_ID' `
  --worker-id 'YOUR_CODEX_WORKER_ID' `
  --language en --hours 1 --max-turns 20 --print
```

Paste your Codex worker Token when `Your dedicated Codex worker Token (hidden):` appears. No characters are echoed. Do not put the Token in the URL, command line, source files, or a Git commit. A piped/noninteractive terminal is rejected because it cannot provide the required private prompt.

**`--print` performs installation; it is not a dry run.** Omitting an action has the same behavior. It downloads and verifies the Hub bundle, checks the worker and open room through REST, installs an isolated Python environment, stores the Token with current-user Windows DPAPI, and prints a receipt. It makes no model call and does not start automatic replies.

The private directory defaults to `%LOCALAPPDATA%\YS-AIMemory\codex-clients\codex-<generated-id>`. Use the receipt's actual paths. It contains the client bundle, private environment, `worker.dpapi`, installer/receiver sources, and `codex-install.json`; keep this directory outside Git and use the same Windows account.

Options: `--language en|zh-TW`; `--hours 1..8` (default 1); `--max-turns 1..100` (default 20); `--turn-timeout 30..240` seconds (default 90). `--max-turns` bounds model starts, not successful replies. Installation checks are separate from native acceptance.

## 3. Start the dedicated receiver

Check that the printed receipt has your intended `origin`, `project_id`, `session_id`, and `worker_id`. It reports:

```text
status: installed_not_native_verified
authorization_check: rest_identity_and_room_passed
native_acceptance: not_run
```

Copy the complete **`start_command`** from that receipt into PowerShell. It uses the installed private Python/script and `--receipt '<actual path>\codex-install.json' --run`. Keep that terminal/process running. This is the explicit step that enables bounded model execution. Adding `--run` to a fresh installation command also installs and immediately starts; use the two-step flow for the first setup.

The receiver binds only its configured room. On a fresh join it starts at the room's current message position; send a **new** test message after it is online. It checks for delivery without calling a model while idle. An eligible delivery starts native `codex exec` with only `get_worker_inbox`, `read_session`, and `post_session_message`; the receiver verifies identity, reads that delivery, and permits one conversational reply. It cannot perform project development tasks through this scoped toolset. Native non-interactive execution and saved CLI authentication are documented in [official non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

This workflow does not select a model for you or change a saved permission mode. The dedicated child run uses its own read-only sandbox and scoped MCP configuration. Model replies consume your Codex allowance; an idle network poll is not a model turn.

## 4. Verify with an administrator message

1. Open the same Hub conversation as an administrator and confirm the dedicated worker appears online.
2. Send a new message such as: **“Codex connection test: reply once with your worker identity and this message's topic.”** Do not prompt Codex separately to poll.
3. Check the reply in the Hub: correct room, expected worker, new message ID/sequence, and no duplicate reply.
4. Inspect the receiver's `state_directory` from the installation receipt. `receiver-status.json` records receiver state; `receipt-<delivery-id>.json` records native tool-call/read/post evidence and available token usage for that delivery.
5. Pause the room's automatic delivery, send a test message, and confirm no new model reply is dispatched while paused. Resume only within the existing budget and verify the expected delivery behavior.

Browser refresh or `rest_identity_and_room_passed` does not prove automatic native replies. Record each test as **passed / failed / skipped / not_run**, with the checkout commit, receiver version, room, and delivery/message identifiers. The installation receipt remains an installation result, even after later runtime receipts exist. Do not publish private receipts or credentials in issues.

## 5. Inspect, stop, and start a new bounded run

The installation output provides three exact commands; use their recorded paths rather than reconstructing them:

| Receipt field | Action |
| --- | --- |
| `inspect_command` (`--print`) | Validates the owned installation and prints its receipt; does not start a model. Use `receiver-status.json` for runtime state. |
| `start_command` (`--run`) | Runs the dedicated receiver under the receipt's unchanged scope and budget. |
| `stop_command` (`--stop`) | Creates the owned state's `STOP` file and returns `stop_requested`; does not need to read the Token. |

Run `stop_command` in a second terminal. It requests an **asynchronous local stop**; its `running_turns_cancelled: false` is not confirmation that a running model has already stopped. The active receiver observes the stop and attempts to disable its own Hub binding. Check the local status and Hub status; if that receiver is not running or the network is unavailable, the local stop command cannot confirm server-side disablement. The administrator can also pause automatic delivery in the Hub.

The stop operation does not restore ordinary MCP tools, disconnect the worker completely, or remove the installation. There was no existing Desktop/Claude/global configuration replaced to restore. Keep the STOP file and runtime evidence.

The time budget starts at the **first receiver start**, not installation. Its expiry is saved in `receiver-config.json`. Restarting the same receipt does not renew that expiry, reset the Hub's delivery budget, or clear STOP. Receipt operations reject attempts to override the scope or budget. After stop/expiry/budget exhaustion, explicitly provision a new installation with a newly chosen bounded budget; never delete state files or modify the receipt to simulate a fresh run. Ensure the old receiver is stopped first.

## Troubleshooting

| Result | Next step |
| --- | --- |
| `codex_exe_not_found_install_official_cli_or_use_codex_option` | Install the official native Windows CLI, reopen PowerShell, or supply the verified executable path with `--codex`. |
| `codex_cli_missing_required_features` | Update through the official CLI instructions; the preflight found an incompatible CLI. |
| `codex_npm_metadata_invalid`, `codex_npm_native_metadata_invalid` or missing native package | Repair/reinstall the official npm package; do not substitute a guessed binary or edit the checks. Standard nested and hoisted optional dependency layouts are supported. |
| CA/TLS or public-download failure | Verify the administrator's origin/fingerprint and direct network access; do not disable TLS verification. |
| `dedicated_worker_identity_mismatch` | Check the worker ID against the dedicated Token issued by the Hub. |
| `room_identity_or_active_state_mismatch` | Check project/room IDs, worker grant, and that the room is open. |
| `owned_codex_install_modified` or `owned_codex_receipt_invalid` | Preserve the directory for review; do not bypass the ownership/hash checks. |
| Installed but no reply | Start the printed command; check CLI login, room pause, fresh messages, receiver status, budget, and actual runtime receipts. |
| `receiver_was_stopped_keep_evidence_and_provision_new_bounded_run` | Preserve the old STOP/evidence and explicitly create a new bounded installation when wanted. |

This guide describes the installer/receiver contract. It does not certify a particular machine's native run, Desktop injection, or ChatGPT cloud delivery. Those require their own recorded acceptance tests.

## Upgrade and lost-response recovery

Upgrade the Hub first, then stop the old receiver and use this page's current pinned installer. Existing installations do not update themselves. Do not overwrite a running receiver or delete its state. Use Claude's disconnect/renew flow; for Codex, confirm the old receiver stopped, then create a new dedicated installation with an explicit budget.

Updated receivers persist the claim request before HTTP and retry transient failures with bounded backoff within their expiry and stop controls. The same request recovers the original notification only while its lease is valid, dispatch has not started, and no full-message read has been recorded, without another delivery attempt or turn charge. Restarting after dispatch does not immediately launch the same model turn again; a genuinely expired lease may be redelivered at normal budget cost. This is not an exactly-once model guarantee or full native crash-lifecycle acceptance.

Expiry alone permits ordinary manual posts again; room pause, disabled bindings, archiving and revoked permissions still apply. An expired automatic reply must never strip its delivery fields and resend as a manual post. See the [delivery API](DELIVERY_API.md).
