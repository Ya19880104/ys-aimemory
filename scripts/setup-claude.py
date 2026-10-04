"""Windows project setup from a pinned Hub URL or verified public bundle.

No Claude login, global configuration, tool approvals, CA installation or hooks
are modified. A new versioned install is retained if setup fails for diagnosis.
"""
import argparse
import getpass
import hashlib
import http.client
import importlib.util
from io import BytesIO
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import ssl
import sys
import tempfile
from urllib.parse import urlsplit
import uuid
from zipfile import ZipFile, BadZipFile

ASSETS = {'bridge.py', 'connection.json', 'ys-ai-memory-ca.crt', 'requirements.lock', 'README.txt'}
BUNDLE_ROUTE = '/downloads/ys-memory-stdio-1.1.1.zip'
CA_ROUTE = '/downloads/ys-ai-memory-ca.crt'
MAX_ASSET = 1024 * 1024
MAX_BUNDLE = 5 * MAX_ASSET
PEM = re.compile(rb'-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----')
DNS = re.compile(r'(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?')


class SetupError(ValueError):
    """Only fixed, non-secret guidance may be included in these messages."""


def run_install_stage(stage, command, **kwargs):
    """Propagate subprocess failure without exposing captured output or argv."""
    try:
        return subprocess.run(command, check=True, capture_output=True, **kwargs)
    except subprocess.CalledProcessError as exc:
        output = exc.stderr or b''
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        output = output.lower()
        reason = 'unknown'
        for category, markers in (
            ('tls', ('certificate verify failed', 'certificate_verify_failed', 'sslerror')),
            ('no_distribution', ('no matching distribution found', 'could not find a version that satisfies')),
            ('access_denied', ('permission denied', 'access is denied', 'access denied', 'winerror 5')),
            ('network', ('connection refused', 'connection reset', 'connection timed out',
                         'read timed out', 'name resolution', 'network is unreachable', 'proxyerror')),
        ):
            if any(marker in output for marker in markers):
                reason = category
                break
        raise SetupError(f'installer_stage={stage} exit_code={int(exc.returncode)} reason={reason}') from None
    except OSError as exc:
        reason = 'access_denied' if isinstance(exc, PermissionError) else 'unknown'
        raise SetupError(f'installer_stage={stage} exit_code=not_started reason={reason}') from None


class SetupParser(argparse.ArgumentParser):
    def error(self, message):
        # A mistakenly supplied Token/URL must not be reflected into stderr.
        raise SetupError('Invalid setup arguments; use --help for the supported options')


def ca_pin(value: str) -> str:
    value = value.replace(':', '').lower()
    if not re.fullmatch('[0-9a-f]{64}', value):
        raise SetupError('A trusted CA DER SHA-256 fingerprint is required')
    return value


def hub_origin(value: str) -> str:
    if any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise SetupError('Use a plain HTTPS Hub URL without credentials, query or fragment')
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.path not in ('', '/')
                or '?' in value or '#' in value or (port is not None and not 1 <= port <= 65535)):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
            host = '[' + str(address) + ']' if address.version == 6 else str(address)
        except ValueError:
            if not DNS.fullmatch(host):
                raise ValueError()
            host = host.lower()
        authority = host + (':' + str(port) if port is not None else '')
        if parsed.netloc.lower() != authority.lower():
            raise ValueError()
        return 'https://' + authority
    except (ValueError, TypeError):
        raise SetupError('Use a plain HTTPS Hub URL without credentials, query or fragment') from None


