"""Silent completion is an authenticated, fenced tool mutation, never a room ack."""
from concurrent.futures import ThreadPoolExecutor
import uuid
import pytest
from sqlalchemy import func, select
from memory_hub.session_service import SessionActor
from memory_hub.store import HubError, SESSION_TABLES
from test_delivery import join, claim, read_delivery, reply, delivery_args, status
from test_sessions import collaboration, room, post, values, human, reject, A, B, Q
from test_index import _migration_db


def complete(hub, session, delivery, actor=A, **changes):
    call = hub.sessions.call if isinstance(actor, SessionActor) else hub.call
    return call('complete_session_delivery', delivery_args(session, delivery,
        idempotency_key=changes.pop('idempotency_key', delivery['reply_idempotency_key']), **changes), actor)


def count_events(hub, session):
    table = SESSION_TABLES['events']
    with hub.store.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table).where(
            table.c.project_id == session['project_id'], table.c.session_id == session['session_id'])).scalar_one()


def prepared(hub):
    session = room(hub); binding = join(hub, session); post(hub, session, B)
    delivery = claim(hub, binding)['delivery']; read_delivery(hub, session, delivery)
    return session, binding, delivery


def test_no_reply_is_atomic_idempotent_and_generates_no_message_or_event(collaboration):
    hub, _, _ = collaboration
    session, binding, delivery = prepared(hub); before = count_events(hub, session)
    first = complete(hub, session, delivery)
    assert first == {'project_id': session['project_id'], 'session_id': session['session_id'],
        'worker_id': A.worker_id, 'delivery_receipt': {'delivery_id': delivery['delivery_id'],
        'status': 'no_reply', 'processed_sequence': delivery['through_sequence']}}
    assert complete(hub, session, delivery) == first
    latest = status(hub, session)['participants'][0]
    assert latest['processed_sequence'] == delivery['through_sequence'] and latest['turns_used'] == 1
    assert latest['latest_delivery']['status'] == 'no_reply'
    assert latest['latest_delivery']['read_at'] is not None
    assert latest['latest_delivery']['replied_at'] is None
    assert latest['latest_delivery']['reply_message_id'] is None
    assert latest['latest_delivery']['reply_sequence'] is None
    assert count_events(hub, session) == before and claim(hub, binding)['status'] == 'idle'
    # Lost response can be read back idempotently even after the old lease expires.
    hub.clock = lambda: 1400
    assert complete(hub, session, delivery) == first
    assert count_events(hub, session) == before


def test_no_reply_requires_every_untruncated_page_and_stable_key(collaboration):
    hub, _, _ = collaboration
    session = room(hub); binding = join(hub, session)
    messages = [post(hub, session, B, body='x' * 7000) for _ in range(2)]
    delivery = claim(hub, binding)['delivery']
    reject('delivery_not_read', lambda: complete(hub, session, delivery))
    hub.call('read_session', values(session, full_text=True, max_bytes=65536), A)
    reject('delivery_not_read', lambda: complete(hub, session, delivery))
    read_delivery(hub, session, delivery, full_text=False)
    reject('delivery_not_read', lambda: complete(hub, session, delivery))
    read_delivery(hub, session, delivery, limit=1)
    reject('delivery_not_read', lambda: complete(hub, session, delivery))
    assert status(hub, session)['participants'][0]['processed_sequence'] == binding['processed_sequence']
    read_delivery(hub, session, delivery, after_sequence=messages[0]['sequence'], limit=1)
    reject('delivery_key_required', lambda: complete(hub, session, delivery, idempotency_key='invented'))
    assert complete(hub, session, delivery)['delivery_receipt']['status'] == 'no_reply'


@pytest.mark.parametrize('actor', [B, Q, SessionActor('worker', A.worker_id, 'Read only', ('p',), 'read_only')])
def test_no_reply_cannot_complete_another_worker_or_read_only_identity(collaboration, actor):
    hub, _, _ = collaboration; session, _, delivery = prepared(hub)
    with pytest.raises(HubError):complete(hub, session, delivery, actor)
    assert status(hub, session)['participants'][0]['latest_delivery']['status'] == 'tool_read'
    reject('forbidden', lambda: hub.sessions.call('complete_session_delivery',
        delivery_args(session, delivery, idempotency_key=delivery['reply_idempotency_key']), human('admin')))


def test_no_reply_rejects_cross_room_and_changed_idempotent_payload(collaboration):
    hub, _, _ = collaboration; session, _, delivery = prepared(hub); other = room(hub)
    reject('not_found', lambda: complete(hub, other, delivery))
    complete(hub, session, delivery)
    changed = delivery | {'lease_id': uuid.uuid4().hex}
    reject('idempotency_conflict', lambda: complete(hub, session, changed))


