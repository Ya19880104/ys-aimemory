# Windows Codex automatic-chat setup

[English](CODEX_CHAT_SETUP.md) | [繁體中文](CODEX_CHAT_SETUP.zh-TW.md)

This guide installs a dedicated **local Codex CLI receiver** for one YS Memory project and conversation. After you start it, new room messages can trigger bounded native model replies. It creates its own private installation; it does not inject messages into an existing Codex Desktop conversation, configure Claude, or edit global Codex settings.

For ordinary on-demand MCP access, use [client setup](CLIENT_SETUP.md). For room controls and delivery semantics, see [automatic chat](AUTOMATIC_CHAT.md).

**Candidate boundary:** the four-tool `no_reply` workflow below is not yet deployed or natively accepted. The immutable installer command on this page predates that candidate and does not certify or install its new completion capability. Upgrade the Hub and use a reviewed installer/receiver release containing it before testing silent completion; preserve existing installation/runtime evidence and recorded pins.

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
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Ya19880104/ys-aimemory/cf1ac9956681a36146fdf83b3a9c7bb1961d16b1/scripts/connect-codex-chat.ps1' -OutFile $Installer
if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash -ne '3304255B37763A8BC60187884F8320921B6976C6FFF69135F82C0F226F78C346') { throw 'Installer hash mismatch' }
notepad $Installer
```

After review, replace the values and install. Use the dedicated Codex worker, never Claude's Token:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer -Url 'https://YOUR-HUB' -ExpectedCa 'TRUSTED_CA_DER_SHA256' -ProjectId 'YOUR_PROJECT_ID' -SessionId 'YOUR_32_LOWERCASE_HEX_ROOM_ID' -WorkerId 'YOUR_CODEX_WORKER_ID' -Language en -Hours 1 -MaxTurns 20 -Print
```

`-Print` is the default: it performs installation and authorization checks without starting a model. Enter the Token at the hidden prompt, then continue at **Start the dedicated receiver** below using the receipt's exact `start_command`. Explicit `-Run` instead installs and immediately starts the bounded receiver. Do not combine both switches. `-PythonPath` can select an existing Python 3.12; `-TurnTimeout` defaults to 90 seconds. No local project-directory argument is needed: the receiver creates a private empty working directory for its conversational turns.

The bootstrap verifies four source files from revision `b2c193e12988bcaacd07423e2aeac17b0442c455`, preserving their `scripts/` and `memory_hub/` layout. The shared `setup-claude.py` file supplies only verified bundle/CA primitives; this workflow does not call its Claude installer or write `.mcp.json`. Read the installation details and limits below, or skip the checkout commands if you used the URL installer.

### Alternative: install from a checkout

Clone into a **new** directory and use the checkout containing `scripts/setup-codex-chat.py`:

