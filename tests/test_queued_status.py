"""Queued reservations in status: Hub admission state only, never a read or reply claim."""
import json
import shutil
import subprocess
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event

from memory_hub.app import create_app
from memory_hub.i18n import CATALOG, LANGUAGES, _locale
from memory_hub.store import DELIVERY_TABLES, HubError
from memory_hub.web_chat_assets import chat_script
from test_delivery import activate, call, claim, join, read_delivery, reply, reserve, status
from test_index import _migration_db
from test_sessions import collaboration, room, post, values, human, ADMIN, A, B, Q

SAFE = {'through_sequence', 'created_at', 'queued_until'}
LABEL, ENDS, NOTE = 'ui_c10d00000001', 'ui_c10d00000002', 'ui_c10d00000003'


def view(hub, session, worker=A.worker_id):
    return next(p for p in status(hub, session)['participants'] if p['worker_id'] == worker)


def human_post(hub, session):
    return hub.sessions.call('post_session_message', values(session, body='Human message',
                             idempotency_key=uuid.uuid4().hex), human())


def shown(reservation):
    """All that status may reveal about a reservation."""
    return {name: reservation[name] for name in SAFE}


def key(number):
    """A reservation identifier with a chosen place in primary-key order."""
    return '%032x' % number


def at(hub, moment):
    hub.delivery.clock = lambda: moment


def store(hub, reservation, **changes):
    """Write a reservation row directly, as history or inconsistent data would leave it."""
    value = {**reservation, **changes}
    with hub.store.engine.begin() as conn:
        conn.execute(DELIVERY_TABLES['joins'].insert().values(project_id='p', operation='reserve',
            actor_kind='worker', worker_id=A.worker_id, request_key=value['reservation_id'],
            payload_hash='0' * 64, result={'status': 'queued', 'reservation': value}))
    return value


def returned(hub, session):
    """Reservations the database handed back during one status call, in order."""
    seen, check = [], hub.delivery._reservation_live
    hub.delivery._reservation_live = lambda *args: seen.append(args[3]['reservation_id']) or check(*args)
    try:
        status(hub, session)
    finally:
        del hub.delivery._reservation_live
    return seen


def request_statements(hub, action):
    """SQL sent to the reservation table while `action` runs."""
    seen = []
    def record(conn, cursor, statement, parameters, context, executemany):
        if 'collab_binding_requests' in statement:
            seen.append(' '.join(statement.split()))
    event.listen(hub.store.engine, 'before_cursor_execute', record)
    try:
        action()
    finally:
        event.remove(hub.store.engine, 'before_cursor_execute', record)
    return seen


