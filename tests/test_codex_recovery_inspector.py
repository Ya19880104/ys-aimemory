"""Read-only recovery report contracts; fixtures only: no model, socket, credential or process."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
from types import SimpleNamespace

import httpx
import pytest
from test_delivery import call, claim, join, read_delivery, reply
from test_index import _migration_db
from test_sessions import collaboration, room, post, A, B

spec = importlib.util.spec_from_file_location('codex_recovery_inspector',
    Path(__file__).parents[1] / 'scripts' / 'inspect-codex-chat-recovery.py')
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)

SCOPE = {'project_id': 'test-project', 'session_id': 'a' * 32, 'worker_id': 'codex-fixture'}
BINDING, DELIVERY, LEASE, REQUEST, REPLY = '0' * 32, 'b' * 32, 'c' * 32, '9' * 32, 'f' * 32
TOKEN = 'synthetic-own-codex-token-never-printed'
# Values that authorize a write or identify the private native session.
SECRETS = (TOKEN, LEASE, REQUEST, 'delivery-' + DELIVERY, 'join-key-fixture', 'native-session-fixture')
ORIGIN = 'https://hub.fixture.test'


def journal(directory, *, binding=True, delivery=True, receipt=False, marker=False, claim=True,
            stop=False, generation=1, scope=SCOPE, reply=REPLY):
    directory.mkdir(parents=True, exist_ok=True)
    def write(name, value):
        (directory / name).write_text(json.dumps(value), encoding='utf-8')
    write('receiver-config.json', {**scope, 'client_dir': 'C:/private/client',
        'credential': 'C:/private/client/worker.dpapi', 'expected_ca': 'e' * 64, 'codex': 'codex.exe',
        'python': 'python.exe', 'after_sequence': None, 'ttl_seconds': 3600, 'max_turns': 20,
        'turn_timeout': 90, 'language': 'en', 'native_session_id': 'native-session-fixture',
        'idempotency_key': 'join-key-fixture', 'expires_at': 5000.0})
    (directory / 'receiver.lock').write_bytes(b'0')
    write('receiver-status.json', {'state': 'failed', 'error_type': 'ReceiverError',
        'error_code': 'native_exit_unconfirmed_preserve_binding', 'at': 100.0})
    if binding:
        write('receiver-binding.json', {**scope, 'binding_id': BINDING, 'generation': generation})
    if claim:
        write('receiver-claim.json', {'project_id': scope['project_id'], 'binding_id': BINDING,
            'lease_seconds': 300, 'generation': generation, 'request_id': REQUEST})
    if delivery:
        write('receiver-delivery.json', {'delivery_id': DELIVERY, 'lease_id': LEASE, 'after_sequence': 4,
            'through_sequence': 6, 'message_ids': ['d' * 32, 'e' * 32],
            'reply_idempotency_key': 'delivery-' + DELIVERY})
    if receipt:
        write('receipt-' + DELIVERY + '.json', {'status': 'passed', 'native_thread_id': 'thread-fixture',
            'native_tool_calls': 3, 'worker_id': scope['worker_id'], 'delivery_id': DELIVERY,
            'read_message_ids': ['d' * 32, 'e' * 32], 'token_usage': {'input_tokens': 'not_reported'},
            'post_receipt': {'message_id': reply, 'sequence': 7, 'session_id': scope['session_id'],
                             'project_id': scope['project_id'], 'body_sha256': '1' * 64}})
    if marker:
        write('native-active.json', {'state': 'starting'})
    if stop:
        (directory / 'STOP').touch()
    return directory


def hub(*, status='processing', generation=1, delivery='dispatched', delivery_id=DELIVERY, cursor=4,
        released=None, **changes):
    latest = None if delivery is None else {'delivery_id': delivery_id, 'status': delivery,
        'after_sequence': 4, 'through_sequence': 6, 'attempts': 1, 'created_at': 90.0,
        'dispatched_at': None if delivery == 'leased' else 91.0,
        'read_at': 92.0 if delivery in ('tool_read', 'replied') else None,
        'replied_at': 93.0 if delivery == 'replied' else None,
        'reply_message_id': REPLY if delivery == 'replied' else None,
        'reply_sequence': 7 if delivery == 'replied' else None}
    participant = {**SCOPE, 'binding_id': BINDING, 'client': 'codex', 'display_name': 'Codex Local',
        'generation': generation, 'version': 2, 'enabled': True, 'expires_at': 5000.0, 'last_seen_at': 95.0,
        'processed_sequence': cursor, 'max_turns': 20, 'turns_used': 1, 'released_at': released,
        'status': status, 'relay_online': False, 'latest_delivery': latest, **changes}
    return {'project_id': SCOPE['project_id'], 'session_id': SCOPE['session_id'],
            'control': {'paused': False, 'version': 1}, 'latest_sequence': 7,
            'participants': [participant], 'has_more': False, 'receipt_semantics': 'fixture'}


def client(answer, calls=None):
    def handle(request):
        if calls is not None:
            calls.append(request)
        return answer(request) if callable(answer) else httpx.Response(200, json=answer)
    return httpx.Client(base_url=ORIGIN, transport=inspector.StatusOnlyTransport(httpx.MockTransport(handle)),
        headers={'Authorization': 'Bearer ' + TOKEN}, trust_env=False, follow_redirects=False, timeout=5)


def snapshot(directory):
    return {str(path.relative_to(directory)): (path.read_bytes() if path.is_file() else None,
            path.stat().st_mtime_ns) for path in sorted(directory.rglob('*'))}


def examine(directory, answer=None, calls=None, **options):
    """Run one report and prove the journal's file set, bytes and mtimes did not change."""
    state = journal(directory, **options)
    before = snapshot(state)
    if answer is None:
        report = inspector.inspect(SCOPE, state)
    else:
        with client(answer, calls) as connection:
            report = inspector.inspect(SCOPE, state, connection)
    assert snapshot(state) == before
    assert {k: report[k] for k in inspector.FIXED} == {'read_only': True, 'automatic_recovery': 'not_performed',
        'retry_permission': 'not_granted_by_this_report', 'native_exit': 'not_established_by_this_report'}
    return report


