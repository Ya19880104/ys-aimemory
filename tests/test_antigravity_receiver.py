import inspect
import json
import os
import subprocess
import time
from unittest.mock import Mock

import pytest

from memory_hub import client_antigravity_receiver as receiver
from memory_hub.client_antigravity_receiver import durable, run
from memory_hub.client_antigravity_receiver import NativeContainmentError
from memory_hub.client_antigravity_receiver import official_metadata_admission, admitted
from memory_hub.client_watch import exclusive
from test_sessions import collaboration, room, human, values, A
from test_index import _migration_db


@pytest.fixture
def rig(tmp_path):
    config = dict(client='gemini', project=str(tmp_path), project_id='project', session_id='room',
        binding_id='binding', generation=1, native_session_id='11111111-1111-1111-1111-111111111111',
        expires_at=400, max_sends=3, idempotency_key='join',
        admission_mode='manually_admitted_dedicated_test')
    event = dict(kind='manual_initial', event_id='initial', conversationId=config['native_session_id'],
        workspacePaths=[str(tmp_path.resolve())], observed_at=100, ui_idle_confirmed=True,
        exclusive_test_conversation=True)
    binding = dict(binding_id='binding', generation=1, project_id='project', session_id='room',
        status='waiting', latest_delivery=None)
    calls = []
    def post(path, json):
        operation = path.rsplit('/', 1)[1]
        calls.append(operation)
        value = {'participants': [binding]} if operation == 'status' else {
            'status': 'ready', 'delivery': dict(delivery_id='delivery', lease_id='lease', lease_until=300)}
        response = Mock()
        response.json.return_value = value
        return response
    def get(path, params):
        assert path == '/v1/chat/status'
        assert params == {'project_id': 'project', 'session_id': 'room'}
        return post(path, params)
    return config, event, binding, Mock(post=post, get=get), calls, tmp_path


@pytest.mark.parametrize('completion', ['replied', 'no_reply'])
def test_return_is_not_idle_and_second_send_needs_real_event(rig,completion):
    config, event, binding, client, calls, directory = rig
    def send(*args, **kwargs):
        binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': completion}
        return Mock(returncode=0)
    execute = Mock(side_effect=send)
    clock = [110]
    states = []
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: clock[0],
               sleep=lambda _: clock.__setitem__(0, 401), on_state=states.append,
               execute=execute) == 'expired'
    assert states == ['needs_native_idle']
    assert execute.call_count == 1
    assert calls[0] == 'status'
    journal=json.loads((directory/'receiver-journal.json').read_text())
    assert journal['attempts'][0]['state']==completion


@pytest.mark.parametrize('state', ['intent', 'unknown', 'returned'])
def test_restart_never_claims_or_resends_ambiguous_attempt(rig, state):
    config, event, binding, client, calls, directory = rig
    scope = {key: config[key] for key in ('project_id', 'session_id', 'binding_id', 'generation', 'native_session_id')}
    durable(directory / 'receiver-journal.json', dict(scope=scope, attempts=[
        dict(delivery_id='delivery', lease_until=105, state=state)], used_events=['initial'], claim_request=None))
    execute = Mock()
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110,
               execute=execute) == 'unresolved'
    assert calls == ['status']
    execute.assert_not_called()


def test_crash_after_intent_before_dispatch_is_preserved(rig):
    config, event, binding, client, calls, directory = rig
    original = client.post
    def crash(path, **kwargs):
        if path.endswith('/dispatched'):
            raise RuntimeError('simulated crash')
        return original(path, **kwargs)
    client.post = crash
    with pytest.raises(RuntimeError):
        run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110)
    assert json.loads((directory / 'receiver-journal.json').read_text())['attempts'][0]['state'] == 'intent'


def test_timeout_does_not_retry(rig):
    config, event, binding, client, calls, directory = rig
    clock = [110]
    execute = Mock(side_effect=subprocess.TimeoutExpired('agentapi', 10))
    def sleep(_):
        clock[0] = 301
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: clock[0],
               sleep=sleep, execute=execute) == 'unresolved'
    assert execute.call_count == 1
    assert calls.count('claim') == 1


