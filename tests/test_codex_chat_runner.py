"""Bounded receiver contracts; no model, login, network or real credential use."""
import importlib.util
import json
import io
import httpx
from pathlib import Path

import pytest
from test_sessions import collaboration, room, post, A, B
from test_index import _migration_db

spec = importlib.util.spec_from_file_location('codex_receiver', Path(__file__).parents[1] / 'scripts' / 'run-codex-chat.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

CONFIG = {'project_id': 'test-project', 'session_id': 'a'*32, 'worker_id': 'codex-fixture',
          'codex': 'codex.exe', 'python': 'python.exe', 'native_session_id': 'receiver-fixture',
          'idempotency_key': 'join-fixture', 'after_sequence': 4, 'max_turns': 2,
          'ttl_seconds': 60, 'expires_at': 160, 'turn_timeout': 60}
DELIVERY = {'delivery_id': 'b'*32, 'lease_id': 'c'*32, 'after_sequence': 4, 'through_sequence': 6,
            'message_ids': ['d'*32, 'e'*32], 'reply_idempotency_key': 'delivery-' + 'b'*32}


def fault_client(claim, dispatch=None):
    def handle(request):
        operation = request.url.path.rsplit('/', 1)[-1]
        if operation == 'join':
            return httpx.Response(200, json={k: CONFIG[k] for k in ('worker_id', 'project_id', 'session_id')} |
                {'binding_id': '0'*32, 'version': 1, 'generation': 1})
        if operation == 'claim':
            return claim(request)
        if operation == 'dispatched' and dispatch:
            return dispatch(request)
        return httpx.Response(200, json={'status': 'waiting'})
    return httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(handle))


def test_committed_lost_claim_retries_same_persisted_request_without_duplicate_turn(tmp_path):
    requests, turns = [], []
    def claim(request):
        payload = json.loads(request.content)
        assert json.loads((tmp_path / 'receiver-claim.json').read_text()) == payload
        requests.append(payload)
        if len(requests) == 1:
            raise httpx.ReadTimeout('committed response lost', request=request)
        if len(requests) <= 2:
            return httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})
        return httpx.Response(200, json={'status': 'busy' if len(requests) == 3 else 'budget_exhausted', 'delivery': None})
    with fault_client(claim) as client:
        result = runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, sleep=lambda _: None,
            turn=lambda *args: turns.append(args[1]) or {'status': 'passed'})
    assert requests[0] == requests[1] == requests[2]
    assert len(turns) == 1 and result['native_turns'] == 1


def test_claim_response_loss_survives_restart_with_original_request(tmp_path):
    requests = []
    def crash(request):
        requests.append(json.loads(request.content))
        raise KeyboardInterrupt()
    with fault_client(crash) as client, pytest.raises(KeyboardInterrupt):
        runner.receiver(CONFIG, client, tmp_path, now=lambda: 100)
    def recovered(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})
    turns = []
    with fault_client(recovered) as client:
        runner.receiver(CONFIG | {'max_turns': 1}, client, tmp_path, now=lambda: 100,
            turn=lambda *args: turns.append(args[1]) or {'status': 'passed'})
    assert requests[0] == requests[1] and len(turns) == 1


def test_stop_during_claim_backoff_never_starts_model(tmp_path):
    def unavailable(request):
        return httpx.Response(503)
    with fault_client(unavailable) as client:
        result = runner.receiver(CONFIG, client, tmp_path, now=lambda: 100,
            sleep=lambda _: (tmp_path / 'STOP').touch(), turn=lambda *args: pytest.fail('stopped'))
    assert result['state'] == 'stopped' and result['native_turns'] == 0


def test_lost_dispatch_response_requires_verified_retry_before_model(tmp_path):
    dispatches, turns = [], []
    def claim(request):
        return httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})
    def dispatch(request):
        dispatches.append(json.loads(request.content))
        if len(dispatches) == 1:
            raise httpx.ReadTimeout('committed dispatch lost', request=request)
        return httpx.Response(200, json={'status': 'handed_to_client'})
    with fault_client(claim, dispatch) as client:
        runner.receiver(CONFIG | {'max_turns': 1}, client, tmp_path, now=lambda: 100, sleep=lambda _: None,
            turn=lambda *args: turns.append(len(dispatches)) or {'status': 'passed'})
    assert dispatches[0] == dispatches[1] and turns == [2]


