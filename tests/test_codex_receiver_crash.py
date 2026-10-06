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
                    # Job termination can race this exact held fixture cleanup.
                    if not self.api.TerminateProcess(self.handle, 1):
                        assert self.api.WaitForSingleObject(self.handle, 5000) == 0
                assert self.api.WaitForSingleObject(self.handle, 5000) == 0
            finally:
                self.api.CloseHandle(self.handle)
        else:
            try:
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


@pytest.mark.parametrize('remaining_budget', [False, True])
def test_hard_parent_crash_preserves_unknown_fence_and_never_redispatches(tmp_path, remaining_budget):
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
sys.path[:0] = json.loads(sys.argv[1])
from test_codex_chat_runner import CONFIG, DELIVERY, fault_client, runner
import httpx
root = Path(sys.argv[2])
root.joinpath('owner.json').write_text(json.dumps({'pid': __import__('os').getpid()}))
runner.command = lambda *args: [sys.executable, str(root / 'fixture_cli.py'), str(root)]
runner.environment = lambda: dict(__import__('os').environ)
with fault_client(lambda request: httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})) as client:
    runner.receiver(CONFIG | {'python': sys.executable}, client, root, now=lambda: 100)
''', encoding='utf-8')
    proc = subprocess.Popen([sys._base_executable, '-I', '-S', str(parent), json.dumps(sys.path), str(tmp_path)],
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
        assert json.loads((tmp_path / 'owner.json').read_text())['pid'] == proc.pid
        child = OwnedChild(json.loads((tmp_path / 'child.json').read_text())['pid'])
        assert child.alive()
        before = {name: (tmp_path / name).read_bytes() for name in
                  ('receiver-claim.json', 'receiver-delivery.json', 'native-active.json', 'server.json')}
        # Hard terminate only our parent, bypassing its Python finally.
        proc.kill()
        proc.wait(timeout=5)
        if os.name == 'nt':
            assert child.api.WaitForSingleObject(child.handle, 5000) == 0
        else:
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
        # Even after Windows kills the job, a crashed parent has not recorded
        # confirmed cleanup. Keep its unknown fence; server cursor is not proof.
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


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows Job Object regression')
@pytest.mark.parametrize('assignment_delay', [0, .3])
def test_native_root_exit_does_not_clear_marker_with_live_descendant(tmp_path, monkeypatch, assignment_delay):
    """An offline CLI exits after spawning a child; no model/tools/network."""
    import threading
    cli = tmp_path / 'exiting_cli.py'
    cli.write_text("""import json, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[1])
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
root.joinpath('child.json').write_text(json.dumps({'pid': child.pid}))
limit = time.monotonic() + 10
while not root.joinpath('child-held').exists():
    if time.monotonic() > limit: raise RuntimeError('fixture_handle_timeout')
    time.sleep(.01)
""", encoding='utf-8')
    children, errors = [], []
    def hold_child():
        try:
            limit = time.monotonic() + 10
            while not (tmp_path / 'child.json').exists():
                if time.monotonic() > limit: raise RuntimeError('fixture_child_timeout')
                time.sleep(.01)
            children.append(OwnedChild(json.loads((tmp_path / 'child.json').read_text())['pid']))
            (tmp_path / 'child-held').touch()
        except Exception as error:
            errors.append(error)
    observer = threading.Thread(target=hold_child, daemon=True)
    observer.start()
    assign = runner.WindowsNativeJob.assign
    def delayed_assignment(job, proc):
        # Deliberately give a venv redirector time to spawn before assignment.
        time.sleep(assignment_delay)
        assign(job, proc)
    monkeypatch.setattr(runner.WindowsNativeJob, 'assign', delayed_assignment)
    monkeypatch.setattr(runner, 'command', lambda *args: [sys.executable, str(cli), str(tmp_path)])
    monkeypatch.setattr(runner, 'environment', lambda: dict(os.environ))
    try:
        with pytest.raises(runner.ReceiverError, match='native_acceptance_incomplete'):
            runner.native_turn(CONFIG | {'python': sys.executable, 'turn_timeout': 15}, DELIVERY,
                               tmp_path, lambda: {'status': 'processing'}, lambda: False)
        observer.join(timeout=10)
        assert not errors and len(children) == 1
        marker = (tmp_path / 'native-active.json').exists()
        assert children[0].api.WaitForSingleObject(children[0].handle, 5000) == 0, (
            f'Native root exited; descendant alive; active_marker={marker}')
        assert not marker
    finally:
        observer.join(timeout=1)
        for child in children:
            child.close()


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows supervisor gate regression')
def test_parent_crash_before_job_assignment_never_starts_native(tmp_path):
    parent = tmp_path / 'unassigned_parent.py'
    parent.write_text('''import json, os, sys, time
