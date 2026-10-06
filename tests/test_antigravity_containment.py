"""Real offline Windows fixture trees; no Hub, provider, network or credentials."""
import ctypes
import json
import os
import sys
import threading
import time

import pytest

from memory_hub import client_antigravity_receiver as receiver
from test_antigravity_receiver import rig  # noqa: F401 - shared offline Hub rig

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Real Windows Job Object regression')
LIMIT = 18  # Generous outer bound; the receiver's own CLI timeout is at most 10 s.

# Offline CLI stand-in. The grandchild inherits stdout and holds it open while
# the root exits or outlives the timeout. Each process records PID + creation.
FIXTURE = r'''import ctypes, json, os, subprocess, sys, time
from ctypes import wintypes
from pathlib import Path
root = Path.cwd()
def record(name):
    api = ctypes.WinDLL('kernel32')
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    times = [wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(api.GetCurrentProcess(), *times):
        raise SystemExit(4)
    value = {'pid': os.getpid(), 'created': times[0].dwHighDateTime << 32 | times[0].dwLowDateTime}
    root.joinpath(name + '.tmp').write_text(json.dumps(value))
    root.joinpath(name + '.tmp').replace(root / (name + '.json'))
if sys.argv[1] == 'grandchild':
    record('grandchild')
    time.sleep(60)
    raise SystemExit(0)
record('root')
mode = json.loads(root.joinpath('mode.json').read_text())
subprocess.Popen([sys.executable, sys.argv[0], 'grandchild'], stdin=subprocess.DEVNULL,
                 stdout=None, stderr=subprocess.DEVNULL)
limit = time.monotonic() + 30
while not root.joinpath('held').exists():
    if time.monotonic() > limit:
        raise SystemExit(3)
    time.sleep(.01)
if mode['root'] == 'exit':
    sys.stdout.write(mode['stdout'])
    sys.stdout.flush()
    raise SystemExit(0)
time.sleep(60)
'''


class Owned:
    """Exact fixture identity (PID plus creation time); never act on a bare PID."""
    def __init__(self, record):
        from ctypes import wintypes
        self.api = api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.restype = wintypes.HANDLE
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE
        self.handle = api.OpenProcess(0x100000 | 0x1000 | 0x1, False, record['pid'])
        times = [wintypes.FILETIME() for _ in range(4)]
        if self.handle and not (api.GetProcessTimes(self.handle, *times) and
                                times[0].dwHighDateTime << 32 | times[0].dwLowDateTime == record['created']):
            api.CloseHandle(self.handle)
            self.handle = None  # Reused PID: not ours, never touch it.

    def exited(self, milliseconds=0):
        return not self.handle or self.api.WaitForSingleObject(self.handle, milliseconds) == 0

    def close(self):
        if self.handle:
            if not self.exited():
                self.api.TerminateProcess(self.handle, 1)
                self.api.WaitForSingleObject(self.handle, 5000)
            self.api.CloseHandle(self.handle)
            self.handle = None


class Tree:
    """Writes the fixture CLI and holds its grandchild exactly before the root proceeds."""
    def __init__(self, directory, root, stdout=''):
        self.directory, self.held, self.errors, self.done = directory, [], [], threading.Event()
        for name in ('get-conversation-metadata', 'send-message'):
            (directory / name).write_text(FIXTURE, encoding='utf-8')
        (directory / 'mode.json').write_text(json.dumps({'root': root, 'stdout': stdout}))
        self.observer = threading.Thread(target=self.hold, daemon=True)
        self.observer.start()

    def hold(self):
        try:
            limit = time.monotonic() + LIMIT
            while not (self.directory / 'grandchild.json').exists():
                if self.done.is_set() or time.monotonic() > limit:
                    raise RuntimeError('fixture_grandchild_not_started')
                time.sleep(.01)
            child = Owned(json.loads((self.directory / 'grandchild.json').read_text()))
            self.held.append(child)
            if child.exited():
                raise RuntimeError('fixture_grandchild_not_held')
            (self.directory / 'held').touch()
        except Exception as error:
            self.errors.append(error)

    def survivors(self):
        return [child for child in self.held if not child.exited(2000)]

    def close(self):
        # Ends only our own exact fixture processes; this also releases a blocked base call.
        self.done.set()
        self.observer.join(LIMIT)
        for child in self.held:
            child.close()
        if (self.directory / 'root.json').exists():
            Owned(json.loads((self.directory / 'root.json').read_text())).close()