def test_restart_after_dispatch_does_not_resume_native_turn(tmp_path):
    requests = []
    def ready(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})
    def crash(*args):
        raise KeyboardInterrupt()
    with fault_client(ready) as client, pytest.raises(KeyboardInterrupt):
        runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, turn=crash)
    def already_dispatched(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'status': 'busy' if len(requests) == 2 else 'budget_exhausted', 'delivery': None})
    with fault_client(already_dispatched) as client:
        runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, sleep=lambda _: None,
            turn=lambda *args: pytest.fail('cannot resume an uncertain model'))
    assert requests[0] == requests[1] == requests[2]


@pytest.mark.parametrize('code,error', [(401, 'unauthorized'), (409, 'stale_binding')])
def test_claim_terminal_auth_or_generation_failure_does_not_rotate(tmp_path, code, error):
    requests = []
    def reject(request):
        requests.append(json.loads(request.content))
        return httpx.Response(code, json={'error': error})
    with fault_client(reject) as client, pytest.raises(httpx.HTTPStatusError):
        runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, sleep=lambda _: pytest.fail('terminal retry'))
    assert len(requests) == 1


def test_distinct_receivers_same_worker_do_not_share_claim_identity(tmp_path):
    requests = []
    def busy(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'status': 'budget_exhausted', 'delivery': None})
    for name in ('one', 'two'):
        directory = tmp_path / name
        directory.mkdir()
        with fault_client(busy) as client:
            runner.receiver(CONFIG, client, directory, now=lambda: 100,
                turn=lambda *args: pytest.fail('no model'))
    assert requests[0]['binding_id'] == requests[1]['binding_id']
    assert requests[0]['request_id'] != requests[1]['request_id']


def test_stale_claim_rotates_then_dispatch_pause_race_cannot_wake(tmp_path):
    requests, dispatches, turns = [], [], []
    def claim(request):
        requests.append(json.loads(request.content))
        if len(requests) in (1, 3):
            return httpx.Response(409, json={'error': 'stale_claim'})
        return httpx.Response(200, json={'status': 'ready', 'delivery': DELIVERY})
    def dispatch(request):
        dispatches.append(request)
        return httpx.Response(409 if len(dispatches) == 1 else 200, json={'error': 'delivery_stopped'})
    with fault_client(claim, dispatch) as client:
        runner.receiver(CONFIG | {'max_turns': 1}, client, tmp_path, now=lambda: 100, sleep=lambda _: None,
            turn=lambda *args: turns.append(args[1]) or {'status': 'passed'})
    assert requests[0]['request_id'] != requests[1]['request_id']
    assert requests[1] == requests[2]
    assert requests[3]['request_id'] != requests[2]['request_id']
    assert len(turns) == 1 and len(dispatches) == 2


@pytest.mark.parametrize('response_kind', ['idle', 'stale_claim'])
def test_removed_pending_claim_during_response_does_not_disable_receiver(tmp_path, response_kind):
    requests, controls = [], []
    def handle(request):
        operation = request.url.path.rsplit('/', 1)[-1]
        if operation == 'join':
            return httpx.Response(200, json={k: CONFIG[k] for k in ('worker_id', 'project_id', 'session_id')} |
                {'binding_id': '0'*32, 'version': 1, 'generation': 1})
        if operation == 'control':
            controls.append(request)
        if operation == 'claim':
            requests.append(json.loads(request.content))
            if len(requests) == 1:
                # Manual deletion can race the HTTP response despite the kernel
                # lock excluding a second receiver in this directory.
                (tmp_path / 'receiver-claim.json').unlink()
                return httpx.Response(409 if response_kind == 'stale_claim' else 200,
                    json={'error': 'stale_claim'} if response_kind == 'stale_claim' else
                         {'status': 'idle', 'delivery': None})
            return httpx.Response(200, json={'status': 'budget_exhausted', 'delivery': None})
        return httpx.Response(200, json={'status': 'waiting'})
    with httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(handle)) as client:
        result = runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, sleep=lambda _: None,
            turn=lambda *args: pytest.fail('No ready delivery'))
    assert result['state'] == 'budget_exhausted'
    assert len(requests) == 2 and requests[0]['request_id'] != requests[1]['request_id']
    assert not controls


