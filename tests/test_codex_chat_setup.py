"""Dedicated installer contract; no actual model, credentials or network calls."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from test_sessions import collaboration, room, post, A, B
from test_index import _migration_db

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location('codex_setup', ROOT / 'scripts/setup-codex-chat.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
PIN, ROOM, ORIGIN = '1' * 64, 'a' * 32, 'https://hub.example.test'


@pytest.fixture
def installation(tmp_path, monkeypatch):
    client_parent = tmp_path / 'private clients'
    native = tmp_path / 'codex.exe'
    native.write_bytes(b'fixture native executable')
    calls = []
    def download(origin, pin, target):
        assert (origin, pin) == (ORIGIN, PIN)
        target.mkdir()
        for name in setup.PUBLIC:
            (target / name).write_bytes(('fixture-' + name).encode())
        (target / 'connection.json').write_text(json.dumps({'version': 1,
            'endpoint': ORIGIN + '/mcp', 'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': PIN}))
        return target
    primitive = SimpleNamespace(hub_origin=lambda x: ORIGIN, ca_pin=lambda x: PIN,
        download_bundle=download, pinned_context=lambda *a: object())
    runner = SimpleNamespace(private_directory=lambda p: p.mkdir(parents=True))
    secret = SimpleNamespace(transform=lambda data: b'fixture-encrypted:' + data[::-1])
    monkeypatch.setattr(setup, 'load', lambda name, path:
        primitive if 'bundle' in name else runner if 'receiver' in name else secret)
    monkeypatch.setattr(setup, 'codex_executable', lambda *a: native)
    monkeypatch.setattr(setup, 'private_token', lambda: 'synthetic-own-codex-token')
    def identity(*args):
        assert args[2:] == ('synthetic-own-codex-token', 'project-a', ROOM, 'codex-own')
        calls.append('rest_identity')
    monkeypatch.setattr(setup, 'check_identity', identity)
    def command(args, **kwargs):
        assert 'exec' not in args and '--run' not in args
        calls.append(args)
        if 'venv' in args:
            python = Path(args[-1]) / 'Scripts/python.exe'
            python.parent.mkdir(parents=True)
            python.write_bytes(b'fixture installed Python')
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
    monkeypatch.setattr(setup.subprocess, 'run', command)
    return SimpleNamespace(parent=client_parent, native=native, calls=calls,
        install=lambda **kw: setup.install(ORIGIN, PIN, 'project-a', ROOM, 'codex-own',
            install_parent=client_parent, **kw))


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_install_provisions_only_own_client_and_generates_actual_launch_paths(installation, tmp_path):
    unrelated = tmp_path / 'existing-project'
    unrelated.mkdir()
    for name in ('.mcp.json', '.codex-config.toml', '.claude-settings.json'):
        (unrelated / name).write_text('keep me')
    receipt = installation.install(language='zh-TW', hours=2, max_turns=3)
    directory = Path(receipt['client_directory'])
    assert directory.parent == installation.parent
    assert (directory / 'worker.dpapi').read_bytes() != b'synthetic-own-codex-token'
    assert receipt['worker_id'] == 'codex-own'
    assert receipt['ttl_seconds'] == 7200 and receipt['max_turns'] == 3
    assert receipt['authorization_check'] == 'rest_identity_and_room_passed'
    assert receipt['global_config_changed'] is False and receipt['claude_config_changed'] is False
    assert not (directory / '.mcp.json').exists()
    assert not (directory / '.codex').exists()
    assert (directory / 'scripts/run-codex-chat.py').is_file()
    assert (directory / 'memory_hub/client_secret.py').is_file()
    assert setup.read_receipt(directory / 'codex-install.json') == receipt
    output = setup.receipt_output(receipt)
    assert output['native_acceptance'] == 'not_run'
    assert '--receipt ' in output['start_command'] and output['start_command'].endswith(' --run')
    assert str(directory / '.venv/Scripts/python.exe') in output['start_command']
    assert 'synthetic-own-codex-token' not in json.dumps(output)
    assert installation.calls[0] == 'rest_identity'
    assert all(p.read_text() == 'keep me' for p in unrelated.iterdir())


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_failed_identity_never_stores_worker_or_installs_dependencies(installation, monkeypatch):
    monkeypatch.setattr(setup, 'check_identity', lambda *a: (_ for _ in ()).throw(setup.SetupError('dedicated_worker_identity_mismatch')))
    with pytest.raises(setup.SetupError, match='dedicated_worker_identity_mismatch'):
        installation.install()
    assert not list(installation.parent.glob('*/worker.dpapi'))
    assert not list(installation.parent.glob('*/codex-install.json'))
    assert installation.calls == []


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_dependency_failure_preserves_private_evidence_but_never_claims_install_success(installation, monkeypatch):
    original = setup.subprocess.run
    def fail_pip(args, **kwargs):
        if 'pip' in args:
            raise subprocess.CalledProcessError(1, args, stderr=b'synthetic-private-index')
        return original(args, **kwargs)
    monkeypatch.setattr(setup.subprocess, 'run', fail_pip)
    with pytest.raises(subprocess.CalledProcessError):
        installation.install()
    assert list(installation.parent.glob('*/worker.dpapi'))
    assert not list(installation.parent.glob('*/codex-install.json'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_receipt_ownership_and_source_changes_fail_closed(installation):
    receipt = installation.install()
    directory = Path(receipt['client_directory'])
    (directory / 'scripts/run-codex-chat.py').write_text('changed')
    with pytest.raises(setup.SetupError, match='owned_codex_install_modified'):
        setup.read_receipt(directory / 'codex-install.json')
    assert not (directory / 'state').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_start_passes_dedicated_scope_and_budget_without_token_in_command(installation, monkeypatch):
    receipt = installation.install(hours=3, max_turns=4, language='zh-TW')
    calls = []
    monkeypatch.setattr(setup.subprocess, 'run', lambda args, **kw: calls.append(args) or SimpleNamespace(returncode=0))
    assert setup.start(receipt) == 0
    assert len(calls) == 1
    args = calls[0]
    assert args[args.index('--credential') + 1] == str(Path(receipt['client_directory']) / 'worker.dpapi')
    assert args[args.index('--worker') + 1] == 'codex-own'
    assert args[args.index('--session') + 1] == ROOM
    assert args[args.index('--ttl-seconds') + 1] == '10800'
    assert args[args.index('--max-turns') + 1] == '4'
    assert args[args.index('--language') + 1] == 'zh-TW'
    assert 'synthetic-own-codex-token' not in str(args)


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_print_never_runs_and_stop_never_decrypts_or_claims_cancelled(installation, monkeypatch, capsys):
    receipt = installation.install()
    path = str(Path(receipt['client_directory']) / 'codex-install.json')
    monkeypatch.setattr(setup, 'start', lambda *a: pytest.fail('Print/stop must not launch receiver'))
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--receipt', path, '--print'])
    assert setup.main() == 0
    assert json.loads(capsys.readouterr().out)['native_acceptance'] == 'not_run'
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--receipt', path, '--stop'])
    assert setup.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output['status'] == 'stop_requested' and output['running_turns_cancelled'] is False
    assert (Path(receipt['state_directory']) / 'STOP').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_explicit_run_is_required_and_saved_scope_cannot_be_changed(installation, monkeypatch, capsys):
    receipt = installation.install()
    path = str(Path(receipt['client_directory']) / 'codex-install.json')
    calls = []
    monkeypatch.setattr(setup, 'start', lambda value: calls.append(value) or 0)
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--receipt', path, '--run'])
    assert setup.main() == 0 and calls == [receipt]
    capsys.readouterr()
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--receipt', path, '--run', '--hours', '8'])
    assert setup.main() == 1 and calls == [receipt]
    assert 'receipt_scope_cannot_be_overridden' in capsys.readouterr().err


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_fresh_default_only_provisions_without_start(installation, monkeypatch, capsys):
    receipt = installation.install()
    calls = []
    monkeypatch.setattr(setup, 'install', lambda *a, **kw: calls.append((a, kw)) or receipt)
    monkeypatch.setattr(setup, 'start', lambda *a: pytest.fail('Default must not run models'))
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--url', ORIGIN, '--expected-ca', PIN,
        '--project-id', 'project-a', '--session-id', ROOM, '--worker-id', 'codex-own'])
    assert setup.main() == 0
    assert calls[0][1] == dict(codex=None, language='en', hours=1, max_turns=20, turn_timeout=90)
    assert json.loads(capsys.readouterr().out)['native_acceptance'] == 'not_run'


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI installation contract')
def test_stopped_install_does_not_silently_clear_stop_or_renew_budget(installation):
    receipt = installation.install()
    state = Path(receipt['state_directory'])
    state.mkdir()
    (state / 'STOP').touch()
    with pytest.raises(setup.SetupError, match='receiver_was_stopped'):
        setup.start(receipt)
    assert (state / 'STOP').exists()


@pytest.mark.parametrize('changes', [
    {'project_id': 'invalid space'}, {'session_id': 'wrong'}, {'worker_id': ''},
    {'worker_id': 'newline\n'}, {'hours': 0}, {'hours': 9}, {'max_turns': 0},
    {'max_turns': 101}, {'turn_timeout': 241}, {'turn_timeout': 29}, {'language': 'other'},
])
def test_invalid_scope_fails(changes):
    values = dict(project_id='p', session_id=ROOM, worker_id='codex-own', language='en',
                  hours=1, max_turns=20, turn_timeout=90)
    with pytest.raises(setup.SetupError, match='invalid_room'):
        setup.check_scope(**(values | changes))


def test_native_executable_discovery_uses_exe_not_wrapper_and_no_model(tmp_path, monkeypatch):
    path = tmp_path / 'codex.exe'
    path.write_bytes(b'fixture')
    lookup, calls = [], []
    monkeypatch.setattr(setup.shutil, 'which', lambda name: lookup.append(name) or str(path))
    def command(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=b'--ignore-user-config --ephemeral --json --sandbox --skip-git-repo-check')
    monkeypatch.setattr(setup.subprocess, 'run', command)
    assert setup.codex_executable() == path
    assert lookup == ['codex.exe']
    assert calls == [[str(path), '--version'], [str(path), 'exec', '--help']]
    with pytest.raises(setup.SetupError, match='native_codex_exe_required'):
        setup.codex_executable(path.with_suffix('.cmd'))


def test_codex_not_found_or_required_flags_missing_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(setup.shutil, 'which', lambda name: None)
    with pytest.raises(setup.SetupError, match='codex_exe_not_found'):
        setup.codex_executable()
    path = tmp_path / 'codex.exe'
    path.write_bytes(b'fixture')
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout=b'old help'))
    with pytest.raises(setup.SetupError, match='missing_required_features'):
        setup.codex_executable(path)


@pytest.mark.parametrize('fault', [None, 'wrong-worker', 'wrong-room', 'archived', 'history', '401', 'redirect'])
def test_rest_precheck_is_own_worker_and_room_only(monkeypatch, fault):
    calls = []
    class Connection:
        def __init__(self, host, port, **kwargs):
            assert (host, port) == ('hub.example.test', 443)
            assert kwargs['context'] == 'verified-context'
        def request(self, method, path, body, headers):
            assert method == 'POST' and headers['Authorization'] == 'Bearer synthetic-token'
            self.path = path
            calls.append((path, json.loads(body)))
        def getresponse(self):
            if self.path.endswith('get_worker_inbox'):
                value = {'worker_id': 'other' if fault == 'wrong-worker' else 'codex-own'}
            else:
                value = {'session': {'project_id': 'p', 'session_id': 'b'*32 if fault == 'wrong-room' else ROOM,
                    'status': 'archived' if fault == 'archived' else 'open'}, 'items': [1] if fault == 'history' else []}
            return SimpleNamespace(status=401 if fault == '401' else 302 if fault == 'redirect' else 200,
                getheader=lambda *a: 'identity', read=lambda maximum: json.dumps(value).encode())
        def close(self): pass
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Connection)
    if fault:
        with pytest.raises(setup.SetupError):
            setup.check_identity(ORIGIN, 'verified-context', 'synthetic-token', 'p', ROOM, 'codex-own')
    else:
        setup.check_identity(ORIGIN, 'verified-context', 'synthetic-token', 'p', ROOM, 'codex-own')
        assert calls[0][1] == {'arguments': {'project_id': 'p'}}
        assert calls[1][1]['arguments']['after_sequence'] == 9223372036854775807
        assert calls[1][1]['arguments']['full_text'] is False


def test_hidden_prompt_rejects_noninteractive_or_echo_fallback(monkeypatch):
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: False)
    with pytest.raises(setup.SetupError, match='interactive_terminal_required'):
        setup.private_token()
    monkeypatch.setattr(sys.stdin, 'isatty', lambda: True)
    def fallback(*args):
        import warnings
        warnings.warn('fallback', setup.getpass.GetPassWarning)
    monkeypatch.setattr(setup.getpass, 'getpass', fallback)
    with pytest.raises(setup.getpass.GetPassWarning):
        setup.private_token()


def test_preflight_reads_real_hub_metadata_without_returning_history(collaboration, monkeypatch):
    hub, _, _ = collaboration
    session = room(hub)
    post(hub, session, B, body='This history must not be read by the installer.')
    seen = []
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, method, path, body, headers):
            arguments = json.loads(body)['arguments']
            self.value = hub.call(path.rsplit('/', 1)[1], arguments, A)
            seen.append(self.value)
        def getresponse(self):
            return SimpleNamespace(status=200, getheader=lambda *a: 'identity',
                read=lambda maximum: json.dumps(self.value).encode())
        def close(self): pass
    monkeypatch.setattr(setup.http.client, 'HTTPSConnection', Connection)
    setup.check_identity(ORIGIN, object(), 'synthetic', session['project_id'], session['session_id'], A.worker_id)
    assert seen[-1]['items'] == [] and seen[-1]['session']['status'] == 'open'


def test_bad_cli_does_not_echo_secret(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--token', 'must-never-print'])
    assert setup.main() == 1
    assert 'must-never-print' not in str(capsys.readouterr())


def test_ps_command_quotes_apostrophes():
    assert setup.ps_quote("C:\\User's data") == "'C:\\User''s data'"