def test_reservation_is_shown_only_while_queued_with_three_safe_scalars(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    before = view(hub, s)
    assert 'queued_reservation' not in before
    message = post(hub, s, B)
    # Unread messages alone are not a reservation.
    assert view(hub, s) == before
    queued = reserve(hub, binding, queue_seconds=600)['reservation']
    shown = view(hub, s)
    assert shown.pop('queued_reservation') == {'through_sequence': message['sequence'],
                                               'created_at': 1000.0, 'queued_until': 1600.0}
    # Additive only: every earlier field, including the status receivers compare, is unchanged.
    assert shown == before and shown['status'] == 'waiting'
    whole = json.dumps(status(hub, s))
    assert set(view(hub, s)['queued_reservation']) == SAFE
    for private in (queued['reservation_id'], message['message_id'], 'reservation_id', 'message_ids',
                    'binding_version', 'control_version'):
        assert private not in whole
    delivery = activate(hub, binding, queued)['delivery']
    active = view(hub, s)
    assert 'queued_reservation' not in active and active['status'] == 'processing'
    read_delivery(hub, s, delivery)
    assert 'queued_reservation' not in view(hub, s)
    reply(hub, s, delivery)
    done = view(hub, s)
    assert 'queued_reservation' not in done and done['latest_delivery']['status'] == 'replied'


@pytest.mark.parametrize('change,state,shown', [
    ('relay_offline', 'offline', True),
    ('archived_then_reopened', 'waiting', True),
    ('paused', 'paused', False),
    ('paused_then_resumed', 'waiting', False),
    ('disabled', 'disabled', False),
    ('disabled_then_enabled', 'waiting', False),
    ('disconnected', 'disconnected', False),
    ('rejoined', 'waiting', False),
    ('queue_expired', 'offline', False),
    ('binding_expired', 'expired', False),
    ('claimed_instead', 'processing', False),
    ('claim_lease_expired', 'offline', False),
    ('cursor_moved', 'waiting', False),
    ('revoked', 'revoked', False),
    ('archived', 'archived', False),
])
def test_only_a_reservation_activation_would_still_accept_is_shown(collaboration, change, state, shown):
    hub, _, _ = collaboration
    s = room(hub)
    binding = join(hub, s, ttl_seconds=600 if change == 'binding_expired' else 3600)
    post(hub, s, B)
    reservation = reserve(hub, binding, queue_seconds=900)['reservation']
    assert set(view(hub, s)['queued_reservation']) == SAFE
    target = dict(project_id='p', binding_id=binding['binding_id'])
    admin = human('admin')
    if change == 'relay_offline':
        hub.delivery.clock = lambda: 1046.0
    elif change.startswith('paused'):
        call(hub, 'pause', admin, **values(s, paused=True, expected_version=1))
        if change == 'paused_then_resumed':
            call(hub, 'pause', admin, **values(s, paused=False, expected_version=2))
    elif change.startswith('disabled'):
        call(hub, 'control', **target, enabled=False, expected_version=1)
        if change == 'disabled_then_enabled':
            call(hub, 'control', **target, enabled=True, expected_version=2)
    elif change in {'disconnected', 'rejoined'}:
        call(hub, 'disconnect', **target, expected_version=1)
        if change == 'rejoined':
            join(hub, s)
    elif change == 'queue_expired':
        hub.delivery.clock = lambda: 1900.0
    elif change == 'binding_expired':
        hub.delivery.clock = lambda: 1600.0
    elif change in {'claimed_instead', 'cursor_moved', 'claim_lease_expired'}:
        delivery = claim(hub, binding, lease_seconds=15)['delivery']
        if change == 'cursor_moved':
            read_delivery(hub, s, delivery); reply(hub, s, delivery)
            post(hub, s, B)
        elif change == 'claim_lease_expired':
            # The pending delivery still owns admission after its lease has run out.
            hub.delivery.clock = lambda: 1100.0
    elif change == 'revoked':
        hub.delivery.principals = lambda conn: [ADMIN, B, Q]
    else:
        hub.call('archive_session', values(s, archived=True, expected_version=1, idempotency_key='close'), ADMIN)
        if change == 'archived_then_reopened':
            hub.call('archive_session', values(s, archived=False, expected_version=2, idempotency_key='open'), ADMIN)
    after = view(hub, s)
    assert after['status'] == state
    assert ('queued_reservation' in after) == shown
    # Status reports exactly what activation would do with this reservation.
    if not shown:
        with pytest.raises(HubError):
            activate(hub, binding, reservation)
    elif state == 'waiting':
        assert activate(hub, binding, reservation)['status'] == 'ready'


def test_a_recorded_activation_is_never_shown_as_queued(collaboration):
    """Safety net for inconsistent data: an activation record without its delivery."""
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    older = reserve(hub, binding, queue_seconds=300)['reservation']
    at(hub, 1001.0)
    newer = reserve(hub, binding, queue_seconds=600)['reservation']
    assert view(hub, s)['queued_reservation'] == shown(newer)
    for reservation, remaining in ((newer, shown(older)), (older, None)):
        with hub.store.engine.begin() as conn:
            conn.execute(DELIVERY_TABLES['joins'].insert().values(project_id='p', operation='activate',
                actor_kind='worker', worker_id=A.worker_id, request_key=reservation['reservation_id'],
                payload_hash='0' * 64, result={}))
        assert view(hub, s).get('queued_reservation') == remaining


STALE = ['queue_expired', 'room_paused_and_resumed', 'binding_disabled_and_enabled', 'cursor_moved', 'rejoined']


@pytest.mark.parametrize('stale', STALE)
def test_more_stale_reservations_than_the_limit_never_hide_the_current_one(collaboration, stale):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s, ttl_seconds=7200); post(hub, s, B)
    target, admin = dict(project_id='p', binding_id=binding['binding_id']), human('admin')
    # Twelve overlapping reservations made through the API; all precede the current one in the primary key.
    old = [reserve(hub, binding, request_id=key(n), queue_seconds=60 if stale == 'queue_expired' else 3600)['reservation']
           for n in range(12)]
    assert 'queued_reservation' in view(hub, s)
    if stale == 'queue_expired':
        at(hub, 1100.0)
    elif stale == 'room_paused_and_resumed':
        call(hub, 'pause', admin, **values(s, paused=True, expected_version=1))
        call(hub, 'pause', admin, **values(s, paused=False, expected_version=2))
    elif stale == 'binding_disabled_and_enabled':
        call(hub, 'control', **target, enabled=False, expected_version=1)
        call(hub, 'control', **target, enabled=True, expected_version=2)
    elif stale == 'cursor_moved':
        delivery = claim(hub, binding)['delivery']
        read_delivery(hub, s, delivery); reply(hub, s, delivery); post(hub, s, B)
    else:
        call(hub, 'disconnect', **target, expected_version=1)
        binding = join(hub, s, ttl_seconds=7200)
    # None of the twelve is returned by the database, let alone shown.
    assert returned(hub, s) == [] and 'queued_reservation' not in view(hub, s)
    current = reserve(hub, binding, request_id=key(99), queue_seconds=300)['reservation']
    assert returned(hub, s) == [current['reservation_id']]
    assert view(hub, s)['queued_reservation'] == shown(current)
    for reservation in old:
        with pytest.raises(HubError):
            activate(hub, binding, reservation)
    assert activate(hub, binding, current)['status'] == 'ready'
    assert 'queued_reservation' not in view(hub, s)


