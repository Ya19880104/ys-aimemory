"""Provision a dedicated Windows Codex receiver without changing client settings.

Default/--print installs and prints a receipt; only --run starts model turns.
The Hub worker Token is hidden input and stored with current-user Windows DPAPI.
"""
import argparse
import getpass
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
import uuid
import warnings

PUBLIC = ('bridge.py', 'connection.json', 'ys-ai-memory-ca.crt', 'requirements.lock', 'README.txt')
SOURCES = ('scripts/setup-codex-chat.py', 'scripts/run-codex-chat.py', 'memory_hub/client_secret.py')


class SetupError(ValueError):
    """Fixed error codes only; never include supplied or remote values."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise SetupError('invalid_arguments_use_help')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plain_path(path):
    path = Path(path)
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (path, *path.parents)):
        raise SetupError('linked_path_refused')
    return path


def file_path(path, maximum=1048576):
    path = plain_path(path)
    if not path.is_file() or path.stat().st_size > maximum:
        raise SetupError('owned_file_invalid')
    return path


def file_bytes(path, maximum=1048576):
    return file_path(path, maximum).read_bytes()


def executable(path):
    path = Path(path)
    if path.suffix.lower() != '.exe' or not path.is_absolute():
        raise SetupError('native_codex_exe_required')
    file_path(path, 1024 * 1048576)
    return path.resolve(strict=True)


def npm_codex_executable():
    """Resolve the official npm shim's native optional package without running it."""
    shim = shutil.which('codex.cmd')
    if not shim:
        return None
    shim = Path(shim)
    wrapper = file_bytes(shim, 65536).decode('utf-8-sig').replace('/', '\\').lower()
    if '%dp0%\\node_modules\\@openai\\codex\\bin\\codex.js' not in wrapper:
        raise SetupError('codex_npm_wrapper_not_recognized')
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower())
    if arch is None:
        raise SetupError('codex_npm_architecture_not_supported')
    package = shim.parent / 'node_modules/@openai/codex'
    metadata = json.loads(file_bytes(package / 'package.json'))
    version = metadata.get('version', '')
    package_name = '@openai/codex-win32-' + arch
    native_version = version + '-win32-' + arch if isinstance(version, str) else ''
    repository = 'git+https://github.com/openai/codex.git'
    if (metadata.get('name') != '@openai/codex'
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?', version)
            or metadata.get('bin') != {'codex': 'bin/codex.js'}
            or metadata.get('repository', {}).get('url') != repository
            or metadata.get('optionalDependencies', {}).get(package_name) != 'npm:@openai/codex@' + native_version):
        raise SetupError('codex_npm_metadata_invalid')
    # These are the two standard Node resolution locations, bounded to this shim.
    # No recursive App-directory search, shell invocation or provider config read.
    candidates = [package / 'node_modules' / package_name,
                  shim.parent / 'node_modules' / package_name]
    triple = 'x86_64-pc-windows-msvc' if arch == 'x64' else 'aarch64-pc-windows-msvc'
    for native in candidates:
        if not (native / 'package.json').exists():
            continue
        info = json.loads(file_bytes(native / 'package.json'))
        if (info.get('name') != '@openai/codex' or info.get('version') != native_version
                or info.get('os') != ['win32'] or info.get('cpu') != [arch]
                or 'vendor' not in info.get('files', [])
                or info.get('repository', {}).get('url') != repository):
            raise SetupError('codex_npm_native_metadata_invalid')
        return executable(native / 'vendor' / triple / 'bin/codex.exe')
    raise SetupError('codex_npm_native_package_missing_reinstall_official_cli')