def bounded(target):
    box = {}
    def call():
        try:
            box['value'] = target()
        except BaseException as error:
            box['error'] = error
    thread = threading.Thread(target=call, daemon=True)
    thread.start()
    thread.join(LIMIT)
    return thread, box


def test_metadata_returns_after_root_exit_although_grandchild_holds_stdout(rig, monkeypatch):
    config, event, binding, client, calls, directory = rig
    config.update(admission_mode='official_host_queue', native_project_id='native-project')
    metadata = json.dumps({'response': {'conversationMetadata': {'metadata': {
        'workspaceUris': [directory.resolve().as_uri()], 'projectId': 'native-project'}}}})
    monkeypatch.chdir(directory)
    tree = Tree(directory, 'exit', metadata)
    thread = None
    try:
        thread, box = bounded(lambda: receiver.official_metadata_admission(config, sys._base_executable))
        blocked, survivors = thread.is_alive(), tree.survivors()
    finally:
        tree.close()
        if thread is not None:
            thread.join(LIMIT)
    assert not tree.errors and len(tree.held) == 1
    assert not blocked, f'metadata call still blocked after {LIMIT}s while a grandchild held stdout'
    assert not survivors, 'grandchild outlived the returned CLI call'
    assert box.get('value', {}).get('scope_verified') is True


def test_send_timeout_kills_stdout_holding_grandchild_and_journals_verified_exit(rig, monkeypatch):
    config, event, binding, client, calls, directory = rig
    monkeypatch.chdir(directory)
    clock = [110]
    tree = Tree(directory, 'hang')
    thread = None
    try:
        thread, box = bounded(lambda: receiver.run(config, client, directory, sys._base_executable,
            lambda: event, now=lambda: clock[0], sleep=lambda _: clock.__setitem__(0, 301)))
        blocked, survivors = thread.is_alive(), tree.survivors()
    finally:
        tree.close()
        if thread is not None:
            thread.join(LIMIT)
    assert not tree.errors and len(tree.held) == 1
    assert not blocked, f'send call still blocked after {LIMIT}s (10s CLI timeout) while a grandchild held stdout'
    assert not survivors, 'grandchild outlived the timed-out CLI call'
    assert box.get('value') == 'unresolved'
    attempt = json.loads((directory / 'receiver-journal.json').read_text())['attempts'][0]
    assert attempt == {'delivery_id': 'delivery', 'lease_until': 300, 'state': 'unknown',
        'error_type': 'TimeoutExpired', 'containment': 'windows_job', 'tree_exit_verified': True}


def within_bound(call, limit=LIMIT * 2):
    """Run a contained call off the test thread so a regressed bound fails instead of hanging pytest."""
    box = {}
    def target():
        try:
            box['value'] = call()
        except BaseException as error:
            box['error'] = error
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(limit)
    assert not thread.is_alive(), 'contained_run_bound_regressed'
    if 'error' in box:
        raise box['error']
    return box.get('value')


def script(tmp_path, body):
    path = tmp_path / 'fixture_cli.py'
    path.write_text(body, encoding='utf-8')
    return [sys._base_executable, '-I', '-S', str(path), str(tmp_path / 'started')]


