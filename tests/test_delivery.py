"""Delivery proofs: durable replay, ownership, fencing and real tool receipts."""
from concurrent.futures import ThreadPoolExecutor
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from memory_hub.app import create_app
from memory_hub.service import Hub
from memory_hub.store import Store, DELIVERY_TABLES, projects
from memory_hub.session_service import SessionActor
from test_sessions import collaboration, room, post, values, human, reject, ADMIN, A, B, Q, IDENTITIES
from test_index import _migration_db


def call(hub, operation, actor=A, **kwargs):
    identity = actor if isinstance(actor, SessionActor) else SessionActor.from_principal(actor)
    return hub.delivery.call(operation, kwargs, identity)


def join(hub, session, actor=A, **kwargs):
    return call(hub, 'join', actor, **values(session, client='claude' if actor == B else 'codex',
        display_name='Claude' if actor == B else 'Codex', native_session_id='native-test-session',
        idempotency_key=uuid.uuid4().hex, **kwargs))


def claim(hub, binding, actor=A, **kwargs):
    return call(hub, 'claim', actor, project_id=binding['project_id'], binding_id=binding['binding_id'], **kwargs)


def delivery_args(session, delivery, **kwargs):
    return values(session, delivery_id=delivery['delivery_id'], lease_id=delivery['lease_id'], **kwargs)


def read_delivery(hub, session, delivery, actor=A, **kwargs):
    return hub.call('read_session', delivery_args(session, delivery,
        **{'after_sequence': delivery['after_sequence'], 'full_text': True, 'max_bytes': 65536, **kwargs}), actor)


def reply(hub, session, delivery, actor=A, **kwargs):
    return hub.call('post_session_message', delivery_args(session, delivery,
        **{'body': 'Native tool reply', 'idempotency_key': delivery['reply_idempotency_key'], **kwargs}), actor)


def status(hub, session):
    return call(hub, 'status', human('admin'), **values(session))


def test_human_broadcast_isolated_durable_and_never_self_triggers(collaboration):
    hub, _, _ = collaboration
    s, other = room(hub), room(hub)
    a, b = join(hub, s), join(hub, s, B)
    elsewhere = join(hub, other)
    message = hub.sessions.call('post_session_message', values(s, body='Human broadcast', idempotency_key='human'), human())
    da, db = claim(hub, a)['delivery'], claim(hub, b, B)['delivery']
    assert da['message_ids'] == db['message_ids'] == [message['message_id']]
    assert claim(hub, elsewhere)['status'] == 'idle'
    assert status(hub, s)['participants'][0]['processed_sequence'] < message['sequence']
    assert read_delivery(hub, s, da)['delivery_receipt']['status'] == 'tool_read'
    written = reply(hub, s, da)
    assert written['delivery_receipt']['processed_sequence'] == da['through_sequence']
    assert claim(hub, a)['status'] == 'idle'
    read_delivery(hub, s, db, B)
    reply(hub, s, db, B)
    followup = claim(hub, a)['delivery']
    assert followup and followup['messages'][0]['actor_id'] == B.worker_id


