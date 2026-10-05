"""Three simultaneous automatic bindings in one room: fan-out, depth cap, budget and pause.

Characterizes the existing rules in delivery_service.py; it changes no product behaviour.
Rounds claim for every binding first (all turns in flight), then read and finish in A, B, C
order, so batch contents are deterministic under the fixture's fixed clock.
"""
import uuid
import pytest
from sqlalchemy import select
from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import SESSION_TABLES
from test_delivery import call, claim, read_delivery, reply, status
from test_delivery_no_reply import complete, count_events
from test_sessions import collaboration, room, values, human, reject, ADMIN, A, B, IDENTITIES
from test_index import _migration_db

C = Principal(worker_id='worker-c', projects=['p'])
CLIENTS = {A.worker_id: 'codex', B.worker_id: 'claude', C.worker_id: 'gemini'}
WA, WB, WC, H = A.worker_id, B.worker_id, C.worker_id, 'human'


@pytest.fixture
def trio(collaboration):
    hub, _, _ = collaboration
    # Same store and fixed clock; only the configured identities gain a third worker.
    return Hub(hub.store, clock=hub.clock, principals=[*IDENTITIES, C])


def bind_all(hub, s, turns=(20, 20, 20)):
    return [(actor, call(hub, 'join', actor, **values(s, client=CLIENTS[actor.worker_id],
        display_name=CLIENTS[actor.worker_id], native_session_id='native-' + actor.worker_id,
        idempotency_key=uuid.uuid4().hex, max_turns=n))) for actor, n in zip((A, B, C), turns)]


def say(hub, s, body):
    return hub.sessions.call('post_session_message', values(s, body=body,
        idempotency_key=uuid.uuid4().hex), human(identity='room-human'))


def timeline(hub, s):
    """Every room message as (author, depth) in sequence order, without read pagination."""
    e = SESSION_TABLES['events']
    with hub.store.engine.connect() as conn:
        rows = conn.execute(select(e.c.payload).where(e.c.project_id == s['project_id'],
            e.c.session_id == s['session_id'], e.c.type == 'message').order_by(e.c.sequence)).scalars().all()
    return [(x['actor']['id'] if x['actor']['kind'] == 'worker' else H, x['automatic_reply_depth']) for x in rows]


def view(hub, s):
    parts = status(hub, s)['participants']
    # Checked at every observation: no binding ever runs past its own budget.
    assert all(p['turns_used'] <= p['max_turns'] for p in parts)
    return {p['worker_id']: p for p in parts}


def states(hub, s):
    return [p['status'] for p in view(hub, s).values()]


def turns(hub, s):
    return [p['turns_used'] for p in view(hub, s).values()]


def claims(hub, s, bindings):
    results = [claim(hub, binding, actor) for actor, binding in bindings]
    view(hub, s)
    return results


def round_of(hub, s, bindings, finish=reply):
    """Claim for all three first, then each ready binding reads fully and finishes."""
    results, written = claims(hub, s, bindings), []
    for (actor, _), result in zip(bindings, results):
        if result['status'] == 'ready':
            read_delivery(hub, s, result['delivery'], actor)
            written.append(finish(hub, s, result['delivery'], actor))
    return results, written


def ids(*messages):
    return [m['message_id'] for m in messages]


def pause(hub, s, paused, version):
    return call(hub, 'pause', ADMIN, **values(s, paused=paused, expected_version=version))


