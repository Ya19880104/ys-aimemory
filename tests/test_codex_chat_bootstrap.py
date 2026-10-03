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
    assert "$SourceRevision = '35771181eeceba4375de631859eac270504103bc'" in SOURCE
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