def test_generation_change_and_stop_prevent_dispatch(rig):
    config, event, binding, client, calls, directory = rig
    binding['generation'] = 2
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110) == 'disconnected'
    (directory / 'STOP').touch()
    calls.clear()
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110) == 'stopped'
    assert calls == []


def test_fresh_native_stop_permits_two_bounded_turns(rig):
    config, event, binding, client, calls, directory = rig
    config['max_sends'] = 2
    event.update(kind='native_stop', fullyIdle=True, terminationReason='model_stop')
    counter = [0]
    original = client.post
    def post(path, **kwargs):
        response = original(path, **kwargs)
        if path.endswith('/claim'):
            value = response.json()
            value['delivery']['delivery_id'] = 'delivery-' + str(counter[0])
        return response
    client.post = post
    def admission():
        return event | {'event_id': 'native-' + str(counter[0])}
    def send(*args, **kwargs):
        counter[0] += 1
        binding['latest_delivery'] = {'delivery_id': 'delivery-' + str(counter[0] - 1), 'status': 'replied'}
        return Mock(returncode=0)
    execute = Mock(side_effect=send)
    assert run(config, client, directory, 'agentapi', admission, now=lambda: 110,
               execute=execute) == 'budget_exhausted'
    assert execute.call_count == 2


def test_live_process_lock_blocks_second_receiver(rig):
    config, event, binding, client, calls, directory = rig
    with exclusive(directory / 'receiver-process.lock') as held:
        assert held
        assert run(config, client, directory, 'agentapi', lambda: event,
                   now=lambda: 110) == 'already_running'
    assert calls == []


def test_stale_admission_waits_then_accepts_new_real_stop(rig):
    config, event, binding, client, calls, directory = rig
    config['max_sends'] = 1
    clock = [170]
    states = []
    def fresh_after_wait(_):
        event.update(kind='native_stop', event_id='fresh-stop', observed_at=171,
                     fullyIdle=True, terminationReason='model_stop')
        clock[0] = 171
    def send(*args, **kwargs):
        binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': 'replied'}
        return Mock(returncode=0)
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: clock[0],
        sleep=fresh_after_wait, execute=send, on_state=states.append) == 'budget_exhausted'
    assert states == ['needs_native_idle']


def test_official_host_queue_scope_provider_and_strict_default(rig):
    config, event, binding, client, calls, directory = rig
    config['native_project_id'] = 'native-project'
    result = Mock(returncode=0, stdout=json.dumps({'response': {'conversationMetadata': {'metadata': {
        'workspaceUris':[directory.resolve().as_uri()], 'projectId':'native-project'}}}}).encode())
    execute = Mock(return_value=result)
    metadata = official_metadata_admission(config, 'agentapi', now=lambda:110, execute=execute)
    assert metadata and 'fullyIdle' not in metadata
    assert not admitted(config, metadata, 110)
    config['admission_mode'] = 'official_host_queue'
    assert admitted(config, metadata, 110)
    result.stdout = json.dumps({'response': {'conversationMetadata': {'metadata': {
        'workspaceUris':['file:///wrong'], 'projectId':'native-project'}}}}).encode()
    assert official_metadata_admission(config, 'agentapi', execute=execute) is None


def test_queue_rechecks_scope_before_each_send(rig):
    config, event, binding, client, calls, directory = rig
    config.update(admission_mode='official_host_queue', native_project_id='native-project', max_sends=1)
    event.update(kind='official_metadata', scope_verified=True, native_project_id='native-project')
    provider = Mock(side_effect=[event, None])
    execute = Mock()
    assert run(config,client,directory,'agentapi',provider,now=lambda:110,execute=execute) == 'unresolved'
    assert provider.call_count == 2
    execute.assert_not_called()


@pytest.mark.parametrize('failure', [OSError('offline'), subprocess.TimeoutExpired('agentapi',10),
                                     Mock(returncode=0,stdout=b'not-json')])
def test_metadata_failure_recovers_without_notification(rig, failure):
    config, event, binding, client, calls, directory = rig
    config.update(admission_mode='official_host_queue',native_project_id='native-project')
    good = Mock(returncode=0,stdout=json.dumps({'response':{'conversationMetadata':{'metadata':{
        'workspaceUris':[directory.resolve().as_uri()],'projectId':'native-project'}}}}).encode())
    execute = Mock(side_effect=[failure,good])
    assert official_metadata_admission(config,'agentapi',execute=execute) is None
    assert official_metadata_admission(config,'agentapi',execute=execute)['scope_verified']
    assert all(call.args[0][1]=='get-conversation-metadata' for call in execute.call_args_list)


