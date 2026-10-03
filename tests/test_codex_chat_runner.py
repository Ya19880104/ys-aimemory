"""Bounded receiver contracts; no model, login, network or real credential use."""
import importlib.util
import json
import io
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('codex_receiver', Path(__file__).parents[1] / 'scripts' / 'run-codex-chat.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

CONFIG = {'project_id': 'test-project', 'session_id': 'a'*32, 'worker_id': 'codex-fixture',
          'codex': 'codex.exe', 'python': 'python.exe', 'native_session_id': 'receiver-fixture',
          'idempotency_key': 'join-fixture', 'after_sequence': 4, 'max_turns': 2,
          'ttl_seconds': 60, 'expires_at': 160, 'turn_timeout': 60}
DELIVERY = {'delivery_id': 'b'*32, 'lease_id': 'c'*32, 'after_sequence': 4, 'through_sequence': 6,
            'message_ids': ['d'*32, 'e'*32], 'reply_idempotency_key': 'delivery-' + 'b'*32}


def arguments(name, **changes):
    if name == 'get_worker_inbox':
        result = {'project_id': CONFIG['project_id']}
    else:
        result = {key: CONFIG[key] for key in ('project_id', 'session_id')} | {
            key: DELIVERY[key] for key in ('delivery_id', 'lease_id')}
        if name == 'read_session':
            result.update(after_sequence=4, limit=20, max_bytes=16384, full_text=True)
        else:
            result.update(body='這是原生對話回覆。', idempotency_key=DELIVERY['reply_idempotency_key'])
    return {'arguments': result | changes}


def event(name, value, ident='call-1', **changes):
    return {'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'ys_memory',
        'tool': name, 'id': ident, 'arguments': arguments(name, **changes),
        'result': {'structuredContent': value}}}


def reading(sequence, message, complete=False):
    return {'session': {key: CONFIG[key] for key in ('project_id', 'session_id')},
        'items': [{'type': 'message', 'message_id': message, 'sequence': sequence, 'body_truncated': False}],
        'next_after_sequence': sequence, 'delivery_receipt': {'delivery_id': DELIVERY['delivery_id'],
        'status': 'tool_read' if complete else 'partial_tool_read',
        'unread_message_ids': [] if complete else [DELIVERY['message_ids'][1]]}}


def reply():
    return {key: CONFIG[key] for key in ('project_id', 'session_id')} | {'message_id': 'f'*32,
        'sequence': 7, 'actor': {'id': CONFIG['worker_id'], 'kind': 'worker'},
        'delivery_receipt': {'delivery_id': DELIVERY['delivery_id'], 'status': 'replied', 'processed_sequence': 6}}


def completed_proof():
    proof = runner.NativeProof(CONFIG, DELIVERY)
    proof.event(event('get_worker_inbox', {'worker_id': CONFIG['worker_id']}, 'identity'))
    proof.event(event('read_session', reading(5, 'd'*32), 'read-1'))
    proof.event(event('read_session', reading(6, 'e'*32, True), 'read-2', after_sequence=5))
    proof.event(event('post_session_message', reply(), 'post'))
    return proof


@pytest.mark.parametrize('name,changes', [
    ('read_session', {'session_id': '9'*32}), ('read_session', {'project_id': 'another-project'}),
    ('read_session', {'lease_id': '9'*32}), ('read_session', {'after_sequence': 0}),
    ('read_session', {'after_sequence': 6}), ('read_session', {'full_text': False}),
    ('read_session', {'limit': True}), ('post_session_message', {'idempotency_key': 'changed'}),
    ('post_session_message', {'body': '字'*401}), ('post_session_message', {'attachment_ids': []}),
])
def test_scoped_gate_rejects_cross_room_token_cost_and_retry_changes(name, changes):
    assert not runner.valid_scope(name, arguments(name, **changes), CONFIG, DELIVERY)


def test_native_proof_requires_every_full_message_across_pages_and_real_post_receipt():
    proof = completed_proof()
    result = proof.finish(0)
    assert result['status'] == 'passed' and result['native_tool_calls'] == 4
    assert result['read_message_ids'] == DELIVERY['message_ids']
    assert result['post_receipt']['sequence'] == 7
    assert '原生對話回覆' not in json.dumps(result, ensure_ascii=False)
    assert 'body_sha256' in result['post_receipt']


def test_native_final_prose_and_forged_read_receipt_do_not_prove_success():
    proof = runner.NativeProof(CONFIG, DELIVERY)
    proof.event({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'All done'}})
    with pytest.raises(runner.ReceiverError, match='incomplete'):
        proof.finish(0)
    proof.event(event('get_worker_inbox', {'worker_id': CONFIG['worker_id']}, 'identity'))
    proof.event(event('read_session', reading(6, 'e'*32, True), 'read'))
    with pytest.raises(runner.ReceiverError, match='not_read'):
        proof.event(event('post_session_message', reply(), 'post'))


def test_native_identity_scope_and_tool_failure_stop():
    with pytest.raises(runner.ReceiverError, match='worker_mismatch'):
        runner.NativeProof(CONFIG, DELIVERY).event(event('get_worker_inbox', {'worker_id': 'other'}))
    failed = event('get_worker_inbox', {'worker_id': CONFIG['worker_id']})
    failed['item']['result']['isError'] = True
    with pytest.raises(runner.ReceiverError, match='tool_failed'):
        runner.NativeProof(CONFIG, DELIVERY).event(failed)
    proof = completed_proof()
    with pytest.raises(runner.ReceiverError, match='extra_native_call'):
        proof.event(event('get_worker_inbox', {'worker_id': CONFIG['worker_id']}, 'again'))