from pathlib import Path
sys.path[:0] = json.loads(sys.argv[1])
from test_codex_chat_runner import runner
root = Path(sys.argv[2])
root.joinpath('owner.json').write_text(json.dumps({'pid': __import__('os').getpid()}))
def pending(job, proc):
    root.joinpath('supervisor.json').write_text(json.dumps({'pid': proc.pid}))
    time.sleep(30)
runner.WindowsNativeJob.assign = pending
runner.environment = lambda: dict(os.environ)
runner.launch_native([sys.executable, '-c',
    'from pathlib import Path; Path(' + repr(str(root / 'unexpected-native')) + ').touch()'],
    root, sys.executable)
''', encoding='utf8')
    proc = subprocess.Popen([sys._base_executable, '-I', '-S', str(parent), json.dumps(sys.path), str(tmp_path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    supervisor = None
    try:
        limit = time.monotonic() + 10
        while not (tmp_path / 'supervisor.json').exists():
            if proc.poll() is not None:
                pytest.fail(proc.stderr.read().decode())
            if time.monotonic() > limit:
                pytest.fail('Supervisor launch did not reach assignment gate')
            time.sleep(.01)
        assert json.loads((tmp_path / 'owner.json').read_text())['pid'] == proc.pid
        supervisor = OwnedChild(json.loads((tmp_path / 'supervisor.json').read_text())['pid'])
        time.sleep(.3)  # It can initialize but must stay behind exact GO.
        assert supervisor.alive() and not (tmp_path / 'unexpected-native').exists()
        proc.kill()
        proc.wait(timeout=5)
        assert supervisor.api.WaitForSingleObject(supervisor.handle, 5000) == 0
        assert not (tmp_path / 'unexpected-native').exists()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        proc.stderr.close()
        if supervisor is not None:
            supervisor.close()


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows isolated supervisor/receipt regression')
def test_real_offline_cli_receipt_records_only_confirmed_job_cleanup(tmp_path, monkeypatch):
    from test_codex_chat_runner import event, reading, reply
    events = [event('get_worker_inbox', {'worker_id': CONFIG['worker_id']}, 'identity'),
        event('read_session', reading(5, 'd'*32), 'read-1'),
        event('read_session', reading(6, 'e'*32, True), 'read-2', after_sequence=5),
        event('post_session_message', reply(), 'post'), {'type': 'turn.completed'}]
    (tmp_path / 'fixture-events.json').write_text(json.dumps(events))
    cli = tmp_path / 'fixture_protocol.py'
    cli.write_text('''import json, sys
from pathlib import Path
for event in json.loads(Path(sys.argv[1]).read_text()):
    print(json.dumps(event), flush=True)
''', encoding='utf8')
    monkeypatch.setattr(runner, 'command', lambda *args:
        [sys.executable, str(cli), str(tmp_path / 'fixture-events.json')])
    monkeypatch.setattr(runner, 'environment', lambda: dict(os.environ))
    result = runner.native_turn(CONFIG | {'python': sys.executable}, DELIVERY, tmp_path,
                               lambda: {'status': 'processing'}, lambda: False)
    assert result['status'] == 'passed'  # Offline protocol data only, not provider acceptance.
    assert result['native_tree_exit_verified'] is True
    assert result['native_containment'] == 'windows_job'
    assert not (tmp_path / 'native-active.json').exists()