SCENARIOS = {
    'read_without_reply': (dict(marker=True), dict(delivery='tool_read'), 'server-read', None),
    'reply_without_local_receipt': (dict(marker=True), dict(delivery='replied', status='disabled', cursor=6),
                                    'server-replied', 'local-completion-missing'),
    'reply_with_local_receipt': (dict(receipt=True), dict(delivery='replied', status='waiting', cursor=6),
                                 'server-replied', 'local-completion-recorded'),
    'dispatched_only': (dict(marker=True), dict(delivery='dispatched'), 'unresolved', 'server_dispatched'),
    'leased_only': (dict(), dict(delivery='leased'), 'unresolved', 'server_leased'),
    'other_generation': (dict(), dict(generation=3, delivery=None), 'stale-generation', None),
    'released': (dict(stop=True), dict(status='disconnected', generation=2, released=120.0, delivery=None),
                 'disconnected', 'owned_release_generation'),
    'hub_latest_is_another_delivery': (dict(), dict(delivery='leased', delivery_id='7' * 32, cursor=9),
                                       'unresolved', 'delivery_not_latest'),
    'nothing_dispatched': (dict(delivery=False, claim=False), dict(delivery=None, status='waiting'), 'no-delivery', None),
    'ownership_record_missing': (dict(binding=False), dict(delivery='tool_read'), 'server-read', None),
}


@pytest.mark.parametrize('name', sorted(SCENARIOS))
def test_named_states_leave_the_journal_identical_and_render_safely(tmp_path, name):
    options, answer, state, detail = SCENARIOS[name]
    calls = []
    report = examine(tmp_path / 'state', hub(**answer), calls, **options)
    assert (report['state'], report['detail']) == (state, detail)
    assert [(request.method, request.url.path) for request in calls] == [('GET', '/v1/chat/status')]
    english = inspector.render(report)
    assert english.isascii() and 'State: ' + state in english
    for output in (english, inspector.render(report, 'zh-TW'), inspector.render(report, 'en', True),
                   json.dumps(inspector.present(report)), json.dumps(inspector.present(report, True))):
        assert not any(secret in output for secret in SECRETS)
        assert 'safe to retry' not in output.lower() and 'retry is safe' not in output.lower()
    # Complete identifiers appear only on explicit request.
    assert BINDING not in english and SCOPE['session_id'] not in english
    assert SCOPE['session_id'] in inspector.render(report, 'en', True)