def test_cli_is_already_in_job_before_spawn_returns_and_before_resume(tmp_path, monkeypatch):
    from ctypes import wintypes
    args = script(tmp_path, "import sys; from pathlib import Path; Path(sys.argv[1]).touch(); "
                            "print('ok'); raise SystemExit(3)")
    seen, spawn = [], receiver.WindowsJob.spawn
    def delayed(job, *args):
        proc = spawn(job, *args)
        inside = wintypes.BOOL()
        job.api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        assert job.api.IsProcessInJob(int(proc._handle), job.handle, ctypes.byref(inside))
        assert inside.value
        time.sleep(1)  # The assigned CLI is still suspended.
        seen.append((tmp_path / 'started').exists())
        return proc
    monkeypatch.setattr(receiver.WindowsJob, 'spawn', delayed)
    result = receiver.contained_run(args, timeout=LIMIT)
    assert seen == [False] and (tmp_path / 'started').exists()
    assert (result.returncode, result.stdout.strip(), result.stderr) == (3, b'ok', None)
    assert (result.containment, result.tree_exit_verified) == ('windows_job', True)


@pytest.mark.parametrize('step,code', [('create', 'native_job_create_process_failed'),
                                       ('attributes', 'native_job_attributes_failed'),
                                       ('resume', 'native_resume_failed')])
def test_failed_atomic_creation_or_resume_never_runs_cli(tmp_path, monkeypatch, step, code):
    args = script(tmp_path, "import sys; from pathlib import Path; Path(sys.argv[1]).touch()")
    started, spawn = [], receiver.WindowsJob.spawn
    def gated(job, *args):
        if step in {'create', 'attributes'}:
            api_name = 'CreateProcessW' if step == 'create' else 'UpdateProcThreadAttribute'
            monkeypatch.setattr(job.api, api_name, lambda *args: 0)
        proc = spawn(job, *args)
        started.append(proc)
        return proc
    def refused(job, proc):
        raise receiver.NativeContainmentError(code)
    monkeypatch.setattr(receiver.WindowsJob, 'spawn', gated)
    if step == 'resume':
        monkeypatch.setattr(receiver.WindowsJob, 'resume', refused)
    with pytest.raises(OSError, match='^' + code + '$') as caught:
        receiver.contained_run(args, timeout=LIMIT)
    assert caught.value.tree_exit_verified is True
    assert not (tmp_path / 'started').exists()
    assert not started or started[0].poll() is not None


def test_pipe_writer_held_outside_job_is_bounded_and_unconfirmed(tmp_path, monkeypatch):
    """No EOF while a process outside the job holds stdout: bounded, never claimed."""
    from ctypes import wintypes
    args = script(tmp_path, "import msvcrt, sys, time; from pathlib import Path\n"
        "root = Path(sys.argv[1]).parent\n"
        "root.joinpath('handle.tmp').write_text(str(msvcrt.get_osfhandle(1)))\n"
        "root.joinpath('handle.tmp').replace(root / 'handle.json')\n"
        "limit = time.monotonic() + 30\n"
        "while not root.joinpath('held').exists() and time.monotonic() < limit:\n"
        "    time.sleep(.01)\n")
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    held, errors, roots, spawn = wintypes.HANDLE(), [], [], receiver.WindowsJob.spawn
    def capture(job, *args):
        proc = spawn(job, *args)
        roots.append(proc)
        return proc
    def duplicate():
        try:
            limit = time.monotonic() + LIMIT
            while not (tmp_path / 'handle.json').exists():
                if time.monotonic() > limit:
                    raise RuntimeError('fixture_handle_timeout')
                time.sleep(.01)
            value = int((tmp_path / 'handle.json').read_text())
            # This test process, outside the job, keeps the CLI's stdout writer open.
            if not api.DuplicateHandle(int(roots[0]._handle), value, api.GetCurrentProcess(),
                                       ctypes.byref(held), 0, False, 2):
                raise RuntimeError('fixture_duplicate_failed')
        except Exception as error:
            errors.append(error)
        finally:
            (tmp_path / 'held').touch()
    monkeypatch.setattr(receiver.WindowsJob, 'spawn', capture)
    monkeypatch.setattr(receiver, 'EXIT_CONFIRM_SECONDS', .5)
    observer = threading.Thread(target=duplicate, daemon=True)
    observer.start()
    try:
        with pytest.raises(receiver.TreeExitUnconfirmed, match='^native_tree_exit_unconfirmed$'):
            within_bound(lambda: receiver.contained_run(args, timeout=LIMIT))
    finally:
        observer.join(LIMIT)
        if held.value:
            api.CloseHandle(held)
    assert not errors and roots[0].poll() is not None


