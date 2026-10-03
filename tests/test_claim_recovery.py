"""Claim response loss never shares a lease with another receiver or charges a retry."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import uuid

import httpx
import pytest
from sqlalchemy import select
from pydantic import ValidationError

from memory_hub.delivery_models import ClaimDelivery
from memory_hub.client_watch import watch
from memory_hub.service import Hub
from memory_hub.store import Store, DELIVERY_TABLES
from test_index import _migration_db
from test_delivery import (collaboration, room, join, post, claim, call, status,
    read_delivery, reply, values, reject, A, B, ADMIN, IDENTITIES)


def request(binding, identifier=None, **extra):
    return {'request_id': identifier or uuid.uuid4().hex, 'generation': binding['generation'],
            'lease_seconds': 300, **extra}


def test_claim_response_loss_restart_recovers_exact_lease_once(collaboration):
    hub, url, sqlite = collaboration
    s = room(hub); binding = join(hub, s, max_turns=1); post(hub, s, B)
    args = request(binding)
    first = claim(hub, binding, **args)
    restarted = Hub(Store(url, allow_sqlite=sqlite), clock=hub.clock, principals=IDENTITIES)
    assert claim(restarted, binding, **args) == first
    observed = status(restarted, s)['participants'][0]
    assert observed['turns_used'] == 1 and observed['latest_delivery']['attempts'] == 1
    assert args['request_id'] not in json.dumps(observed)
    assert claim(restarted, binding, **request(binding))['status'] == 'busy'
    assert claim(restarted, binding)['status'] == 'busy'  # Legacy receiver too.
    with hub.store.engine.connect() as conn:
        row = conn.execute(select(DELIVERY_TABLES['joins']).where(
            DELIVERY_TABLES['joins'].c.operation == 'claim')).mappings().one()
    assert row['request_key'] == hashlib.sha256(args['request_id'].encode()).hexdigest()


def test_concurrent_different_receivers_never_receive_same_live_lease(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda args: claim(hub, binding, **args),
                                [request(binding), request(binding)]))
    assert sorted(item['status'] for item in results) == ['busy', 'ready']
    assert status(hub, s)['participants'][0]['turns_used'] == 1


def test_key_conflicts_generation_and_expiry_cannot_recreate_lease(collaboration):
    hub, _, _ = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    args = request(binding, lease_seconds=15)
    first = claim(hub, binding, **args)['delivery']
    reject('idempotency_conflict', lambda: claim(hub, binding, **(args | {'lease_seconds': 30})))
    other = join(hub, room(hub))
    reject('idempotency_conflict', lambda: claim(hub, other, **args))
    reject('stale_binding', lambda: claim(hub, binding, **(args | {'generation': 99})))
    clock[0] += 16
    reject('stale_claim', lambda: claim(hub, binding, **args))
    assert status(hub, s)['participants'][0]['turns_used'] == 1
    second = claim(hub, binding, **request(binding, lease_seconds=15))['delivery']
    assert second['delivery_id'] == first['delivery_id'] and second['lease_id'] != first['lease_id']
    assert second['attempts'] == 2
    reject('stale_delivery', lambda: read_delivery(hub, s, first))


def test_replay_never_rewakes_dispatched_read_or_replied_delivery(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    args = request(binding); delivery = claim(hub, binding, **args)['delivery']
    call(hub, 'dispatched', project_id='p', binding_id=binding['binding_id'],
         delivery_id=delivery['delivery_id'], lease_id=delivery['lease_id'])
    assert claim(hub, binding, **args) == {'status': 'busy', 'delivery': None}
    read_delivery(hub, s, delivery)
    assert claim(hub, binding, **args)['status'] == 'busy'
    reply(hub, s, delivery)
    reject('stale_claim', lambda: claim(hub, binding, **args))
    assert claim(hub, binding, **request(binding))['status'] == 'idle'
    assert status(hub, s)['participants'][0]['turns_used'] == 1


@pytest.mark.parametrize('control', ['pause', 'disable', 'rejoin'])
def test_claim_recovery_cannot_bypass_administrative_fences(collaboration, control):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    args = request(binding); original = claim(hub, binding, **args)['delivery']
    if control == 'pause':
        call(hub, 'pause', ADMIN, **values(s, paused=True, expected_version=1))
        assert claim(hub, binding, **args)['status'] == 'paused'
        call(hub, 'pause', ADMIN, **values(s, paused=False, expected_version=2))
        reject('stale_claim', lambda: claim(hub, binding, **args))
    else:
        call(hub, 'control', ADMIN, project_id='p', binding_id=binding['binding_id'],
             enabled=False, expected_version=1)
        assert claim(hub, binding, **args)['status'] == 'disabled'
        if control == 'rejoin':
            join(hub, s)
            reject('stale_binding', lambda: claim(hub, binding, **args))
        else:
            call(hub, 'control', ADMIN, project_id='p', binding_id=binding['binding_id'],
                 enabled=True, expected_version=2)
            reject('stale_claim', lambda: claim(hub, binding, **args))
    assert status(hub, s)['participants'][0]['processed_sequence'] == binding['processed_sequence']
    reject('stale_delivery' if control != 'rejoin' else 'not_found', lambda: read_delivery(hub, s, original))


@pytest.mark.parametrize('control', ['pause', 'disable', 'archive', 'revoke'])
def test_binding_expiry_restores_manual_only_without_safety_controls(collaboration, control):
    hub, _, _ = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s, ttl_seconds=60); post(hub, s, B)
    delivery = claim(hub, binding)['delivery']
    clock[0] += 61
    manual = post(hub, s, A, body='Manual after expiry')
    assert manual['sequence'] > delivery['through_sequence']
    assert status(hub, s)['participants'][0]['processed_sequence'] == binding['processed_sequence']
    reject('delivery_stopped', lambda: read_delivery(hub, s, delivery))
    reject('delivery_stopped', lambda: reply(hub, s, delivery))
    if control == 'pause':
        call(hub, 'pause', ADMIN, **values(s, paused=True, expected_version=1))
    elif control == 'disable':
        call(hub, 'control', ADMIN, project_id='p', binding_id=binding['binding_id'],
             enabled=False, expected_version=1)
    elif control == 'archive':
        hub.call('archive_session', values(s, archived=True, expected_version=1,
            idempotency_key='archive'), ADMIN)
    else:
        hub._principals = tuple(p for p in hub._principals if p.worker_id != A.worker_id)
    reject('session_archived' if control == 'archive' else 'delivery_stopped',
           lambda: post(hub, s, A, body='Control cannot be bypassed by expiry'))


def test_optional_claim_recovery_fields_are_paired():
    base = {'project_id': 'p', 'binding_id': '1' * 32}
    assert ClaimDelivery.model_validate(base).request_id is None
    for extra in ({'request_id': '2' * 32}, {'generation': 1},
                  {'request_id': 'invalid', 'generation': 1}):
        with pytest.raises(ValidationError):
            ClaimDelivery.model_validate(base | extra)


def test_watcher_lost_claim_survives_process_restart_without_double_budget(collaboration, tmp_path):
    hub, _, _ = collaboration
    s = room(hub)
    config = dict(project_id='p', session_id=s['session_id'], client='claude',
        display_name='Claude', native_session_id='native', after_sequence=None,
        max_turns=1, idempotency_key='watch-restart', expires_at=1400, ttl_seconds=3600)
    # Join before the human event as real fresh setup starts at the latest event.
    binding = call(hub, 'join', **{key: config[key] for key in (
        'project_id', 'session_id', 'client', 'display_name', 'native_session_id',
        'after_sequence', 'max_turns', 'idempotency_key', 'ttl_seconds')})
    post(hub, s, B)
    requests = []
    lost = [True]
    def handle(req):
        operation = req.url.path.rsplit('/', 1)[-1]; data = json.loads(req.content)
        result = call(hub, operation, **data)
        if operation == 'claim':
            requests.append(data)
            if lost[0]:
                lost[0] = False
                raise httpx.ReadError('response lost after server commit', request=req)
        return httpx.Response(200, json=result)
    class Restart(Exception): pass
    def restart(_): raise Restart()
    event = {'hook_event_name': 'Stop', 'session_id': 'native'}
    state = tmp_path / 'status.json'
    with httpx.Client(base_url='https://hub.test', transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(Restart):
            watch(config, event, client, state, now=lambda:1000, sleep=restart)
        pending = json.loads((tmp_path / 'chat-claim.json').read_text())
        assert pending['request_id'] == requests[0]['request_id']
        assert watch(config, event, client, state, now=lambda:1000, sleep=lambda _:pytest.fail('No busy stall'))
    assert requests[0] == requests[1]
    observed = status(hub, s)['participants'][0]
    assert observed['turns_used'] == 1 and observed['latest_delivery']['attempts'] == 1
    assert not (tmp_path / 'chat-claim.json').exists()



def test_idle_busy_pause_do_not_grow_memos_and_same_operation_converges(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    args = request(binding)
    for _ in range(10):
        assert claim(hub, binding, **args)['status'] == 'idle'
    requests = DELIVERY_TABLES['joins']
    def memos():
        with hub.store.engine.connect() as conn:
            return conn.execute(select(requests).where(requests.c.operation == 'claim')).mappings().all()
    assert memos() == []
    post(hub, s, B, body='Private message body never belongs in a claim memo')
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: claim(hub, binding, **args), range(2)))
    assert results[0] == results[1] and results[0]['status'] == 'ready'
    for _ in range(10):
        assert claim(hub, binding, **request(binding))['status'] == 'busy'
    call(hub, 'pause', ADMIN, **values(s, paused=True, expected_version=1))
    for _ in range(10):
        assert claim(hub, binding, **request(binding))['status'] == 'paused'
    observed = memos()
    assert len(observed) == 1 and 'Private message body' not in json.dumps(observed[0]['result'])
    assert status(hub, s)['participants'][0]['turns_used'] == 1



def test_partial_tool_read_without_dispatch_prevents_ready_replay(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    messages = [post(hub, s, B) for _ in range(2)]
    args = request(binding)
    delivery = claim(hub, binding, **args)['delivery']
    partial = read_delivery(hub, s, delivery, limit=1)
    assert partial['delivery_receipt']['status'] == 'partial_tool_read'
    assert len(partial['delivery_receipt']['unread_message_ids']) == 1
    assert claim(hub, binding, **args) == {'status': 'busy', 'delivery': None}
    observed = status(hub, s)['participants'][0]
    assert observed['latest_delivery']['status'] == 'leased'
    assert observed['latest_delivery']['dispatched_at'] is None
    assert observed['latest_delivery']['read_at'] is None
    assert observed['turns_used'] == observed['latest_delivery']['attempts'] == 1
    assert observed['processed_sequence'] == binding['processed_sequence']
    # The same lease can finish its remaining read/reply without another start.
    assert read_delivery(hub, s, delivery, after_sequence=messages[0]['sequence'], limit=1)[
        'delivery_receipt']['status'] == 'tool_read'
    reply(hub, s, delivery)


def test_exhausted_expired_pending_restores_manual_preserves_unread(collaboration):
    hub, _, _ = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s, max_turns=1)
    message = post(hub, s, B)
    delivery = claim(hub, binding, lease_seconds=15)['delivery']
    reject('delivery_metadata_required', lambda: post(hub, s, A))
    clock[0] += 16
    assert claim(hub, binding)['status'] == 'budget_exhausted'
    post(hub, s, A, body='Manual after final lease expiry')
    observed = status(hub, s)['participants'][0]
    assert observed['processed_sequence'] == binding['processed_sequence']
    assert observed['turns_used'] == 1
    reject('stale_delivery', lambda: read_delivery(hub, s, delivery))
    reject('stale_delivery', lambda: reply(hub, s, delivery))
    call(hub, 'disconnect', project_id='p', binding_id=binding['binding_id'], expected_version=1)
    renewed = join(hub, s)
    assert message['message_id'] in claim(hub, renewed)['delivery']['message_ids']


@pytest.mark.parametrize('control', ['pause', 'disable', 'archive', 'revoke', 'remaining_budget', 'failed_remaining', 'failed_exhausted'])
def test_exhausted_expired_pending_safety_edges(collaboration, control):
    hub, _, _ = collaboration
    clock = [1000.0]; hub.clock = lambda: clock[0]
    s = room(hub); binding = join(hub, s, max_turns=2 if control in {'remaining_budget', 'failed_remaining'} else 1)
    post(hub, s, B); delivery = claim(hub, binding, lease_seconds=15)['delivery']
    clock[0] += 16
    if control.startswith('failed_'):
        with hub.store.engine.begin() as conn:
            t = DELIVERY_TABLES['deliveries']
            conn.execute(t.update().where(t.c.delivery_id == delivery['delivery_id']).values(status='failed'))
    if control == 'pause':
        call(hub, 'pause', ADMIN, **values(s, paused=True, expected_version=1))
    elif control == 'disable':
        call(hub, 'control', ADMIN, project_id='p', binding_id=binding['binding_id'], enabled=False, expected_version=1)
    elif control == 'archive':
        hub.call('archive_session', values(s, archived=True, expected_version=1, idempotency_key='archive'), ADMIN)
    elif control == 'revoke':
        hub._principals = tuple(p for p in hub._principals if p.worker_id != A.worker_id)
    if control == 'failed_exhausted':
        post(hub, s, A)
        assert status(hub, s)['participants'][0]['latest_delivery']['status'] == 'failed'
    else:
        code = 'delivery_metadata_required' if control in {'remaining_budget', 'failed_remaining'} else 'session_archived' if control == 'archive' else 'delivery_stopped'
        reject(code, lambda: post(hub, s, A))