def codex_executable(explicit=None):
    found = explicit or shutil.which('codex.exe') or npm_codex_executable()
    if not found:
        raise SetupError('codex_exe_not_found_install_official_cli_or_use_codex_option')
    path = executable(found)
    for args in ([str(path), '--version'], [str(path), 'exec', '--help']):
        result = subprocess.run(args, capture_output=True, check=True, timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if len(result.stdout) > 131072:
            raise SetupError('codex_preflight_output_invalid')
        if args[-1] == '--help' and any(flag not in result.stdout for flag in
                (b'--ignore-user-config', b'--ephemeral', b'--json', b'--sandbox', b'--skip-git-repo-check')):
            raise SetupError('codex_cli_missing_required_features')
    return path


def check_scope(project_id, session_id, worker_id, language, hours, max_turns, turn_timeout):
    if (not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', project_id or '')
            or not re.fullmatch(r'[0-9a-f]{32}', session_id or '')
            or not worker_id or len(worker_id) > 128 or not worker_id.strip()
            or any(ord(c) < 32 for c in worker_id)
            or language not in ('en', 'zh-TW') or not 1 <= hours <= 8
            or not 1 <= max_turns <= 100 or not 30 <= turn_timeout <= 240):
        raise SetupError('invalid_room_worker_language_or_budget')


def private_token():
    if not sys.stdin.isatty():
        raise SetupError('interactive_terminal_required_for_private_token_prompt')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        token = getpass.getpass('Your dedicated Codex worker Token (hidden): ')
    if not token or len(token) > 4096 or '${' in token or any(not 33 <= ord(c) <= 126 for c in token):
        raise SetupError('actual_worker_token_required')
    return token


def check_identity(origin, context, token, project_id, session_id, worker_id):
    """REST authorization check only; never report it as native MCP acceptance."""
    parsed = urlsplit(origin)
    def call(name, arguments):
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, context=context, timeout=15)
        try:
            connection.request('POST', '/v1/tools/' + name,
                body=json.dumps({'arguments': arguments}).encode(),
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                         'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
                raise SetupError('hub_authorization_check_failed')
            body = response.read(65537)
            if len(body) > 65536:
                raise SetupError('hub_authorization_response_too_large')
            value = json.loads(body)
            if not isinstance(value, dict):
                raise SetupError('hub_authorization_response_invalid')
            return value
        finally:
            connection.close()
    identity = call('get_worker_inbox', {'project_id': project_id})
    if identity.get('worker_id') != worker_id:
        raise SetupError('dedicated_worker_identity_mismatch')
    # Read room metadata without loading historical message bodies.
    room = call('read_session', {'project_id': project_id, 'session_id': session_id,
        'after_sequence': 9223372036854775807, 'limit': 1, 'max_bytes': 65536, 'full_text': False})
    session = room.get('session', {})
    if (session.get('project_id') != project_id or session.get('session_id') != session_id
            or session.get('status') != 'open' or room.get('items') != []):
        raise SetupError('room_identity_or_active_state_mismatch')


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def receipt_output(receipt):
    directory = Path(receipt['client_directory'])
    script = directory / 'scripts/setup-codex-chat.py'
    prefix = '& ' + ps_quote(receipt['python']) + ' ' + ps_quote(script) + ' --receipt ' + ps_quote(directory / 'codex-install.json')
    return {**receipt, 'receipt_path': str(directory / 'codex-install.json'),
            'start_command': prefix + ' --run', 'stop_command': prefix + ' --stop',
            'disconnect_command': prefix + ' --disconnect',
            'inspect_command': prefix + ' --print', 'native_acceptance': 'not_run'}


def install(url, expected_ca, project_id, session_id, worker_id, *, codex=None,
            language='en', hours=1, max_turns=20, turn_timeout=90, install_parent=None):
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        raise SetupError('windows_python312_required')
    check_scope(project_id, session_id, worker_id, language, hours, max_turns, turn_timeout)
    source = Path(__file__).resolve().parents[1]
    primitive = load('codex_verified_bundle_setup', source / 'scripts/setup-claude.py')
    runner = load('codex_verified_receiver_setup', source / 'scripts/run-codex-chat.py')
    origin, pin = primitive.hub_origin(url), primitive.ca_pin(expected_ca)
    native = codex_executable(codex)
    parent = Path(install_parent or (Path(os.environ['LOCALAPPDATA']) / 'YS-AIMemory/codex-clients'))
    directory = parent / ('codex-' + uuid.uuid4().hex)
    plain_path(directory)
    if directory.exists():
        raise SetupError('new_installation_directory_required')
    runner.private_directory(directory)
    directory = directory.resolve(strict=True)
    bundle = primitive.download_bundle(origin, pin, directory / 'verified-bundle')
    for name in PUBLIC:
        (directory / name).write_bytes(file_bytes(bundle / name))
    for name in SOURCES:
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_bytes(source / name))
    context = primitive.pinned_context(file_bytes(directory / 'ys-ai-memory-ca.crt'), pin)
    token = private_token()
    try:
        check_identity(origin, context, token, project_id, session_id, worker_id)
        secret = load('codex_verified_private_secret', source / 'memory_hub/client_secret.py')
        protected = secret.transform(token.encode('ascii'))
    finally:
        token = None
    (directory / 'worker.dpapi').write_bytes(protected)
    subprocess.run([sys.executable, '-m', 'venv', str(directory / '.venv')],
                   capture_output=True, check=True, timeout=120)
    python = directory / '.venv/Scripts/python.exe'
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-q',
                    '-r', str(directory / 'requirements.lock')], capture_output=True, check=True,
                   timeout=300, cwd=directory)
    # Offline dependency/CA check, with no model, credential or Hub write.
    subprocess.run([str(python), str(directory / 'bridge.py'), '--compact', '--print-claude-config'],
                   capture_output=True, check=True, timeout=30, cwd=directory)
    receipt = {'kind': 'ys-memory-dedicated-codex', 'version': 1,
        'status': 'installed_not_native_verified', 'client_directory': str(directory),
        'python': str(python), 'codex': str(native), 'origin': origin, 'ca_sha256': pin,
        'project_id': project_id, 'session_id': session_id, 'worker_id': worker_id,
        'language': language, 'ttl_seconds': hours * 3600, 'max_turns': max_turns,
        'turn_timeout': turn_timeout, 'state_directory': str(directory / 'state'),
        'token_storage': 'Windows current-user DPAPI', 'authorization_check': 'rest_identity_and_room_passed',
        'global_config_changed': False, 'claude_config_changed': False,
        'desktop_chat_injected': False,
        'files': {name: hashlib.sha256(file_bytes(directory / name)).hexdigest() for name in (*PUBLIC, *SOURCES)}}
    (directory / 'codex-install.json').write_text(json.dumps(receipt, ensure_ascii=True, indent=2), encoding='utf-8')
    return receipt