def test_newer_expired_reservations_never_hide_an_older_valid_one(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s, ttl_seconds=7200); post(hub, s, B)
    lasting = reserve(hub, binding, request_id=key(99), queue_seconds=3600)['reservation']
    for n in range(12):
        at(hub, 1001.0 + n)
        brief = reserve(hub, binding, request_id=key(n), queue_seconds=60)['reservation']
    # Thirteen valid reservations exceed the limit: the newest is shown, and only it is inspected.
    assert returned(hub, s) == [brief['reservation_id']] and brief['created_at'] == 1012.0
    assert view(hub, s)['queued_reservation'] == shown(brief)
    at(hub, 1100.0)
    # The twelve newer ones have expired. They are not returned, so they cannot fill the limit.
    assert returned(hub, s) == [lasting['reservation_id']]
    assert view(hub, s)['queued_reservation'] == shown(lasting) == {
        'through_sequence': lasting['through_sequence'], 'created_at': 1000.0, 'queued_until': 4600.0}
    assert activate(hub, binding, lasting)['status'] == 'ready'


def test_of_overlapping_valid_reservations_the_newest_then_widest_then_longest_is_shown(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s, ttl_seconds=7200); first = post(hub, s, B)
    early = reserve(hub, binding, request_id=key(1), queue_seconds=3600)['reservation']
    assert view(hub, s)['queued_reservation'] == shown(early)
    at(hub, 1005.0)
    # Newest first, although the earlier one lasts longer and precedes it in the primary key.
    late = reserve(hub, binding, request_id=key(2), queue_seconds=600)['reservation']
    assert view(hub, s)['queued_reservation'] == shown(late) and late['queued_until'] < early['queued_until']
    # Made at the same instant after one more message: the wider range, although it ends sooner.
    second = post(hub, s, B)
    wider = reserve(hub, binding, request_id=key(4), queue_seconds=300)['reservation']
    assert (wider['created_at'], wider['through_sequence']) == (late['created_at'], second['sequence'])
    assert late['through_sequence'] == first['sequence'] < second['sequence']
    assert view(hub, s)['queued_reservation'] == shown(wider)
    # Same instant and range: the one that lasts longest, so the displayed expiry is stable.
    longest = reserve(hub, binding, request_id=key(5), queue_seconds=900)['reservation']
    assert [view(hub, s)['queued_reservation'] for _ in range(3)] == [shown(longest)] * 3
    # Every one of the four is still acceptable; the status row describes the one shown.
    assert activate(hub, binding, longest)['delivery']['through_sequence'] == second['sequence']


