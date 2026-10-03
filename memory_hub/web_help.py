"""Public onboarding and a strictly validated public CA download."""
from .i18n import tr, documentation_url, locale
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from fastapi.responses import Response

from .web import e, page
from .web_quickstart import walkthrough, install_walkthrough_images, daily_chat_guidance


CA_DOWNLOAD = "/downloads/ys-ai-memory-ca.crt"
BUNDLE_DOWNLOAD = "/downloads/ys-memory-stdio-1.1.1.zip"
MAX_CA_BYTES = 65536
_PEM_CERT = re.compile(rb"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----")
_DNS_NAME = re.compile(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def public_base_url(value=None):
    """Return a configured HTTPS authority, never a request-derived origin."""
    value = os.getenv("HUB_PUBLIC_BASE_URL", "") if value is None else value
    if value == "":
        return "https://localhost"
    error = "HUB_PUBLIC_BASE_URL must be an HTTPS authority without credentials, path, query or fragment"
    if not isinstance(value, str) or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise ValueError(error)
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or "?" in value or "#" in value
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError(error)
        try:
            address = ipaddress.ip_address(host)
            host = "[" + str(address) + "]" if address.version == 6 else str(address)
        except ValueError:
            if not _DNS_NAME.fullmatch(host):
                raise ValueError(error) from None
            host = host.lower()
        # Explicit empty ports and malformed bracket suffixes are not authorities.
        authority = host + (":" + str(port) if port is not None else "")
        if parsed.netloc.lower() != authority.lower():
            raise ValueError(error)
        return "https://" + authority
    except ValueError:
        raise ValueError(error) from None


@dataclass(frozen=True)
class PublicCA:
    pem: bytes
    fingerprint: str


def _public_ca(path):
    """A misconfigured private key, chain or leaf is never downloadable."""
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_CA_BYTES + 1)
        if len(content) > MAX_CA_BYTES or not _PEM_CERT.fullmatch(content.strip()):
            return None
        certificate = x509.load_pem_x509_certificate(content)
        if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            return None
        fingerprint = ":".join(f"{byte:02X}" for byte in certificate.fingerprint(hashes.SHA256()))
        return PublicCA(certificate.public_bytes(serialization.Encoding.PEM), fingerprint)
    except (OSError, ValueError, x509.ExtensionNotFound, x509.DuplicateExtension):
        return None


def cloud_event_help():
    guide = 'CHATGPT_PRIVATE_TUNNEL' + ('.zh-TW' if locale() == 'zh-TW' else '') + '.md'
    steps = ('cloud_event_enable', 'cloud_event_subscribe', 'cloud_event_verify', 'cloud_event_stop')
    return ('<section id="cloud-event-chat" class="panel"><h2>' + e(tr('cloud_event_heading')) +
            '</h2><p>' + e(tr('cloud_event_scope')) + '</p><ol>' +
            ''.join('<li>' + e(tr(key)) + '</li>' for key in steps) +
            '</ol><pre class="path"><code id="cloud-event-prompt">' + e(tr('cloud_event_prompt')) +
            '</code></pre><p><a id="cloud-event-guide" href="' + e(documentation_url(guide)) + '">' +
            e(tr('cloud_event_guide')) + '</a></p></section>')


