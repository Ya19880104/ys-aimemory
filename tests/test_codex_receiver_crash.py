"""Real fixture process crash; no provider, socket, credential or native client."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_codex_chat_runner import CONFIG, DELIVERY, fault_client, runner


class OwnedChild:
    def __init__(self, pid):
        self.pid = pid
        self.handle = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            self.api = ctypes.WinDLL('kernel32', use_last_error=True)
            self.api.OpenProcess.restype = wintypes.HANDLE
            self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.api.CloseHandle.argtypes = [wintypes.HANDLE]
            self.handle = self.api.OpenProcess(0x100000 | 1, False, pid)
            assert self.handle, 'Cannot acquire exact owned fixture process handle'

    def alive(self):
        if self.handle:
            return self.api.WaitForSingleObject(self.handle, 0) == 258
        os.kill(self.pid, 0)
        return True

    def close(self):
        if self.handle:
            try:
                if self.alive():
                    assert self.api.TerminateProcess(self.handle, 1)
                assert self.api.WaitForSingleObject(self.handle, 5000) == 0
            finally:
                self.api.CloseHandle(self.handle)
        else:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize('remaining_budget', [False, True])
def test_hard_parent_crash_preserves_live_child_and_never_redispatches(tmp_path, remaining_budget):
    assert Path(runner.__file__).resolve() == Path(__file__).resolve().parents[1] / 'scripts' / 'run-codex-chat.py'
    # Exercise both unknown committed-post outcome and an inflight attempt
    # before post with remaining budget and an expired/replacement lease.
    (tmp_path / 'remaining.json').write_text(json.dumps(remaining_budget))
    cli = tmp_path / 'fixture_cli.py'
    cli.write_text('''import json, os, sys, time
from pathlib import Path
root = Path(sys.argv[1])
remaining = json.loads(root.joinpath('remaining.json').read_text())
root.joinpath('server.json').write_text(json.dumps({'attempts': 1, 'turns': 1, 'cursor': 4 if remaining else 6, 'post_count': 0 if remaining else 1}))
root.joinpath('child.tmp').write_text(json.dumps({'pid': os.getpid()}))
root.joinpath('child.tmp').replace(root / 'child.json')
time.sleep(20)
''', encoding='utf-8')
    parent = tmp_path / 'fixture_parent.py'
    tests = Path(__file__).resolve().parent
    parent.write_text('''import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from test_codex_chat_runner import CONFIG, DELIVERY, fault_client, runner
import httpx
root = Path(sys.argv[2])
runner.command = lambda *args: [sys.executable, str(root / 'fixture_cli.py'), str(root)]
runner.environment = lambda: dict(__import__('os').environ)
with fault_client(lambda request: httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})) as client:
    runner.receiver(CONFIG, client, root, now=lambda: 100)
''', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, str(parent), str(tests), str(tmp_path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    child = None
    try:
        deadline = time.monotonic() + 10
        while not (tmp_path / 'child.json').exists():
            if proc.poll() is not None:
                pytest.fail(f'Fixture parent exited: {proc.stderr.read().decode()}')
            if time.monotonic() > deadline:
                pytest.fail('Fixture CLI did not start in 10 seconds')
            time.sleep(.02)
        child = OwnedChild(json.loads((tmp_path / 'child.json').read_text())['pid'])
        assert child.alive()
        before = {name: (tmp_path / name).read_bytes() for name in
                  ('receiver-claim.json', 'receiver-delivery.json', 'native-active.json', 'server.json')}
        # Hard terminate only our parent, bypassing its Python finally.
        proc.kill()
        proc.wait(timeout=5)
        assert child.alive()
        calls = []
        operations = []
        def committed(request):
            calls.append(json.loads(request.content))
            import httpx
            if remaining_budget:
                # Actual service contract: admitted live replay is busy. Only
                # after stale_claim can a new request receive a replacement lease.
                if len(calls) == 1:
                    return httpx.Response(409, json={'error': 'stale_claim'})
                return httpx.Response(200, json={'status': 'ready',
                    'delivery': DELIVERY | {'lease_id': 'f' * 32}})
            return httpx.Response(200, json={'status': 'budget_exhausted', 'delivery': None})
        with fault_client(committed) as client:
            original = client.post
            def recorded_post(url, **kwargs):
                operations.append(str(url).rsplit('/', 1)[-1])
                return original(url, **kwargs)
            client.post = recorded_post
            with pytest.raises(runner.ReceiverError, match='native_exit_unconfirmed_preserve_binding'):
                runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, sleep=lambda _: None)
        assert 'dispatched' not in operations
        assert calls == []
        assert all((tmp_path / name).read_bytes() == value for name, value in before.items())
        assert not list(tmp_path.glob('receipt-*.json'))
        # Even after a successful server post, an unconfirmed live child prevents
        # release; no local receipt may be invented from server cursor alone.
        (tmp_path / 'STOP').touch()
        with fault_client(committed) as client, pytest.raises(
                runner.ReceiverError, match='native_exit_unconfirmed_preserve_binding'):
            runner.disconnect(CONFIG, client, tmp_path)
        with fault_client(committed) as client:
            assert runner.receiver(CONFIG, client, tmp_path, now=lambda: 100) == {'state': 'stopped'}
        assert (tmp_path / 'STOP').exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        proc.stderr.close()
        if child is not None:
            child.close()