WRONG = {'binding_id': lambda value: 'f' * 32, 'generation': lambda value: value + 1,
         'binding_version': lambda value: value + 1, 'control_version': lambda value: value + 1,
         'after_sequence': lambda value: value - 1, 'queued_until': lambda value: 1100.0}


@pytest.mark.parametrize('field', WRONG)
def test_each_fence_is_applied_by_the_database_before_the_limit(collaboration, field):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s); post(hub, s, B)
    valid = reserve(hub, binding, request_id=key(99), queue_seconds=600)['reservation']
    at(hub, 1100.0)
    # Nine newer rows, one more than the limit, each stale in this one respect only.
    # A queue that ends exactly now has expired.
    for n in range(9):
        store(hub, valid, reservation_id=key(n), created_at=1010.0 + n, **{field: WRONG[field](valid[field])})
    assert returned(hub, s) == [valid['reservation_id']]
    assert view(hub, s)['queued_reservation'] == shown(valid)


def test_a_row_the_activation_check_rejects_is_skipped_not_trusted(collaboration):
    """Inconsistent rows the API cannot create: the database filter is never the only check."""
    hub, _, _ = collaboration
    s, other = room(hub), room(hub); binding = join(hub, s); post(hub, s, B)
    valid = reserve(hub, binding, request_id=key(99), queue_seconds=600)['reservation']
    at(hub, 1100.0)
    forged = [store(hub, valid, reservation_id=key(n), created_at=1010.0 + n, **wrong)['reservation_id']
              for n, wrong in enumerate(({'session_id': other['session_id']}, {'project_id': 'q'},
                                         {'worker_id': B.worker_id}, {'generation': str(valid['generation'])}))]
    assert returned(hub, s) == forged[::-1] + [valid['reservation_id']]
    assert view(hub, s)['queued_reservation'] == shown(valid)


def test_other_bindings_rooms_and_workers_never_borrow_a_reservation(collaboration):
    hub, _, _ = collaboration
    s, other = room(hub), room(hub)
    mine, theirs, elsewhere = join(hub, s), join(hub, s, B), join(hub, other)
    first, second = human_post(hub, s), human_post(hub, other)
    reserve(hub, mine, queue_seconds=300)
    assert view(hub, s)['queued_reservation']['through_sequence'] == first['sequence']
    assert 'queued_reservation' not in view(hub, s, B.worker_id)
    assert 'queued_reservation' not in view(hub, other)
    reserve(hub, elsewhere, queue_seconds=400)
    call(hub, 'reserve', B, project_id='p', binding_id=theirs['binding_id'], generation=theirs['generation'],
         request_id=uuid.uuid4().hex, queue_seconds=500)
    assert view(hub, s)['queued_reservation']['queued_until'] == 1300.0
    assert view(hub, other)['queued_reservation'] == {'through_sequence': second['sequence'],
                                                       'created_at': 1000.0, 'queued_until': 1400.0}
    assert view(hub, s, B.worker_id)['queued_reservation']['queued_until'] == 1500.0
    # Overlapping reservations of one binding made at the same instant: one row, the longest.
    longer = reserve(hub, mine, queue_seconds=700)['reservation']
    assert view(hub, s)['queued_reservation']['queued_until'] == 1700.0
    activate(hub, mine, longer)
    assert 'queued_reservation' not in view(hub, s)
    assert view(hub, s, B.worker_id)['queued_reservation']['queued_until'] == 1500.0