def test_only_the_exact_status_get_reaches_the_transport(tmp_path):
    calls = []
    examine(tmp_path / 'state', hub(), calls)
    request = calls[0]
    assert dict(request.url.params) == {k: SCOPE[k] for k in ('project_id', 'session_id')}
    assert request.content == b'' and len(calls) == 1
    with client(hub(), calls) as connection:
        for attempt in (lambda: connection.post('/v1/chat/status', json={}),
                        lambda: connection.post('/v1/chat/claim', json={'binding_id': BINDING}),
                        lambda: connection.post('/v1/chat/disconnect', json={}),
                        lambda: connection.get('/v1/chat/claim'),
                        lambda: connection.get('/v1/tools/get_worker_inbox'),
                        lambda: connection.get('/v1/chat/status', params={**SCOPE}),
                        lambda: connection.get('/v1/chat/status', params={'project_id': 'p'}),
                        lambda: connection.request('DELETE', '/v1/chat/status'),
                        lambda: connection.put('/v1/chat/status', json={})):
            with pytest.raises(inspector.InspectorError, match='only_status_get_permitted'):
                attempt()
    assert len(calls) == 1


def test_reply_without_local_receipt_is_distinct_from_read_without_reply(tmp_path):
    read = examine(tmp_path / 'read', hub(delivery='tool_read'), marker=True)
    replied = examine(tmp_path / 'replied', hub(delivery='replied', status='disabled', cursor=6), marker=True)
    assert read['state'] == 'server-read' and 'hub_reply_record' in read['evidence_missing']
    assert 'do_not_post_substitute_reply' in read['next_safe_action']
    assert (replied['state'], replied['detail']) == ('server-replied', 'local-completion-missing')
    assert 'hub_reply_record' not in replied['evidence_missing']
    assert 'do_not_resend_reply_exists' in replied['next_safe_action']
    assert replied['local']['completion']['status'] == 'absent'
    assert replied['hub']['binding']['latest_delivery']['reply_sequence'] == 7
    # The marker still means native exit is unconfirmed, whatever the Hub recorded.
    for report in (read, replied):
        assert 'native_exit_unconfirmed' in report['evidence_missing']
        assert 'marker_blocks_restart_and_disconnect' in report['next_safe_action']
    other = examine(tmp_path / 'other', hub(delivery='replied', cursor=6), receipt=True, reply='8' * 32)
    assert other['detail'] == 'local-completion-mismatch' and 'ask_administrator' in other['next_safe_action']
    claimed = examine(tmp_path / 'claimed', hub(delivery='tool_read'), receipt=True)
    assert claimed['state'] == 'server-read' and 'local_completion_not_confirmed_by_hub' in claimed['evidence_missing']


@pytest.mark.parametrize('answer,detail', [
    (dict(delivery=None, cursor=6), 'no_hub_delivery'),
    (dict(delivery=None, cursor=99), 'no_hub_delivery'),
    (dict(delivery='replied', delivery_id='7' * 32, cursor=9), 'delivery_not_latest'),
])
def test_a_cursor_alone_is_never_reply_evidence(tmp_path, answer, detail):
    report = examine(tmp_path / 'state', hub(status='waiting', **answer))
    assert (report['state'], report['detail']) == ('unresolved', detail)
    assert 'cursor_alone_is_not_reply_evidence' in report['evidence_missing']
    assert 'do_not_resend_reply_exists' not in report['next_safe_action']


def test_scope_binding_and_generation_mismatches_are_named(tmp_path):
    calls = []
    foreign = dict(SCOPE, worker_id='another-worker')
    report = examine(tmp_path / 'journal-scope', hub(), calls, scope=foreign)
    assert (report['state'], report['detail']) == ('scope-mismatch', 'journal_scope')
    assert calls == [] and report['hub']['reason'] == 'not_queried_after_local_problem'
    report = examine(tmp_path / 'hub-scope', hub(worker_id='another-worker'))
    assert (report['state'], report['detail']) == ('scope-mismatch', 'hub_binding_scope')
    other_room = hub() | {'session_id': '5' * 32}
    assert examine(tmp_path / 'room', other_room)['detail'] == 'invalid_response'
    report = examine(tmp_path / 'unlisted', hub(binding_id='4' * 32))
    assert (report['state'], report['detail']) == ('unavailable', 'binding_not_listed')
    assert examine(tmp_path / 'paged', hub(binding_id='4' * 32) | {'has_more': True})['detail'] == 'binding_not_in_first_page'
    stale = examine(tmp_path / 'stale', hub(generation=3, delivery='replied', cursor=6), marker=True)
    assert stale['state'] == 'stale-generation' and 'do_not_start_this_receipt' in stale['next_safe_action']
    assert 'journaled_delivery_not_exposed_for_this_generation' in stale['evidence_missing']
    released = examine(tmp_path / 'released', hub(status='disconnected', generation=5, released=120.0, delivery=None))
    assert (released['state'], released['detail']) == ('disconnected', 'other_generation')
    unowned = examine(tmp_path / 'unowned', hub(delivery='tool_read'), binding=False)
    assert 'local_binding_ownership' in unowned['evidence_missing']


