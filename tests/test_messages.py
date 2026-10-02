"""Private project messages; all identities and databases are disposable."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from memory_hub.app import create_app
from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import HubError, Store, events, projects
from test_index import _migration_db


ADMIN = Principal(worker_id='operator', projects=['p', 'q'], role='admin')
A = Principal(worker_id='worker-a', projects=['p'])
B = Principal(worker_id='worker-b', projects=['p'])
C = Principal(worker_id='worker-c', projects=['p'], role='approver')
Q = Principal(worker_id='worker-q', projects=['q'])
IDENTITIES = [ADMIN, A, B, C, Q]


@pytest.fixture
def messaging(_migration_db):
    url, sqlite, _ = _migration_db
    hub = Hub(Store(url, allow_sqlite=sqlite), clock=lambda:1000.0, principals=IDENTITIES)
    for project in ('p', 'q'):
        hub.call('create_project', {'project_id':project}, ADMIN)
    return hub, url, sqlite


def send(hub, actor=A, **changes):
    args = {'project_id':'p', 'recipient_worker_id':B.worker_id, 'thread_id':'dialogue-1',
            'body':'Hello', 'idempotency_key':uuid.uuid4().hex, **changes}
    return hub.call('send_message', args, actor)


def inbox(hub, actor=A, **changes):
    return hub.call('list_messages', {'project_id':'p', **changes}, actor)


def reject(code, action):
    with pytest.raises(HubError) as caught:
        action()
    assert caught.value.code == code


def test_private_message_preserves_text_and_audit_omits_body(messaging):
    hub, _, _ = messaging
    body = '  hello\nexact whitespace\n'
    sent = send(hub, body=body)
    assert sent == {'message_id':sent['message_id'], 'sequence':2, 'project_id':'p',
                    'thread_id':'dialogue-1', 'sender_worker_id':A.worker_id,
                    'recipient_worker_id':B.worker_id, 'body':body, 'created_at':1000.0,
                    'reply_to_message_id':None}
    for actor in (A, B):
        assert inbox(hub, actor) == {'project_id':'p', 'worker_id':actor.worker_id,
            'items':[sent], 'next_after_sequence':2, 'has_more':False}
    for actor in (C, ADMIN):
        assert inbox(hub, actor)['items'] == []
    with hub.store.engine.connect() as conn:
        audit = conn.execute(select(events.c.event).where(events.c.project_id=='p', events.c.sequence==2)).scalar_one()
    assert audit['operation']=='send_message' and audit['worker_id']==A.worker_id
    assert audit['references']['message_id']==sent['message_id']
    assert body not in json.dumps(audit) and 'body' not in audit['references']


def test_sender_scope_and_recipient_are_server_authorized(messaging):
    hub, _, _ = messaging
    with pytest.raises(ValidationError): send(hub, sender_worker_id=B.worker_id)
    with pytest.raises(ValidationError): inbox(hub, worker_id=B.worker_id)
    reject('forbidden', lambda: send(hub, project_id='q', recipient_worker_id=Q.worker_id))
    reject('forbidden', lambda: inbox(hub, project_id='q'))
    for recipient in ('unknown', Q.worker_id, 'web-operator'):
        reject('unknown_recipient', lambda: send(hub, recipient_worker_id=recipient))
    reject('same_worker', lambda: send(hub, recipient_worker_id=A.worker_id))
    assert inbox(hub)['items']==[]
    assert send(hub, C)['sender_worker_id']==C.worker_id
    assert send(hub, ADMIN)['sender_worker_id']==ADMIN.worker_id


@pytest.mark.parametrize('changes', [
    {'body':''}, {'body':' \t\n'}, {'body':'x'*8001}, {'body':'中'*2667}, {'body':'text\x00suffix'},
    {'thread_id':''}, {'thread_id':'bad/thread'}, {'thread_id':'x'*129},
    {'idempotency_key':''}, {'idempotency_key':'x'*129},
    {'recipient_worker_id':'worker-b\x00'}, {'idempotency_key':'key\x00'}, {'reply_to_message_id':'reply\x00'},
])
def test_invalid_send_leaves_no_message(messaging, changes):
    hub, _, _ = messaging
    with pytest.raises(ValidationError): send(hub, **changes)
    assert inbox(hub)['items']==[]


def test_utf8_byte_limit_accepts_exactly_8000_bytes(messaging):
    hub, _, _ = messaging
    body = '中'*2666+'ab'
    assert len(body.encode('utf-8'))==8000
    assert send(hub, body=body)['body']==body


@pytest.mark.parametrize('changes', [{'after_sequence':-1}, {'after_sequence':2**63}, {'limit':0}, {'limit':51},
                                  {'thread_id':'bad/id'}, {'thread_id':'thread\x00'}, {'project_id':'p\x00'}])
def test_invalid_list_cursor_and_limits(messaging, changes):
    hub, _, _ = messaging
    with pytest.raises(ValidationError): inbox(hub, **changes)


def test_pagination_filters_participants_before_limit_and_preserves_empty_cursor(messaging):
    hub, _, _ = messaging
    wanted = []
    for number in range(5):
        send(hub, ADMIN, recipient_worker_id=C.worker_id, body='private-other')
        wanted.append(send(hub, thread_id='even' if number%2==0 else 'odd', body=str(number)))
    first = inbox(hub, B, limit=2)
    assert first['items']==wanted[:2] and first['has_more'] is True
    second = inbox(hub, B, after_sequence=first['next_after_sequence'], limit=2)
    assert second['items']==wanted[2:4] and second['has_more'] is True
    last = inbox(hub, B, after_sequence=second['next_after_sequence'], limit=2)
    assert last['items']==wanted[4:] and last['has_more'] is False
    empty = inbox(hub, B, after_sequence=last['next_after_sequence'])
    assert empty['items']==[] and empty['next_after_sequence']==wanted[-1]['sequence']
    assert empty['has_more'] is False
    assert inbox(hub, B, thread_id='even')['items']==wanted[::2]


def test_reply_requires_same_project_thread_and_participants(messaging):
    hub, _, _ = messaging
    parent = send(hub)
    reply = send(hub, B, recipient_worker_id=A.worker_id, reply_to_message_id=parent['message_id'])
    assert reply['reply_to_message_id']==parent['message_id']
    hidden = send(hub, ADMIN, recipient_worker_id=C.worker_id)
    another_project = send(hub, ADMIN, project_id='q', recipient_worker_id=Q.worker_id)
    for invalid_parent, changes in [
        ('missing', {}), (hidden['message_id'], {}), (another_project['message_id'], {}),
        (parent['message_id'], {'thread_id':'other'}),
        (parent['message_id'], {'recipient_worker_id':C.worker_id}),
    ]:
        reject('not_found', lambda: send(hub, reply_to_message_id=invalid_parent, **changes))
    assert inbox(hub)['items']==[parent, reply]


def test_idempotency_binds_exact_payload_and_sender(messaging):
    hub, _, _ = messaging
    original = send(hub, idempotency_key='same')
    assert send(hub, idempotency_key='same')==original
    for changes in ({'body':'changed'}, {'body':'Hello '}, {'thread_id':'another'},
                    {'recipient_worker_id':C.worker_id}, {'reply_to_message_id':original['message_id']}):
        reject('idempotency_conflict', lambda: send(hub, idempotency_key='same', **changes))
    other = send(hub, C, idempotency_key='same')
    assert other['message_id']!=original['message_id']
    assert inbox(hub)['items']==[original]
    audit = hub.call('audit_log', {'project_id':'p'}, ADMIN)['events']
    assert sum(row['operation']=='send_message' for row in audit)==2


def test_idempotency_key_can_be_reused_in_another_project(messaging):
    hub, _, _ = messaging
    first = send(hub, ADMIN, idempotency_key='same-project-key')
    second = send(hub, ADMIN, project_id='q', recipient_worker_id=Q.worker_id, idempotency_key='same-project-key')
    assert first['message_id']!=second['message_id']
    assert first['sequence']==second['sequence']==2


def test_revoked_recipient_allows_only_identical_retry_and_keeps_history(messaging):
    hub, _, _ = messaging
    issued = hub.credentials.issue('p', 'managed-chat', 'operator', 1000)
    original = send(hub, recipient_worker_id='managed-chat', idempotency_key='same')
    hub.credentials.revoke('p', issued['token_id'], 1, 'operator', 1001)
    assert send(hub, recipient_worker_id='managed-chat', idempotency_key='same')==original
    reject('unknown_recipient', lambda: send(hub, recipient_worker_id='managed-chat'))
    assert inbox(hub)['items']==[original]


def test_audit_failure_rolls_back_message_and_dedupe(messaging, monkeypatch):
    hub, _, _ = messaging
    audit = hub.store.audit
    def fail_after_audit(*args, **kwargs):
        audit(*args, **kwargs)
        raise RuntimeError('synthetic audit failure')
    with monkeypatch.context() as patch:
        patch.setattr(hub.store, 'audit', fail_after_audit)
        with pytest.raises(RuntimeError, match='synthetic audit failure'):
            send(hub, idempotency_key='retry')
    assert inbox(hub)['items']==[]
    sent = send(hub, idempotency_key='retry')
    assert sent['sequence']==2
    assert inbox(hub)['items']==[sent]


def test_concurrent_dedupe_and_sends_use_one_committed_sequence(messaging):
    hub, url, sqlite = messaging
    other = Hub(Store(url, allow_sqlite=sqlite), clock=hub.clock, principals=IDENTITIES)
    def retry(number):
        return send(hub if number%2 else other, idempotency_key='concurrent')
    with ThreadPoolExecutor(4) as pool:
        retried = list(pool.map(retry, range(8)))
    assert len({row['message_id'] for row in retried})==1
    def distinct(number):
        return send(hub if number%2 else other, body=str(number), idempotency_key='message-'+str(number))
    with ThreadPoolExecutor(4) as pool:
        sent = list(pool.map(distinct, range(12)))
    all_rows = inbox(other)['items']
    assert len(all_rows)==13
    assert [row['sequence'] for row in all_rows]==list(range(2, 15))
    assert {row['message_id'] for row in all_rows}=={row['message_id'] for row in [*sent, retried[0]]}


def test_concurrent_conflicting_idempotency_has_one_winner(messaging):
    hub, url, sqlite = messaging
    other = Hub(Store(url, allow_sqlite=sqlite), principals=IDENTITIES)
    def attempt(number):
        try:
            return send(hub if number else other, body=str(number), idempotency_key='race')
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sum(isinstance(row, dict) for row in results)==1
    assert 'idempotency_conflict' in results


def test_messages_do_not_change_context_leases_or_knowledge(messaging):
    hub, _, _ = messaging
    hub.call('register_source', {'project_id':'p', 'source_id':'spec', 'content':'source', 'uri':'fixture:spec', 'commit':'fixture'}, ADMIN)
    hub.call('create_task', {'project_id':'p', 'task_id':'t', 'goal':'Fixture', 'allowed_paths':['fixture/**'],
        'acceptance_criteria':['pass'], 'source_ids':['spec']}, ADMIN)
    packet = hub.call('prepare_task', {'project_id':'p', 'task_id':'t', 'workspace':'fixture', 'branch':'fixture', 'commit':'fixture'}, A)
    lease = hub.call('claim_task', {'project_id':'p', 'task_id':'t'}, A)
    gate = {'project_id':'p', 'packet_id':packet['packet_id'], 'fence':lease['fence']}
    hub.call('read_source', {'project_id':'p', 'packet_id':packet['packet_id'], 'source_id':'spec'}, A)
    hub.call('acknowledge_context', {'project_id':'p', 'packet_id':packet['packet_id']}, A)
    hub.call('accept_handoff', gate, A)
    with hub.store.engine.begin() as conn:
        before = conn.execute(select(projects.c.state).where(projects.c.id=='p')).scalar_one()
        hub.store.index.queue(conn, 'p', 'source', 'spec', before['revision'])
        jobs_before = conn.execute(select(hub.store.index.jobs).order_by(hub.store.index.jobs.c.id)).all()
    send(hub, body='private-unindexed-dialogue')
    inbox(hub)
    with hub.store.engine.connect() as conn:
        after = conn.execute(select(projects.c.state).where(projects.c.id=='p')).scalar_one()
        assert conn.execute(select(hub.store.index.jobs).order_by(hub.store.index.jobs.c.id)).all()==jobs_before
    assert {key:value for key,value in after.items() if key!='sequence'}=={key:value for key,value in before.items() if key!='sequence'}
    assert hub.call('validate_task_context', gate, A)['valid'] is True
    hub.clock = lambda:10000.0
    assert send(hub, body='A message needs no live lease')['created_at']==10000.0


def test_messages_survive_restart(messaging):
    hub, url, sqlite = messaging
    sent = send(hub)
    restarted = Hub(Store(url, allow_sqlite=sqlite), principals=IDENTITIES)
    assert inbox(restarted, B)['items']==[sent]


def test_rest_and_mcp_share_authenticated_message_identity(_migration_db, monkeypatch):
    url, sqlite, _ = _migration_db
    for name in ('HUB_WEB_USERNAME', 'HUB_WEB_PASSWORD_HASH', 'HUB_WEB_PROJECTS'):
        monkeypatch.delenv(name, raising=False)
    token_a, token_b, token_admin = ('test-only-chat-a-000000000000', 'test-only-chat-b-000000000000', 'test-only-chat-admin-00000000')
    app = create_app(database_url=url, allow_sqlite=sqlite,
        auth_tokens=json.dumps({token_a:A.model_dump(), token_b:B.model_dump(), token_admin:ADMIN.model_dump()}))
    app.state.hub.call('create_project', {'project_id':'p'}, ADMIN)
    args = {'project_id':'p', 'recipient_worker_id':B.worker_id, 'thread_id':'client-dialogue', 'body':'Hello', 'idempotency_key':'rest-first'}
    with TestClient(app) as client:
        assert client.post('/v1/tools/send_message', json={'arguments':args}).status_code==401
        headers_a = {'Authorization':'Bearer '+token_a}
        sent = client.post('/v1/tools/send_message', headers=headers_a, json={'arguments':args})
        assert sent.status_code==200
        assert sent.json()['sender_worker_id']==A.worker_id
        forged = client.post('/v1/tools/send_message', headers=headers_a, json={'arguments':{**args, 'sender_worker_id':B.worker_id}})
        assert forged.status_code==422
        headers_b = {'Authorization':'Bearer '+token_b, 'Accept':'application/json, text/event-stream'}
        listed = client.post('/mcp', headers=headers_b, json={'jsonrpc':'2.0', 'id':1, 'method':'tools/list', 'params':{}})
        tools = {tool['name']:tool for tool in listed.json()['result']['tools']}
        assert {'send_message', 'list_messages'} <= tools.keys()
        def mcp(name, values):
            result = client.post('/mcp', headers=headers_b, json={'jsonrpc':'2.0', 'id':2, 'method':'tools/call',
                'params':{'name':name, 'arguments':{'arguments':values}}}).json()['result']
            assert result.get('isError') is not True
            return result.get('structuredContent') or json.loads(next(item['text'] for item in result['content'] if item['type']=='text'))
        assert mcp('list_messages', {'project_id':'p'})['items']==[sent.json()]
        reply = mcp('send_message', {**args, 'recipient_worker_id':A.worker_id, 'idempotency_key':'mcp-reply',
            'reply_to_message_id':sent.json()['message_id'], 'body':'Received'})
        assert reply['sender_worker_id']==B.worker_id
        result = client.post('/v1/tools/list_messages', headers=headers_a, json={'arguments':{'project_id':'p'}})
        assert result.json()['items']==[sent.json(), reply]