def test_real_rest_contract_claim_dispatch_and_restart_no_resend(collaboration, tmp_path):
    from fastapi.testclient import TestClient
    from memory_hub.app import create_app
    hub, url, sqlite = collaboration
    session = room(hub)
    token = 'synthetic-antigravity-receiver-token'
    app = create_app(database_url=url, allow_sqlite=sqlite,
                     auth_tokens=json.dumps({token: A.model_dump()}))
    with TestClient(app, headers={'Authorization': 'Bearer ' + token}) as client:
        joined = client.post('/v1/chat/join', json=values(session, client='gemini', display_name='Gemini',
            native_session_id='11111111-1111-1111-1111-111111111111', max_turns=2,
            ttl_seconds=600, idempotency_key='real-receiver-test')).json()
        hub.sessions.call('post_session_message', values(session, body='Synthetic hello',
                          idempotency_key='real-human'), human())
        started = time.time()
        clock = [started]
        config = dict(client='gemini', project=str(tmp_path), **values(session),
            binding_id=joined['binding_id'], generation=joined['generation'],
            native_session_id='11111111-1111-1111-1111-111111111111', expires_at=started+590,
            max_sends=2, idempotency_key='real-receiver-test', admission_mode='manually_admitted_dedicated_test')
        event = dict(kind='manual_initial', event_id='real-initial', observed_at=started,
            conversationId=config['native_session_id'], workspacePaths=[str(tmp_path.resolve())],
            ui_idle_confirmed=True, exclusive_test_conversation=True)
        execute = Mock(return_value=Mock(returncode=0))
        assert run(config, client, tmp_path, 'agentapi', lambda: event, now=lambda: clock[0],
                   sleep=lambda _: clock.__setitem__(0, started+301), execute=execute) == 'unresolved'
        packet = json.loads((tmp_path / 'chat-delivery.json').read_text())
        assert len(packet['delivery_id']) == len(packet['lease_id']) == 32
        assert packet['join_key'] == config['idempotency_key']
        state = client.get('/v1/chat/status', params=values(session)).json()['participants'][0]
        assert state['latest_delivery']['status'] == 'dispatched'
        assert run(config, client, tmp_path, 'agentapi', lambda: event, now=lambda: started+301,
                   execute=execute) == 'unresolved'
        assert execute.call_count == 1


@pytest.mark.parametrize('attempts', [[], [{'delivery_id':'old', 'lease_until':99, 'state':'replied'}]])
def test_stale_claim_rotates_only_without_any_native_attempt(rig, attempts):
    import httpx
    config, event, binding, client, calls, directory = rig
    event.update(kind='native_stop', fullyIdle=True, terminationReason='model_stop')
    scope = {key: config[key] for key in ('project_id','session_id','binding_id','generation','native_session_id')}
    durable(directory/'receiver-journal.json', {'scope':scope, 'attempts':attempts, 'used_events':[], 'claim_request':'saved-request'})
    original = client.post
    keys = []
    def post(path, **kwargs):
        if path.endswith('/claim'):
            keys.append(kwargs['json']['request_id'])
            response = httpx.Response(409, json={'error':'stale_claim'}, request=httpx.Request('POST','https://hub.example.test/claim'))
            return response
        return original(path, **kwargs)
    client.post = post
    execute = Mock()
    clock = [110]
    def sleep(_): clock[0] = 401
    result = run(config, client, directory, 'agentapi', lambda:event, now=lambda:clock[0], sleep=sleep, execute=execute)
    journal = json.loads((directory/'receiver-journal.json').read_text())
    assert result == ('expired' if not attempts else 'unresolved')
    assert journal['claim_request'] == (None if not attempts else 'saved-request')
    assert journal['attempts'] == attempts and journal['used_events'] == []
    assert keys == ['saved-request']
    execute.assert_not_called()