@pytest.mark.parametrize('fault,reason', [
    (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('slow ' + TOKEN, request=request)), 'timeout'),
    (lambda request: (_ for _ in ()).throw(httpx.ConnectError('refused ' + TOKEN, request=request)), 'transport_error'),
    (lambda request: httpx.Response(503, text='maintenance ' + TOKEN), 'http_503'),
    (lambda request: httpx.Response(401, json={'error': 'unauthorized'}), 'http_401'),
    (lambda request: httpx.Response(302, headers={'Location': ORIGIN + '/v1/chat/claim'}), 'http_302'),
    (lambda request: httpx.Response(200, text='<html>' + TOKEN), 'invalid_response'),
    (lambda request: httpx.Response(200, json=[]), 'invalid_response'),
    (lambda request: httpx.Response(200, json=hub() | {'participants': 'none'}), 'invalid_response'),
    (lambda request: httpx.Response(200, json=hub(generation='1')), 'invalid_response'),
    (lambda request: httpx.Response(200, content=b' ' * 4096 + b'{}'), 'response_too_large'),
    (None, 'not_queried'),
])
def test_unavailable_hub_keeps_local_facts_and_claims_nothing(tmp_path, monkeypatch, fault, reason):
    monkeypatch.setattr(inspector, 'RESPONSE_LIMIT', 4096)
    calls = []
    report = examine(tmp_path / 'state', fault, calls, marker=True)
    assert (report['state'], report['detail']) == ('unavailable', reason)
    assert report['hub'] == {'route': 'GET /v1/chat/status', 'status_read': False, 'reason': reason, 'binding': None}
    assert 'hub_status_not_read' in report['evidence_missing'] and len(calls) <= 1
    assert report['local']['delivery']['status'] == 'valid' and report['local']['native_marker']['status'] == 'present'
    text = inspector.render(report) + json.dumps(inspector.present(report, True))
    assert TOKEN not in text and 'maintenance' not in text and 'server-replied' not in text


@pytest.mark.parametrize('damage,detail', [
    (lambda state: (state / 'receiver-binding.json').write_text('{"binding_id": '), 'malformed'),
    (lambda state: (state / 'receiver-delivery.json').write_text('[]'), 'malformed'),
    (lambda state: (state / 'receiver-delivery.json').write_text(json.dumps({'delivery_id': DELIVERY})), 'malformed'),
    (lambda state: (state / 'receiver-claim.json').write_bytes(b'\xff\xfe'), 'malformed'),
    (lambda state: (state / 'receiver-status.json').write_text(' ' * 70000), 'too_large'),
    (lambda state: ((state / 'receiver-claim.json').unlink(), (state / 'receiver-claim.json').mkdir()), 'not_a_file'),
    (lambda state: (state / ('receipt-' + DELIVERY + '.json')).write_text(json.dumps({'status': 'failed'})), 'malformed'),
])
def test_malformed_or_oversized_state_is_refused_without_a_hub_request(tmp_path, damage, detail):
    state = journal(tmp_path / 'state', marker=True)
    damage(state)
    before, calls = snapshot(state), []
    with client(hub(delivery='replied'), calls) as connection:
        report = inspector.inspect(SCOPE, state, connection)
    assert (report['state'], report['detail']) == ('invalid-local-state', detail)
    assert calls == [] and snapshot(state) == before
    assert 'ask_administrator' in report['next_safe_action'] and 'native_exit_unconfirmed' in report['evidence_missing']
    assert inspector.render(report) and inspector.render(report, 'zh-TW')


