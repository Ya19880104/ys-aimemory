import json
import subprocess
import time
from unittest.mock import Mock

import pytest

from memory_hub.client_antigravity_receiver import durable, run
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


def test_return_is_not_idle_and_second_send_needs_real_event(rig):
    config, event, binding, client, calls, directory = rig
    def send(*args, **kwargs):
        binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': 'replied'}
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