@pytest.mark.parametrize('status,body', [(409,{'error':'other'}),(500,{'error':'stale_claim'}),(409,[])])
def test_other_claim_errors_preserve_request_and_do_not_send(rig,status,body):
    import httpx
    config,event,binding,client,calls,directory=rig
    original=client.post
    def failed(path,**kwargs):
        if path.endswith('/claim'):
            return httpx.Response(status,json=body,request=httpx.Request('POST','https://hub.example.test/claim'))
        return original(path,**kwargs)
    client.post=failed
    execute=Mock()
    with pytest.raises(httpx.HTTPStatusError):
        run(config,client,directory,'agentapi',lambda:event,now=lambda:110,execute=execute)
    journal=json.loads((directory/'receiver-journal.json').read_text())
    assert journal['claim_request'] and not journal['attempts'] and not journal['used_events']
    execute.assert_not_called()



def test_stale_unattempted_claim_recovery_uses_new_key_once(rig):
    import httpx
    config,event,binding,client,calls,directory=rig
    original=client.post
    keys=[]
    def post(path,**kwargs):
        if path.endswith('/claim'):
            keys.append(kwargs['json']['request_id'])
            if len(keys)==1:
                return httpx.Response(409,json={'error':'stale_claim'},request=httpx.Request('POST','https://hub.example.test/claim'))
        return original(path,**kwargs)
    client.post=post
    def execute(*args,**kwargs):
        (directory/'STOP').touch()
        return Mock(returncode=0)
    send=Mock(side_effect=execute)
    result=run(config,client,directory,'agentapi',lambda:event,now=lambda:110,sleep=lambda _:None,execute=send)
    assert result=='stopped' and len(keys)==2 and keys[0]!=keys[1] and send.call_count==1
    journal=json.loads((directory/'receiver-journal.json').read_text())
    assert len(journal['attempts'])==1 and journal['attempts'][0]['state']=='returned'
    assert journal['claim_request'] is None and journal['used_events']==['initial']


def contained(value):
    value.containment, value.tree_exit_verified = 'windows_job', True
    return value


@pytest.mark.parametrize('outcome,fields', [
    (lambda: contained(subprocess.CompletedProcess(['agentapi'], 0)),
     {'state': 'returned', 'returncode': 0, 'containment': 'windows_job', 'tree_exit_verified': True}),
    (lambda: contained(subprocess.TimeoutExpired('agentapi', 10)),
     {'state': 'unknown', 'error_type': 'TimeoutExpired', 'containment': 'windows_job', 'tree_exit_verified': True}),
    # Injected/POSIX executors carry no owned-tree proof: no exit claim is recorded.
    (lambda: Mock(returncode=0), {'state': 'returned', 'returncode': 0, 'containment': 'none'}),
    (lambda: subprocess.TimeoutExpired('agentapi', 10),
     {'state': 'unknown', 'error_type': 'TimeoutExpired', 'containment': 'none'}),
    # A launch-phase failure keeps its fixed code; the CLI never ran.
    (lambda: contained(NativeContainmentError('native_job_create_failed')),
     {'state': 'unknown', 'error_type': 'NativeContainmentError', 'containment': 'windows_job',
      'tree_exit_verified': True, 'error_code': 'native_job_create_failed'})])
def test_attempt_records_only_exact_owned_tree_exit_evidence(rig, outcome, fields):
    config, event, binding, client, calls, directory = rig
    def execute(*args, **kwargs):
        (directory / 'STOP').touch()
        value = outcome()
        if isinstance(value, BaseException):
            raise value
        return value
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110,
               execute=execute) == 'stopped'
    attempt = json.loads((directory / 'receiver-journal.json').read_text())['attempts'][0]
    assert attempt == {'delivery_id': 'delivery', 'lease_until': 300} | fields


def test_unconfirmed_tree_exit_stays_unresolved_and_fences_restart(rig):
    config, event, binding, client, calls, directory = rig
    def execute(*args, **kwargs):
        # Even a later replied receipt cannot clear a possibly live native tree.
        binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': 'replied'}
        raise receiver.TreeExitUnconfirmed()
    send = Mock(side_effect=execute)
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110,
               execute=send) == 'unresolved'
    journal = json.loads((directory / 'receiver-journal.json').read_text())
    assert journal['attempts'] == [{'delivery_id': 'delivery', 'lease_until': 300, 'state': 'unknown',
        'error_code': 'native_tree_exit_unconfirmed', 'containment': 'windows_job',
        'tree_exit_verified': False, 'phase': 'send'}]
    calls.clear()
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110,
               execute=send) == 'unresolved'
    assert calls == [] and send.call_count == 1
    assert json.loads((directory / 'receiver-journal.json').read_text()) == journal