def test_lookup_is_skipped_or_bounded_and_history_is_not_returned(collaboration):
    hub, _, _ = collaboration
    s = room(hub); binding = join(hub, s)
    # Steady state: nothing after the cursor, so the reservation table is not read at all.
    assert request_statements(hub, lambda: status(hub, s)) == []
    for _ in range(10):
        post(hub, s, B)
        delivery = activate(hub, binding, reserve(hub, binding)['reservation'])['delivery']
        read_delivery(hub, s, delivery); reply(hub, s, delivery)
    # Only this worker's own reply follows the cursor: one bounded lookup, no activation probe.
    idle = request_statements(hub, lambda: status(hub, s))
    assert len(idle) == 1 and 'LIMIT' in idle[0] and 'queued_reservation' not in view(hub, s)
    latest = post(hub, s, B)
    reserve(hub, binding, queue_seconds=300)
    live = request_statements(hub, lambda: status(hub, s))
    assert len(live) == 2 and 'LIMIT' in live[0]
    # The ten earlier reservations are filtered by the database, not fetched and inspected here.
    assert len(returned(hub, s)) == 1
    assert view(hub, s)['queued_reservation'] == {'through_sequence': latest['sequence'],
                                                   'created_at': 1000.0, 'queued_until': 1300.0}
    # A blocked or busy binding answers from its status alone.
    call(hub, 'pause', human('admin'), **values(s, paused=True, expected_version=1))
    assert request_statements(hub, lambda: status(hub, s)) == []
    assert view(hub, s)['status'] == 'paused' and 'queued_reservation' not in view(hub, s)


def test_rest_status_route_adds_the_optional_key_for_authorized_readers_only(collaboration):
    hub, url, sqlite = collaboration
    s = room(hub)
    owner, peer, outsider = ('synthetic-queued-status-' + name + '-token-12345' for name in ('owner', 'peer', 'other'))
    app = create_app(database_url=url, allow_sqlite=sqlite, auth_tokens=json.dumps({
        owner: A.model_dump(), peer: B.model_dump(), outsider: Q.model_dump()}))
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer ' + owner}
        joined = client.post('/v1/chat/join', headers=headers, json=values(s, client='chatgpt',
            display_name='Cloud', native_session_id='test-cloud', idempotency_key='queued-join')).json()
        message = post(hub, s, B)
        request_id = uuid.uuid4().hex
        assert client.post('/v1/chat/reserve', headers=headers, json={'project_id': 'p',
            'binding_id': joined['binding_id'], 'generation': 1, 'request_id': request_id}).json()['status'] == 'queued'
        for token in (owner, peer):
            answer = client.get('/v1/chat/status', headers={'Authorization': 'Bearer ' + token}, params=values(s))
            participant = answer.json()['participants'][0]
            assert answer.status_code == 200 and set(participant['queued_reservation']) == SAFE
            assert participant['queued_reservation']['through_sequence'] == message['sequence']
            assert participant['status'] in {'waiting', 'offline'}
            assert request_id not in answer.text and message['message_id'] not in answer.text
        assert client.get('/v1/chat/status', headers={'Authorization': 'Bearer ' + outsider},
                          params=values(s)).status_code == 403
        assert client.get('/v1/chat/status', params=values(s)).status_code == 401