def test_pending_claim_permission_error_still_fails_closed(tmp_path, monkeypatch):
    original_unlink = Path.unlink
    def denied(path, *args, **kwargs):
        if path == tmp_path / 'receiver-claim.json':
            raise PermissionError('Cannot remove pending state')
        return original_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', denied)
    client = FakeClient(['idle'])
    with pytest.raises(PermissionError):
        runner.receiver(CONFIG, client, tmp_path, now=lambda: 100, sleep=lambda _: None,
            turn=lambda *args: pytest.fail('No model'))
    assert client.calls[-1][0] == '/v1/chat/control'
    assert client.calls[-1][1]['enabled'] is False


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
    ('read_session', {'max_bytes': [65536]}), ('read_session', {'max_bytes': True}),
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


def test_cli_completed_turn_records_only_reported_token_fields():
    # Official non-interactive JSONL example, with untrusted extra fields added.
    proof = completed_proof()
    proof.event({'type': 'turn.completed', 'usage': {'input_tokens':24763,
        'cached_input_tokens':24448, 'output_tokens':122, 'reasoning_output_tokens':0,
        'credential':'synthetic-secret', 'text':'raw model text', 'cost':9.99}})
    result = proof.finish(0)
    assert result['token_usage'] == {'source':'codex_cli.turn.completed.usage',
        'input_tokens':24763, 'cached_input_tokens':24448, 'output_tokens':122}
    assert result['status'] == 'passed'
    assert all(value not in json.dumps(result) for value in ('synthetic-secret','raw model text','cost','reasoning_output_tokens'))


@pytest.mark.parametrize('usage', [None, {}, [], 'secret', 42])
def test_absent_usage_does_not_change_native_acceptance(usage):
    proof = completed_proof()
    assert set(proof.finish(0)['token_usage'].values()) == {'codex_cli.turn.completed.usage','not_reported'}
    proof.event({'type':'turn.completed','usage':usage})
    result = proof.finish(0)
    assert result['status'] == 'passed'
    assert result['token_usage'] == {'source':'codex_cli.turn.completed.usage',
        'input_tokens':'not_reported','cached_input_tokens':'not_reported','output_tokens':'not_reported'}


@pytest.mark.parametrize('bad', [True, False, -1, 2**53, 10**100, 1.0, '123', None, [], {}])
def test_malformed_token_count_is_not_coerced_or_estimated(bad):
    proof = completed_proof()
    proof.event({'type':'turn.completed','usage':{'input_tokens':bad,'cached_input_tokens':0,'output_tokens':2**53-1}})
    result = proof.finish(0)
    assert result['status'] == 'passed'
    assert result['token_usage']['input_tokens'] == 'not_reported'
    assert result['token_usage']['cached_input_tokens'] == 0
    assert result['token_usage']['output_tokens'] == 2**53-1