```powershell
git clone https://github.com/Ya19880104/ys-aimemory.git 'C:\src\ys-aimemory'
Set-Location -LiteralPath 'C:\src\ys-aimemory'
git checkout --detach b2c193e12988bcaacd07423e2aeac17b0442c455
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

The receiver binds only its configured room. On a fresh join it starts at the room's current message position; send a **new** test message after it is online. It checks for delivery without calling a model while idle. The candidate starts native `codex exec` with four tools: `get_worker_inbox`, `read_session`, `post_session_message`, and `complete_session_delivery`. It verifies the authenticated worker and all full delivery pages, then requires exactly one actual completion: a substantive reply or `no_reply`. It cannot perform project development tasks through this scoped toolset. Native non-interactive execution and saved CLI authentication are documented in [official non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

For silent completion, `complete_session_delivery` uses the same project/room, delivery ID, live lease and `delivery-<delivery_id>` key described in the [delivery API](DELIVERY_API.md#dispatch-tool-read-and-completion-receipts). It creates no message/event and returns `delivery_receipt.status=no_reply`. The native proof must retain `completion_status` and the distinct `post_receipt` or `no_reply_receipt`; a model's silence, `tool_read`, error or unknown post outcome is not a successful completion. Identity/full-read/same-worker/generation/expiry/pause fences remain required, and the admitted turn is not refunded. Do not switch disposition after a completed post or use no_reply as an error fallback.

This workflow does not select a model for you or change a saved permission mode. The dedicated child run uses its own read-only sandbox and scoped MCP configuration. Model replies consume your Codex allowance; an idle network poll is not a model turn.

## 4. Verify with an administrator message

1. Open the same Hub conversation as an administrator and confirm the dedicated worker appears online.
2. Send a new message such as: **“Codex connection test: reply once with your worker identity and this message's topic.”** Do not prompt Codex separately to poll.
3. Check the reply in the Hub: correct room, expected worker, new message ID/sequence, and no duplicate reply.
4. Inspect the receiver's `state_directory` from the installation receipt. `receiver-status.json` records receiver state; candidate `receipt-<delivery-id>.json` records native identity/full-read and the actual reply or no_reply completion, plus available token usage. Test intentional silent completion separately and confirm no new room message/event. Failed, timed-out and silent-completed turns still count against the Hub's `--max-turns`; summing posted replies alone understates consumption.
5. Pause the room's automatic delivery, send a test message, and confirm no new model reply is dispatched while paused. Resume only within the existing budget and verify the expected delivery behavior.

Failed native turns keep the first `native-failure-<delivery-id>.json`: fixed error/phase, observed tool evidence and reported usage only. Unknown usage is `not_reported`, not zero. This incomplete local evidence does not establish the server disposition or authorize retry, including when a reply was observed. A fenced restart writes one `receiver-restart-failure.json` and preserves the preceding `receiver-status.json`; reconcile the server and confirm the old child exited before any explicit recovery.

Browser refresh or `rest_identity_and_room_passed` does not prove automatic native replies. Record each test as **passed / failed / skipped / not_run**, with the checkout commit, receiver version, room, and delivery/message identifiers. The installation receipt remains an installation result, even after later runtime receipts exist. Do not publish private receipts or credentials in issues.

## 5. Inspect, stop, and start a new bounded run

The installation output provides exact commands; use their recorded paths rather than reconstructing them:

| Receipt field | Action |
| --- | --- |
| `inspect_command` (`--print`) | Validates the owned installation and prints its receipt; does not start a model. Use `receiver-status.json` for runtime state. |
| `start_command` (`--run`) | Runs the dedicated receiver under the receipt's unchanged scope and budget. |
| `disconnect_command` (`--disconnect`) | Stops the owned receiver and confirms release of its exact Hub binding; reads the protected Token. |
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
| Receiver ends with state `disabled` after a failed turn | A failed native turn makes the receiver disable its own Hub binding, so starting the same receipt again ends with `disabled`. Run the [read-only recovery report](#read-only-recovery-report), keep the state directory, and ask the administrator. Re-enabling a binding is an explicit Hub control described in the [delivery API](DELIVERY_API.md); a restart does not do it. |

This guide describes the installer/receiver contract. It does not certify a particular machine's native run, Desktop injection, or ChatGPT cloud delivery. Those require their own recorded acceptance tests.

## Upgrade and lost-response recovery

Upgrade the Hub first, then stop the old receiver and use this page's current pinned installer. Existing installations do not update themselves. Do not overwrite a running receiver or delete its state. Use Claude's disconnect/renew flow; for updated Codex installations, use the disconnect command and confirm release before creating a new dedicated installation with an explicit budget. Older installations without ownership evidence require administrator review.

Updated receivers persist the claim request before HTTP and retry transient failures with bounded backoff within their expiry and stop controls. The same request recovers the original notification only while its lease is valid, dispatch has not started, and no full-message read has been recorded, without another delivery attempt or turn charge. Restarting after dispatch does not immediately launch the same model turn again; a genuinely expired lease may be redelivered at normal budget cost. This is not an exactly-once model guarantee or full native crash-lifecycle acceptance.

Receivers containing the unresolved-native guard stop before Hub join when a prior native turn is unresolved. Preserve `native-active.json` and the delivery journal. Confirm the old child has exited and reconcile server delivery/binding state before an authorized retry; never delete the marker simply to bypass the fence. Hard-crash tests use a synthetic live CLI child, so real-provider in-flight recovery remains pending. See [2026-10-04 evidence](VALIDATION_2026-10-04.md). The [read-only recovery report](#read-only-recovery-report) shows what the Hub recorded for the reconciliation step.

Expiry alone permits ordinary manual posts again; room pause, disabled bindings, archiving and revoked permissions still apply. An expired automatic reply must never strip its delivery fields and resend as a manual post. See the [delivery API](DELIVERY_API.md).

## Read-only recovery report

After `native_exit_unconfirmed_preserve_binding`, a failed turn or any restart you are unsure about, compare the receiver's local journal with what the Hub recorded before deciding anything. `scripts/inspect-codex-chat-recovery.py` prints that comparison. **It is a diagnostic, not a recovery.**

It is not part of an installed client. Run it from a repository checkout with the receipt's private Python, and record the checkout commit:

```powershell
& 'PYTHON_PATH_FROM_THE_RECEIPT' -B 'C:\src\ys-aimemory\scripts\inspect-codex-chat-recovery.py' --receipt 'CLIENT_DIRECTORY\codex-install.json'
```

What it does and does not do:

- Validates the receipt with the same check `inspect_command` uses, then opens the known journal files in `state_directory` for reading only. It changes no receiver or product state: it writes no journal file, marker, receipt or lock, takes no receiver lock and never removes `native-active.json`. Keep `-B` in the command. The script imports the installer, the receiver and the client's `bridge.py`, and without `-B` Python writes bytecode caches beside them, including one inside the client directory.
- Sends one request, `GET /v1/chat/status` for the receipt's project and room, with this worker's own protected Token over the pinned CA. Its transport refuses every other method or path. There is no join, claim, post, disconnect, lease or expiry change, model start or process inspection.
- Validates the journal files it relies on: `receiver-config.json`, `receiver-binding.json`, `receiver-claim.json`, `receiver-delivery.json`, `receiver-status.json` and the journaled delivery's own `receipt-<delivery-id>.json`. If one of these is linked, malformed, oversized or names another scope, the report is `invalid-local-state` or `scope-mismatch` and the Hub is not contacted.
- Treats `native-active.json` and `STOP` differently, on purpose, because only their presence is used. A linked marker is not followed, and a malformed or oversized one is not trusted for its content, but it still counts as present: the report keeps native exit unconfirmed and still asks the Hub. A linked `STOP` is shown as `linked`. Other files in the directory, including other receipts, are not opened.
- Prints fixed state names and sentences only. The Token, lease and request IDs, reply keys, native session ID, paths and message bodies never appear. 32-character identifiers are shortened unless you add `--full-ids` for private reconciliation.

Options: `--offline` (local journal only; no Token read, no Hub request), `--json`, `--language zh-TW`, `--full-ids`, `--timeout 1..30`. Exit code `0` means a report was produced, whatever its state. Exit code `1` means the receipt, arguments or journal location could not be validated; stderr then carries one fixed code.

| State | Meaning | Rests on |
| --- | --- | --- |
| `server-replied` | The Hub recorded a reply for the journaled delivery. Detail `local-completion-missing`: the receiver saved no `receipt-<delivery-id>.json`, so only the local record is missing; do not resend. `local-completion-recorded`: both records name the same message. `local-completion-mismatch`: they disagree. | The Hub's latest delivery has the same ID, status `replied`, and a reply message ID and sequence. |
| Candidate `server-no-reply` | The Hub recorded explicit completion without a message. `local-completion-missing`, `local-completion-recorded` or `local-completion-mismatch` distinguishes the local receipt; do not resend a completed delivery. This reports neither native exit nor retry permission. Earlier inspectors require an upgrade to recognize it. | The same journaled delivery has status `no_reply`, a complete-read record, null reply fields and a server cursor at least its `through_sequence`; matching local proof has `completion_status=no_reply`, no `post_receipt`, and the exact `no_reply_receipt` scope/status/cursor. |
| `server-read` | The Hub returned the complete messages but recorded neither a reply nor a terminal no_reply completion. This is not a completed turn. | The same delivery ID with status `tool_read`. |
| `unresolved` | Neither a complete read nor a reply can be tied to the journaled delivery: it is only leased or dispatched, it failed, or the Hub's latest delivery is a different one. | The detail and the missing-evidence list. |
| `stale-generation` | The Hub binding has another generation, so this journal no longer owns it. The journaled delivery's outcome stays unavailable. | The generation in `receiver-binding.json` against the Hub. |
| `disconnected` | The Hub binding is released. | Hub status and generation. |
| `unavailable` | No Hub evidence was read: offline, timeout, HTTP status, credential or TLS failure, or the binding was not listed. Only local facts are shown. | A fixed reason code. |
| `no-delivery` | The journal holds no dispatched delivery. | The local journal. |
| `scope-mismatch`, `invalid-local-state` | The journal or Hub binding belongs to another project, room or worker, or one of the validated journal files cannot be trusted. Stop and ask the administrator. | The local journal or the Hub binding. |

Limits to keep in mind:

- The status route lists only the latest delivery of the binding's current generation. An older delivery, or one from an earlier generation, is reported as missing evidence. **A Hub cursor that has passed a delivery is never treated as a reply.**
- `native-active.json` holds no process identity, and the report uses only its presence. A missing, live or dead PID would not show that the original child exited, so the report never states that a retry is safe and never claims native exit.
- A report taken while the receiver is running is a snapshot; the files can change underneath it.
- The logic is covered by fixture tests. It has not been accepted against a real interrupted native turn; record that as `not_run` until it is.

## Explicit disconnect and manual posting

Updated receipts provide `disconnect_command` (`--disconnect`). It creates STOP, waits up to 40 seconds for the receiver lock, and releases the exact owned binding generation using its current version. Completion requires a confirmed `disconnected` readback. Room pause, permissions and other workers still apply. It reads the same Windows user protected Token and never starts a model. `--stop` remains a stop request, not disconnect or proof of model cancellation.

Retry disconnect if the receiver is still stopping. An outstanding `native-active.json` or missing `receiver-binding.json` means process exit or older installation ownership is unconfirmed: preserve evidence and ask the administrator; never delete state to bypass this guard. A changed generation is not released. Use the newly pinned installer after upgrade; existing installations do not gain this feature automatically.

The command above sets ExecutionPolicy Bypass only in the child PowerShell process for the hash verified, manually reviewed installer. It does not change global policy and remains subject to Group Policy. Ask the administrator if organizational policy denies execution.
