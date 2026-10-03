# Windows Claude project installation

[English](CLAUDE_WINDOWS_SETUP.md) | [繁體中文](CLAUDE_WINDOWS_SETUP.zh-TW.md)

## Prerequisites

Windows, Python 3.12, and Claude Desktop Code → Local signed into your chosen work project. Obtain the verified Hub HTTPS origin, dedicated worker token/project grant, and public CA DER SHA-256 fingerprint through a trusted channel. This installs Hub connectivity, not Claude or model authentication.

## URL installer

After cloning, run with your own non-secret values:

```powershell
& 'C:\src\ys-aimemory\scripts\connect-claude.ps1' -Url 'https://memory.example.internal:8443' -ExpectedCa 'YOUR_64_HEX_DER_SHA256' -Project 'C:\work\my-project'
```

The script downloads two public source files at an immutable revision and verifies their SHA-256 digests. Inspect its pinned revision when reviewing upgrades. Use `-PythonPath` for an explicit existing Python 3.12 executable. It does not change execution policy, global settings, CA trust, model login, or tool permissions.

Alternatively extract the stdio bundle downloaded through verified HTTPS into a new directory:

```powershell
py -3.12 'C:\src\ys-aimemory\scripts\setup-claude.py' --bundle 'C:\Downloads\ys-memory-client' --project 'C:\work\my-project' --expected-ca 'YOUR_64_HEX_DER_SHA256'
```

Enter your token only at the hidden local prompt. Installation creates a dedicated environment and merges the project's `.mcp.json`. An existing `ys_memory` entry causes a stop for review. Other entries remain; the prior configuration is encrypted for backup. Windows-user DPAPI stores the token, decrypted by the launcher. Read the receipt's actual paths; Store processes can map local storage differently. Do not commit credentials or encrypted backups.

## Native check

`installed_not_native_verified` means configuration completed, not native acceptance. Open a new Local Code chat in exactly this project and review trust/MCP prompts:

```text
Use native YS Memory MCP. My project_id is PROJECT_ID.
Find memory_tools/memory_call, discover get_worker_inbox, then call its schema
with the original arguments wrapper. Report the returned worker_id.
Do not claim a task. If tools are absent report NOT_RUN; do not substitute a script.
```

Verify the issued identity. Create/select a Hub conversation, copy its join instructions, and ask Claude to read the newest message and write one reply. Independently confirm author/message ID/sequence in the Hub. This manual test does not enable [automatic chat](AUTOMATIC_CHAT.md).

For an existing entry review whether it already works. Missing native tools require checking project path, new chat, trust, and receipt. DPAPI requires the installing Windows user. CA errors require reverifying the pin/SAN; do not weaken TLS or add global tokens to hide project-selection errors.
