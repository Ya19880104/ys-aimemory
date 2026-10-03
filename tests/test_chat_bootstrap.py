"""Pinned bootstrap layout and fail-closed ownership, without live credentials/models."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / 'scripts' / 'connect-chat.ps1'
SOURCE = SCRIPT.read_text(encoding='utf-8')
BODY = SOURCE.split("$Bootstrap = @'\n", 1)[1].split("\n'@", 1)[0]
bootstrap = ModuleType('reviewed_chat_bootstrap')
exec(compile(BODY, str(SCRIPT), 'exec'), bootstrap.__dict__)
PIN = '1' * 64
ORIGIN = 'https://hub.example.test'


def test_bootstrap_pins_exact_required_files_and_preserves_layout(tmp_path):
    revision = re.search(r"\$SourceRevision = '([0-9a-f]{40})'", SOURCE).group(1)
    assert revision == '3b6e3aace065c67f336192c993b74757268b8b83'
    entries = re.findall(r"Source = '([^']+)'; Sha256 = '([0-9a-f]{64})'", SOURCE)
    assert len(entries) == 5
    assert {name for name, _ in entries} == {
        'scripts/setup-chat.py', 'scripts/setup-claude.py',
        'memory_hub/client_watch.py', 'memory_hub/client_chat_bridge.py',
        'memory_hub/client_secret.py'}
    for name, expected in entries:
        body = (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(body).hexdigest() == expected
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    chat = bootstrap.load('isolated_bootstrap_layout', tmp_path / 'scripts/setup-chat.py')
    # Existing configure() resolves both copied helpers relative to __file__.
    source_root = Path(chat.__file__).resolve().parents[1]
    assert (source_root / 'memory_hub/client_watch.py').is_file()
    assert (source_root / 'memory_hub/client_chat_bridge.py').is_file()
    assert 'Join-Path $SetupDirectory $File.Source' in SOURCE
    assert '$Digest -ne $File.Sha256' in SOURCE
    assert '$Handler.AllowAutoRedirect = $false' in SOURCE
    assert '$Handler.UseProxy = $false' in SOURCE
    assert 'Set-ExecutionPolicy' not in SOURCE


@pytest.fixture
def owned(tmp_path):
    project = tmp_path / 'project with spaces'
    project.mkdir()
    client = tmp_path / 'owned client'
    client.mkdir()
    source = tmp_path / 'source'
    (source / 'memory_hub').mkdir(parents=True)
    launcher = (ROOT / 'memory_hub/client_secret.py').read_bytes()
    (source / 'memory_hub/client_secret.py').write_bytes(launcher)
    (client / 'launcher.py').write_bytes(launcher)
    (client / 'worker.dpapi').write_bytes(b'synthetic-encrypted-fixture')
    python = client / '.venv/Scripts/python.exe'
    python.parent.mkdir(parents=True)
    python.write_bytes(b'synthetic-owned-environment')
    entry = {'command': str(python), 'args': ['-B', str(client / 'launcher.py'),
        '--config', str(client / 'connection.json'), '--compact']}
    original = json.dumps({'mcpServers': {'ys_memory': entry,
        'unrelated': {'command': 'preserve'}}}).encode()
    (project / '.mcp.json').write_bytes(original)
    receipt = {'status': 'installed_not_native_verified', 'project': str(project),
        'client_directory': str(client), 'config_sha256': hashlib.sha256(original).hexdigest(),
        'ca_sha256': PIN, 'global_config_changed': False}
    (client / 'install-receipt.json').write_text(json.dumps(receipt))
    (client / 'connection.json').write_text(json.dumps({'version': 1,
        'endpoint': ORIGIN + '/mcp', 'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': PIN}))
    for name in ('bridge.py', 'ys-ai-memory-ca.crt', 'requirements.lock'):
        (client / name).write_bytes(('synthetic-' + name).encode())
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    for name in ('bridge.py', 'connection.json', 'ys-ai-memory-ca.crt', 'requirements.lock'):
        shutil.copyfile(client / name, bundle / name)
    return SimpleNamespace(project=project.resolve(), client=client.resolve(), source=source,
                           bundle=bundle, original=original, receipt=receipt)


def test_owned_install_reuses_only_verified_public_evidence_without_reading_token(owned, monkeypatch):
    original = Path.read_bytes

    def no_secret_read(path):
        assert path.name != 'worker.dpapi'
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', no_secret_read)
    assert bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN) == owned.client
    bootstrap.verify_bundle(owned.client, owned.bundle)
    assert (owned.project / '.mcp.json').read_bytes() == owned.original


@pytest.mark.parametrize('change', ['unowned', 'config_hash', 'project', 'client_directory',
    'ca', 'origin', 'launcher', 'extra_env', 'chat_bound', 'receipt', 'token_missing', 'bridge', 'lock'])
def test_changed_or_unowned_configuration_is_preserved(owned, change):
    receipt = owned.receipt.copy()
    if change == 'unowned':
        (owned.project / '.mcp.json').write_text('{"mcpServers":{"ys_memory":{"url":"https://elsewhere.test"}}}')
    elif change == 'config_hash':
        (owned.project / '.mcp.json').write_bytes(owned.original + b'\n')
    elif change in ('project', 'client_directory'):
        receipt[change] = str(owned.project / 'different')
    elif change == 'ca':
        receipt['ca_sha256'] = '2' * 64
    elif change == 'origin':
        value = json.loads((owned.client / 'connection.json').read_text())
        value['endpoint'] = 'https://different.test/mcp'
        (owned.client / 'connection.json').write_text(json.dumps(value))
    elif change == 'launcher':
        (owned.client / 'launcher.py').write_text('raise Exception("must never execute")')
    elif change == 'extra_env':
        config = json.loads(owned.original)
        config['mcpServers']['ys_memory']['env'] = {'UNRELATED': 'preserve'}
        body = json.dumps(config).encode()
        (owned.project / '.mcp.json').write_bytes(body)
        receipt['config_sha256'] = hashlib.sha256(body).hexdigest()
    elif change == 'chat_bound':
        (owned.client / 'chat-binding.json').write_text('{"session_id":"old-room"}')
    elif change == 'receipt':
        receipt['status'] = 'unknown-installer'
    elif change == 'token_missing':
        (owned.client / 'worker.dpapi').unlink()
    elif change == 'bridge':
        (owned.client / 'bridge.py').write_bytes(b'changed')
    elif change == 'lock':
        (owned.client / 'requirements.lock').write_bytes(b'changed')
    (owned.client / 'install-receipt.json').write_text(json.dumps(receipt))
    before = (owned.project / '.mcp.json').read_bytes()
    with pytest.raises(bootstrap.BootstrapError):
        directory = bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN)
        bootstrap.verify_bundle(directory, owned.bundle)
    assert (owned.project / '.mcp.json').read_bytes() == before


def test_fresh_project_keeps_other_mcp_servers(owned):
    target = owned.project / '.mcp.json'
    target.write_text('{"mcpServers":{"other":{"command":"preserve"}}}')
    before = target.read_bytes()
    assert bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN) is None
    assert target.read_bytes() == before


@pytest.mark.parametrize('value', ['null', '[]', '{"mcpServers":[]}','{"mcpServers":{"ys_memory":null}}'])
def test_invalid_config_never_becomes_fresh_install(owned, value):
    target = owned.project / '.mcp.json'
    target.write_text(value)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN)
    assert target.read_text() == value


def test_linked_launcher_refused_before_execution(owned, monkeypatch):
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda p: p.name == 'launcher.py' or original(p))
    with pytest.raises(bootstrap.BootstrapError, match='linked_path_refused'):
        bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN)


@pytest.mark.skipif(os.name != 'nt', reason='Windows bootstrap orchestration')
def test_orchestration_reuses_owned_install_and_forwards_room_limits(owned, monkeypatch):
    calls = []
    installer = SimpleNamespace(hub_origin=lambda x: ORIGIN, ca_pin=lambda x: PIN,
        download_bundle=lambda *args: owned.bundle)
    def configure(project, project_id, session_id, **kwargs):
        calls.append((project, project_id, session_id, kwargs))
        return {'status': 'configured_waiting_for_native_hook', 'activation_prompt': 'synthetic-activation'}
    chat = SimpleNamespace(configure=configure)
    monkeypatch.setattr(bootstrap, 'load', lambda name, path: chat if 'chat_setup' in name else installer)
    monkeypatch.setattr(bootstrap.getpass, 'getpass', lambda *a: pytest.fail('Existing DPAPI should be reused'))
    receipt = bootstrap.run(owned.source, ORIGIN, PIN, owned.project, 'project-a', 'a'*32, 'zh-TW', 2, 3)
    assert calls == [(owned.project, 'project-a', 'a'*32, {'language': 'zh-TW', 'hours': 2, 'max_turns': 3})]
    assert receipt['native_acceptance'] == 'not_run'
    assert receipt['lifecycle_python'] == str(owned.client / '.venv/Scripts/python.exe')
    assert json.loads((owned.source / 'chat-bootstrap-receipt.json').read_text()) == receipt


@pytest.mark.skipif(os.name != 'nt', reason='Windows bootstrap orchestration')
def test_unknown_install_fails_before_hub_network_or_token(owned, monkeypatch):
    (owned.project / '.mcp.json').write_text('{"mcpServers":{"ys_memory":{"url":"https://other.test"}}}')
    installer = SimpleNamespace(hub_origin=lambda x: ORIGIN, ca_pin=lambda x: PIN,
        download_bundle=lambda *a: pytest.fail('Unknown configuration must fail before Hub download'))
    monkeypatch.setattr(bootstrap, 'load', lambda *a: installer)
    monkeypatch.setattr(bootstrap.getpass, 'getpass', lambda *a: pytest.fail('Must not request Token'))
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.run(owned.source, ORIGIN, PIN, owned.project, 'p', 'a'*32, 'en', 8, 20)


@pytest.mark.skipif(os.name != 'nt', reason='Windows bootstrap orchestration')
def test_fresh_install_prompts_once_and_then_configures_without_token_in_receipt(owned, monkeypatch):
    (owned.project / '.mcp.json').unlink()
    calls = []
    def install(bundle, project, pin, token):
        assert (bundle, project, pin, token) == (owned.bundle, owned.project, PIN, 'synthetic-worker-token')
        calls.append('installed')
        (project / '.mcp.json').write_bytes(owned.original)
    installer = SimpleNamespace(hub_origin=lambda x: ORIGIN, ca_pin=lambda x: PIN,
        download_bundle=lambda *a: owned.bundle, install=install)
    def configure(*a, **kw):
        assert calls == ['prompted', 'installed']
        return {'status': 'configured_waiting_for_native_hook', 'activation_prompt': 'synthetic-activation'}
    chat = SimpleNamespace(configure=configure)
    monkeypatch.setattr(bootstrap, 'load', lambda name, path: chat if 'chat_setup' in name else installer)
    def hidden_prompt(*args):
        calls.append('prompted')
        return 'synthetic-worker-token'
    monkeypatch.setattr(bootstrap.getpass, 'getpass', hidden_prompt)
    monkeypatch.setattr(bootstrap.sys.stdin, 'isatty', lambda: True)
    bootstrap.run(owned.source, ORIGIN, PIN, owned.project, 'p', 'a'*32, 'en', 8, 20)
    assert 'synthetic-worker-token' not in (owned.source / 'chat-bootstrap-receipt.json').read_text()
    assert calls == ['prompted', 'installed']


@pytest.mark.skipif(os.name != 'nt', reason='Windows bootstrap orchestration')
def test_fresh_install_without_private_terminal_refuses_token_input(owned, monkeypatch):
    (owned.project / '.mcp.json').unlink()
    installer = SimpleNamespace(hub_origin=lambda x: ORIGIN, ca_pin=lambda x: PIN,
        download_bundle=lambda *a: owned.bundle)
    monkeypatch.setattr(bootstrap, 'load', lambda *a: installer)
    monkeypatch.setattr(bootstrap.sys.stdin, 'isatty', lambda: False)
    monkeypatch.setattr(bootstrap.getpass, 'getpass', lambda *a: pytest.fail('No fallback echo input'))
    with pytest.raises(bootstrap.BootstrapError, match='interactive_terminal_required'):
        bootstrap.run(owned.source, ORIGIN, PIN, owned.project, 'p', 'a'*32, 'en', 8, 20)


@pytest.mark.skipif(os.name != 'nt', reason='Windows bootstrap orchestration')
def test_concurrent_config_change_during_download_prevents_chat_setup(owned, monkeypatch):
    changed = b'{"mcpServers":{"ys_memory":{"command":"user-replaced"}}}'
    def download(*args):
        (owned.project / '.mcp.json').write_bytes(changed)
        return owned.bundle
    installer = SimpleNamespace(hub_origin=lambda x: ORIGIN, ca_pin=lambda x: PIN,
        download_bundle=download, configure=lambda *a, **kw: pytest.fail('Changed config must not be activated'))
    monkeypatch.setattr(bootstrap, 'load', lambda *a: installer)
    monkeypatch.setattr(bootstrap.getpass, 'getpass', lambda *a: pytest.fail('Must not request Token'))
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.run(owned.source, ORIGIN, PIN, owned.project, 'p', 'a'*32, 'en', 8, 20)
    assert (owned.project / '.mcp.json').read_bytes() == changed


def test_embedded_cli_arguments_keep_spaces_and_do_not_echo_exceptions(tmp_path):
    # Execute the real entrypoint argument slicing, substituting only run().
    prelude = BODY.split("if __name__ == '__main__':", 1)[0]
    main = BODY[len(prelude):]
    test_script = tmp_path / 'bootstrap_cli.py'
    test_script.write_text(prelude + '\ndef run(*args):\n    return list(args)\n' + main)
    args = ['source folder', ORIGIN, PIN, 'project folder', 'project-a', 'a'*32, 'zh-TW', '2', '3']
    result = subprocess.run([sys.executable, str(test_script), *args], capture_output=True, check=True)
    assert json.loads(result.stdout) == [*args[:7], 2, 3]
    test_script.write_text(prelude + '\ndef run(*args):\n    raise RuntimeError("secret-must-not-print")\n' + main)
    result = subprocess.run([sys.executable, str(test_script), *args], capture_output=True)
    assert result.returncode == 1
    assert b'secret-must-not-print' not in result.stdout + result.stderr
    assert result.stderr.strip() == b'chat_bootstrap_failed: RuntimeError'


@pytest.mark.skipif(os.name != 'nt', reason='PowerShell Windows entrypoint')
@pytest.mark.parametrize('arguments', [
    ['-Url', 'https://user:must-not-print@example.test'],
    ['-Url', ORIGIN, '-Hours', '9'],
    ['-Url', ORIGIN, '-MaxTurns', '0'],
    ['-Url', ORIGIN, '-Language', 'xx'],
])
def test_powershell_rejects_invalid_inputs_before_any_download(tmp_path, arguments):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:
        pytest.skip('PowerShell unavailable')
    result = subprocess.run([shell, '-NoProfile', '-File', str(SCRIPT), *arguments,
        '-ExpectedCa', PIN, '-Project', str(tmp_path), '-ProjectId', 'project-a',
        '-SessionId', 'a'*32], capture_output=True, timeout=20)
    assert result.returncode == 1
    assert b'must-not-print' not in result.stdout + result.stderr
    assert not (tmp_path / '.mcp.json').exists()


@pytest.mark.parametrize('with_type', [False, True])
def test_legitimate_disconnect_restoration_retains_exact_full_config_custody(owned, with_type):
    # The adapter-generated stdio entry is merged at installation. Disconnect
    # restores it with the same JSON serializer without losing other servers.
    config = json.loads(owned.original)
    if with_type:
        config['mcpServers']['ys_memory']['type'] = 'stdio'
    installed = (json.dumps(config, ensure_ascii=True, indent=2) + '\n').encode()
    receipt = owned.receipt | {'config_sha256': hashlib.sha256(installed).hexdigest()}
    (owned.client / 'install-receipt.json').write_text(json.dumps(receipt))
    chat_config = json.loads(installed)
    chat_config['mcpServers']['ys_memory'] = {'command': config['mcpServers']['ys_memory']['command'],
        'args': [str(owned.client / 'chat-bridge.py')]}
    # Model setup-chat.disconnect's exact entry restoration and serialization.
    chat_config['mcpServers']['ys_memory'] = config['mcpServers']['ys_memory']
    restored = (json.dumps(chat_config, ensure_ascii=True, indent=2) + '\n').encode()
    assert restored == installed
    (owned.project / '.mcp.json').write_bytes(restored)
    (owned.client / 'chat-binding.json').write_text('{"disconnected_at":100}')
    assert bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN) == owned.client
    assert (owned.project / '.mcp.json').read_bytes() == restored

    chat_config['mcpServers']['unrelated']['command'] = 'changed-by-another-owner'
    changed = (json.dumps(chat_config, ensure_ascii=True, indent=2) + '\n').encode()
    (owned.project / '.mcp.json').write_bytes(changed)
    with pytest.raises(bootstrap.BootstrapError, match='existing_mcp_ownership_verification_failed'):
        bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN)
    assert (owned.project / '.mcp.json').read_bytes() == changed


def test_owned_receipt_cannot_authorize_wrong_stdio_type(owned):
    config = json.loads(owned.original)
    config['mcpServers']['ys_memory']['type'] = 'http'
    raw = json.dumps(config).encode()
    (owned.project / '.mcp.json').write_bytes(raw)
    (owned.client / 'install-receipt.json').write_text(json.dumps(
        owned.receipt | {'config_sha256': hashlib.sha256(raw).hexdigest()}))
    with pytest.raises(bootstrap.BootstrapError, match='existing_mcp_ownership_verification_failed'):
        bootstrap.existing_install(owned.project, owned.source, ORIGIN, PIN)
    assert (owned.project / '.mcp.json').read_bytes() == raw
