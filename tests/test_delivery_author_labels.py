"""Automatic message labels follow validated room bindings without changing identity."""
import pytest

from memory_hub.models import Principal
from memory_hub.session_service import SessionActor
from test_delivery import (call, claim, read_delivery, reply,
                           collaboration, room, post, values, reject, A, B)
from test_index import _migration_db
from test_web_sessions import room as web_room, action


def bind(hub, session, client='codex', actor=A):
    return call(hub, 'join', actor, **values(session, client=client,
        display_name='Untrusted administrator alias', native_session_id='label-test',
        idempotency_key='join-' + client))


@pytest.mark.parametrize('client,label', [('claude', 'Claude'), ('codex', 'Codex'),
    ('chatgpt', 'ChatGPT'), ('gemini', 'Gemini'), ('grok', 'Grok'), ('other', A.worker_id)])
def test_automatic_label_is_canonical_not_worker_display_name(collaboration, client, label):
    hub, _, _ = collaboration
    session = room(hub)
    binding = bind(hub, session, client)
    post(hub, session, B)
    delivery = claim(hub, binding)['delivery']
    read_delivery(hub, session, delivery)
    result = reply(hub, session, delivery)
    assert result['actor'] == {'kind': 'worker', 'id': A.worker_id, 'display_name': label}
    stored = hub.call('read_session', values(session, full_text=True), A)
    event = next(item for item in stored['items'] if item.get('message_id') == result['message_id'])
    assert event['actor'] == result['actor']
    assert event['automatic_reply_depth'] == 1
    assert reply(hub, session, delivery) == result


def test_manual_and_historical_labels_are_not_inferred_from_later_binding(collaboration):
    hub, _, _ = collaboration
    session, elsewhere = room(hub), room(hub)
    old = post(hub, session, A)
    binding = bind(hub, session)
    post(hub, session, B)
    delivery = claim(hub, binding)['delivery']
    read_delivery(hub, session, delivery)
    result = reply(hub, session, delivery)
    assert post(hub, elsewhere, A)['actor']['display_name'] == A.worker_id
    call(hub, 'disconnect', project_id='p', binding_id=binding['binding_id'], expected_version=1)
    assert post(hub, session, A)['actor']['display_name'] == A.worker_id
    bind(hub, session, 'claude')
    assert reply(hub, session, delivery) == result  # Idempotent old receipt keeps its original label.
    stored = hub.call('read_session', values(session, full_text=True), A)
    labels = {item['message_id']: item['actor']['display_name'] for item in stored['items']
              if item['type'] == 'message'}
    assert labels[old['message_id']] == A.worker_id
    assert labels[result['message_id']] == 'Codex'


def test_label_requires_current_own_worker_room_and_lease(collaboration):
    hub, _, _ = collaboration
    now = [1000.0]
    hub.clock = lambda: now[0]
    session, elsewhere = room(hub), room(hub)
    binding = bind(hub, session)
    post(hub, session, B)
    delivery = claim(hub, binding, lease_seconds=15)['delivery']
    read_delivery(hub, session, delivery)
    reject('not_found', lambda: reply(hub, session, delivery, B))
    reject('not_found', lambda: reply(hub, elsewhere, delivery))
    now[0] += 16
    reject('stale_delivery', lambda: reply(hub, session, delivery))
    stored = hub.call('read_session', values(session, full_text=True), A)
    assert not any(item['actor']['id'] == A.worker_id for item in stored['items'])


def test_web_operator_alias_overrides_canonical_automatic_label(web_room):
    client, hub, _ = web_room
    session = action(client, 'create_session', {'project_id': 'shared', 'title': 'Author alias'}).json()
    principal = Principal(worker_id='ai-a', projects=['shared'], role='worker')
    actor = SessionActor.from_principal(principal)
    binding = bind(hub, session, actor=actor)
    posted = action(client, 'post_session_message', values(session, body='Please reply'), 'human')
    assert posted.status_code == 200
    delivery = claim(hub, binding, principal)['delivery']
    read_delivery(hub, session, delivery, principal)
    result = reply(hub, session, delivery, principal)
    assert result['actor'] == {'kind': 'worker', 'id': 'ai-a', 'display_name': 'Codex'}
    response = client.get('/ui/chat/data', params={'op': 'read', 'project': 'shared',
                                                  'session': session['session_id']})
    assert response.status_code == 200
    event = next(item for item in response.json()['items'] if item.get('message_id') == result['message_id'])
    assert event['actor'] == {'kind': 'worker', 'id': 'ai-a', 'display_name': 'Codex 測試端'}