def test_metadata_unconfirmed_tree_exit_is_raised_not_a_retryable_miss(rig):
    config = rig[0]
    execute = Mock(side_effect=receiver.TreeExitUnconfirmed())
    with pytest.raises(receiver.TreeExitUnconfirmed, match='^native_tree_exit_unconfirmed$'):
        official_metadata_admission(config, 'agentapi', execute=execute)


METADATA_FENCE = {'error_code': 'native_tree_exit_unconfirmed', 'containment': 'windows_job',
                  'tree_exit_verified': False, 'phase': 'metadata'}


def queue_rig(rig):
    """Real metadata provider over one injected executor for metadata and send."""
    config, event, binding, client, calls, directory = rig
    config.update(admission_mode='official_host_queue', native_project_id='native-project')
    good = Mock(returncode=0, stdout=json.dumps({'response': {'conversationMetadata': {'metadata': {
        'workspaceUris': [directory.resolve().as_uri()], 'projectId': 'native-project'}}}}).encode())
    execute = Mock()
    def start():
        return run(config, client, directory, 'agentapi', lambda: official_metadata_admission(
            config, 'agentapi', now=lambda: 110, execute=execute), now=lambda: 110, execute=execute)
    return config, binding, calls, directory, good, execute, start


@pytest.mark.parametrize('prior', [None, [{'delivery_id': 'old', 'lease_until': 99, 'state': 'replied'}]])
def test_metadata_unconfirmed_before_claim_is_journaled_and_fences_restart(rig, prior):
    config, binding, calls, directory, good, execute, start = queue_rig(rig)
    path = directory / 'receiver-journal.json'
    scope = {key: config[key] for key in ('project_id', 'session_id', 'binding_id', 'generation', 'native_session_id')}
    if prior:
        durable(path, dict(scope=scope, attempts=prior, used_events=['old-event'], claim_request=None))
    execute.side_effect = receiver.TreeExitUnconfirmed()
    assert start() == 'unresolved'
    journal = json.loads(path.read_text())
    assert journal == dict(scope=scope, attempts=prior or [], used_events=['old-event'] if prior else [],
                           claim_request=None, native_tree_unconfirmed=METADATA_FENCE)
    assert calls == ['status'] and execute.call_count == 1
    # Healthy metadata later must not relaunch any CLI or reach the Hub.
    execute.side_effect, execute.return_value = None, good
    calls.clear()
    assert start() == 'unresolved'
    assert calls == [] and execute.call_count == 1
    assert json.loads(path.read_text()) == journal


def test_metadata_unconfirmed_after_dispatch_fences_restart_despite_later_receipt(rig):
    config, binding, calls, directory, good, execute, start = queue_rig(rig)
    path = directory / 'receiver-journal.json'
    execute.side_effect = [good, receiver.TreeExitUnconfirmed()]
    assert start() == 'unresolved'
    assert [call.args[0][1] for call in execute.call_args_list] == ['get-conversation-metadata'] * 2
    assert calls == ['status', 'heartbeat', 'claim', 'dispatched']
    journal = json.loads(path.read_text())
    assert journal['attempts'] == [{'delivery_id': 'delivery', 'lease_until': 300, 'state': 'unknown'} |
                                   METADATA_FENCE]
    # A Hub receipt settles the delivery, never the possibly live metadata tree.
    binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': 'replied'}
    execute.side_effect, execute.return_value = None, good
    calls.clear()
    assert start() == 'unresolved'
    assert calls == [] and execute.call_count == 2
    assert json.loads(path.read_text()) == journal


def test_default_executor_is_owned_windows_job():
    expected = receiver.contained_run if os.name == 'nt' else subprocess.run
    for function in (run, official_metadata_admission):
        assert inspect.signature(function).parameters['execute'].default is expected