def test_unconfirmed_job_accounting_raises_fixed_code_and_closes_owned_job(tmp_path, monkeypatch):
    args = script(tmp_path, "print('ok')")
    closed = []
    close = receiver.WindowsJob.close
    monkeypatch.setattr(receiver.WindowsJob, 'active_processes', lambda job: 1)
    monkeypatch.setattr(receiver.WindowsJob, 'close', lambda job: closed.append(1) or close(job))
    monkeypatch.setattr(receiver, 'EXIT_CONFIRM_SECONDS', .5)
    with pytest.raises(receiver.TreeExitUnconfirmed, match='^native_tree_exit_unconfirmed$'):
        within_bound(lambda: receiver.contained_run(args, timeout=LIMIT))
    assert closed == [1]


@pytest.mark.parametrize('unconfirmed', [1, 2])  # 1: before claim; 2: fresh check after dispatch.
def test_real_metadata_unconfirmed_exit_fences_receiver_restart(rig, monkeypatch, unconfirmed):
    config, event, binding, client, calls, directory = rig
    config.update(admission_mode='official_host_queue', native_project_id='native-project')
    (directory / 'metadata.json').write_text(json.dumps({'response': {'conversationMetadata': {'metadata': {
        'workspaceUris': [directory.resolve().as_uri()], 'projectId': 'native-project'}}}}))
    (directory / 'get-conversation-metadata').write_text("from pathlib import Path\n"
        "with open('launches.txt', 'a') as stream: stream.write('x')\n"
        "print(Path('metadata.json').read_text())\n", encoding='utf-8')
    log = directory / 'launches.txt'
    launches = lambda: len(log.read_text()) if log.exists() else 0
    active = receiver.WindowsJob.active_processes
    monkeypatch.setattr(receiver.WindowsJob, 'active_processes',
                        lambda job: 1 if launches() == unconfirmed else active(job))
    monkeypatch.setattr(receiver, 'EXIT_CONFIRM_SECONDS', .5)
    monkeypatch.chdir(directory)
    def start():
        return receiver.run(config, client, directory, sys._base_executable, lambda:
            receiver.official_metadata_admission(config, sys._base_executable, now=lambda: 110), now=lambda: 110)
    assert start() == 'unresolved' and launches() == unconfirmed
    journal = json.loads((directory / 'receiver-journal.json').read_text())
    fence = {'error_code': 'native_tree_exit_unconfirmed', 'containment': 'windows_job',
             'tree_exit_verified': False, 'phase': 'metadata'}
    if unconfirmed == 1:
        assert (journal['native_tree_unconfirmed'], journal['attempts'], calls) == (fence, [], ['status'])
    else:
        assert journal['attempts'] == [{'delivery_id': 'delivery', 'lease_until': 300, 'state': 'unknown'} | fence]
        assert calls == ['status', 'heartbeat', 'claim', 'dispatched']
    binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': 'replied'}
    calls.clear()
    assert start() == 'unresolved'
    assert calls == [] and launches() == unconfirmed


def test_output_beyond_limit_is_discarded_not_parsed(tmp_path):
    args = script(tmp_path, "import sys; sys.stdout.write('x' * 64)")
    result = receiver.contained_run(args, timeout=LIMIT, limit=16)
    assert (result.returncode, result.stdout, result.tree_exit_verified) == (0, None, True)


def test_stdout_read_error_discards_partial_output(tmp_path, monkeypatch):
    """A broken pipe read is incomplete output, never a complete result to parse."""
    args = script(tmp_path, "import sys; sys.stdout.write('partial-output')")
    popen = receiver._AtomicJobPopen
    class BrokenStdout:
        def __init__(self, stream):
            self.stream = stream
        def read1(self, size):
            raise OSError('fixture_read_error')
        def close(self):
            self.stream.close()
    def broken(*a, **k):
        proc = popen(*a, **k)
        proc.stdout = BrokenStdout(proc.stdout)
        return proc
    monkeypatch.setattr(receiver, '_AtomicJobPopen', broken)
    result = within_bound(lambda: receiver.contained_run(args, timeout=LIMIT))
    assert (result.returncode, result.stdout, result.tree_exit_verified) == (0, None, True)