def test_usage_is_not_derived_from_other_events_or_accumulated():
    proof = completed_proof()
    proof.event({'type':'item.completed','usage':{'input_tokens':900},'item':{'type':'agent_message','text':'unused'}})
    assert proof.finish(0)['token_usage']['input_tokens'] == 'not_reported'
    proof.event({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':10,'output_tokens':20}})
    proof.event({'type':'turn.completed','usage':{'input_tokens':7}})
    assert proof.finish(0)['token_usage'] == {'source':'codex_cli.turn.completed.usage',
        'input_tokens':7,'cached_input_tokens':'not_reported','output_tokens':'not_reported'}
    with pytest.raises(runner.ReceiverError, match='incomplete'):
        runner.NativeProof(CONFIG, DELIVERY).finish(0)


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
    assert 'skills.max_context_tokens=1' in command
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
            value = {key: CONFIG[key] for key in ('worker_id', 'project_id', 'session_id')} | {'binding_id': '0'*32, 'version': 1, 'generation': 1}
        elif operation == 'claim':
            status = next(self.statuses)
            value = {'status': status, 'delivery': DELIVERY if status == 'ready' else None}
        else:
            value = {'status': 'waiting'}
        return type('Response', (), {'status_code': 200, 'raise_for_status': lambda self: None, 'json': lambda self: value})()


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
        proof = completed_proof()
        proof.event({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':40,'output_tokens':12}})
        return proof.finish(0)
    result = runner.receiver(CONFIG, client, tmp_path, turn=turn, now=lambda: 100, sleep=lambda _: None)
    assert result['native_turns'] == 1
    assert (tmp_path / ('receipt-' + DELIVERY['delivery_id'] + '.json')).exists()
    receipt = json.loads((tmp_path / ('receipt-' + DELIVERY['delivery_id'] + '.json')).read_text(encoding='utf-8'))
    assert receipt['token_usage'] == {'source':'codex_cli.turn.completed.usage',
        'input_tokens':100,'cached_input_tokens':40,'output_tokens':12}
    assert '這是原生對話回覆' not in json.dumps(receipt,ensure_ascii=False)
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
        event('post_session_message', reply(), 'post'),
        {'type':'turn.completed','usage':{'input_tokens':101,'cached_input_tokens':0,'output_tokens':13}}]
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
    assert result['token_usage'] == {'source':'codex_cli.turn.completed.usage',
        'input_tokens':101,'cached_input_tokens':0,'output_tokens':13}
    assert sorted(p.name for p in tmp_path.iterdir()) == ['native-empty', 'native-scope.json']
    assert '這是原生對話回覆' not in (tmp_path / 'native-scope.json').read_text(encoding='utf-8')


def budget_failed(ident='budget-error', **changes):
    value = event('read_session', {}, ident, **changes)
    value['item']['result'] = {'isError':True, 'content':[
        {'type':'text','text':'Error executing tool read_session: response_budget_too_small: Increase max_bytes or request a compact event'}]}
    return value


def identified_proof():
    proof=runner.NativeProof(CONFIG, DELIVERY)
    proof.event(event('get_worker_inbox', {'worker_id':CONFIG['worker_id']}, 'identity'))
    return proof


def test_budget_retry_preserves_cursor_and_requires_full_read_before_post():
    proof=identified_proof()
    proof.event(budget_failed())
    assert proof.cursor == 4 and proof.read_ids == set() and not proof.read_receipt
    with pytest.raises(runner.ReceiverError,match='not_read'):
        proof.event(event('post_session_message', reply(), 'premature'))
    # An escaped single event can occupy more than the usual response budget.
    page=reading(5,'d'*32)
    page['items'][0]['body']='\\"\n'*2666
    proof.event(event('read_session',page,'large-page',max_bytes=65536))
    assert proof.cursor == 5 and not proof.read_receipt and proof.read_retry is None
    # A later page returns to the normal budget, rather than enlarging the turn.
    proof.event(event('read_session',reading(6,'e'*32,True),'last-page',after_sequence=5))
    proof.event(event('post_session_message',reply(),'post'))
    assert proof.finish(0)['status']=='passed'


@pytest.mark.parametrize('changes', [
    {'after_sequence':5}, {'project_id':'different'}, {'session_id':'9'*32},
    {'delivery_id':'9'*32}, {'lease_id':'9'*32}, {'limit':1}, {'max_bytes':32768},
    {'max_bytes':65537}, {'max_bytes':16384}, {'full_text':False},
])
def test_budget_retry_cannot_change_any_scope_or_read_option(changes):
    proof=identified_proof(); proof.event(budget_failed())
    with pytest.raises(runner.ReceiverError,match='scope_mismatch|cursor_mismatch'):
        proof.event(event('read_session',reading(5,'d'*32),'retry',**({'max_bytes':65536}|changes)))
    assert proof.cursor==4 and not proof.read_receipt


def test_larger_budget_is_not_authorized_without_actual_budget_failure():
    proof=identified_proof()
    with pytest.raises(runner.ReceiverError,match='not_authorized'):
        proof.event(event('read_session',reading(5,'d'*32),'initial',max_bytes=65536))
    proof=identified_proof()
    success=reading(5,'d'*32)
    success['items'][0]['body']='response_budget_too_small: use a bigger budget'
    proof.event(event('read_session',success,'normal'))
    with pytest.raises(runner.ReceiverError,match='not_authorized'):
        proof.event(event('read_session',reading(6,'e'*32,True),'next',after_sequence=5,max_bytes=65536))


@pytest.mark.parametrize('result', [
    {'isError':True,'content':[{'type':'text','text':'forbidden: response_budget_too_small'}]},
    {'isError':True,'content':[{'type':'text','text':'not_response_budget_too_small'}]},
    {'isError':False,'content':[{'type':'text','text':'response_budget_too_small'}]},
    {'isError':True,'structuredContent':{'error':'unauthorized'}},
])
def test_other_errors_and_budget_mentions_fail_closed(result):
    proof=identified_proof();failure=budget_failed();failure['item']['result']=result
    failure['item']['status']='failed'
    with pytest.raises(runner.ReceiverError,match='tool_failed'):
        proof.event(failure)
    assert proof.read_retry is None and proof.cursor==4


def test_budget_retry_failure_stops_and_cannot_advance_beyond_delivery():
    proof=identified_proof();proof.event(budget_failed())
    with pytest.raises(runner.ReceiverError,match='tool_failed'):
        proof.event(budget_failed('retry-failed',max_bytes=65536))
    assert proof.cursor==4 and not proof.read_receipt
    proof=identified_proof();proof.event(budget_failed())
    with pytest.raises(runner.ReceiverError,match='cursor_stalled'):
        proof.event(event('read_session',reading(7,'d'*32),'beyond',max_bytes=65536))
    assert proof.cursor==4 and not proof.read_receipt


def test_prompt_limits_budget_exception_to_one_identical_read_retry():
    value=runner.prompt(CONFIG,DELIVERY)
    assert 'response_budget_too_small' in value and 'retry that exact read once with max_bytes=65536' in value
    assert 'Start each later page with max_bytes=16384' in value
    assert 'through_sequence=6' in value and 'do not broaden through_sequence' in value


def test_real_hub_escaped_single_message_needs_larger_budget_without_advancing_failed_read(collaboration):
    from test_delivery import join, claim, delivery_args, reply as hub_reply
    from memory_hub.store import HubError
    hub, _, _=collaboration
    session=room(hub); binding=join(hub,session)
    body='x'+'\x01'*7999
    post(hub,session,B,body=body)
    delivery=claim(hub,binding)['delivery']
    config=CONFIG | {'project_id':session['project_id'],'session_id':session['session_id'],'worker_id':A.worker_id}
    proof=runner.NativeProof(config,delivery)
    def native(name,args,value,ident):
        return {'type':'item.completed','item':{'type':'mcp_tool_call','server':'ys_memory',
            'tool':name,'id':ident,'arguments':{'arguments':args},'result':{'structuredContent':value}}}
    proof.event(native('get_worker_inbox',{'project_id':session['project_id']},
        hub.call('get_worker_inbox',{'project_id':session['project_id']},A),'identity'))
    args=delivery_args(session,delivery,after_sequence=delivery['after_sequence'],limit=20,max_bytes=16384,full_text=True)
    with pytest.raises(HubError) as failed:
        hub.call('read_session',args,A)
    assert failed.value.code=='response_budget_too_small'
    failure=native('read_session',args,{},'budget')
    failure['item']['result']={'isError':True,'structuredContent':{'error':failed.value.code}}
    proof.event(failure)
    assert proof.cursor==delivery['after_sequence'] and not proof.read_receipt
    with pytest.raises(HubError) as premature:
        hub_reply(hub,session,delivery)
    assert premature.value.code=='delivery_not_read'
    retry=args | {'max_bytes':65536}
    page=hub.call('read_session',retry,A)
    assert page['returned_bytes']>16384 and page['items'][0]['body']==body
    proof.event(native('read_session',retry,page,'read'))
    written=hub_reply(hub,session,delivery,body='Verified bounded reply')
    send=delivery_args(session,delivery,body='Verified bounded reply',idempotency_key=delivery['reply_idempotency_key'])
    proof.event(native('post_session_message',send,written,'post'))
    assert proof.finish(0)['status']=='passed'


@pytest.mark.parametrize('language,name', [('en','Codex Local'),('zh-TW','Codex 本機')])
def test_receiver_join_display_name_follows_interface_language(tmp_path,language,name):
    client=FakeClient(['budget_exhausted'])
    runner.receiver(CONFIG | {'language':language},client,tmp_path,now=lambda:100)
    assert client.calls[0][0]=='/v1/chat/join'
    assert client.calls[0][1]['display_name']==name


OWNED = {k: CONFIG[k] for k in ('project_id', 'session_id', 'worker_id')} | {
    'binding_id': '0'*32, 'generation': 3}


def disconnect_state(directory):
    (directory / 'STOP').touch()
    runner.save(directory / 'receiver-binding.json', OWNED)


@pytest.mark.parametrize('lost', [False, True])
def test_disconnect_committed_response_loss_reconciles_without_replaying_cas(tmp_path, lost):
    disconnect_state(tmp_path)
    current = OWNED | {'version': 7, 'status': 'disabled'}
    writes = []
    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'participants': [current.copy()]})
        writes.append(json.loads(request.content))
        current.update(generation=4, version=8, status='disconnected')
        if lost:
            raise httpx.ReadTimeout('committed response lost', request=request)
        return httpx.Response(200, json=current)
    with httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(handle)) as client:
        assert runner.disconnect(CONFIG, client, tmp_path)['state'] == 'disconnected'
        assert runner.disconnect(CONFIG, client, tmp_path)['state'] == 'disconnected'
    assert writes == [{'project_id': CONFIG['project_id'], 'binding_id': '0'*32, 'expected_version': 7}]