def _manual(base, ca):
    codex = '[mcp_servers.ys_memory]\nurl = "' + base + '/mcp"\nbearer_token_env_var = "YS_AIMEMORY_TOKEN"'
    claude = json.dumps({"mcpServers": {"ys_memory": {"type": "http", "url": base + "/mcp",
                       "headers": {"Authorization": "Bearer ${YS_AIMEMORY_TOKEN}"}}}}, ensure_ascii=False, indent=2)
    send_example = json.dumps({"project_id": "conversation-sandbox", "recipient_worker_id": "agent-b",
                               "thread_id": "hello-20261002", "body": (tr('ui_8897f3cf3993')),
                               "idempotency_key": "a-hello-001", "reply_to_message_id": None},
                              ensure_ascii=False, indent=2)
    list_example = json.dumps({"project_id": "conversation-sandbox", "thread_id": "hello-20261002",
                               "after_sequence": 0, "limit": 20}, ensure_ascii=False, indent=2)
    ca_status = (f'''<p><a class="button" href="{CA_DOWNLOAD}{tr('ui_407a03a350b8') + '</a></p><p>' + tr('ui_ff5d555f4f71') + '</p><p class="path">'}{e(ca.fingerprint)}</p>''') if ca else (
                 ('<p class="alert">' + tr('ui_9b6acf295a57') + '</p>'))
    bundle_status = (f'''<p><a id="stdio-bundle-download" class="button" href="{e(base + BUNDLE_DOWNLOAD)}{tr('ui_92a0f8ab5674') + '</a></p>'}''') if ca else (
                    ('<p class="alert">' + tr('ui_c457642193a2') + '</p>'))
    bundle_download_command = 'curl.exe --cacert .\\ys-ai-memory-ca.crt --fail --output .\\ys-memory-stdio-1.1.1.zip "' + base + BUNDLE_DOWNLOAD + '"'
    bundle_install_command = r'''py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe .\bridge.py --compact --print-claude-config'''
    bundle_start_command = r'''$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
try { claude } finally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }'''
    fingerprint_command = r'''$pem = Get-Content .\ys-ai-memory-ca.crt -Raw
$der = [Convert]::FromBase64String(($pem -replace '-----BEGIN CERTIFICATE-----|-----END CERTIFICATE-----|\s',''))
$sha = [Security.Cryptography.SHA256]::Create()
([BitConverter]::ToString($sha.ComputeHash($der))).Replace('-', ':')
$sha.Dispose()'''
    process_command = r'''$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
$env:NODE_EXTRA_CA_CERTS = (Resolve-Path .\ys-ai-memory-ca.crt).Path
claude'''
    codex_command = r'''$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Worker token' -AsSecureString)).Password
$env:CODEX_CA_CERTIFICATE = (Resolve-Path .\ys-ai-memory-ca.crt).Path
codex'''
    return f"""{'<main class="management manual"><header><div><div class="eyebrow">' + tr('ui_b20e4d20fa45') + '</div>\n<h1>' + tr('ui_55403f156fd6') + '</h1><p class="muted">' + tr('ui_2c9b1fd3e18a') + '</p></div>\n<a class="button" href="'}{e(base)}{tr('ui_40a387f5c1ca') + '</a></header>\n<nav class="panel" aria-label="' + tr('ui_32bacd38843e') + '"><a href="#overview">' + tr('ui_87833f84e4d3') + '</a><a href="#trust">' + tr('ui_fd77300453df') + '</a><a href="#project">' + tr('ui_b757d2c55394') + '</a><a href="#clients">' + tr('ui_b2ccb4ae68ec') + '</a><a href="#sessions">' + tr('ui_8e8945207822') + '</a><a href="#results">' + tr('ui_4113fcca8121') + '</a><a href="#efficient">' + tr('ui_a8cbf8b6df1c') + '</a><a href="#memory">' + tr('ui_3c411728b9ec') + '</a><a href="#handoff">' + tr('ui_e714f2242ac1') + '</a><a href="#accounts">' + tr('ui_aea803cc9f69') + '</a><a href="#tokens">' + tr('ui_56848dca4148') + '</a><a href="#problems">' + tr('ui_f92d99c7621b') + '</a></nav>\n\n'}{daily_chat_guidance()}{walkthrough(base)}{cloud_event_help()}{'\n<section id="overview" class="panel"><h2>' + tr('ui_2d71309d7ba5') + '</h2>\n<p>' + tr('ui_5f496aceaec6') + '</p>\n<table><thead><tr><th>' + tr('ui_0c4e6cbfd54f') + '</th><th>' + tr('ui_05b36669c4ad') + '</th><th>' + tr('ui_0760dbb01fa8') + '</th></tr></thead><tbody><tr><td>' + tr('ui_e564b916b12e') + '</td><td>' + tr('ui_ed2d81ddb0ae') + '</td><td><code>project_id</code></td></tr><tr><td>' + tr('ui_932be7091ff4') + '</td><td>' + tr('ui_40506de3003b') + '</td><td><code>session_id</code>／Session</td></tr><tr><td>' + tr('ui_d36a0f127d55') + '</td><td>' + tr('ui_5d891a6bdcf0') + '</td><td><code>message_id</code>' + tr('ui_39f63c472d97') + '</td></tr><tr><td>' + tr('ui_766e98213e5d') + '</td><td>' + tr('ui_d4e7bca3a821') + '</td><td><code>artifact_id</code></td></tr></tbody></table>\n<p><strong>' + tr('ui_73f63294aa92') + '</strong>' + tr('ui_552626c1a00f') + '</p><p>' + tr('ui_3da56e027d87') + '<strong>' + tr('ui_27fbc4052a5b') + '</strong>' + tr('ui_07a979374ba1') + '</p>\n<p>' + tr('ui_0e6cc15485de') + '</p></section>\n\n<section id="trust" class="panel"><h2>' + tr('ui_6900bfa28a6d') + '</h2>\n<p>' + tr('ui_d72a926824e1') + '</p>\n'}{ca_status}{'\n<ol><li>' + tr('ui_12dc1c291361') + '</li><li>' + tr('ui_81c7954d0d28') + '<code>Get-FileHash</code>' + tr('ui_d0dc2ea7e24d') + '</li><li>' + tr('ui_cad9a569da0e') + ('</li><li>' + tr('ui_91fb7df54786'))}{e(base)}{tr('ui_a7c8de9e5e4c') + '</a>' + tr('ui_8d20a0d88604') + '</li></ol>\n<details><summary>' + tr('ui_b64f32bd7580') + '</summary><p>' + tr('ui_003ba82b72cd') + '</p><pre class="path"><code>'}{e(fingerprint_command)}{'</code></pre></details>\n<p class="alert">' + tr('ui_dce692b76aba') + '</p>\n<p>' + tr('ui_3ace6f730712') + '</p></section>\n\n<section id="project" class="panel"><h2>' + tr('ui_98d3ded7472b') + '</h2>\n<ol><li>' + tr('ui_04b9b6c9a6dc') + '</li><li>' + tr('ui_70d9794d38cc') + '<code>website-discussion</code>' + tr('ui_9565554a1495') + ('</li><li>' + tr('ui_1c05e54ee42e'))}{e(base)}{tr('ui_3a3464be03e4') + '</a>' + tr('ui_c6d58a59cb33') + '<code>codex-dev</code>' + tr('ui_4aee732a64fc') + '<code>claude-review</code>。</li><li>' + tr('ui_d74ce7c3be4f') + '</li></ol>\n<p>' + tr('ui_315c76e6df36') + '</p>\n<table><thead><tr><th>' + tr('ui_e1d9222fd0b4') + '</th><th>' + tr('ui_c8e6f9c91609') + '</th></tr></thead><tbody><tr><td>' + tr('ui_da959811b0c7') + '</td><td>' + tr('ui_3baf4f0f75a8') + '</td></tr><tr><td>AI worker Token</td><td>' + tr('ui_823fb17434ae') + '</td></tr><tr><td>' + tr('ui_cd620cfdd557') + '</td><td>' + tr('ui_41a8b911a1fa') + '</td></tr></tbody></table>\n<p>' + tr('ui_be9fd57c4ed1') + '</p></section>\n\n<section id="clients" class="panel"><h2>' + tr('ui_8ea2bd49e400') + '</h2>\n<p>' + tr('ui_83c3f7514066') + '<code>'}{e(base)}{'/mcp</code>' + tr('ui_45f5a090f76c') + '</p>\n<h3>' + tr('ui_06a30c9b2358') + '</h3>\n'}{bundle_status}{'\n<ol><li>' + tr('ui_bd53d075b796') + '<code>C:/Tools/ys-memory-client</code>' + tr('ui_211a71cbe2d2') + '</li><li>' + tr('ui_805323e5f0d5') + '</li><li>' + tr('ui_b12b7a0cdc9b') + '</li></ol>\n<pre class="path"><code id="stdio-install-example">'}{e(bundle_install_command)}{'</code></pre>\n<details><summary>' + tr('ui_f4b6e4ecdb0e') + '</summary><p>' + tr('ui_75ea65c4323f') + '</p><pre class="path"><code>'}{e(bundle_download_command)}{'</code></pre></details>\n<p>' + tr('ui_1581caff3b82') + '<code>bridge.py</code>、<code>connection.json</code>' + tr('ui_31782ab8c52e') + '<code>requirements.lock</code>' + tr('ui_c6408c8b22b2') + '<code>README.txt</code>' + tr('ui_8dcf409c760f') + '</p>\n\n<h3>' + tr('ui_a5eea3fbb37d') + '</h3>\n<p><strong>' + tr('ui_210b24e0821f') + '</strong>' + tr('ui_87e51596e233') + '</p>\n<p>' + tr('ui_58642f90a1bd') + '<strong>' + tr('ui_da5ebedc24b2') + '</strong>' + tr('ui_d39524d54274') + '</p>\n<p><strong>' + tr('ui_258eef21a9fd') + '</strong>' + tr('ui_da8ed309bcae') + '<code>.mcp.json</code>' + tr('ui_66e3e579f41e') + '<code>${YS_AIMEMORY_TOKEN:-}</code>' + tr('ui_d92e016ffbba') + '<code>.gitignore</code>' + tr('ui_bf21ac34ce51') + '</p>\n<ol><li>' + tr('ui_d8e6d744d548') + '<code>mcpServers.ys_memory</code>' + tr('ui_3b35114d6b59') + '<code>.mcp.json</code>' + tr('ui_09f4ca01680f') + '<code>${YS_AIMEMORY_TOKEN}</code>' + tr('ui_c1de889a47cf') + '</li><li>' + tr('ui_4a2c5bdfae5b') + '<code>YS_AIMEMORY_TOKEN</code>' + tr('ui_9a003904675e') + '</li><li>' + tr('ui_79821e3fb0ed') + '<strong>' + tr('ui_eae64b134022') + '</strong>' + tr('ui_93a992b74985') + '</li><li>' + tr('ui_aea4da90172d') + '</li></ol>\n<p>' + tr('ui_768ab32ea2a7') + '<code>.mcp.ys-memory.json</code>' + tr('ui_26cc08b9a1c3') + '</p>\n<p>' + tr('ui_12151664e8aa') + '<strong>' + tr('ui_715219e85b80') + '</strong>' + tr('ui_5a656f93f284') + '<code>${YS_AIMEMORY_TOKEN}</code>' + tr('ui_fcae23e4ddfc') + '<code>${YS_AIMEMORY_TOKEN:-}</code>' + tr('ui_23395bf5d0bf') + '<code>TOKEN_MISSING</code>' + tr('ui_2d1d1e7ff0a1') + '</p>\n<details><summary>' + tr('ui_b571633f19b6') + '</summary><p>' + tr('ui_4210cac14ffc') + '<code>.mcp.json</code>' + tr('ui_f61980f461dd') + '</p><pre class="path"><code>'}{e(bundle_start_command)}{'</code></pre><p>' + tr('ui_170c27cb37ee') + '</p></details>\n\n<h3>' + tr('ui_a588e154bb52') + '</h3>\n<p>' + tr('ui_2171da3a87b0') + '<code>.codex/config.toml</code>' + tr('ui_f91021117df0') + '</p>\n<pre class="path"><code>[mcp_servers.ys_memory]\nenabled = false\ncommand = \'C:/Tools/ys-memory-client/.venv/Scripts/python.exe\'\nargs = [\'-B\', \'C:/Tools/ys-memory-client/bridge.py\', \'--config\', \'C:/Tools/ys-memory-client/connection.json\', \'--compact\']\nenv_vars = [\'YS_AIMEMORY_TOKEN\']\nstartup_timeout_sec = 60</code></pre>\n<p><code>enabled=false</code>' + tr('ui_096475390cae') + '</p>\n<details><summary>' + tr('ui_dc42d118abd3') + '</summary><pre class="path"><code>$env:YS_AIMEMORY_TOKEN = [System.Net.NetworkCredential]::new(\'\', (Read-Host \'Your worker token\' -AsSecureString)).Password\ntry { codex -c \'mcp_servers.ys_memory.enabled=true\' }\nfinally { Remove-Item Env:YS_AIMEMORY_TOKEN -ErrorAction SilentlyContinue }</code></pre><p>' + tr('ui_e043ca928573') + '</p></details>\n\n<h4>' + tr('ui_43f6840b5883') + '</h4>\n<ol><li>' + tr('ui_3d545b525f22') + '<code>enabled</code>' + tr('ui_fd2c0760f043') + '<code>true</code>' + tr('ui_9de457b6d2a5') + '<code>false</code>' + tr('ui_9107bc057268') + '</li><li>' + tr('ui_b231f17270e5') + '<a href="https://learn.chatgpt.com/docs/extend/mcp?surface=app">' + tr('ui_d2411785c01e') + '</a>' + tr('ui_d3976b5a572c') + '<code>/mcp</code>' + tr('ui_0ba9094f0a69') + '</li><li><code>env_vars</code>' + tr('ui_23fb72d02e09') + '<code>YS_AIMEMORY_TOKEN</code>' + tr('ui_7b11b4443342') + '</li><li>' + tr('ui_896358e5ae1b') + '</li></ol>\n<h3>' + tr('ui_7f375f08bae2') + '</h3>\n<p>' + tr('ui_44de39ec9cd8') + '<code>memory_tools</code>' + tr('ui_c6408c8b22b2') + '<code>memory_call</code>' + tr('ui_4c4ae31dc4a3') + '<strong>' + tr('ui_e76a4eb1dfac') + '</strong></p>\n<details><summary>' + tr('ui_796d41f1ed53') + '</summary><p>' + tr('ui_6c17bffad9dc') + '<code>memory_tools</code>' + tr('ui_1998f4cbefb6') + '</p><pre class="path"><code>{"name":"get_worker_inbox"}</code></pre><p>' + tr('ui_6c9292fa914c') + '<code>memory_call</code>' + tr('ui_a3662a7a0a6b') + '<code>my-project</code>' + tr('ui_f7807da0073f') + '</p><pre class="path"><code>{"name":"get_worker_inbox","arguments":{"arguments":{"project_id":"my-project"}}}</code></pre><p>' + tr('ui_417c22e6b6ee') + '<code>{"arguments":{"project_id":"my-project"}}</code>' + tr('ui_ccb1e5a9a3ee') + '</p></details>\n<p>' + tr('ui_6edf83cd3646') + '</p>\n<details><summary>' + tr('ui_0a012bc6f4f1') + '</summary><table><thead><tr><th>' + tr('ui_157b2f926735') + '</th><th>' + tr('ui_044f3483aea4') + '</th></tr></thead><tbody><tr><td>TOKEN_MISSING</td><td>' + tr('ui_23d485229994') + '</td></tr><tr><td>AUTH_REJECTED</td><td>' + tr('ui_e8940dadcae3') + '</td></tr><tr><td>TLS_VERIFY_FAILED</td><td>' + tr('ui_9a9e640740b9') + '</td></tr><tr><td>UPSTREAM_FAILED</td><td>' + tr('ui_15db15139d2a') + '</td></tr></tbody></table><p>' + tr('ui_e4c1b0f2e337') + '</p></details>\n<h3>' + tr('ui_6900f54d62a5') + '</h3>\n<p>' + tr('ui_29fc656f0161') + '<code>.gemini/settings.json</code>' + tr('ui_a2f3407ec8cf') + '</p>\n<p>' + tr('ui_15f7e476fd60') + '</p>\n<p>' + tr('ui_7abe20477194') + ('<a href="' + documentation_url('MULTI_CLIENT_SETUP.zh-TW.md') + '">') + tr('ui_9e565a17a8e8') + '</a>' + tr('ui_c4a76f026c40') + '<a href="https://geminicli.com/docs/tools/mcp-server/">' + tr('ui_b68007e8fa76') + '</a> · <a href="https://docs.x.ai/developers/tools/remote-mcp">' + tr('ui_85cebbd89020') + '</a></p>\n<details><summary>' + tr('ui_445d562b3544') + '</summary><p>' + tr('ui_7598b8f478b4') + '</p><h4>Codex</h4><pre class="path"><code>'}{e(codex)}</code></pre><pre class="path"><code>{e(codex_command)}</code></pre><h4>Claude Code</h4><pre class="path"><code>{e(claude)}</code></pre><pre class="path"><code>{e(process_command)}{'</code></pre><p>' + tr('ui_ca00b21d1db8') + '<code>UNSUPPORTED_CONSTRAINT_TYPE</code>' + tr('ui_7648aceaff79') + '</p></details></section>\n\n<section id="sessions" class="panel"><h2>' + tr('ui_a4cd88fb68f5') + '</h2>\n<h3>' + tr('ui_de0bf03028f7') + ('</h3>\n<ol><li>' + tr('ui_91fb7df54786'))}{e(base)}{tr('ui_b78575e4a99d') + '</a>' + tr('ui_4824ec45d7de') + '</li><li>' + tr('ui_a91eab985fbf') + '</li><li>' + tr('ui_b0e7b0f391b9') + '</li><li>' + tr('ui_b2b096bfe08c') + '</li></ol>\n<p>' + tr('ui_91448a50f7a8') + '<code>list_sessions</code>' + tr('ui_52cf923a6cbf') + '<code>project_id</code>、<code>session_id</code>' + tr('ui_5cc94b14ed12') + '</p>\n<h3>' + tr('ui_8ad2eb3d74f0') + '</h3>\n<pre class="path"><code>' + tr('ui_78e474228f9c') + '</code></pre>\n<p>' + tr('ui_9a7183fcfac2') + '</p>\n<h3>' + tr('ui_b51076f90dd3') + '</h3>\n<ol><li>' + tr('ui_887a73274538') + '</li><li>' + tr('ui_e69ae475cced') + '<code>reply_to_message_id</code>。</li><li>' + tr('ui_d20b03dc938a') + '</li><li>' + tr('ui_fc244ab80fe4') + '</li></ol>\n<p>' + tr('ui_2d2990979eae') + '<strong>' + tr('ui_f7deb3d5381a') + '</strong>' + tr('ui_33b3101b17e8') + '</p>\n<p>' + tr('ui_df67adcb67be') + '<code>idempotency_key</code>' + tr('ui_dd858257bfbf') + '</p>\n<details><summary>' + tr('ui_6899cd48dbcb') + '</summary><p>' + tr('ui_08cd27bfc59c') + '</p><pre class="path"><code id="session-read-example">{\n  "name": "read_session",\n  "arguments": {"arguments": {\n    "project_id": "my-project",\n    "session_id": "0123456789abcdef0123456789abcdef",\n    "after_sequence": 0,\n    "limit": 5,\n    "max_bytes": 4096,\n    "full_text": false\n  }}\n}</code></pre></details></section>\n\n<section id="results" class="panel"><h2>' + tr('ui_1df0769630fe') + '</h2>\n<p>' + tr('ui_0369899d7dce') + '</p>\n<h3>' + tr('ui_b6d770533a5c') + '</h3>\n<ol><li>' + tr('ui_cce529d99a60') + '</li><li>' + tr('ui_0f544ab99265') + '</li><li>' + tr('ui_fa82f62eb6a9') + '</li><li>' + tr('ui_68654f6058f8') + '</li></ol>\n<p>' + tr('ui_1dfb992f311a') + '<code>create_session_artifact</code>' + tr('ui_4607f876dbd5') + '</p>\n<h3>' + tr('ui_e6e3dc07d52a') + '</h3>\n<p>' + tr('ui_477dd2e6c922') + '<strong>' + tr('ui_a1685b023eca') + '</strong>' + tr('ui_7f0e6e2cf457') + '</p>\n<p>' + tr('ui_f17fb5dfce5b') + '</p>\n<h3>' + tr('ui_8096e05b471d') + '</h3>\n<ol><li>' + tr('ui_83363673727b') + '</li><li>' + tr('ui_8077f6f676c6') + '</li><li>' + tr('ui_b9dbc0099f10') + '</li></ol></section>\n\n<section id="efficient" class="panel"><h2>' + tr('ui_483608b30878') + '</h2>\n<ol><li><strong>' + tr('ui_41b8007345d8') + '</strong>' + tr('ui_5d04e94cf752') + '</li><li><strong>' + tr('ui_a0bfdc5bcd42') + '</strong><code>memory_tools</code>' + tr('ui_c717bb3439f6') + '<code>memory_call</code>' + tr('ui_c26ce9faf150') + '</li><li><strong>' + tr('ui_f8405d54ab6d') + '</strong><code>list_sessions</code>' + tr('ui_b0ff36f3549f') + '</li><li><strong>' + tr('ui_0985cb9e8e77') + '</strong>' + tr('ui_6bf6bbd99dea') + '<code>next_after_sequence</code>' + tr('ui_7271b0132cd1') + '<code>after_sequence</code>' + tr('ui_a339a862d5cb') + '<code>has_more=true</code>' + tr('ui_40615c1098ac') + '</li><li><strong>' + tr('ui_bd734f966aa0') + '</strong>' + tr('ui_a715e48d434b') + '<code>limit=5</code>、<code>max_bytes=4096</code>' + tr('ui_8601b3d67803') + '<code>response_budget_too_small</code>' + tr('ui_e3a69f4a38a8') + '</li><li><strong>' + tr('ui_4a3c16302814') + '</strong>' + tr('ui_e14b553167e6') + '<code>after_sequence</code>、<code>limit=1</code>、<code>full_text=true</code>、<code>max_bytes=65536</code>' + tr('ui_5877ce02e1d8') + '</li></ol>\n<p>' + tr('ui_1c67973e1f22') + '</p>\n<details><summary>' + tr('ui_33c0129a8965') + '</summary><p>' + tr('ui_13913d8debdf') + '<code>.mcp.ys-memory.json</code>' + tr('ui_006dda9601bb') + '<code>.mcp.json</code>' + tr('ui_23bf0cf24805') + '<code>claude --strict-mcp-config --mcp-config ./.mcp.ys-memory.json</code>' + tr('ui_1895453b49f7') + '</p></details></section>\n\n<section id="memory" class="panel"><h2>' + tr('ui_2b575bede21c') + ('</h2>\n<p>' + tr('ui_dfc8f70bf945'))}{e(base)}{tr('ui_2c47814c055b') + '</a>' + tr('ui_294895476a85') + '</p>\n<ol><li>' + tr('ui_99d320912f27') + '</li><li>' + tr('ui_ac97c3caa9ad') + '</li><li>' + tr('ui_8425a96aba01') + '</li></ol>\n<p>' + tr('ui_f85178149c65') + '</p></section>\n\n<section id="handoff" class="panel"><h2>' + tr('ui_f078144dcb32') + '</h2>\n<p>' + tr('ui_91b056376fed') + '<code>get_worker_inbox</code>' + tr('ui_cc85633cfa59') + '</p><p class="path">' + tr('ui_7122049c0a39') + '</p>\n<p>' + tr('ui_c0582f4cb671') + '</p>\n<p>' + tr('ui_fe812566f216') + '<code>handoff_task</code>' + tr('ui_1706ad1b2dd6') + ('<code>complete_task</code>' + tr('ui_63bdf9d28c67'))}{e(base)}{tr('ui_349b0f806305') + '</a>' + tr('ui_d0e5696c4d54') + '</p></section>\n\n<section id="accounts" class="panel"><h2>' + tr('ui_94bdd083987a') + ('</h2>\n<p>' + tr('ui_24660d4d79d5'))}{e(base)}{tr('ui_82c2d6b7c657') + ('</a>' + tr('ui_0ea60de1cece'))}{e(base)}{tr('ui_d8e991e5c94e') + '</a>' + tr('ui_68581dc92b4a') + '</p>\n<p>' + tr('ui_6529c10aabd1') + '</p>\n<p>' + tr('ui_e9aca871d372') + '</p></section>\n\n<section id="tokens" class="panel"><h2>' + tr('ui_a4b35c1ad2d6') + '</h2>\n<p>' + tr('ui_c7489723aa7c') + '</p>\n<p>' + tr('ui_62463309a641') + '</p></section>\n\n<section id="messages" class="panel"><h2>' + tr('ui_173febc7cf1a') + '</h2>\n<p>' + tr('ui_b19c6191f190') + '<code>send_message</code>／<code>list_messages</code>' + tr('ui_63623f284633') + '</p>\n<details><summary>' + tr('ui_266f0b2eb186') + '</summary><p>' + tr('ui_bb2cc550d813') + '</p><pre class="path"><code id="message-send-example">'}{e(send_example)}</code></pre><pre class="path"><code id="message-list-example">{e(list_example)}{'</code></pre><p>' + tr('ui_5463552246e6') + '</p></details></section>\n\n<section id="problems" class="panel"><h2>' + tr('ui_6556e4f6a364') + '</h2>\n<table><thead><tr><th>' + tr('ui_60f2b940f33d') + '</th><th>' + tr('ui_044f3483aea4') + '</th></tr></thead><tbody>\n<tr><td>' + tr('ui_4e1a8b455d94') + '</td><td>' + tr('ui_8bc9b56b4f7d') + '</td></tr>\n<tr><td>' + tr('ui_e2473e9bd25d') + '</td><td>' + tr('ui_7e3f2da290ca') + '</td></tr>\n<tr><td>' + tr('ui_f4c4f11d85b1') + '</td><td>' + tr('ui_454dcd6e8642') + '</td></tr>\n<tr><td>' + tr('ui_2b5a2a63fb96') + '</td><td>' + tr('ui_97d2a77693ff') + '</td></tr>\n<tr><td>' + tr('ui_e7fc1d3379d5') + '</td><td>' + tr('ui_5ae4e5e77f36') + '</td></tr>\n<tr><td>' + tr('ui_930f3c0d0b33') + '</td><td>' + tr('ui_48ef5386e0af') + '</td></tr>\n<tr><td>' + tr('ui_9e7f54cb95e5') + '</td><td>' + tr('ui_faa428ea4794') + '</td></tr>\n<tr><td>' + tr('ui_6417f19d0ed3') + '</td><td>' + tr('ui_7c7a73d7be16') + '</td></tr>\n<tr><td>' + tr('ui_e76ec0336ab3') + '</td><td>' + tr('ui_815873a58642') + '</td></tr>\n<tr><td>response_budget_too_small</td><td>' + tr('ui_93bd3eca7f17') + '</td></tr>\n<tr><td>' + tr('ui_4429f8f60e8a') + '</td><td>' + tr('ui_959106944369') + '</td></tr>\n</tbody></table>\n<p>' + tr('ui_1565b08ed7e5') + '</p></section>\n\n<section class="panel"><h2>' + tr('ui_ea375332b426') + '</h2><p>' + tr('ui_7a646ac91074') + '<a href="https://code.claude.com/docs/en/desktop#shared-configuration">' + tr('ui_a84befb2221a') + '</a>、<a href="https://code.claude.com/docs/en/mcp">Claude MCP</a>、<a href="https://learn.chatgpt.com/docs/extend/mcp?surface=cli">Codex MCP</a>、<a href="https://learn.chatgpt.com/docs/auth#custom-ca-bundles">' + tr('ui_c359b7a173eb') + '</a>、<a href="https://modelcontextprotocol.io/specification/2025-11-25/basic/transports">' + tr('ui_105e1a1679e0') + '</a>。</p></section>\n<p class="foot">' + tr('ui_8fb1048e9678') + '</p></main>'}"""


def install_help(app):
    from .i18n import install_language
    install_language(app)
    base = public_base_url()
    ca_path = os.getenv("HUB_PUBLIC_CA_FILE") or "/app/public/ys-ai-memory-ca.crt"
    install_walkthrough_images(app)

    @app.api_route("/help", methods=["GET", "HEAD"], include_in_schema=False)
    def help_page():
        response = page(_manual(base, _public_ca(ca_path)), css='.manual figure{margin:20px 0}.manual img{display:block;max-width:100%;height:auto;border-radius:10px}.manual figcaption{margin-top:8px;color:#aabbca}')
        # Only this public manual displays bundled screenshots. The validated
        # configured HTTPS origin also works when opening the HTTP help page.
        response.headers['Content-Security-Policy'] += "; img-src 'self' " + base
        return response

    @app.api_route(CA_DOWNLOAD, methods=["GET", "HEAD"], include_in_schema=False)
    def download_ca():
        ca = _public_ca(ca_path)
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if ca is None:
            return Response("Public CA unavailable", status_code=404, media_type="text/plain", headers=headers)
        headers["Content-Disposition"] = 'attachment; filename="ys-ai-memory-ca.crt"'
        return Response(ca.pem, media_type="application/x-x509-ca-cert", headers=headers)