@pytest.mark.parametrize('max_turns', [1, 2, 3])
def test_human_fans_out_to_three_peers_fan_out_once_and_depth_two_never_delivers(trio, max_turns):
    hub = trio; s = room(hub); bindings = bind_all(hub, s, (max_turns,) * 3)
    root = say(hub, s, 'One human topic for three AIs')
    first, (ra, rb, rc) = round_of(hub, s, bindings)
    assert [r['delivery']['message_ids'] for r in first] == [ids(root)] * 3
    assert [w['delivery_receipt']['processed_sequence'] for w in (ra, rb, rc)] == [root['sequence']] * 3
    second, _ = round_of(hub, s, bindings)
    if max_turns == 1:
        # Budget check precedes the event scan: peer replies stay unprocessed, never over budget.
        assert second == [{'status': 'budget_exhausted', 'delivery': None}] * 3
        assert timeline(hub, s) == [(H, 0), (WA, 1), (WB, 1), (WC, 1)]
        assert [p['processed_sequence'] for p in view(hub, s).values()] == [root['sequence']] * 3
        assert turns(hub, s) == [1, 1, 1] and states(hub, s) == ['budget_exhausted'] * 3
        return
    # Each depth-1 reply reaches exactly the other two bindings, never its author.
    assert [r['delivery']['message_ids'] for r in second] == [ids(rb, rc), ids(ra, rc), ids(ra, rb)]
    assert all({m['automatic_reply_depth'] for m in r['delivery']['messages']} == {1} for r in second)
    third, _ = round_of(hub, s, bindings)
    # Delivery admits only depth < 2, so replies stop at depth 2 and no depth 3 is created.
    assert timeline(hub, s) == [(H, 0), (WA, 1), (WB, 1), (WC, 1), (WA, 2), (WB, 2), (WC, 2)]
    assert turns(hub, s) == [2, 2, 2]
    if max_turns == 2:
        assert third == [{'status': 'budget_exhausted', 'delivery': None}] * 3
        assert states(hub, s) == ['budget_exhausted'] * 3
    else:
        # Spare budget remains: the depth cap, not the budget, ends the chain.
        assert [r['status'] for r in third] == ['idle'] * 3
        assert [r['status'] for r in claims(hub, s, bindings)] == ['idle'] * 3
        assert states(hub, s) == ['waiting'] * 3 and turns(hub, s) == [2, 2, 2]


def test_human_interjection_during_three_inflight_turns_reaches_all_in_sequence_order(trio):
    hub = trio; s = room(hub); bindings = bind_all(hub, s)
    root = say(hub, s, 'First human topic')
    da, db, dc = [r['delivery'] for r in claims(hub, s, bindings)]
    assert states(hub, s) == ['processing'] * 3
    read_delivery(hub, s, da, A); ra = reply(hub, s, da, A)
    interjection = say(hub, s, 'Human interjection while B and C are still running')
    late = []
    for actor, delivery in ((B, db), (C, dc)):
        page = read_delivery(hub, s, delivery, actor)
        # An in-flight read stops at its through_sequence; the interjection waits for the next batch.
        assert [x['message_id'] for x in page['items'] if x['type'] == 'message'] == ids(root)
        late.append(reply(hub, s, delivery, actor))
    rb, rc = late
    second, _ = round_of(hub, s, bindings)
    assert [r['delivery']['message_ids'] for r in second] == [
        ids(interjection, rb, rc), ids(ra, interjection, rc), ids(ra, interjection, rb)]
    for r in second:
        sequences = [m['sequence'] for m in r['delivery']['messages']]
        assert sequences == sorted(sequences)
        assert [(m['actor_kind'], m['automatic_reply_depth']) for m in r['delivery']['messages']
                if m['message_id'] == interjection['message_id']] == [('human', 0)]
    third, _ = round_of(hub, s, bindings)
    # The interjection is never redelivered; only peers' new depth-1 answers fan out.
    assert all(interjection['message_id'] not in r['delivery']['message_ids'] for r in third)
    assert [r['status'] for r in claims(hub, s, bindings)] == ['idle'] * 3
    # A batch holding a new human root answers at depth 1 even with older AI context.
    assert timeline(hub, s) == [(H, 0), (WA, 1), (H, 0), (WB, 1), (WC, 1),
                                (WA, 1), (WB, 1), (WC, 1), (WA, 2), (WB, 2), (WC, 2)]
    assert turns(hub, s) == [3, 3, 3]