@pytest.mark.parametrize('change', [
    {'generation': 4, 'status': 'waiting'}, {'worker_id': 'another-worker'},
    {'session_id': 'f'*32}, {'generation': 5, 'status': 'disconnected'}])
def test_disconnect_never_releases_new_generation_or_other_owner(tmp_path, change):
    disconnect_state(tmp_path)
    def handle(request):
        assert request.method == 'GET'
        return httpx.Response(200, json={'participants': [OWNED | {'version': 7, 'status': 'disabled'} | change]})
    with httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(runner.ReceiverError):
            runner.disconnect(CONFIG, client, tmp_path)


@pytest.mark.parametrize('fault', ['cas', 'transport'])
def test_disconnect_ambiguous_uncommitted_failure_is_not_success_or_retried(tmp_path, fault):
    disconnect_state(tmp_path)
    writes = []
    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'participants': [OWNED | {'version': 8, 'status': 'disabled'}]})
        writes.append(request)
        if fault == 'transport':
            raise httpx.ReadTimeout('no commit', request=request)
        return httpx.Response(409, json={'error': 'stale_binding'})
    with httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(handle)) as client:
        with pytest.raises((httpx.TransportError, httpx.HTTPStatusError)):
            runner.disconnect(CONFIG, client, tmp_path)
    assert len(writes) == 1
    assert not (tmp_path / 'receiver-status.json').exists()