def test_native_command_is_ephemeral_scoped_and_no_provider_secret_inheritance(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY', 'provider-secret-never-inherit')
    monkeypatch.setenv('YS_AIMEMORY_TOKEN', 'other-worker-never-inherit')
    monkeypatch.setenv('CODEX_HOME', 'other-session-never-inherit')
    command = runner.command(CONFIG | {'delivery': DELIVERY}, tmp_path / 'scope.json', tmp_path)
    assert '--ephemeral' in command and '--ignore-user-config' in command
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert '--dangerously-bypass-approvals-and-sandbox' not in command
    assert 'project_doc_max_bytes=0' in command
    assert not {'OPENAI_API_KEY', 'YS_AIMEMORY_TOKEN', 'CODEX_HOME'} & runner.environment().keys()
    assert 'get_worker_inbox' in command[-1] and 'through_sequence=6' in command[-1]
    assert 'provider-secret' not in json.dumps(command)


class FakeClient:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.calls = []

    def post(self, path, json):
        self.calls.append((path, json))
        operation = path.rsplit('/', 1)[-1]
        if operation == 'join':
            value = {key: CONFIG[key] for key in ('worker_id', 'project_id', 'session_id')} | {'binding_id': '0'*32, 'version': 1}
        elif operation == 'claim':
            status = next(self.statuses)
            value = {'status': status, 'delivery': DELIVERY if status == 'ready' else None}
        else:
            value = {'status': 'waiting'}
        return type('Response', (), {'raise_for_status': lambda self: None, 'json': lambda self: value})()


def test_idle_paused_budget_polling_never_spawns_model(tmp_path):
    client, waits = FakeClient(['idle', 'paused', 'budget_exhausted']), []
    def forbidden(*args):
        pytest.fail('No model can run for idle/pause/budget')
    result = runner.receiver(CONFIG, client, tmp_path, turn=forbidden, now=lambda: 100, sleep=waits.append)
    assert result['state'] == 'budget_exhausted' and waits == [3, 3]
    assert not any(path.endswith('dispatched') for path, _ in client.calls)


def test_only_ready_delivery_runs_native_turn_and_failure_never_retries(tmp_path):
    client = FakeClient(['ready', 'budget_exhausted'])
    def turn(config, delivery, directory, heartbeat, stop):
        assert heartbeat()['status'] == 'waiting'
        return completed_proof().finish(0)
    result = runner.receiver(CONFIG, client, tmp_path, turn=turn, now=lambda: 100, sleep=lambda _: None)
    assert result['native_turns'] == 1
    assert (tmp_path / ('receipt-' + DELIVERY['delivery_id'] + '.json')).exists()
    calls = [path for path, _ in client.calls]
    assert calls.count('/v1/chat/dispatched') == 1
    assert not any('/tools/' in path for path in calls), 'REST must never impersonate native read/post'
    failed = FakeClient(['ready'])
    def stop_turn(*args):
        raise runner.ReceiverError('native_tool_failed')
    with pytest.raises(runner.ReceiverError):
        runner.receiver(CONFIG, failed, tmp_path, turn=stop_turn, now=lambda: 100, sleep=lambda _: None)
    assert len([path for path, _ in failed.calls if path.endswith('claim')]) == 1
    assert failed.calls[-1] == ('/v1/chat/control', {'project_id': CONFIG['project_id'],
        'binding_id': '0'*32, 'enabled': False, 'expected_version': 1})


def test_stop_file_does_not_even_join(tmp_path):
    (tmp_path / 'STOP').touch()
    client = FakeClient([])
    assert runner.receiver(CONFIG, client, tmp_path)['state'] == 'stopped'
    assert client.calls == []


def test_native_process_heartbeats_during_turn_and_persists_only_scope_and_receipt(monkeypatch, tmp_path):
    native_events = [event('get_worker_inbox', {'worker_id': CONFIG['worker_id']}, 'identity'),
        event('read_session', reading(5, 'd'*32), 'read-1'),
        event('read_session', reading(6, 'e'*32, True), 'read-2', after_sequence=5),
        event('post_session_message', reply(), 'post')]
    class Process:
        stdout = io.StringIO('\n'.join(json.dumps(item) for item in native_events) + '\n')
        def poll(self): return 0
        def wait(self, timeout): return 0
    def launch(args, **kwargs):
        assert kwargs['shell'] is False and kwargs['stderr'] is runner.subprocess.DEVNULL
        return Process()
    monkeypatch.setattr(runner.subprocess, 'Popen', launch)
    clock, heartbeats = [0], []
    def now():
        clock[0] += 3
        return clock[0]
    def heartbeat():
        heartbeats.append(True)
        return {'status': 'processing'}
    result = runner.native_turn(CONFIG, DELIVERY, tmp_path, heartbeat, lambda: False, now=now)
    assert result['status'] == 'passed' and heartbeats
    assert sorted(p.name for p in tmp_path.iterdir()) == ['native-empty', 'native-scope.json']
    assert '這是原生對話回覆' not in (tmp_path / 'native-scope.json').read_text(encoding='utf-8')