def read_receipt(path):
    path = Path(path)
    receipt = json.loads(file_bytes(path))
    directory = path.resolve(strict=True).parent
    if (path.name != 'codex-install.json' or receipt.get('kind') != 'ys-memory-dedicated-codex'
            or type(receipt.get('version')) is not int or receipt['version'] != 1
            or receipt.get('status') != 'installed_not_native_verified'
            or receipt.get('client_directory') != str(directory)
            or receipt.get('python') != str(directory / '.venv/Scripts/python.exe')
            or receipt.get('state_directory') != str(directory / 'state')
            or receipt.get('global_config_changed') is not False
            or receipt.get('claude_config_changed') is not False
            or set(receipt.get('files', {})) != set(PUBLIC) | set(SOURCES)):
        raise SetupError('owned_codex_receipt_invalid')
    check_scope(receipt['project_id'], receipt['session_id'], receipt['worker_id'], receipt['language'],
                receipt['ttl_seconds'] / 3600, receipt['max_turns'], receipt['turn_timeout'])
    for name, digest in receipt['files'].items():
        if hashlib.sha256(file_bytes(directory / name)).hexdigest() != digest:
            raise SetupError('owned_codex_install_modified')
    if not re.fullmatch('[0-9a-f]{64}', receipt['ca_sha256']):
        raise SetupError('owned_ca_pin_invalid')
    config = json.loads(file_bytes(directory / 'connection.json'))
    if config != {'version': 1, 'endpoint': receipt['origin'] + '/mcp',
                  'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': receipt['ca_sha256']}:
        raise SetupError('owned_hub_configuration_mismatch')
    return receipt


