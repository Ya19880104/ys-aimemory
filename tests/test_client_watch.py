import json
from pathlib import Path
import httpx

from memory_hub.client_watch import bind_activation, exclusive, reminder, watch


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
    assert '"delivery_id": "d"' in message
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
    assert 'once' in text and 'through_sequence=12' in text
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