def download(url: str, *, context=None, maximum: int) -> bytes:
    """Direct bounded request: no environment proxies, credentials or redirects."""
    parsed = urlsplit(url)
    if parsed.scheme == 'https' and context is not None:
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                                 context=context, timeout=15)
    elif parsed.scheme == 'http' and parsed.path == CA_ROUTE and context is None:
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=15)
    else:
        raise SetupError('Unsupported download transport')
    try:
        connection.request('GET', parsed.path, headers={'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
            raise SetupError('Public download unavailable; redirects are not accepted')
        length = response.getheader('Content-Length')
        if length is not None and (not length.isdecimal() or int(length) > maximum):
            raise SetupError('Public download exceeds the allowed size')
        content = response.read(maximum + 1)
        if len(content) > maximum or (length is not None and len(content) != int(length)):
            raise SetupError('Public download size is invalid')
        return content
    finally:
        connection.close()


def pinned_context(pem: bytes, expected_ca: str) -> ssl.SSLContext:
    if len(pem) > 65536 or not PEM.fullmatch(pem.strip()):
        raise SetupError('Public CA format invalid')
    try:
        text = pem.decode('ascii')
        actual = hashlib.sha256(ssl.PEM_cert_to_DER_cert(text)).hexdigest()
        if actual != ca_pin(expected_ca):
            raise SetupError('Downloaded CA differs from the trusted fingerprint; stop and verify the source')
        # Do not use create_default_context: it can honor SSLKEYLOGFILE.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=text)
        context.verify_flags |= ssl.VERIFY_X509_STRICT
        if (context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname
                or context.keylog_filename is not None or len(context.get_ca_certs()) != 1):
            raise SetupError('Strict TLS verification unavailable')
        return context
    except SetupError:
        raise
    except (ValueError, UnicodeError, ssl.SSLError):
        raise SetupError('Public CA cannot establish verified HTTPS') from None


def download_bundle(url: str, expected_ca: str, destination: Path) -> Path:
    origin, pin = hub_origin(url), ca_pin(expected_ca)
    parsed = urlsplit(origin)
    host = '[' + parsed.hostname + ']' if ':' in parsed.hostname else parsed.hostname
    # The only plaintext fetch is a PUBLIC certificate from the Hub's existing
    # HTTP CA endpoint. Authenticate its exact DER with an independent pin BEFORE
    # trusting it; no credentials or executable bytes travel over HTTP.
    pem = download('http://' + host + CA_ROUTE, maximum=65536)
    context = pinned_context(pem, pin)
    content = download(origin + BUNDLE_ROUTE, context=context, maximum=MAX_BUNDLE)
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) != len(ASSETS) or {item.filename for item in infos} != ASSETS:
                raise SetupError('Unexpected public bundle files')
            if any(item.file_size > MAX_ASSET or item.flag_bits & 1
                   or (item.external_attr >> 16) & 0o170000 == 0o120000 for item in infos):
                raise SetupError('Unsafe public bundle member')
            assets = {name: archive.read(name) for name in ASSETS}
    except (BadZipFile, RuntimeError, NotImplementedError):
        raise SetupError('Invalid public bundle archive') from None
    config = json.loads(assets['connection.json'])
    if (config != {'version': 1, 'endpoint': origin + '/mcp',
                   'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': pin}
            or type(config.get('version')) is not int):
        raise SetupError('Bundle connection differs from the requested Hub')
    pinned_context(assets['ys-ai-memory-ca.crt'], pin)
    # Validate all bytes before touching the destination, never extract paths.
    destination.mkdir(exist_ok=False)
    for name, body in assets.items():
        (destination / name).write_bytes(body)
    return destination


def merged_config(raw: bytes | None, entry: dict) -> bytes:
    config = json.loads(raw.decode('utf-8-sig')) if raw else {}
    if not isinstance(config, dict) or not isinstance(config.get('mcpServers', {}), dict):
        raise SetupError('Invalid existing MCP configuration; repair the JSON before setup')
    servers = config.setdefault('mcpServers', {})
    if 'ys_memory' in servers:
        raise SetupError('ys_memory already exists; review it instead of overwriting')
    servers['ys_memory'] = entry
    return (json.dumps(config, ensure_ascii=True, indent=2) + '\n').encode()


def install(bundle: Path, project: Path, expected_ca: str, token: str, *, install_parent=None):
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        raise SetupError('Run on Windows with Python 3.12')
    bundle, project = bundle.resolve(strict=True), project.resolve(strict=True)
    if not bundle.is_dir() or not project.is_dir():
        raise SetupError('Choose existing directories')
    target = project / '.mcp.json'
    if target.is_symlink():
        raise SetupError('MCP configuration must not be a symlink')
    original = target.read_bytes() if target.exists() else None
    if original and len(original) > 1024 * 1024:
        raise SetupError('MCP configuration too large')
    merged_config(original, {})  # Validate before installation or secrets.
    if not token or len(token) > 4096 or '${' in token or any(not 33 <= ord(c) <= 126 for c in token):
        raise SetupError('Supply the actual worker Token, not an environment-variable reference')
    expected_ca = ca_pin(expected_ca)
    for name in ASSETS:
        asset = bundle / name
        if not asset.is_file() or asset.is_symlink() or asset.stat().st_size > 1024 * 1024:
            raise SetupError('Invalid public bundle asset; extract all five files into one directory')
    connection = json.loads((bundle / 'connection.json').read_text(encoding='utf-8'))
    if connection.get('ca_sha256') != expected_ca:
        raise SetupError('Bundle CA pin differs from the trusted fingerprint; stop and verify the source')
    parent = Path(install_parent or (Path(os.environ['LOCALAPPDATA']) / 'YS-AIMemory' / 'clients'))
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / ('claude-' + uuid.uuid4().hex)
    directory.mkdir()
    # Store apps may virtualize LOCALAPPDATA. Use the final physical path so
    # another desktop application can launch these same files.
    directory = directory.resolve(strict=True)
    for name in ASSETS:
        shutil.copyfile(bundle / name, directory / name)
    launcher = Path(__file__).resolve().with_name('client_secret.py')
    if not launcher.is_file():
        launcher = Path(__file__).resolve().parents[1] / 'memory_hub' / 'client_secret.py'
    shutil.copyfile(launcher, directory / 'launcher.py')
    run_install_stage('venv', [sys.executable, '-m', 'venv', str(directory / '.venv')])
    python = directory / '.venv' / 'Scripts' / 'python.exe'
    run_install_stage('dependencies', [str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-q',
                    '-r', str(directory / 'requirements.lock')], cwd=directory)
    # Verify real certificate/pin with the installed adapter before committing configuration.
    result = run_install_stage('adapter_verification',
        [str(python), str(directory / 'bridge.py'), '--compact', '--print-claude-config'], cwd=directory)
    entry = json.loads(result.stdout)['mcpServers']['ys_memory']
    entry['args'][1] = str(directory / 'launcher.py')
    entry.pop('env', None)
    candidate = merged_config(original, entry)
    spec = importlib.util.spec_from_file_location('ys_secret_setup', launcher)
    secret = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(secret)
    protected = secret.transform(token.encode('ascii'))
    (directory / 'worker.dpapi').write_bytes(protected)
    if (target.read_bytes() if target.exists() else None) != original:
        raise SetupError('MCP configuration changed during setup; leave it untouched')
    if original is not None:
        (directory / 'previous-mcp.dpapi').write_bytes(secret.transform(original))
    pending = project / ('.mcp.setup-' + uuid.uuid4().hex + '.tmp')
    try:
        with pending.open('xb') as stream:
            stream.write(candidate)
        os.replace(pending, target)
    finally:
        pending.unlink(missing_ok=True)
    receipt = {'status':'installed_not_native_verified', 'project':str(project), 'client_directory':str(directory),
               'config_sha256':hashlib.sha256(candidate).hexdigest(), 'ca_sha256':expected_ca,
               'token_storage':'Windows current-user DPAPI; no plaintext token in project configuration',
               'global_config_changed':False, 'automatic_chat_enabled':False}
    (directory / 'install-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt


def main():
    parser = SetupParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--bundle', type=Path, help='Previously verified extracted public bundle')
    source.add_argument('--url', help='HTTPS Hub base URL; its public CA must match --expected-ca')
    parser.add_argument('--project', type=Path, default=Path.cwd(), help='Claude project; defaults to current directory')
    parser.add_argument('--expected-ca', required=True)
    # Process environment is useful for an authorized installer; otherwise hidden input.
    try:
        args = parser.parse_args()
        pin = ca_pin(args.expected_ca)
        with tempfile.TemporaryDirectory(prefix='ys-memory-setup-') as temporary:
            bundle = download_bundle(args.url, pin, Path(temporary) / 'bundle') if args.url else args.bundle
            token = os.environ.pop('YS_AIMEMORY_SETUP_TOKEN', '') or getpass.getpass('Your Claude worker Token: ')
            receipt = install(bundle, args.project, pin, token)
        print(json.dumps(receipt, ensure_ascii=True, indent=2))
        print('Open a NEW local Claude Code session in this project; verify the worker through native MCP.')
        return 0
    except Exception as exc:
        guidance = str(exc) if isinstance(exc, SetupError) else type(exc).__name__
        print('setup_failed: ' + guidance, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