def start(receipt, *, disconnect=False):
    directory = Path(receipt['client_directory'])
    codex = codex_executable(receipt['codex'])
    file_path(Path(receipt['python']), 20 * 1048576)
    credential = directory / 'worker.dpapi'
    if credential.is_symlink() or not credential.is_file() or not 0 < credential.stat().st_size <= 16384:
        raise SetupError('owned_credential_missing')
    if not disconnect and (plain_path(receipt['state_directory']) / 'STOP').exists():
        raise SetupError('receiver_was_stopped_keep_evidence_and_provision_new_bounded_run')
    command = [receipt['python'], '-B', str(directory / 'scripts/run-codex-chat.py'),
        '--client-dir', str(directory), '--credential', str(credential),
        '--expected-ca', receipt['ca_sha256'], '--project', receipt['project_id'],
        '--session', receipt['session_id'], '--worker', receipt['worker_id'],
        '--state-dir', receipt['state_directory'], '--codex', str(codex), '--python', receipt['python'],
        '--ttl-seconds', str(receipt['ttl_seconds']), '--max-turns', str(receipt['max_turns']),
        '--turn-timeout', str(receipt['turn_timeout']), '--language', receipt['language']]
    if disconnect:
        command.append('--disconnect')
    return subprocess.run(command, cwd=directory, check=False).returncode


def main():
    parser = Parser(description=__doc__)
    parser.add_argument('--receipt', type=Path, help='Inspect/start/stop an existing owned install')
    parser.add_argument('--url')
    parser.add_argument('--expected-ca')
    parser.add_argument('--project-id')
    parser.add_argument('--session-id')
    parser.add_argument('--worker-id')
    parser.add_argument('--codex', type=Path, help='Optional actual codex.exe; otherwise resolved from PATH')
    parser.add_argument('--language', choices=('en', 'zh-TW'), help='Default: en')
    parser.add_argument('--hours', type=int, help='1-8 hours; default: 1')
    parser.add_argument('--max-turns', type=int, help='1-100 starts; default: 20')
    parser.add_argument('--turn-timeout', type=int, help='30-240 seconds; default: 90')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--print', action='store_true', dest='print_only', help='Provision/inspect only (default), no model')
    action.add_argument('--run', action='store_true', help='Explicitly start the bounded dedicated receiver')
    action.add_argument('--disconnect', action='store_true', help='Stop then release the exact owned binding; needs the protected Token')
    action.add_argument('--stop', action='store_true', help='Request stop via an existing receipt; does not read Token')
    try:
        args = parser.parse_args()
        if args.receipt:
            if any(value is not None for value in (args.url, args.expected_ca, args.project_id,
                    args.session_id, args.worker_id, args.codex, args.language, args.hours,
                    args.max_turns, args.turn_timeout)):
                raise SetupError('receipt_scope_cannot_be_overridden')
            receipt = read_receipt(args.receipt)
        else:
            if args.stop or args.disconnect or not all((args.url, args.expected_ca, args.project_id, args.session_id, args.worker_id)):
                raise SetupError('required_installation_arguments_missing')
            receipt = install(args.url, args.expected_ca, args.project_id, args.session_id, args.worker_id,
                codex=args.codex, language=args.language or 'en', hours=1 if args.hours is None else args.hours,
                max_turns=20 if args.max_turns is None else args.max_turns,
                turn_timeout=90 if args.turn_timeout is None else args.turn_timeout)
        if args.stop or args.disconnect:
            state = plain_path(receipt['state_directory'])
            state.mkdir(exist_ok=True)
            plain_path(state / 'STOP').touch(exist_ok=True)
            if args.disconnect:
                return start(receipt, disconnect=True)
            print(json.dumps({'status': 'stop_requested', 'stop_file': str(state / 'STOP'),
                              'running_turns_cancelled': False}))
            return 0
        print(json.dumps(receipt_output(receipt), ensure_ascii=True, indent=2), flush=True)
        return start(receipt) if args.run else 0
    except Exception as exc:
        code = str(exc) if isinstance(exc, SetupError) else type(exc).__name__
        print('codex_setup_failed: ' + code, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