def test_linked_state_is_never_followed(tmp_path, monkeypatch):
    state = journal(tmp_path / 'state')
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path.name == 'receiver-delivery.json' or original(path))
    opened = []
    real_open = Path.open
    monkeypatch.setattr(Path, 'open', lambda path, *a, **k: opened.append(path.name) or real_open(path, *a, **k))
    report = inspector.inspect(SCOPE, state)
    assert (report['state'], report['detail']) == ('invalid-local-state', 'linked')
    assert 'receiver-delivery.json' not in opened and 'receiver-binding.json' in opened
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path.name == 'STOP' or original(path))
    assert inspector.inspect(SCOPE, state)['local']['stop'] == 'linked'
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path.name == 'state' or original(path))
    with pytest.raises(inspector.InspectorError, match='linked_state_refused'):
        inspector.inspect(SCOPE, state)


def test_real_symlink_target_is_not_read_or_changed(tmp_path):
    state = journal(tmp_path / 'state', binding=False)
    target = tmp_path / 'outside.json'
    target.write_text(json.dumps({**SCOPE, 'binding_id': BINDING, 'generation': 1}))
    try:
        os.symlink(target, state / 'receiver-binding.json')
    except (OSError, NotImplementedError):
        pytest.skip('this host does not permit creating a symlink fixture')
    before = target.read_bytes()
    report = inspector.inspect(SCOPE, state)
    assert (report['state'], report['detail']) == ('invalid-local-state', 'linked')
    assert report['local']['binding'] == {'status': 'linked', 'modified_at': None} and target.read_bytes() == before


@pytest.mark.parametrize('content', [{'state': 'starting'}, {'state': 'starting', 'pid': os.getpid()},
                                     {'state': 'starting', 'pid': 2 ** 22 + 7}, {'state': 'exited'}, []])
def test_marker_never_becomes_retry_permission_native_exit_or_process_use(tmp_path, monkeypatch, content):
    def forbidden(*args, **kwargs):
        raise AssertionError('the report must not start, signal or query a process')
    for name in ('Popen', 'run', 'call', 'check_output'):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, 'kill', forbidden)
    monkeypatch.setattr(os, 'system', forbidden)
    assert not hasattr(inspector, 'subprocess')
    state = journal(tmp_path / 'state')
    (state / 'native-active.json').write_text(json.dumps(content))
    before = snapshot(state)
    with client(hub(delivery='replied', status='disabled', cursor=6)) as connection:
        report = inspector.inspect(SCOPE, state, connection)
    assert snapshot(state) == before
    # A live, dead or absent PID in the marker changes nothing: presence is the only fact used.
    assert report['local']['native_marker']['status'] == 'present' and 'pid' not in json.dumps(report)
    assert report['local']['native_marker']['recorded_state'] == ('starting' if isinstance(content, dict)
        and content.get('state') == 'starting' else 'unrecognized')
    assert (report['state'], report['detail']) == ('server-replied', 'local-completion-missing')
    assert 'native_exit_unconfirmed' in report['evidence_missing']
    assert report['retry_permission'] == 'not_granted_by_this_report'
    assert report['native_exit'] == 'not_established_by_this_report'
    assert 'grants no retry' in inspector.render(report)


@pytest.mark.parametrize('spoil,recorded', [
    (lambda path: path.write_text('{"state": '), 'malformed'),
    (lambda path: path.write_text(' ' * 70000), 'too_large'),
    (lambda path: (path.unlink(), path.mkdir()), 'not_a_file'),
    (None, 'linked'),
])
def test_untrusted_marker_or_stop_still_counts_as_present_and_the_hub_is_asked(tmp_path, monkeypatch, spoil, recorded):
    """Presence is the only fact used, so an unreadable marker must never look like an absent one."""
    state = journal(tmp_path / 'state', marker=True, stop=True)
    if spoil:
        spoil(state / 'native-active.json')
    else:
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink',
                            lambda path: path.name in ('native-active.json', 'STOP') or original(path))
    before, calls = snapshot(state), []
    with client(hub(delivery='tool_read'), calls) as connection:
        report = inspector.inspect(SCOPE, state, connection)
    assert snapshot(state) == before and len(calls) == 1
    assert report['local']['problems'] == [] and report['state'] == 'server-read'
    assert report['local']['native_marker']['status'] == 'present'
    assert report['local']['native_marker']['recorded_state'] == recorded
    assert 'native_exit_unconfirmed' in report['evidence_missing']
    assert 'marker_blocks_restart_and_disconnect' in report['next_safe_action']
    assert report['local']['stop'] == ('linked' if spoil is None else 'present')
    assert inspector.render(report) and inspector.render(report, 'zh-TW')