@pytest.mark.parametrize('fence', ['lease', 'expired', 'paused', 'disabled', 'disconnected'])
def test_no_reply_obeys_live_lease_and_administrative_fences(collaboration, fence):
    hub, _, _ = collaboration; session, binding, delivery = prepared(hub)
    if fence == 'lease':delivery = delivery | {'lease_id': uuid.uuid4().hex}
    elif fence == 'expired':hub.clock = lambda: 1400
    elif fence == 'paused':
        hub.delivery.call('pause', values(session, paused=True, expected_version=1), human('admin'))
    else:
        hub.delivery.call('disconnect' if fence == 'disconnected' else 'control',
            {'project_id': session['project_id'], 'binding_id': binding['binding_id'], 'expected_version':1} |
            ({} if fence == 'disconnected' else {'enabled':False}), human('admin'))
    with pytest.raises(HubError):complete(hub, session, delivery)
    assert status(hub, session)['participants'][0]['processed_sequence'] == binding['processed_sequence']


@pytest.mark.parametrize('first', ['reply', 'no_reply'])
def test_exactly_one_completion_disposition(collaboration, first):
    hub, _, _ = collaboration; session, _, delivery = prepared(hub)
    (reply if first == 'reply' else complete)(hub, session, delivery)
    reject('stale_delivery', lambda: (complete if first == 'reply' else reply)(hub, session, delivery))


def test_reply_and_no_reply_race_has_one_winner(collaboration):
    hub, _, _ = collaboration; session, _, delivery = prepared(hub); before = count_events(hub, session)
    def finish(action):
        try:return action(hub, session, delivery)['delivery_receipt']['status']
        except HubError as error:return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, [reply, complete]))
    assert results.count('stale_delivery') == 1
    winner = next(x for x in results if x != 'stale_delivery')
    assert count_events(hub, session) == before + (winner == 'replied')


def test_ai_fanout_still_works_but_silent_completion_does_not_fan_out(collaboration):
    hub, _, _ = collaboration; session = room(hub); a, b = join(hub, session), join(hub, session, B)
    hub.sessions.call('post_session_message', values(session, body='Discuss this', idempotency_key='human'), human())
    da = claim(hub, a)['delivery']; read_delivery(hub, session, da); reply(hub, session, da)
    db = claim(hub, b, B)['delivery']
    assert any(m['actor_id'] == A.worker_id and m['automatic_reply_depth'] == 1 for m in db['messages'])
    read_delivery(hub, session, db, B); before = count_events(hub, session)
    complete(hub, session, db, B)
    assert count_events(hub, session) == before
    assert claim(hub, a)['status'] == 'idle' and claim(hub, b, B)['status'] == 'idle'


def test_later_human_is_not_consumed_by_completing_old_batch(collaboration):
    hub, _, _ = collaboration; session = room(hub); binding = join(hub, session)
    first = hub.sessions.call('post_session_message', values(session, body='First human', idempotency_key='first'), human())
    old = claim(hub, binding)['delivery']; read_delivery(hub, session, old)
    later = hub.sessions.call('post_session_message', values(session, body='Second human', idempotency_key='later'), human())
    complete(hub, session, old)
    assert status(hub, session)['participants'][0]['processed_sequence'] == first['sequence']
    new = claim(hub, binding)['delivery']
    assert new['message_ids'] == [later['message_id']] and new['after_sequence'] == first['sequence']
    read_delivery(hub, session, new); before = count_events(hub, session); complete(hub, session, new)
    assert count_events(hub, session) == before and claim(hub, binding)['status'] == 'idle'
    assert status(hub, session)['participants'][0]['turns_used'] == 2


def test_old_generation_after_rejoin_cannot_silently_complete(collaboration):
    hub, _, _ = collaboration; session, binding, old = prepared(hub)
    hub.delivery.call('disconnect', {'project_id':session['project_id'], 'binding_id':binding['binding_id'],
        'expected_version':1}, human('admin'))
    new_binding = join(hub, session)
    assert new_binding['generation'] > binding['generation']
    with pytest.raises(HubError):complete(hub, session, old)
    assert status(hub, session)['participants'][0]['processed_sequence'] == new_binding['processed_sequence']


def test_same_key_does_not_alias_other_operation_or_room(collaboration):
    hub, _, _ = collaboration; session, _, delivery = prepared(hub)
    complete(hub, session, delivery)
    reject('stale_delivery', lambda: reply(hub, session, delivery))
    other = room(hub); other_binding = join(hub, other); post(hub, other, B)
    other_delivery = claim(hub, other_binding)['delivery']; read_delivery(hub, other, other_delivery)
    reject('delivery_key_required', lambda: complete(hub, other, other_delivery,
        idempotency_key=delivery['reply_idempotency_key']))
    assert status(hub, other)['participants'][0]['latest_delivery']['status'] == 'tool_read'
