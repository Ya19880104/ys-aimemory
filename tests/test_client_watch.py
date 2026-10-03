import json
from pathlib import Path
import httpx

import pytest
from memory_hub.client_watch import WatchStopped, bind_activation, exclusive, reminder, watch


def config():
    return dict(project_id='p', session_id='room', client='claude',
        display_name='Claude', native_session_id='native', after_sequence=10,
        max_turns=20, idempotency_key='fixed-install', expires_at=500)


def delivery():
    return dict(delivery_id='d', lease_id='fence', after_sequence=10,
        through_sequence=12, reply_idempotency_key='once')


def test_idle_pause_and_ready_never_read_or_write_message(tmp_path):
    requests, sleeps = [], []
    statuses = iter(['idle', 'paused', 'ready'])
    clock = [100]
    def handle(req):
        requests.append((req.url.path, json.loads(req.content)))
        op = req.url.path.rsplit('/', 1)[-1]
        if op == 'join':
            return httpx.Response(200, json={'binding_id': 'b'})
        if op == 'claim':
            state = next(statuses)
            return httpx.Response(200, json={'status': state, 'delivery': delivery()})
        return httpx.Response(200, json={})
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    with httpx.Client(base_url='https://hub.test', transport=httpx.MockTransport(handle)) as client:
        message = watch(config(), {'hook_event_name':'Stop', 'session_id':'native'},
            client, tmp_path/'status.json', now=lambda:clock[0], sleep=sleep)
    assert sleeps == [3,5]
    assert requests[-1][0] == '/v1/chat/dispatched'
    assert requests[-1][1]['lease_id'] == 'fence'
    assert not any('/v1/tools/' in path for path,_ in requests)
    assert 'chat_read' in message and 'chat_reply' in message
    assert json.loads((tmp_path/'chat-delivery.json').read_text())['delivery_id'] == 'd'
    assert json.loads((tmp_path/'status.json').read_text())['state'] == 'handed_to_client'


def test_wrong_native_conversation_cannot_poll(tmp_path):
    class Never:
        def post(self, *args, **kwargs):
            raise AssertionError('wrong native conversation reached Hub')
    assert watch(config(), {'hook_event_name':'Stop','session_id':'other'}, Never(),
                 tmp_path/'status.json', now=lambda:100) is None


def test_stop_and_expiry_make_zero_requests(tmp_path):
    class Never:
        def post(self, *args, **kwargs):
            raise AssertionError('stopped listener reached Hub')
    event = {'hook_event_name':'Stop','session_id':'native'}
    assert watch(config(), event, Never(), tmp_path/'status.json', now=lambda:501) is None
    (tmp_path/'STOP').touch()
    assert watch(config(), event, Never(), tmp_path/'status.json', now=lambda:100) is None


def test_budget_exhausted_does_not_wake(tmp_path):
    def handle(req):
        return httpx.Response(200, json={'binding_id':'b'} if req.url.path.endswith('join')
             else {'status':'budget_exhausted'})
    with httpx.Client(base_url='https://hub.test', transport=httpx.MockTransport(handle)) as client:
        assert watch(config(), {'hook_event_name':'Stop','session_id':'native'}, client,
            tmp_path/'status.json', now=lambda:100) is None


def test_kernel_lock_releases_without_deleting_stale_file(tmp_path):
    lock = tmp_path/'listener.lock'
    with exclusive(lock) as first:
        assert first
        with exclusive(lock) as second:
            assert not second
    with exclusive(lock) as restarted:
        assert restarted


def test_notification_contains_metadata_not_chat_body():
    record = delivery() | {'body':'untrusted message text'}
    text = reminder(config(), record)
    assert record['body'] not in text
    assert 'stable write key' in text and 'ready_to_reply=true' in text
    assert 'brief English conversational reply' in text
    assert 'brief Traditional Chinese conversational reply' in reminder(config() | {'language':'zh-TW'}, record)


def test_one_time_activation_matches_exact_response_and_project(tmp_path):
    c = config() | {'native_session_id': None, 'project_path': str(tmp_path),
                    'activation_phrase': 'YS_MEMORY_JOIN_random'}
    event = {'hook_event_name':'Stop', 'session_id':'new-native', 'cwd':str(tmp_path),
             'last_assistant_message':'quoted YS_MEMORY_JOIN_random not an activation'}
    assert not bind_activation(c, event)
    event['last_assistant_message'] = 'YS_MEMORY_JOIN_random'
    assert not bind_activation(c, event | {'cwd':str(tmp_path/'other')})
    assert bind_activation(c, event)
    assert c['native_session_id'] == 'new-native' and 'activation_phrase' not in c
    assert not bind_activation(c, event | {'session_id':'other'})