def test_real_hub_status_payloads_name_each_step_of_one_delivery(collaboration, tmp_path):
    """The product delivery service, not a hand-written payload, answers the status route."""
    from memory_hub.session_service import SessionActor
    service, _, _ = collaboration
    session = room(service)
    binding = join(service, session)
    post(service, session, B)
    delivery = claim(service, binding)['delivery']
    scope = {'project_id': 'p', 'session_id': session['session_id'], 'worker_id': A.worker_id}
    state = tmp_path / 'state'
    state.mkdir()
    def write(name, value):
        (state / name).write_text(json.dumps(value), encoding='utf-8')
    write('receiver-binding.json', {**scope, 'binding_id': binding['binding_id'], 'generation': binding['generation']})
    write('receiver-delivery.json', {k: delivery[k] for k in ('delivery_id', 'lease_id', 'after_sequence',
        'through_sequence', 'message_ids', 'reply_idempotency_key')})
    write('native-active.json', {'state': 'starting'})
    requests = []
    def answer(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json=service.delivery.call('status', dict(request.url.params),
                                                              SessionActor.from_principal(A)))
    def named():
        before = snapshot(state)
        with client(answer) as connection:
            report = inspector.inspect(scope, state, connection)
        assert snapshot(state) == before and 'native_exit_unconfirmed' in report['evidence_missing']
        assert delivery['lease_id'] not in json.dumps(inspector.present(report, True))
        return report['state'], report['detail']
    target = dict(project_id='p', binding_id=binding['binding_id'])
    assert named() == ('unresolved', 'server_leased')
    call(service, 'dispatched', **target, delivery_id=delivery['delivery_id'], lease_id=delivery['lease_id'])
    assert named() == ('unresolved', 'server_dispatched')
    read_delivery(service, session, delivery)
    assert named() == ('server-read', None)
    written = reply(service, session, delivery)
    assert named() == ('server-replied', 'local-completion-missing')
    write('receipt-' + delivery['delivery_id'] + '.json', {'status': 'passed', 'worker_id': A.worker_id,
        'delivery_id': delivery['delivery_id'], 'post_receipt': {'message_id': written['message_id'],
        'sequence': written['sequence'], 'session_id': scope['session_id'], 'project_id': 'p'}})
    assert named() == ('server-replied', 'local-completion-recorded')
    call(service, 'disconnect', **target, expected_version=binding['version'])
    assert named() == ('disconnected', 'owned_release_generation')
    join(service, session)
    assert named() == ('stale-generation', None)
    assert set(requests) == {('GET', '/v1/chat/status')} and len(requests) == 7


def test_absent_journal_and_offline_report(tmp_path):
    report = inspector.inspect(SCOPE, tmp_path / 'never-started')
    assert (report['state'], report['detail'], report['local']['journal']) == ('unavailable', 'not_queried', 'absent')
    assert not (tmp_path / 'never-started').exists()
    assert 'has not started' in inspector.render(report)


@pytest.fixture
def installation(tmp_path):
    setup, runner = inspector.load_sources()
    directory = (tmp_path / 'codex-client')
    directory.mkdir()
    directory = directory.resolve(strict=True)
    names = (*setup.PUBLIC, *setup.SOURCES)
    for name in names:
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_bytes(('fixture ' + name).encode())
    (directory / 'connection.json').write_text(json.dumps({'version': 1, 'endpoint': ORIGIN + '/mcp',
        'ca_file': 'ys-ai-memory-ca.crt', 'ca_sha256': 'e' * 64}))
    receipt = {'kind': 'ys-memory-dedicated-codex', 'version': 1, 'status': 'installed_not_native_verified',
        'client_directory': str(directory), 'python': str(directory / '.venv/Scripts/python.exe'),
        'codex': 'C:/fixture/codex.exe', 'origin': ORIGIN, 'ca_sha256': 'e' * 64, **SCOPE, 'language': 'en',
        'ttl_seconds': 3600, 'max_turns': 20, 'turn_timeout': 90, 'state_directory': str(directory / 'state'),
        'token_storage': 'Windows current-user DPAPI', 'authorization_check': 'rest_identity_and_room_passed',
        'global_config_changed': False, 'claude_config_changed': False, 'desktop_chat_injected': False,
        'files': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}}
    (directory / 'codex-install.json').write_text(json.dumps(receipt))
    journal(directory / 'state', marker=True)
    return SimpleNamespace(directory=directory, receipt=directory / 'codex-install.json', setup=setup, runner=runner)