def test_one_silent_completion_advances_only_its_binding_and_wakes_no_peer(trio):
    hub = trio; s = room(hub); bindings = bind_all(hub, s)
    root = say(hub, s, 'Human question; one AI may stay silent')
    da, db, dc = [r['delivery'] for r in claims(hub, s, bindings)]
    for actor, delivery in zip((A, B, C), (da, db, dc)):
        read_delivery(hub, s, delivery, actor)
    ra = reply(hub, s, da, A)
    before = count_events(hub, s)
    silent = complete(hub, s, db, B)
    assert silent['delivery_receipt'] == {'delivery_id': db['delivery_id'], 'status': 'no_reply',
                                          'processed_sequence': root['sequence']}
    assert count_events(hub, s) == before
    rc = reply(hub, s, dc, C)
    seen = view(hub, s)[WB]
    assert seen['processed_sequence'] == root['sequence'] and seen['turns_used'] == 1
    assert seen['latest_delivery']['status'] == 'no_reply' and seen['latest_delivery']['reply_message_id'] is None
    second = claims(hub, s, bindings)
    assert [r['delivery']['message_ids'] for r in second] == [ids(rc), ids(ra, rc), ids(ra)]
    assert not any(m['actor_id'] == WB for r in second for m in r['delivery']['messages'])
    # Everyone silent this round: no event is created and no binding is woken again.
    before = count_events(hub, s)
    for (actor, _), r in zip(bindings, second):
        read_delivery(hub, s, r['delivery'], actor); complete(hub, s, r['delivery'], actor)
    assert count_events(hub, s) == before
    assert [r['status'] for r in claims(hub, s, bindings)] == ['idle'] * 3
    assert timeline(hub, s) == [(H, 0), (WA, 1), (WC, 1)] and turns(hub, s) == [2, 2, 2]


def test_pause_holds_new_human_with_budget_left_and_masks_exhaustion_until_resume(trio):
    hub = trio; s = room(hub); bindings = bind_all(hub, s, (3, 3, 1))
    first = say(hub, s, 'Before pause')
    round_of(hub, s, bindings, finish=complete)
    assert states(hub, s) == ['waiting', 'waiting', 'budget_exhausted'] and turns(hub, s) == [1, 1, 1]
    assert pause(hub, s, True, 1)['paused']
    held = say(hub, s, 'Human message while paused')
    # Real precedence: _blocked() (revoked > disconnected > archived > paused > disabled > expired)
    # is checked before failed/processing/budget_exhausted, so pause masks C's exhaustion.
    assert states(hub, s) == ['paused'] * 3
    assert claims(hub, s, bindings) == [{'status': 'paused', 'delivery': None}] * 3
    seen = view(hub, s)
    # Only the counters still show exhaustion while paused; budget remains for A and B.
    assert [(p['turns_used'], p['max_turns']) for p in seen.values()] == [(1, 3), (1, 3), (1, 1)]
    assert [p['processed_sequence'] for p in seen.values()] == [first['sequence']] * 3
    pause(hub, s, False, 2)
    assert states(hub, s) == ['waiting', 'waiting', 'budget_exhausted']
    resumed = claims(hub, s, bindings)
    assert [r['delivery']['message_ids'] for r in resumed[:2]] == [ids(held)] * 2
    assert resumed[2] == {'status': 'budget_exhausted', 'delivery': None}
    assert view(hub, s)[WC]['processed_sequence'] == first['sequence'] and turns(hub, s) == [2, 2, 1]


def test_pause_fences_three_inflight_turns_and_retry_after_resume_is_charged(trio):
    hub = trio; s = room(hub); bindings = bind_all(hub, s, (3, 3, 1))
    root = say(hub, s, 'Topic interrupted by pause')
    inflight = [r['delivery'] for r in claims(hub, s, bindings)]
    assert states(hub, s) == ['processing'] * 3 and turns(hub, s) == [1, 1, 1]
    pause(hub, s, True, 1)
    for (actor, _), delivery in zip(bindings, inflight):
        reject('delivery_stopped', lambda: read_delivery(hub, s, delivery, actor))
    assert states(hub, s) == ['paused'] * 3
    pause(hub, s, False, 2)
    for (actor, _), delivery in zip(bindings, inflight):
        reject('stale_delivery', lambda: read_delivery(hub, s, delivery, actor))
    assert states(hub, s) == ['waiting', 'waiting', 'budget_exhausted']
    retried = claims(hub, s, bindings)
    for old, new in zip(inflight[:2], [r['delivery'] for r in retried[:2]]):
        # Same batch and reply key under a new lease; the pause is not a failed attempt.
        assert new['delivery_id'] == old['delivery_id'] and new['lease_id'] != old['lease_id']
        assert new['message_ids'] == ids(root) and new['attempts'] == 1
    # The interrupted model start is not refunded: C's only turn is gone and its batch stays unprocessed.
    assert retried[2] == {'status': 'budget_exhausted', 'delivery': None}
    seen = view(hub, s)
    assert turns(hub, s) == [2, 2, 1] and seen[WC]['latest_delivery']['status'] == 'leased'
    assert seen[WC]['processed_sequence'] < root['sequence']