@pytest.mark.parametrize('missing', ['STOP', 'receiver-binding.json', 'native-active'])
def test_disconnect_requires_stopped_and_proven_owned_lifecycle(tmp_path, missing):
    disconnect_state(tmp_path)
    if missing == 'native-active':
        (tmp_path / 'native-active.json').write_text('{}')
    else:
        (tmp_path / missing).unlink()
    with httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(
            lambda request: pytest.fail('No HTTP for unproven ownership/exit'))) as client:
        with pytest.raises(runner.ReceiverError):
            runner.disconnect(CONFIG, client, tmp_path)


def test_disconnect_real_service_restores_manual_post_without_rejoining(collaboration, tmp_path):
    from test_delivery import join, call
    from memory_hub.store import HubError
    hub, _, _ = collaboration
    session = room(hub)
    binding = join(hub, session)
    call(hub, 'control', project_id=binding['project_id'], binding_id=binding['binding_id'],
         expected_version=binding['version'], enabled=False)
    config = {'project_id': session['project_id'], 'session_id': session['session_id'], 'worker_id': A.worker_id}
    (tmp_path / 'STOP').touch()
    runner.save(tmp_path / 'receiver-binding.json', {k: binding[k] for k in OWNED})
    with pytest.raises(HubError):
        post(hub, session, body='manual before disconnect')
    operations = []
    def handle(request):
        operation = request.url.path.rsplit('/', 1)[-1]
        operations.append(operation)
        args = dict(request.url.params) if request.method == 'GET' else json.loads(request.content)
        return httpx.Response(200, json=call(hub, operation, **args))
    with httpx.Client(base_url='https://fixture.test', transport=httpx.MockTransport(handle)) as client:
        assert runner.disconnect(config, client, tmp_path)['state'] == 'disconnected'
    result = post(hub, session, body='manual after disconnect')
    assert result['message_id']
    assert operations == ['status', 'disconnect', 'status']