def test_cli_reads_the_validated_receipt_and_changes_nothing(installation, monkeypatch, capsys):
    calls, built = [], []
    def own(receipt, runner, timeout):
        built.append((receipt['client_directory'], timeout))
        return client(hub(delivery='replied', status='disabled', cursor=6), calls), TOKEN
    monkeypatch.setattr(inspector, 'own_client', own)
    before = snapshot(installation.directory)
    assert inspector.main(['--receipt', str(installation.receipt), '--json', '--timeout', '7']) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert (report['state'], report['detail']) == ('server-replied', 'local-completion-missing')
    assert built == [(str(installation.directory), 7)] and len(calls) == 1
    assert report['local']['delivery']['delivery_id'] == DELIVERY[:8] + '...'
    assert inspector.main(['--receipt', str(installation.receipt), '--language', 'zh-TW', '--full-ids']) == 0
    localized = capsys.readouterr().out
    assert '狀態：server-replied' in localized and DELIVERY in localized
    assert snapshot(installation.directory) == before
    for text in (output.out, output.err, localized):
        assert not any(secret in text for secret in SECRETS) and str(installation.directory) not in text


def test_cli_offline_reads_no_credential_and_failures_use_fixed_codes(installation, monkeypatch, capsys):
    monkeypatch.setattr(inspector, 'own_client', lambda *a: pytest.fail('offline must not read the Token'))
    assert inspector.main(['--receipt', str(installation.receipt), '--offline', '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report['state'], report['detail']) == ('unavailable', 'not_queried')
    def broken(*args):
        raise RuntimeError('DPAPI failed for ' + TOKEN)
    monkeypatch.setattr(inspector, 'own_client', broken)
    assert inspector.main(['--receipt', str(installation.receipt), '--json']) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)['detail'] == 'own_credential_or_tls_unavailable' and TOKEN not in output.out + output.err
    # A report that would contain the Token is withheld entirely.
    monkeypatch.setattr(inspector, 'own_client', lambda *a: (client(hub()), TOKEN))
    monkeypatch.setattr(inspector, 'render', lambda *a: 'leak ' + TOKEN)
    assert inspector.main(['--receipt', str(installation.receipt)]) == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err.strip() == 'codex_recovery_inspection_failed: redaction_guard_stopped_output'
    before = snapshot(installation.directory)
    (installation.directory / 'scripts/run-codex-chat.py').write_text('changed after installation')
    assert inspector.main(['--receipt', str(installation.receipt), '--offline']) == 1
    assert capsys.readouterr().err.strip() == 'codex_recovery_inspection_failed: owned_codex_install_modified'
    for arguments in ([], ['--receipt', str(installation.receipt), '--token', TOKEN],
                      ['--receipt', str(installation.receipt), '--timeout', '0']):
        assert inspector.main(arguments) == 1
        output = capsys.readouterr()
        assert output.err.strip() == 'codex_recovery_inspection_failed: invalid_arguments_use_help' and TOKEN not in output.err
    assert set(snapshot(installation.directory)) == set(before)


def test_own_client_uses_documented_credentials_behind_the_status_only_transport(installation, monkeypatch):
    asked = []
    def credentials(config):
        asked.append(config)
        return None, {'endpoint': ORIGIN + '/mcp'}, ssl.create_default_context(), TOKEN
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.fixture.test:3128')
    receipt = installation.setup.read_receipt(installation.receipt)
    connection, token = inspector.own_client(receipt, SimpleNamespace(credentials=credentials), 7)
    with connection:
        assert asked == [{'client_dir': str(installation.directory), 'expected_ca': 'e' * 64,
                          'credential': str(installation.directory / 'worker.dpapi')}]
        assert token == TOKEN and isinstance(connection._transport, inspector.StatusOnlyTransport)
        assert (connection.base_url.scheme, connection.base_url.host) == ('https', 'hub.fixture.test')
        assert not connection.trust_env and not connection.follow_redirects
        assert connection.timeout == httpx.Timeout(7) and connection._mounts == {}
        with pytest.raises(inspector.InspectorError, match='only_status_get_permitted'):
            connection.post('/v1/chat/disconnect', json={})
