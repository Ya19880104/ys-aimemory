"""Public source pins/layout and safe Windows bootstrap argument rejection."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / 'scripts/connect-codex-chat.ps1'
SOURCE = SCRIPT.read_text(encoding='utf-8')


def test_pins_cover_installer_receiver_secret_and_bundle_primitive(tmp_path):
    assert "$SourceRevision = '3b6e3aace065c67f336192c993b74757268b8b83'" in SOURCE
    entries = re.findall(r"Source = '([^']+)'; Sha256 = '([0-9a-f]{64})'", SOURCE)
    assert len(entries) == 4
    assert {name for name, _ in entries} == {'scripts/setup-codex-chat.py',
        'scripts/setup-claude.py', 'scripts/run-codex-chat.py', 'memory_hub/client_secret.py'}
    for name, digest in entries:
        body = (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(body).hexdigest() == digest
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    assert (tmp_path / 'scripts/setup-codex-chat.py').is_file()
    assert (tmp_path / 'scripts/run-codex-chat.py').parents[1] / 'memory_hub/client_secret.py' == tmp_path / 'memory_hub/client_secret.py'
    assert 'Join-Path $SetupDirectory $File.Source' in SOURCE
    assert '$Digest -ne $File.Sha256' in SOURCE
    assert '$Handler.AllowAutoRedirect = $false' in SOURCE
    assert '$Handler.UseProxy = $false' in SOURCE
    assert "else { $InstallerArguments += '--print' }" in SOURCE
    assert 'Set-ExecutionPolicy' not in SOURCE and 'Invoke-Expression' not in SOURCE


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell bootstrap')
@pytest.mark.parametrize('arguments', [
    ['-Url', 'https://user:never-print-secret@example.test'],
    ['-Url', 'https://hub.test', '-Hours', '9'],
    ['-Url', 'https://hub.test', '-MaxTurns', '0'],
    ['-Url', 'https://hub.test', '-TurnTimeout', '241'],
    ['-Url', 'https://hub.test', '-Run', '-Print'],
])
def test_invalid_input_is_rejected_before_download(tmp_path, arguments):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:
        pytest.skip('PowerShell unavailable')
    result = subprocess.run([shell, '-NoProfile', '-File', str(SCRIPT), *arguments,
        '-ExpectedCa', '1'*64, '-ProjectId', 'p', '-SessionId', 'a'*32,
        '-WorkerId', 'codex-own'], capture_output=True, timeout=20, cwd=tmp_path)
    assert result.returncode == 1
    assert b'never-print-secret' not in result.stdout + result.stderr
    assert not list(tmp_path.iterdir())



def bootstrap_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location('codex_disconnect_setup', ROOT / 'scripts/setup-codex-chat.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_receipt_exposes_distinct_disconnect_and_stop_commands():
    module = bootstrap_module()
    receipt = {'client_directory': 'C:/owned', 'python': 'C:/owned/python.exe'}
    output = module.receipt_output(receipt)
    assert output['disconnect_command'].endswith(' --disconnect')
    assert output['stop_command'].endswith(' --stop')


@pytest.mark.parametrize('action', ['--stop', '--disconnect'])
def test_lifecycle_creates_stop_before_disconnect_without_reprovision(tmp_path, monkeypatch, action):
    import sys
    module = bootstrap_module()
    receipt = {'state_directory': str(tmp_path / 'state')}
    monkeypatch.setattr(module, 'read_receipt', lambda path: receipt)
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--receipt', str(tmp_path / 'codex-install.json'), action])
    calls = []
    def start(value, *, disconnect=False):
        assert (tmp_path / 'state/STOP').exists()
        calls.append(disconnect)
        return 0
    monkeypatch.setattr(module, 'start', start)
    monkeypatch.setattr(module, 'install', lambda *a, **k: pytest.fail('Never reprovision lifecycle'))
    assert module.main() == 0
    assert calls == ([True] if action == '--disconnect' else [])


def test_disconnect_without_receipt_rejected_before_install(monkeypatch):
    import sys
    module = bootstrap_module()
    monkeypatch.setattr(sys, 'argv', ['setup-codex-chat.py', '--disconnect'])
    monkeypatch.setattr(module, 'install', lambda *a, **k: pytest.fail('No installation on disconnect'))
    assert module.main() == 1