RENDER = r'''
'use strict';
// Runs the production delivery-panel code, extracted verbatim, against a minimal DOM.
const fs = require('node:fs'), vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8')), source = input.script;
const start = source.indexOf('  const deliveryNames='), end = source.indexOf('  async function refreshDelivery()');
if (start < 0 || end < start) throw new Error('delivery panel code moved; update this extraction');
class Element {
  constructor() { this.children = []; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
}
const ids = new Map();
const $ = id => { if (!ids.has(id)) ids.set(id, new Element()); return ids.get(id); };
function node(tag, text, cls) { const n = new Element(); n.tag = tag; if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
const state = {room: {session_id: 'a'.repeat(32)}, busy: false, stopped: false,
  delivery: {control: {paused: false, version: 1}, participants: input.people, has_more: false}};
const context = vm.createContext({$, node, state, cfg: {dataset: {role: 'admin'}}});
vm.runInContext(source.slice(0, source.indexOf('\n')) + '\n' + source.slice(start, end) + '\nrenderDelivery();', context);
process.stdout.write(JSON.stringify($('delivery-participants').children.map(row => row.children.map(
  child => ({tag: child.tag, text: child.textContent, cls: child.className || null, title: child.title || null})))));
'''
NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='Node.js is required to run the delivery panel code')
@pytest.mark.parametrize('language', LANGUAGES)
def test_panel_says_queued_not_yet_read_without_claiming_delivery(tmp_path, language):
    queued = {'through_sequence': 92, 'created_at': 1000.0, 'queued_until': 1900.0}
    base = {'worker_id': 'cloud-worker', 'display_name': 'Cloud', 'relay_online': True, 'turns_used': 1,
            'max_turns': 20, 'latest_delivery': None}
    people = [{**base, 'status': 'waiting', 'queued_reservation': queued},
              {**base, 'status': 'offline', 'relay_online': False, 'queued_reservation': queued},
              {**base, 'status': 'waiting'},
              # The server never sends these; the panel must still keep each status truthful.
              {**base, 'status': 'processing', 'queued_reservation': queued},
              {**base, 'status': 'paused', 'queued_reservation': queued},
              {**base, 'status': 'waiting', 'queued_reservation': {'through_sequence': '92', 'queued_until': 1900.0}},
              {**base, 'status': 'waiting', 'queued_reservation': {'through_sequence': 92}}]
    token = _locale.set(language)
    try:
        script = chat_script()
    finally:
        _locale.reset(token)
    harness = tmp_path / 'render.cjs'
    harness.write_text(RENDER, encoding='utf-8')
    result = subprocess.run([NODE, str(harness)], input=json.dumps({'script': script, 'people': people}),
                            capture_output=True, text=True, encoding='utf-8', timeout=30, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(result.stdout)
    phrase = {key: CATALOG[key][language] for key in (LABEL, ENDS, NOTE)}
    text = [''.join(child['text'] + '|' for child in row) for row in rows]
    waiting, offline, plain = rows[0], rows[1], rows[2]
    # A waiting binding with a queue no longer says it is waiting for new messages.
    assert waiting[2] == {'tag': 'span', 'text': phrase[LABEL], 'cls': None, 'title': None}
    assert plain[2]['text'] != phrase[LABEL] and plain[2]['text'] not in text[0]
    detail = [child for child in waiting if child['title'] == phrase[NOTE]]
    assert len(detail) == 1 and detail[0]['text'].startswith(phrase[ENDS]) and detail[0]['text'].endswith('#92')
    assert text[0].count(phrase[LABEL]) == 1
    # An offline relay keeps its own status and shows the queue beside it.
    assert offline[2]['text'] not in {phrase[LABEL], plain[2]['text']}
    assert {'tag': 'span', 'text': phrase[LABEL], 'cls': 'receipt', 'title': None} in offline
    assert any(child['title'] == phrase[NOTE] and child['text'].endswith('#92') for child in offline)
    # Nothing queued, another status, or malformed metadata: no queue wording at all.
    for index in (2, 3, 4, 5, 6):
        assert phrase[LABEL] not in text[index] and phrase[ENDS] not in text[index], index
        assert all(child['title'] is None for child in rows[index])
    assert text[3] != text[2] and text[4] != text[2]