@pytest.mark.parametrize('max_turns', [2, 3, 4])
def test_minimum_budget_for_root_interjection_pause_scenario_batched(trio, max_turns):
    """Human A -> three replies -> human B -> replies -> pause -> human C, fully batched.

    Turn 1 answers A (depth 1). Turn 2 batches B with peers' depth-1 answers and answers at
    depth 1 again. Turn 3 answers those at depth 2. A fourth claim is idle only with budget left,
    so C is held by the pause alone, and delivered on resume, only from max_turns=4.
    """
    hub = trio; s = room(hub); bindings = bind_all(hub, s, (max_turns,) * 3)
    say(hub, s, 'Human A')
    round_of(hub, s, bindings)
    say(hub, s, 'Human interjection B')
    second, _ = round_of(hub, s, bindings)
    assert [r['status'] for r in second] == ['ready'] * 3
    third, _ = round_of(hub, s, bindings)
    fourth, _ = round_of(hub, s, bindings)
    if max_turns == 2:
        assert [r['status'] for r in third + fourth] == ['budget_exhausted'] * 6
    else:
        assert [r['status'] for r in third] == ['ready'] * 3
        assert [r['status'] for r in fourth] == ['budget_exhausted' if max_turns == 3 else 'idle'] * 3
    assert turns(hub, s) == [min(3, max_turns)] * 3
    pause(hub, s, True, 1)
    held = say(hub, s, 'Human C while paused')
    assert claims(hub, s, bindings) == [{'status': 'paused', 'delivery': None}] * 3
    assert states(hub, s) == ['paused'] * 3
    pause(hub, s, False, 2)
    after = claims(hub, s, bindings)
    if max_turns < 4:
        assert after == [{'status': 'budget_exhausted', 'delivery': None}] * 3
    else:
        assert [r['delivery']['message_ids'] for r in after] == [ids(held)] * 3
        assert turns(hub, s) == [4, 4, 4]


@pytest.mark.parametrize('observer_turns', [6, 7])
def test_unbatched_interleaving_charges_one_binding_six_turns_before_pause(trio, observer_turns):
    """Worst case for A: each trigger (2 humans + up to 2 depth-1 replies per peer) is its own turn."""
    hub = trio; s = room(hub)
    bindings = bind_all(hub, s, (observer_turns, 20, 20)); (_, a), (_, b), (_, c) = bindings

    def step(actor, binding, expected):
        result = claim(hub, binding, actor)
        assert result['status'] == 'ready' and result['delivery']['message_ids'] == ids(*expected)
        read_delivery(hub, s, result['delivery'], actor)
        written = reply(hub, s, result['delivery'], actor)
        view(hub, s)
        return written
    ha = say(hub, s, 'Human A')
    ra1 = step(A, a, [ha]); rb1 = step(B, b, [ha, ra1]); step(A, a, [rb1])
    rc1 = step(C, c, [ha, ra1, rb1]); step(A, a, [rc1]); step(B, b, [rc1])
    assert [r['status'] for r in claims(hub, s, bindings)] == ['idle'] * 3
    hb = say(hub, s, 'Human interjection B')
    ra4 = step(A, a, [hb]); rb3 = step(B, b, [hb, ra4]); step(A, a, [rb3])
    rc2 = step(C, c, [hb, ra4, rb3]); step(A, a, [rc2]); step(B, b, [rc2])
    # Exhaustion is reported before the scan, so A's settled claim is budget_exhausted at 6/6.
    assert [r['status'] for r in claims(hub, s, bindings)] == [
        'budget_exhausted' if observer_turns == 6 else 'idle', 'idle', 'idle']
    assert turns(hub, s) == [6, 4, 2]
    assert [d for _, d in timeline(hub, s)] == [0, 1, 1, 2, 1, 2, 2, 0, 1, 1, 2, 1, 2, 2]
    pause(hub, s, True, 1)
    held = say(hub, s, 'Human C while paused')
    assert claims(hub, s, bindings) == [{'status': 'paused', 'delivery': None}] * 3
    pause(hub, s, False, 2)
    after = claims(hub, s, bindings)
    assert [r['delivery']['message_ids'] for r in after[1:]] == [ids(held)] * 2
    if observer_turns == 6:
        assert after[0] == {'status': 'budget_exhausted', 'delivery': None}
    else:
        assert after[0]['delivery']['message_ids'] == ids(held) and turns(hub, s) == [7, 5, 3]