def test_dispatch_cannot_forge_tool_read_or_reply_receipt(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    delivery = claim(hub, binding)['delivery']
    ack = call(hub, 'dispatched', project_id='p', binding_id=binding['binding_id'],
               delivery_id=delivery['delivery_id'], lease_id=delivery['lease_id'])
    assert ack == {'delivery_id': delivery['delivery_id'], 'status': 'handed_to_client', 'tool_read': False}
    reject('delivery_not_read', lambda: reply(hub, s, delivery))
    # A normal room read has no delivery linkage and cannot satisfy the receipt.
    hub.call('read_session', values(s, full_text=True), A)
    reject('delivery_not_read', lambda: reply(hub, s, delivery))
    read_delivery(hub, s, delivery)
    reject('delivery_key_required', lambda: reply(hub, s, delivery, idempotency_key='different'))
    first = reply(hub, s, delivery)
    assert reply(hub, s, delivery) == first
    assert status(hub, s)['participants'][0]['latest_delivery']['status'] == 'replied'


def test_partial_truncated_reads_and_byte_budget_do_not_advance_cursor(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    messages = [post(hub, s, B, body='x' * 7000) for _ in range(2)]
    delivery = claim(hub, binding)['delivery']
    compact = read_delivery(hub, s, delivery, full_text=False)
    assert compact['delivery_receipt']['status'] == 'partial_tool_read'
    assert len(compact['delivery_receipt']['unread_message_ids']) == 2
    first = read_delivery(hub, s, delivery, limit=1)
    assert len(first['delivery_receipt']['unread_message_ids']) == 1
    reject('delivery_not_read', lambda: reply(hub, s, delivery))
    second = read_delivery(hub, s, delivery, after_sequence=messages[0]['sequence'], limit=1)
    assert second['delivery_receipt']['status'] == 'tool_read'
    assert second['returned_bytes'] == len(json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
    assert second['returned_bytes'] <= 65536
    assert status(hub, s)['participants'][0]['processed_sequence'] == binding['processed_sequence']
    reply(hub, s, delivery)


def test_pause_cas_idempotency_and_running_lease_stop(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    delivery = claim(hub, binding)['delivery']
    args = values(s, paused=True, expected_version=1, idempotency_key='pause')
    paused = call(hub, 'pause', human('admin'), **args)
    assert paused['paused'] and paused['version'] == 2 and not paused['running_turns_cancelled']
    assert call(hub, 'pause', human('admin'), **args) == paused
    reject('forbidden', lambda: call(hub, 'pause', A, **args))
    reject('stale_control', lambda: call(hub, 'pause', ADMIN, **{**args, 'idempotency_key': 'old-version'}))
    assert claim(hub, binding)['status'] == 'paused'
    reject('delivery_stopped', lambda: read_delivery(hub, s, delivery))
    reject('delivery_stopped', lambda: post(hub, s, A, body='Cannot remove delivery fields to bypass pause'))
    hub.sessions.call('post_session_message', values(s, body='Human may still speak',
        idempotency_key='human-while-paused'), human())
    call(hub, 'pause', ADMIN, **values(s, paused=False, expected_version=2))
    reject('stale_delivery', lambda: read_delivery(hub, s, delivery))
    delivery = claim(hub, binding)['delivery']
    read_delivery(hub, s, delivery)
    reject('delivery_metadata_required', lambda: post(hub, s, A, body='Cannot bypass the fenced reply'))
    reply(hub, s, delivery)


def test_restart_retries_same_delivery_new_fence_without_losing_cursor(collaboration):
    hub, url, sqlite = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    first = claim(hub, binding, lease_seconds=15)['delivery']
    call(hub, 'dispatched', project_id='p', binding_id=binding['binding_id'],
         delivery_id=first['delivery_id'], lease_id=first['lease_id'])
    clock[0] += 16
    restarted = Hub(Store(url, allow_sqlite=sqlite), clock=lambda: clock[0], principals=IDENTITIES)
    second = claim(restarted, binding, lease_seconds=15)['delivery']
    assert second['delivery_id'] == first['delivery_id'] and second['lease_id'] != first['lease_id']
    assert second['reply_idempotency_key'] == first['reply_idempotency_key']
    reject('stale_delivery', lambda: read_delivery(restarted, s, first))
    read_delivery(restarted, s, second)
    saved = reply(restarted, s, second)
    # A response lost after commit is recovered by the original idempotent post.
    clock[0] += 1000
    assert reply(restarted, s, second) == saved
    assert claim(restarted, binding)['status'] == 'idle'


def test_concurrent_claims_only_one_active_batch(collaboration):
    hub, url, sqlite = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    other = Hub(Store(url, allow_sqlite=sqlite), clock=hub.clock, principals=IDENTITIES)
    with ThreadPoolExecutor(4) as pool:
        replies = list(pool.map(lambda i: claim(hub if i % 2 else other, binding), range(8)))
    assert [r['status'] for r in replies].count('ready') == 1
    assert [r['status'] for r in replies].count('busy') == 7
    assert status(hub, s)['participants'][0]['turns_used'] == 1


def test_new_message_during_turn_is_not_skipped_by_successful_reply(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); before = post(hub, s, B)
    first = claim(hub, binding)['delivery']
    after = post(hub, s, B, body='Human interruption after dispatch')
    read_delivery(hub, s, first)
    reply(hub, s, first)
    next_batch = claim(hub, binding)['delivery']
    assert next_batch['message_ids'] == [after['message_id']]
    assert next_batch['after_sequence'] == before['sequence']


def test_idle_own_messages_do_not_consume_model_budget_and_human_id_is_not_worker_id(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    for _ in range(22):
        post(hub, s, A)
    assert claim(hub, binding)['status'] == 'idle'
    assert claim(hub, binding)['status'] == 'idle'
    human_message = hub.sessions.call('post_session_message', values(s, body='Same ID, human',
        idempotency_key='same-id'), human(identity=A.worker_id))
    found = claim(hub, binding)['delivery']
    assert found['message_ids'] == [human_message['message_id']]
    assert status(hub, s)['participants'][0]['turns_used'] == 1


def test_post_failure_rolls_back_message_receipt_cursor_and_legacy_hash_is_preserved(collaboration, monkeypatch):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    delivery = claim(hub, binding)['delivery']; read_delivery(hub, s, delivery)
    before = hub.call('read_session', values(s), A)
    original = hub.delivery.record_tool_reply
    def fail(*args):
        original(*args)
        raise RuntimeError('injected after reply receipt')
    monkeypatch.setattr(hub.delivery, 'record_tool_reply', fail)
    with pytest.raises(RuntimeError):
        reply(hub, s, delivery)
    assert hub.call('read_session', values(s), A) == before
    assert status(hub, s)['participants'][0]['latest_delivery']['status'] == 'tool_read'
    assert status(hub, s)['participants'][0]['processed_sequence'] == binding['processed_sequence']
    monkeypatch.setattr(hub.delivery, 'record_tool_reply', original)
    assert reply(hub, s, delivery)['delivery_receipt']['status'] == 'replied'
    # No delivery metadata means the exact pre-v6 request hash stays replayable.
    args = values(s, body='Legacy request', idempotency_key='legacy',
                  reply_to_message_id=None, attachment_ids=[])
    legacy = hub.call('post_session_message', args, A)
    from memory_hub.session_service import compact
    from memory_hub.store import SESSION_TABLES
    import hashlib
    with hub.store.engine.connect() as conn:
        digest = conn.execute(select(SESSION_TABLES['requests'].c.payload_hash).where(
            SESSION_TABLES['requests'].c.request_key == 'legacy')).scalar_one()
    assert digest == hashlib.sha256(compact(args)).hexdigest()
    assert hub.call('post_session_message', {**args, 'delivery_id': None, 'lease_id': None}, A) == legacy


def test_oversized_receipt_rolls_back_read_state(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    for _ in range(20):
        post(hub, s, B, body='x' * 2200)
    delivery = claim(hub, binding)['delivery']
    # A maximum budget always supports normal pagination; a tiny one must not
    # record unseen bytes when adding the delivery receipt exceeds that budget.
    ordinary = hub.call('read_session', values(s, after_sequence=delivery['after_sequence'],
        full_text=True, limit=1, max_bytes=65536), A)
    limited = ordinary['returned_bytes'] + 1
    assert limited >= 2048
    reject('response_budget_too_small', lambda: read_delivery(hub, s, delivery, limit=1, max_bytes=limited))
    assert status(hub, s)['participants'][0]['latest_delivery']['read_at'] is None
    with hub.store.engine.connect() as conn:
        assert conn.execute(select(DELIVERY_TABLES['deliveries'].c.read_message_ids)).scalar_one() == []


def test_budget_expiry_and_three_attempt_failure_are_bounded(collaboration):
    hub, _, _ = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s, max_turns=1, ttl_seconds=60); post(hub, s, B)
    claim(hub, binding, lease_seconds=15)
    clock[0] += 16
    assert claim(hub, binding)['status'] == 'budget_exhausted'
    clock[0] += 60
    assert claim(hub, binding)['status'] == 'expired'
    another = join(hub, s, max_turns=10)
    for _ in range(3):
        assert claim(hub, another, lease_seconds=15)['status'] == 'ready'
        clock[0] += 16
    assert claim(hub, another)['status'] == 'failed'
    assert status(hub, s)['participants'][0]['processed_sequence'] == binding['processed_sequence']


def test_join_replay_preserves_cursor_rebind_fences_old_native_and_hides_identifier(collaboration):
    hub, _, _ = collaboration
    s = room(hub)
    args = values(s, client='claude', display_name='Claude local', native_session_id='private-native-id',
                  idempotency_key='join-one')
    binding = call(hub, 'join', **args)
    assert call(hub, 'join', **args) == binding
    post(hub, s, B)
    old = claim(hub, binding)['delivery']
    reject('binding_exists', lambda: join(hub, s))
    call(hub, 'control', human('admin'), project_id='p', binding_id=binding['binding_id'],
         enabled=False, expected_version=1)
    fresh = join(hub, s)
    assert fresh['binding_id'] == binding['binding_id'] and fresh['generation'] == 2
    assert fresh['processed_sequence'] == binding['processed_sequence']
    reject('not_found', lambda: read_delivery(hub, s, old))
    observed = status(hub, s)
    assert 'private-native-id' not in json.dumps(observed) and 'native_session_hash' not in json.dumps(observed)
    assert claim(hub, fresh)['delivery']['message_ids'] == old['message_ids']


def test_scope_role_archival_revocation_and_presence(collaboration):
    hub, _, _ = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s)
    reject('forbidden', lambda: claim(hub, binding, B))
    reject('forbidden', lambda: call(hub, 'status', Q, **values(s)))
    assert call(hub, 'status', human('read_only'), **values(s))['participants']
    clock[0] += 46
    assert status(hub, s)['participants'][0]['status'] == 'offline'
    beat = call(hub, 'heartbeat', project_id='p', binding_id=binding['binding_id'])
    assert beat['relay_online'] and beat['status'] == 'waiting'
    hub.call('archive_session', values(s, archived=True, expected_version=1, idempotency_key='close'), ADMIN)
    assert claim(hub, binding)['status'] == 'archived'
    hub._principals = tuple(p for p in hub._principals if p.worker_id != A.worker_id)
    assert status(hub, s)['participants'][0]['status'] == 'revoked'
    reject('forbidden', lambda: claim(hub, binding))


def test_v6_additive_migration_preserves_existing_messages_and_task_revision(collaboration):
    hub, url, sqlite = collaboration
    s = room(hub); msg = post(hub, s)
    with hub.store.engine.begin() as conn:
        state = conn.execute(select(projects.c.state).where(projects.c.id == 'p')).scalar_one()
        for name in ('joins', 'deliveries', 'bindings', 'controls'):
            DELIVERY_TABLES[name].drop(conn)
        conn.execute(hub.store.index.migrations.delete().where(hub.store.index.migrations.c.version == 6))
    def upgrade(_):
        updated = Hub(Store(url, allow_sqlite=sqlite), principals=IDENTITIES)
        assert status(updated, s)['participants'] == []
        assert hub.call('read_session', values(s), A)['items'][-1]['message_id'] == msg['message_id']
        with updated.store.engine.connect() as conn:
            assert conn.execute(select(projects.c.state).where(projects.c.id == 'p')).scalar_one() == state
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(upgrade, range(3)))


def test_rest_auth_schema_status_and_no_mcp_discovery_cost(collaboration, monkeypatch):
    hub, url, sqlite = collaboration
    s = room(hub)
    token = 'synthetic-delivery-test-token-12345'
    app = create_app(database_url=url, auth_tokens=json.dumps({token: A.model_dump()}), allow_sqlite=sqlite)
    with TestClient(app) as client:
        assert client.get('/v1/chat/status', params=values(s)).status_code == 401
        headers = {'Authorization': 'Bearer ' + token}
        joined = client.post('/v1/chat/join', headers=headers, json=values(s, client='claude',
            display_name='Claude', native_session_id='test-local', idempotency_key='rest-join'))
        assert joined.status_code == 200
        assert client.get('/v1/chat/status', headers=headers, params=values(s)).json()['participants']
        bad = client.post('/v1/chat/dispatched', headers=headers, json={'status': 'tool_read', 'secret': 'do-not-echo'})
        assert bad.status_code == 422 and 'do-not-echo' not in bad.text
        tools = client.post('/mcp', headers={**headers, 'Accept': 'application/json, text/event-stream'},
            json={'jsonrpc':'2.0', 'id':1, 'method':'tools/list', 'params':{}}).json()['result']['tools']
        assert not any(x['name'] in {'join', 'claim', 'heartbeat', 'dispatched'} for x in tools)
