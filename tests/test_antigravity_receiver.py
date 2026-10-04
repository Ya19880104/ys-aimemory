import json
import subprocess
from unittest.mock import Mock

import pytest

from memory_hub.client_antigravity_receiver import durable, run
from memory_hub.client_watch import exclusive


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
    return config, event, binding, Mock(post=post), calls, tmp_path


def test_return_is_not_idle_and_second_send_needs_real_event(rig):
    config, event, binding, client, calls, directory = rig
    def send(*args, **kwargs):
        binding['latest_delivery'] = {'delivery_id': 'delivery', 'status': 'replied'}
        return Mock(returncode=0)
    execute = Mock(side_effect=send)
    assert run(config, client, directory, 'agentapi', lambda: event, now=lambda: 110,
               execute=execute) == 'needs_native_idle'
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
