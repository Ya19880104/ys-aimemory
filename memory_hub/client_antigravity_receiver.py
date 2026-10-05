"""Bounded official-sidecar receiver. Transport completion never proves native idle.

Caller supplies an authenticated scoped HTTP client and fresh native admission.
No provider credentials, histories, global configuration, or model APIs are read.
On Windows each official CLI call runs in an owned job and returns only after
its whole process tree has exited. An unconfirmed exit of either call is
journaled and fences every later start until explicit recovery.
"""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
from urllib.parse import unquote, urlsplit

import httpx

from .client_watch import exclusive, reminder


TERMINAL = {'paused', 'disabled', 'disconnected', 'expired', 'revoked', 'archived',
            'budget_exhausted', 'failed'}
CREATE_SUSPENDED = 0x4
EXIT_CONFIRM_SECONDS = 10
OUTPUT_LIMIT = 1 << 20


class NativeContainmentError(OSError):
    """Fixed launch-phase code; raised only after every started process is gone."""


class TreeExitUnconfirmed(RuntimeError):
    """Owned native processes may survive: never infer a reply, exit or retry."""
    code = 'native_tree_exit_unconfirmed'

    def __init__(self):
        super().__init__(self.code)


class WindowsJob:
    """Unnamed, non-inheritable KILL_ON_JOB_CLOSE job; this object owns its only handle."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.handle = ctypes, None
        api = self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        class BasicLimits(ctypes.Structure):
            _fields_ = [('user_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                ('flags', wintypes.DWORD), ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t),
                ('active_limit', wintypes.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                ('reads', 'writes', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', BasicLimits), ('io', Counters)] + [(name, ctypes.c_size_t)
                for name in ('process_memory', 'job_memory', 'peak_process', 'peak_job')]
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in
                ('user_time', 'kernel_time', 'period_user', 'period_kernel')] + [(name, wintypes.DWORD)
                for name in ('page_faults', 'total_processes', 'active_processes', 'terminated_processes')]
        class Thread(ctypes.Structure):  # THREADENTRY32
            _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('thread', wintypes.DWORD),
                ('owner', wintypes.DWORD), ('base', wintypes.LONG), ('delta', wintypes.LONG),
                ('flags', wintypes.DWORD)]
        self.Accounting, self.Thread = Accounting, Thread
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                  wintypes.DWORD, ctypes.c_void_p]
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        api.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        api.Thread32First.argtypes = api.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(Thread)]
        api.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenThread.restype = wintypes.HANDLE
        api.ResumeThread.argtypes = [wintypes.HANDLE]
        api.ResumeThread.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = api.CreateJobObjectW(None, None)  # Not inheritable; no named/global job.
        if not self.handle:
            raise NativeContainmentError('native_job_create_failed')
        limits = Limits()
        limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE, without either breakaway flag.
        if not api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise NativeContainmentError('native_job_limits_failed')

    def assign(self, proc):
        # Still suspended: the CLI has not executed a single instruction yet.
        if not self.api.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise NativeContainmentError('native_job_assignment_failed')

    def resume(self, proc):
        """Resume the only initial thread; our open process handle pins this PID."""
        ctypes, api = self.ctypes, self.api
        snapshot = api.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot in (None, ctypes.c_void_p(-1).value):
            raise NativeContainmentError('native_resume_failed')
        threads, entry = [], self.Thread()
        entry.size = ctypes.sizeof(entry)
        try:
            found = api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.owner == proc.pid:
                    threads.append(entry.thread)
                found = api.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            api.CloseHandle(snapshot)
        thread = api.OpenThread(2, False, threads[0]) if len(threads) == 1 else None  # SUSPEND_RESUME
        if not thread:
            raise NativeContainmentError('native_resume_failed')
        try:
            if api.ResumeThread(thread) != 1:  # Exactly our CREATE_SUSPENDED count.
                raise NativeContainmentError('native_resume_failed')
        finally:
            api.CloseHandle(thread)

    def active_processes(self):
        info = self.Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, self.ctypes.byref(info),
                                                  self.ctypes.sizeof(info), None):
            raise TreeExitUnconfirmed()
        return info.active_processes

    def finish(self):
        # A returned root or pipe EOF never proves that its descendants have exited.
        if not self.api.TerminateJobObject(self.handle, 1):
            raise TreeExitUnconfirmed()
        deadline = time.monotonic() + EXIT_CONFIRM_SECONDS
        while self.active_processes() != 0:
            if time.monotonic() >= deadline:
                raise TreeExitUnconfirmed()
            time.sleep(.02)

    def close(self):
        handle, self.handle = self.handle, None
        return not handle or bool(self.api.CloseHandle(handle))


def _settle(job, proc, assigned, reader):
    """True only when every started process is gone and the job handle is closed."""
    settled = closed = False
    try:
        if proc is not None:
            if assigned:
                job.finish()
            else:
                proc.kill()  # Suspended outside the job: it never executed.
            proc.wait(timeout=EXIT_CONFIRM_SECONDS)
        if reader is not None:
            reader.join(EXIT_CONFIRM_SECONDS)  # EOF once no pipe holder remains.
        settled = reader is None or not reader.is_alive()
    except Exception:
        pass
    finally:
        closed = job is None or job.close()  # KILL_ON_JOB_CLOSE ends any unconfirmed member.
    if settled and proc is not None:
        proc.stdout.close()
    return settled and closed


def contained_run(args, *, timeout, creationflags=0, shell=False, capture_output=True,
                  limit=OUTPUT_LIMIT):
    """subprocess.run subset for one Windows CLI call inside an owned job.

    Created suspended, assigned, then resumed, so no descendant starts outside
    the job. Root exit or timeout ends the whole job; pipe EOF is never awaited
    first. Bounded stdout only; stderr is discarded. Raises TreeExitUnconfirmed
    unless zero active job members, root exit and pipe EOF are all observed.
    """
    if shell or not capture_output:
        raise ValueError('contained_run_requires_argv_capture')
    deadline, chunks, size, broken = time.monotonic() + timeout, [], [0], []
    job = proc = reader = error = None
    assigned = timed_out = False

    def read():
        try:
            while data := proc.stdout.read1(65536):
                size[0] += len(data)
                if size[0] <= limit:
                    chunks.append(data)
        except (OSError, ValueError):
            broken.append(1)  # Exit is judged by job accounting; this output is incomplete.

    try:
        job = WindowsJob()
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, close_fds=True,
            creationflags=creationflags | CREATE_SUSPENDED)
        job.assign(proc)
        assigned = True
        job.resume(proc)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            proc.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
    except BaseException as exc:
        error = exc
    if not _settle(job, proc, assigned, reader):
        raise TreeExitUnconfirmed() from error
    if error is None and timed_out:
        error = subprocess.TimeoutExpired(args[0], timeout)
    if error is not None:
        error.containment, error.tree_exit_verified = 'windows_job', True
        raise error
    result = subprocess.CompletedProcess(args, proc.returncode,
                                         b''.join(chunks) if size[0] <= limit and not broken else None)
    result.containment, result.tree_exit_verified = 'windows_job', True
    return result


default_execute = contained_run if os.name == 'nt' else subprocess.run  # POSIX: offline fixtures only.


def tree_evidence(value):
    """Exact owned-job proof only; injected or POSIX executors claim no tree exit."""
    if (getattr(value, 'containment', None) == 'windows_job' and
            getattr(value, 'tree_exit_verified', None) is True):
        return {'containment': 'windows_job', 'tree_exit_verified': True}
    return {'containment': 'none'}


def unconfirmed(phase):
    """Fence for a possibly live owned tree: no reply, exit or return code is claimed."""
    return {'error_code': TreeExitUnconfirmed.code, 'containment': 'windows_job',
            'tree_exit_verified': False, 'phase': phase}


def durable(path, value):
    """Atomic replace after flushing content; never discard an attempt on restart."""
    pending = path.with_name(path.name + '.pending')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)
    if os.name != 'nt':
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def admitted(config, event, now):
    if not isinstance(event, dict):
        return False
    if (event.get('conversationId') != config['native_session_id'] or
            event.get('workspacePaths') != [str(Path(config['project']).resolve())] or
            type(event.get('observed_at')) not in (int, float) or
            not 0 <= now - event['observed_at'] <= 60):
        return False
    if config.get('admission_mode') == 'official_host_queue' and event.get('kind') == 'official_metadata':
        return (event.get('scope_verified') is True and event.get('native_project_id') ==
                config.get('native_project_id') and isinstance(config.get('native_project_id'), str))
    if event.get('kind') == 'native_stop':
        return event.get('fullyIdle') is True and event.get('terminationReason') == 'model_stop'
    return (config.get('admission_mode') == 'manually_admitted_dedicated_test' and
            event.get('kind') == 'manual_initial' and event.get('ui_idle_confirmed') is True and
            event.get('exclusive_test_conversation') is True)


def run(config, client, directory, executable, admission, *, now=time.time,
        sleep=time.sleep, execute=default_execute, on_state=lambda state: None):
    """Resume same binding only. `admission()` returns observed metadata, never guesses.

    Manual admission admits only the initial send. Later sends need fresh native
    Stop metadata. The callable must supply unique event_id values for real events.
    An unconfirmed native tree exit (metadata or send) is journaled and fences
    every later start, even after a Hub receipt for the same delivery.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (config.get('client') != 'gemini' or
            str(uuid.UUID(config['native_session_id'])) != config['native_session_id'] or
            type(config.get('max_sends')) is not int or not 1 <= config['max_sends'] <= 100 or
            not now() < config['expires_at'] <= now() + 86400 or
            not Path(config['project']).resolve(strict=True).is_dir()):
        raise ValueError('invalid_receiver_scope')
    path = directory / 'receiver-journal.json'
    scope = {key: config[key] for key in ('project_id', 'session_id', 'binding_id',
                                         'generation', 'native_session_id')}
    with exclusive(directory / 'receiver-process.lock') as acquired:
        if not acquired:
            return 'already_running'
        journal = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'scope': scope, 'attempts': [], 'used_events': [], 'claim_request': None}
        if journal['scope'] != scope:
            return 'scope_mismatch'
        if 'native_tree_unconfirmed' in journal or any(
                item.get('tree_exit_verified') is False for item in journal['attempts']):
            return 'unresolved'  # Possibly live native tree: explicit recovery only.

        def call(operation, data):
            response = (client.get('/v1/chat/status', params=data) if operation == 'status'
                        else client.post('/v1/chat/' + operation, json=data))
            response.raise_for_status()
            return response.json()

        ref = {key: config[key] for key in ('project_id', 'binding_id')}
        while now() < config['expires_at'] and not (directory / 'STOP').exists():
            # Never claim before reconciling the durable notification attempt.
            status = call('status', {key: config[key] for key in ('project_id', 'session_id')})
            binding = next((item for item in status['participants']
                            if item['binding_id'] == config['binding_id']), None)
            if binding is None or binding['generation'] != config['generation']:
                return 'disconnected'
            if binding['project_id'] != config['project_id'] or binding['session_id'] != config['session_id']:
                return 'scope_mismatch'
            active = next((item for item in journal['attempts'] if item['state'] not in {'replied', 'no_reply'}), None)
            if active:
                latest = binding.get('latest_delivery') or {}
                if latest.get('delivery_id') == active['delivery_id'] and latest.get('status') in {'replied', 'no_reply'}:
                    active['state'] = latest['status']
                    durable(path, journal)
                elif now() >= active['lease_until']:
                    return 'unresolved'
                elif binding['status'] in TERMINAL:
                    return binding['status']
                else:
                    sleep(min(3, max(0, config['expires_at'] - now())))
                    continue
            if binding['status'] in TERMINAL:
                return binding['status']
            if len(journal['attempts']) >= config['max_sends']:
                return 'budget_exhausted'
            try:
                event = admission()
            except TreeExitUnconfirmed:
                # Nothing claimed yet: a journal-level fence blocks every restart.
                journal['native_tree_unconfirmed'] = unconfirmed('metadata')
                durable(path, journal)
                return 'unresolved'
            event_id = event.get('event_id') if isinstance(event, dict) else None
            if (not isinstance(event_id, str) or not event_id or event_id in journal['used_events'] or
                    not admitted(config, event, now()) or
                    (event.get('kind') == 'manual_initial' and journal['attempts'])):
                on_state('needs_native_idle')
                sleep(min(3, max(0, config['expires_at'] - now())))
                continue
            if journal['claim_request'] is None:
                journal['claim_request'] = uuid.uuid4().hex
                durable(path, journal)
            call('heartbeat', ref)
            try:
                claimed = call('claim', ref | {'generation': config['generation'],
                               'request_id': journal['claim_request'], 'lease_seconds': 300})
            except httpx.HTTPStatusError as exc:
                try:
                    stale = exc.response.status_code == 409 and exc.response.json().get('error') == 'stale_claim'
                except (ValueError, AttributeError):
                    stale = False
                if not stale:
                    raise
                # Legacy journals cannot associate prior attempts with this key:
                # rotate only when no native intent has ever been journaled.
                if journal['attempts']:
                    return 'unresolved'
                journal['claim_request'] = None
                durable(path, journal)
                sleep(min(3, max(0, config['expires_at'] - now())))
                continue
            if claimed['status'] == 'idle':
                sleep(min(3, max(0, config['expires_at'] - now())))
                continue
            if claimed['status'] != 'ready':
                return claimed['status']
            delivery = claimed['delivery']
            if any(item['delivery_id'] == delivery['delivery_id'] for item in journal['attempts']):
                return 'unresolved'
            # Preserve intent BEFORE dispatch or external notification. A crash
            # at any later point becomes unresolved, never an automatic resend.
            journal['attempts'].append({'delivery_id': delivery['delivery_id'],
                'lease_until': delivery['lease_until'], 'state': 'intent'})
            journal['used_events'].append(event_id)
            journal['claim_request'] = None
            durable(path, journal)
            if now() >= min(config['expires_at'], delivery['lease_until']) or (directory / 'STOP').exists():
                return 'unresolved'
            call('dispatched', ref | {key: delivery[key] for key in ('delivery_id', 'lease_id')})
            durable(directory / 'chat-delivery.json', delivery | {'join_key': config['idempotency_key']})
            # Fresh admission rechecked immediately before invoking the official CLI.
            if (not admitted(config, event, now()) or (directory / 'STOP').exists() or
                    now() >= min(config['expires_at'], delivery['lease_until'])):
                return 'unresolved'
            if config.get('admission_mode') == 'official_host_queue':
                # Query the official host again immediately before every send.
                # This establishes scope only, never busy/idle/completion.
                try:
                    fresh = admission()
                except TreeExitUnconfirmed:
                    # Dispatched, never sent; a later receipt must not clear this.
                    journal['attempts'][-1].update(state='unknown', **unconfirmed('metadata'))
                    durable(path, journal)
                    return 'unresolved'
                if not admitted(config, fresh, now()) or fresh.get('kind') != 'official_metadata':
                    return 'unresolved'
                if (directory / 'STOP').exists() or now() >= min(config['expires_at'], delivery['lease_until']):
                    return 'unresolved'
            try:
                result = execute([executable, 'send-message', config['native_session_id'], reminder(config, delivery)],
                    shell=False, capture_output=True, timeout=max(.001, min(10,
                    config['expires_at'] - now(), delivery['lease_until'] - now())),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                journal['attempts'][-1].update(state='returned', returncode=result.returncode,
                                               **tree_evidence(result))
            except TreeExitUnconfirmed:
                # Neither reply nor exit is claimed; the durable fence blocks restarts too.
                journal['attempts'][-1].update(state='unknown', **unconfirmed('send'))
                durable(path, journal)
                return 'unresolved'
            except (OSError, subprocess.TimeoutExpired) as exc:
                journal['attempts'][-1].update(state='unknown', error_type=type(exc).__name__,
                                               **tree_evidence(exc))
                if isinstance(exc, NativeContainmentError):  # Keep the fixed launch-phase code.
                    journal['attempts'][-1]['error_code'] = str(exc)
            durable(path, journal)
        return 'stopped' if (directory / 'STOP').exists() else 'expired'


def official_metadata_admission(config, executable, *, now=time.time, execute=default_execute):
    """Official CLI metadata only; discard raw output, never query histories/RPC.

    An unconfirmed native tree exit is raised, never treated as a retryable miss;
    run() journals it as a restart fence.
    """
    try:
        return _official_metadata(config, executable, now=now, execute=execute)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, KeyError):
        return None


def _official_metadata(config, executable, *, now, execute):
    result = execute([executable, 'get-conversation-metadata', config['native_session_id']],
        shell=False, capture_output=True, timeout=10,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode != 0:
        return None
    value = json.loads(result.stdout)
    for key in ('response', 'conversationMetadata', 'metadata'):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
        if isinstance(value, str) and key == 'response':
            value = json.loads(value)
    if not isinstance(value, dict):
        return None
    uris = value.get('workspaceUris')
    if not isinstance(uris, list) or len(uris) != 1 or not isinstance(uris[0], str):
        return None
    uri = urlsplit(uris[0])
    expected = urlsplit(Path(config['project']).resolve(strict=True).as_uri())
    if (uri.scheme != 'file' or uri.netloc or uri.query or uri.fragment or
            unquote(uri.path).casefold() != unquote(expected.path).casefold() or
            value.get('projectId') != config.get('native_project_id')):
        return None
    return {'kind':'official_metadata', 'scope_verified':True, 'event_id':uuid.uuid4().hex,
            'conversationId':config['native_session_id'], 'workspacePaths':[str(Path(config['project']).resolve())],
            'native_project_id':value['projectId'], 'observed_at':now()}
