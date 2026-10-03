import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('claude_setup', Path(__file__).parents[1] / 'scripts/setup-claude.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_setup_preserves_unrelated_servers_and_refuses_existing_memory_server():
    original = {'mcpServers': {'other': {'command':'existing', 'env':{'EXAMPLE':'synthetic'}}}, 'custom':True}
    result = json.loads(setup.merged_config(json.dumps(original).encode(), {'command':'new'}))
    assert result['mcpServers']['other'] == original['mcpServers']['other'] and result['custom'] is True
    with pytest.raises(ValueError, match='already exists'):
        setup.merged_config(json.dumps(result).encode(), {'command':'replacement'})


@pytest.mark.skipif(os.name != 'nt', reason='Windows current-user DPAPI')
def test_dpapi_roundtrip_and_corrupted_ciphertext_rejected():
    from memory_hub.client_secret import transform
    token = b'fixture-worker-value-not-a-real-token'
    encrypted = transform(token)
    assert token not in encrypted and transform(encrypted, decrypt=True) == token
    with pytest.raises(RuntimeError, match='protection failed'):
        transform(b'invalid cipher', decrypt=True)


def test_setup_rejects_malformed_shared_configuration():
    for raw in (b'[]', b'{"mcpServers": []}', b'{invalid'):
        with pytest.raises((ValueError, TypeError)):
            setup.merged_config(raw, {'command':'new'})


def test_cli_does_not_echo_secret_exception_or_token(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['setup-claude.py', '--bundle', '.', '--project', '.', '--expected-ca', '0' * 64])
    monkeypatch.setenv('YS_AIMEMORY_SETUP_TOKEN', 'synthetic-input-never-print')

    def fail(*args):
        raise RuntimeError('synthetic-private-package-index-value')

    monkeypatch.setattr(setup, 'install', fail)
    assert setup.main() == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err == 'setup_failed: RuntimeError\n'
    assert 'YS_AIMEMORY_SETUP_TOKEN' not in os.environ


@pytest.mark.skipif(os.name != 'nt', reason='Windows installer and DPAPI')
@pytest.mark.parametrize('scenario', ['success', 'concurrent_edit', 'dependency_failure'])
def test_install_preserves_config_and_keeps_secrets_out_of_shared_files(tmp_path, monkeypatch, scenario):
    from memory_hub.client_secret import transform
    project, bundle, clients = (tmp_path / name for name in ('project', 'bundle', 'clients'))
    project.mkdir()
    bundle.mkdir()
    original = b'{"mcpServers":{"unrelated":{"env":{"EXAMPLE":"synthetic-backup-value"}}}}'
    target = project / '.mcp.json'
    target.write_bytes(original)
    for name in setup.ASSETS:
        (bundle / name).write_text('{}', encoding='utf-8')
    pin = '1' * 64
    (bundle / 'connection.json').write_text(json.dumps({'ca_sha256':pin}), encoding='utf-8')
    changed = b'{"mcpServers":{"changed_by_user":{}}}'

    def subprocess_fixture(args, **kwargs):
        if 'pip' in args and scenario == 'dependency_failure':
            raise subprocess.CalledProcessError(1, args, stderr=b'synthetic-private-index')
        if '--print-claude-config' in args:
            directory = Path(kwargs['cwd'])
            if scenario == 'concurrent_edit':
                target.write_bytes(changed)
            return SimpleNamespace(stdout=json.dumps({'mcpServers':{'ys_memory':{
                'command': str(directory / '.venv/Scripts/python.exe'),
                'args': ['-B', str(directory / 'bridge.py'), '--compact'],
                'env': {'YS_AIMEMORY_TOKEN': '${YS_AIMEMORY_TOKEN:-}'}}}}).encode())
        return SimpleNamespace(stdout=b'')

    monkeypatch.setattr(setup.subprocess, 'run', subprocess_fixture)
    if scenario != 'success':
        with pytest.raises((setup.SetupError, subprocess.CalledProcessError)):
            setup.install(bundle, project, pin, 'synthetic-worker-value', install_parent=clients)
        assert target.read_bytes() == (changed if scenario == 'concurrent_edit' else original)
        return
    receipt = setup.install(bundle, project, pin, 'synthetic-worker-value', install_parent=clients)
    installed = Path(receipt['client_directory'])
    config = json.loads(target.read_bytes())
    assert config['mcpServers']['unrelated'] == json.loads(original)['mcpServers']['unrelated']
    assert 'env' not in config['mcpServers']['ys_memory']
    assert config['mcpServers']['ys_memory']['args'][1] == str(installed / 'launcher.py')
    assert transform((installed / 'worker.dpapi').read_bytes(), decrypt=True) == b'synthetic-worker-value'
    assert transform((installed / 'previous-mcp.dpapi').read_bytes(), decrypt=True) == original
    assert b'synthetic-worker-value' not in target.read_bytes()
    assert b'synthetic-backup-value' not in (installed / 'previous-mcp.dpapi').read_bytes()