def test_deploy_outage_recovers_without_model_or_cursor_advance(tmp_path):
    clock, requests, joins = [100], [], []
    def handle(req):
        data = json.loads(req.content)
        requests.append(req.url.path)
        if req.url.path.endswith('join'):
            joins.append(data)
            if len(joins) == 1:
                return httpx.Response(503)
            if len(joins) == 2:
                raise httpx.ConnectError('offline', request=req)
            return httpx.Response(200, json={'binding_id':'b'})
        if req.url.path.endswith('claim'):
            return httpx.Response(200, json={'status':'ready','delivery':delivery()})
        return httpx.Response(200, json={})
    with httpx.Client(base_url='https://hub.test', transport=httpx.MockTransport(handle)) as client:
        result = watch(config(), {'hook_event_name':'Stop','session_id':'native'},client,
            tmp_path/'status.json',now=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s))
    assert len(joins) == 3 and joins[0] == joins[1] == joins[2]
    assert clock[0] == 106 and result.count('new message arrived') == 1
    assert all('/v1/tools/' not in path for path in requests)


def test_pause_between_claim_and_dispatch_does_not_wake_with_stale_lease(tmp_path):
    claims, dispatches, clock = [0], [0], [100]
    def handle(req):
        if req.url.path.endswith('join'):
            return httpx.Response(200,json={'binding_id':'b'})
        if req.url.path.endswith('claim'):
            claims[0] += 1
            if claims[0] == 2:
                return httpx.Response(200,json={'status':'paused'})
            return httpx.Response(200,json={'status':'ready','delivery':delivery() | {'lease_id':str(claims[0])}})
        if req.url.path.endswith('dispatched'):
            dispatches[0] += 1
            return httpx.Response(409 if dispatches[0] == 1 else 200,json={})
        return httpx.Response(200,json={})
    with httpx.Client(base_url='https://hub.test',transport=httpx.MockTransport(handle)) as client:
        result = watch(config(), {'hook_event_name':'Stop','session_id':'native'},client,
            tmp_path/'status.json',now=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s))
    assert 'chat_read' in result
    assert json.loads((tmp_path/'chat-delivery.json').read_text())['lease_id'] == '3'


def test_reconnect_remains_bounded_by_original_expiry(tmp_path):
    clock = [100]
    with httpx.Client(base_url='https://hub.test', transport=httpx.MockTransport(lambda r:httpx.Response(503))) as client:
        with pytest.raises(WatchStopped):
            watch(config() | {'expires_at':110}, {'hook_event_name':'Stop','session_id':'native'},client,
                tmp_path/'status.json',now=lambda:clock[0],sleep=lambda s:clock.__setitem__(0,clock[0]+s))
    assert clock[0] == 110


def test_revoked_credentials_do_not_retry_or_wake(tmp_path):
    requests=[]
    def handle(req):
        requests.append(req)
        return httpx.Response(403)
    with httpx.Client(base_url='https://hub.test',transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            watch(config(), {'hook_event_name':'Stop','session_id':'native'},client,
                tmp_path/'status.json',now=lambda:100,sleep=lambda _:pytest.fail('must not retry'))
    assert len(requests) == 1


def test_activation_accepts_existing_nested_project_directory(tmp_path):
    nested = tmp_path / 'src' / 'component'
    nested.mkdir(parents=True)
    c = config() | {'native_session_id': None, 'project_path': str(tmp_path),
                    'activation_phrase': 'YS_MEMORY_JOIN_random'}
    assert bind_activation(c, {'hook_event_name': 'Stop', 'session_id': 'new-native',
        'cwd': str(nested), 'last_assistant_message': 'YS_MEMORY_JOIN_random'})
    assert c['native_session_id'] == 'new-native'


@pytest.mark.parametrize('change,reason', [
    ({'last_assistant_message': 'YS_MEMORY_JOIN_wrong'}, 'phrase_mismatch'),
    ({'session_id': ''}, 'invalid_native_session'),
    ({'cwd': ''}, 'project_mismatch'),
    ({'cwd': 'missing'}, 'project_mismatch'),
])
def test_explicit_activation_mismatch_is_diagnostic_without_binding(tmp_path, change, reason):
    c = config() | {'native_session_id': None, 'project_path': str(tmp_path),
                    'activation_phrase': 'YS_MEMORY_JOIN_random'}
    original = c.copy()
    event = {'hook_event_name': 'Stop', 'session_id': 'new-native',
             'cwd': str(tmp_path), 'last_assistant_message': 'YS_MEMORY_JOIN_random'} | change
    state = tmp_path / 'status.json'
    assert not bind_activation(c, event, state)
    assert c == original
    record = json.loads(state.read_text())
    assert record['state'] == 'activation_mismatch' and record['reason'] == reason
    assert set(record) == {'state', 'reason', 'at'}


def test_activation_rejects_existing_outside_project_and_quiet_unrelated_stop(tmp_path):
    project, outside = tmp_path / 'project', tmp_path / 'project-other'
    project.mkdir()
    outside.mkdir()
    c = config() | {'native_session_id': None, 'project_path': str(project),
                    'activation_phrase': 'YS_MEMORY_JOIN_random'}
    state = tmp_path / 'status.json'
    event = {'hook_event_name': 'Stop', 'session_id': 'new-native', 'cwd': str(outside),
             'last_assistant_message': 'ordinary assistant response'}
    assert not bind_activation(c, event, state)
    assert not state.exists()
    assert not bind_activation(c, event | {'last_assistant_message': 'YS_MEMORY_JOIN_random'}, state)
    assert json.loads(state.read_text())['reason'] == 'project_mismatch'
    assert c['native_session_id'] is None
