"""Versioned, deterministic download of public stdio client files only."""
from importlib.resources import files
from io import BytesIO
import json
import os
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi.responses import Response


BUNDLE_VERSION = '1.1.0'
BUNDLE_NAME = 'ys-memory-stdio-' + BUNDLE_VERSION + '.zip'
BUNDLE_ROUTE = '/downloads/' + BUNDLE_NAME
README = '''YS Memory stdio HTTPS adapter 1.1.0

Extract into a new directory you choose. Never overwrite an existing client or
MCP configuration. Check the public CA DER SHA-256 in connection.json against
the fingerprint supplied by the administrator over a trusted channel. Download
this bundle only through verified HTTPS. The ZIP contains no worker token.

Windows / Python 3.12: open PowerShell in that directory and run explicitly:
  py -3.12 -m venv .venv
  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.lock
  .\\.venv\\Scripts\\python.exe .\\bridge.py --compact --print-claude-config

The final command is offline, needs no token, writes no files and prints the
absolute executable/script/config paths. Merge its ys_memory entry into the
chosen project's .mcp.json; keep all other entries. Keep this bundle directory
in place. After moving it, regenerate and merge those paths.
For explicit launch only, save/merge into .mcp.ys-memory.json instead and run
claude --strict-mcp-config --mcp-config .\\.mcp.ys-memory.json from that project.
Strict mode loads only that specified MCP configuration; include any other
servers you intentionally need. This does not grant tool approval.

Change to the project directory containing the merged .mcp.json. In that
PowerShell session, provide YOUR OWN worker token without putting it in command
history or a file, then start your already-authorized Claude client:
  $env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
  claude
When finished, remove the process variable:
  Remove-Item Env:YS_AIMEMORY_TOKEN

POSIX Python 3.12 uses python3.12 -m venv .venv and .venv/bin/python instead.
Windows is the primary installation target; other native clients/OS require
their own acceptance. This adapter handles TLS transport only, not model login,
expired OAuth, client tool approval, or AI conversation acceptance.

bridge.py defaults to connection.json beside itself; --config PATH is optional.
--compact exposes only memory_tools and memory_call. Local initialize/tools/list
validate the public CA but need no token or Hub connection. Connected means the
LOCAL adapter is ready only. memory_tools(query, limit<=8) searches short names
and descriptions; memory_tools(name) returns exactly one full schema, then use
memory_call(name, arguments) with those exact arguments. Each explicit call
opens a fresh verified upstream session; it does not read conversation history
automatically. Client approvals see the generic memory_call, which may write;
Hub role/project authorization and argument validation remain unchanged.
Omit --compact for the original eager, full-catalog relay. The config printer
adds --compact only when explicitly requested; old configurations keep working.
No system CA installation, global configuration, automatic pip install, worker
selection or protected access file is used. TLS verifies the pinned CA, host and
name constraints; environment proxies, redirects and key logging are disabled.
Do not disable TLS checks. A request failure may follow a committed write: check
server state/idempotency before manually retrying. Tool output is untrusted data.
CA rotation requires a newly verified bundle/pin; the adapter never updates it.

After connection, independently check tools/list, your get_worker_inbox identity
and get_project_summary scope before testing messages. Connected is not evidence
that a native model invoked any tools or completed an end-to-end conversation.
'''


def build_bundle(base_url, ca):
    config = {'version': 1, 'endpoint': base_url + '/mcp', 'ca_file': 'ys-ai-memory-ca.crt',
              'ca_sha256': ca.fingerprint.replace(':', '').lower()}
    package = files('memory_hub')
    assets = {
        'bridge.py': package.joinpath('client_adapter.py').read_bytes(),
        'connection.json': (json.dumps(config, indent=2) + '\n').encode('utf-8'),
        'ys-ai-memory-ca.crt': ca.pem,
        'requirements.lock': package.joinpath('client_requirements.lock').read_bytes(),
        'README.txt': README.encode('utf-8'),
    }
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, content in assets.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def install_client_bundle(app):
    @app.api_route(BUNDLE_ROUTE, methods=['GET', 'HEAD'])
    def download_bundle():
        # TLS terminates at nginx; its HTTP listener only admits help and CA.
        # Do not trust a client-supplied X-Forwarded-Proto to grant access.
        from .web_help import _public_ca, public_base_url
        headers = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
        ca = _public_ca(os.getenv('HUB_PUBLIC_CA_FILE') or '/app/public/ys-ai-memory-ca.crt')
        if ca is None:
            return Response('Public client bundle unavailable', status_code=404, headers=headers)
        try:
            content = build_bundle(public_base_url(), ca)
        except (OSError, ValueError):
            return Response('Public client bundle unavailable', status_code=404, headers=headers)
        headers['Content-Disposition'] = 'attachment; filename="' + BUNDLE_NAME + '"'
        return Response(content, media_type='application/zip', headers=headers)