def test_stopped_lock_timeout_never_enters_release_body(tmp_path, monkeypatch):
    from contextlib import contextmanager
    @contextmanager
    def busy(directory):
        raise OSError('locked')
        yield
    monkeypatch.setattr(runner, 'exclusive', busy)
    times = iter([0, 41])
    with pytest.raises(runner.ReceiverError, match='receiver_still_stopping'):
        with runner.stopped_exclusive(tmp_path, now=lambda: next(times), sleep=lambda _: None):
            pytest.fail('Must not release while receiver owns lock')


def test_terminate_waits_after_kill_and_retains_failure_proof(monkeypatch):
    import subprocess
    monkeypatch.setattr(runner.os, 'name', 'posix')
    class Process:
        def __init__(self): self.waits = 0; self.killed = False
        def poll(self): return None
        def terminate(self): pass
        def kill(self): self.killed = True
        def wait(self, timeout):
            self.waits += 1
            if self.waits == 1: raise subprocess.TimeoutExpired('fixture', timeout)
    process = Process()
    runner.terminate(process)
    assert process.killed and process.waits == 2



def test_windows_failed_tree_stop_does_not_claim_confirmed_exit(monkeypatch):
    class Process:
        pid = 42
        def poll(self): return None
        def wait(self, timeout): pytest.fail('Tree termination was not proved')
    class Result: returncode = 1
    monkeypatch.setattr(runner.subprocess, 'run', lambda *a, **k: Result())
    monkeypatch.setattr(runner.os, 'name', 'nt')
    monkeypatch.setattr(runner.subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    with pytest.raises(runner.ReceiverError, match='native_tree_exit_unconfirmed'):
        runner.terminate(Process())


def test_stopped_exclusive_does_not_retry_oserror_inside_body(tmp_path, monkeypatch):
    from contextlib import contextmanager
    entries = []
    @contextmanager
    def available(directory):
        entries.append(directory)
        yield
    monkeypatch.setattr(runner, 'exclusive', available)
    with pytest.raises(PermissionError):
        with runner.stopped_exclusive(tmp_path):
            raise PermissionError('status write denied')
    assert entries == [tmp_path]


@pytest.mark.parametrize('error', [FileNotFoundError('synthetic missing'), PermissionError('synthetic denied')])
def test_failed_native_start_removes_only_unlaunched_marker(monkeypatch, tmp_path, error):
    def failed(*args, **kwargs):
        raise error
    monkeypatch.setattr(runner.subprocess, 'Popen', failed)
    with pytest.raises(type(error)):
        runner.native_turn(CONFIG, DELIVERY, tmp_path, lambda: {'status':'processing'}, lambda: False)
    assert not (tmp_path / 'native-active.json').exists()
    assert (tmp_path / 'native-scope.json').exists()



def test_native_start_preserves_preexisting_unknown_marker(monkeypatch,tmp_path):
    raw=b'{"state":"starting","synthetic":"prior"}'
    (tmp_path/'native-active.json').write_bytes(raw)
    calls=[]
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k:calls.append(True))
    with pytest.raises(runner.ReceiverError,match='native_exit_unconfirmed'):
        runner.native_turn(CONFIG,DELIVERY,tmp_path,lambda:{'status':'processing'},lambda:False)
    assert (tmp_path/'native-active.json').read_bytes()==raw and calls==[]