def test_receiver_crash_at_launch_boundary_kills_suspended_cli(tmp_path):
    """Kill the exact receiver after creation, before it can resume its CLI."""
    import subprocess
    from pathlib import Path
    receiver_path = Path(receiver.__file__).resolve().parent.parent
    packages = next(path for path in sys.path if Path(path).name == 'site-packages')
    worker_path = tmp_path / 'crash_worker.py'
    child_path = tmp_path / 'suspended_cli.py'
    child_path.write_text("from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(60)")
    worker_path.write_text(r'''import ctypes, json, sys, time
from ctypes import wintypes
from pathlib import Path
sys.path[:0] = sys.argv[1:3]
from memory_hub import client_antigravity_receiver as receiver
root = Path(sys.argv[3])
api = ctypes.WinDLL('kernel32')
api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4

def hold(proc):
    times = [wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(int(proc._handle), *times):
        raise RuntimeError('fixture_process_time_failed')
    record = {'pid': proc.pid, 'created': times[0].dwHighDateTime << 32 | times[0].dwLowDateTime}
    root.joinpath('created.tmp').write_text(json.dumps(record))
    root.joinpath('created.tmp').replace(root / 'created.json')
    time.sleep(60)

# Baseline stops before the separate assignment; fixed implementation stops
# when its atomic spawn has returned, still before resume.
if hasattr(receiver.WindowsJob, 'spawn'):
    spawn = receiver.WindowsJob.spawn
    def gated(job, *args, **kwargs):
        proc = spawn(job, *args, **kwargs)
        hold(proc)
        return proc
    receiver.WindowsJob.spawn = gated
else:
    def gated(job, proc):
        hold(proc)
    receiver.WindowsJob.assign = gated
receiver.contained_run([sys.executable, '-I', '-S', str(root / 'suspended_cli.py'),
                        str(root / 'started')], timeout=10)
''', encoding='utf-8')
    worker = subprocess.Popen([sys._base_executable, '-I', '-S', str(worker_path),
        str(receiver_path), packages, str(tmp_path)], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    owned = None
    try:
        deadline = time.monotonic() + 30
        record = tmp_path / 'created.json'
        while not record.exists():
            assert worker.poll() is None, 'fixture receiver exited before its creation gate'
            assert time.monotonic() < deadline, 'fixture receiver creation gate timed out'
            time.sleep(.02)
        owned = Owned(json.loads(record.read_text()))
        assert not owned.exited() and not (tmp_path / 'started').exists()
        worker.kill()  # Exact retained receiver process handle, never a PID/name sweep.
        worker.wait(timeout=5)
        child_exited = owned.exited(5000)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)
        if owned is not None:
            owned.close()  # Reap only the exact fake CLI if the baseline leaked it.
    assert child_exited, 'receiver crash leaked a suspended CLI outside its owned job'
    assert not (tmp_path / 'started').exists()


def test_launch_failure_after_atomic_creation_still_accounts_for_owned_job(tmp_path, monkeypatch):
    args = script(tmp_path, "from pathlib import Path; import sys; Path(sys.argv[1]).touch()")
    roots, popen = [], receiver._AtomicJobPopen
    def failed(*args, **kwargs):
        proc = popen(*args, **kwargs)
        roots.append(proc)
        raise OSError('fixture_after_creation')
    monkeypatch.setattr(receiver, '_AtomicJobPopen', failed)
    try:
        with pytest.raises(OSError, match='^fixture_after_creation$') as caught:
            within_bound(lambda: receiver.contained_run(args, timeout=LIMIT))
        assert caught.value.tree_exit_verified is True
        assert roots[0].poll() is not None and not (tmp_path / 'started').exists()
    finally:
        for proc in roots:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            proc.stdout.close()