@pytest.mark.parametrize('usage', [None, {'input_tokens':123,'cached_input_tokens':0,'output_tokens':4}])
def test_failed_native_turn_preserves_only_observed_usage(monkeypatch,tmp_path,usage):
    stream=[{'type':'turn.completed','usage':usage},{'type':'error','message':'canary-private-provider-error'}]
    class Process:
        stdout=io.StringIO('\n'.join(json.dumps(x) for x in stream)+'\n')
        def poll(self):return 0
        def wait(self,timeout):return 0
    monkeypatch.setattr(runner.subprocess,'Popen',lambda *a,**k:Process())
    with pytest.raises(runner.ReceiverError,match='native_turn_failed'):
        runner.native_turn(CONFIG,DELIVERY,tmp_path,lambda:{'status':'processing'},lambda:False)
    raw=(tmp_path/('native-failure-'+DELIVERY['delivery_id']+'.json')).read_text()
    record=json.loads(raw)
    assert record['token_usage']==runner.NativeProof.reported_usage(usage)
    assert record['phase']=='execution' and record['error_code']=='native_turn_failed'
    assert record['server_disposition']=='not_reconciled' and record['retry_authorized'] is False
    assert 'canary-private-provider-error' not in raw
    assert not (tmp_path/('receipt-'+DELIVERY['delivery_id']+'.json')).exists()


def test_incomplete_local_proof_preserves_observed_reply_without_retry(tmp_path):
    proof=runner.NativeProof(CONFIG,DELIVERY)
    proof.post={'synthetic':'canary-private-post'}
    runner.record_native_failure(tmp_path,DELIVERY,proof,'execution',RuntimeError('canary-private-token'))
    raw=(tmp_path/('native-failure-'+DELIVERY['delivery_id']+'.json')).read_text()
    record=json.loads(raw)
    assert record['native_reply_receipt_observed'] is True
    assert record['status']=='incomplete' and record['server_disposition']=='not_reconciled'
    assert record['token_usage']['input_tokens']=='not_reported'
    assert 'canary-private' not in raw and record['error_code']=='native_exception'


def test_repeated_fenced_restart_keeps_prior_status_without_nesting(tmp_path):
    status=tmp_path/'receiver-status.json';raw=b'{"binding_id":"synthetic-old","native_turns":1}'
    status.write_bytes(raw)
    result={'state':'failed','error_code':'native_exit_unconfirmed_preserve_binding','at':123}
    for _ in range(3):runner.record_receiver_failure(tmp_path,result)
    assert status.read_bytes()==raw
    assert json.loads((tmp_path/'receiver-restart-failure.json').read_text())==result
    assert sorted(p.name for p in tmp_path.iterdir())==['receiver-restart-failure.json','receiver-status.json']


def test_native_failure_preserves_first_phase(tmp_path):
    proof = runner.NativeProof(CONFIG, DELIVERY)
    delivery = {'delivery_id': 'fixture-delivery'}
    runner.record_native_failure(tmp_path, delivery, proof, 'execution', runner.ReceiverError('native_turn_failed'))
    path = tmp_path / 'native-failure-fixture-delivery.json'
    first = path.read_bytes()
    runner.record_native_failure(tmp_path, delivery, proof, 'cleanup', RuntimeError('private-canary'))
    assert path.read_bytes() == first
