"""Private gateway contracts; no provider account, live Token or callback used."""
import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest
import httpx

from memory_hub import cloud_tunnel_gateway as cloud

KEY = base64.b64encode(bytes(range(32))).decode()  # Synthetic fixture only.
SECRET = 'whsec_' + base64.b64encode(b'synthetic-webhook-secret-32-bytes').decode()
URL = 'https://callback.example.test/mcp-events/synthetic'


class Hub(cloud.HubClient):
    """Real SQLite Hub behind an in-process transport, with synthetic identities."""
    def __init__(self, config, clock):
        from memory_hub.service import Hub as ProductHub
        from memory_hub.store import Store
        from memory_hub.models import Principal
        from memory_hub.session_service import SessionActor
        self.config, self.messages, self.pause, self.revoked = config, [], False, False
        self.sequence, self.posts, self.reads = 0, [], []
        self.clock = clock
        self.actor = SessionActor('worker', config['worker_id'], 'ChatGPT fixture', ('pilot',), 'worker')
        self.principal = Principal(worker_id=config['worker_id'], projects=['pilot'])
        admin = Principal(worker_id='operator', projects=['pilot'], role='admin')
        self.other = Principal(worker_id='other-ai', projects=['pilot'])
        self.real = ProductHub(Store('sqlite:///' + str(Path(config['state_path']).with_name('hub.sqlite')), allow_sqlite=True), clock=clock,
                               principals=[self.principal, self.other, admin])
        self.real.call('create_project', {'project_id': 'pilot'}, admin)
        room = self.real.call('create_session', {'project_id': 'pilot', 'title': 'Synthetic room', 'idempotency_key': 'room'}, admin)
        config['session_id'] = room['session_id']
        self.sequence = room['latest_sequence']

    def identity(self):
        if self.revoked:
            raise cloud.GatewayError('Hub unavailable')
        return {'worker_id': self.config['worker_id'], 'project_id': self.config['project_id'],
                'session_id': self.config['session_id']}

    def paused(self):
        if self.pause == 'unavailable':
            raise cloud.GatewayError('Pause unavailable')
        state = self.real.delivery.call('status', {'project_id':'pilot','session_id':self.config['session_id']}, self.actor)
        return self.pause or state['control']['paused']

    def latest(self): return self.sequence

    def _tool(self, name, **arguments):
        from memory_hub.store import HubError
        try:
            return self.real.call(name, {'project_id':'pilot', **arguments}, self.principal)
        except HubError as exc:
            raise cloud.GatewayError('Hub rejected request: ' + exc.code, -32001, exc.code) from None

    def read(self, after, limit=5, **kwargs):
        self.reads.append(after)
        return super().read(after, limit, **kwargs)

    def relay(self, operation, **arguments):
        return self.real.delivery.call(operation, {'project_id':'pilot', **arguments}, self.actor)

    def add(self, sender='human-admin', body='new test message'):
        from memory_hub.session_service import SessionActor
        from uuid import uuid4
        own = sender == self.config['worker_id']
        actor = SessionActor('worker' if own else 'human', sender, sender, ('pilot',), 'worker' if own else 'member')
        result = self.real.sessions.call('post_session_message', {'project_id':'pilot',
            'session_id':self.config['session_id'], 'body':body, 'idempotency_key':uuid4().hex}, actor)
        self.sequence = result['sequence']
        self.messages.append(result)
        return result

    def post(self, body, key, **kwargs):
        result = super().post(body, key, **kwargs)
        self.posts.append((body, key))
        self.sequence = result['sequence']
        return result


@pytest.fixture
def pilot(tmp_path):
    config = {'hub_url': 'https://hub.example.test', 'project_id': 'pilot', 'session_id': 'a' * 32,
        'worker_id': 'chatgpt-pilot', 'state_path': str(tmp_path / 'private.sqlite'),
        'callback_hosts': ['callback.example.test'], 'poll_interval': 60,
        'max_events_per_subscription': 20, 'subscription_ttl': 60}
    sent, now = [], [1000.0]
    hub = Hub(config, lambda: now[0])
    result = {'status': 202}
    def sender(url, body, headers, hosts):
        packet = json.loads(body)
        sent.append((url, packet, headers, body))
        if packet.get('type') == 'verification':
            return 200, cloud.compact({'challenge': packet['challenge']})
        return result['status'], b''
    gateway = cloud.Gateway(config, hub, box=cloud.SecretBox(KEY), sender=sender, clock=lambda: now[0])
    return SimpleNamespace(gateway=gateway, config=config, hub=hub, sent=sent, now=now, result=result, sender=sender)


def subscription(secret=SECRET, url=URL):
    return {'name': cloud.EVENT_NAME, 'arguments': {},
            'delivery': {'mode': 'webhook', 'url': url, 'secret': secret}, 'cursor': None}


def unsubscribe(url=URL):
    return {'name': cloud.EVENT_NAME, 'arguments': {}, 'delivery': {'mode': 'webhook', 'url': url}}


def rpc(gateway, method, params=None):
    return gateway.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}})


def test_mcp2_catalog_and_fixed_tool_scope(pilot):
    gateway = pilot.gateway
    assert rpc(gateway, 'server/discover')['result']['supportedVersions'] == ['2026-07-28']
    assert set(rpc(gateway, 'server/discover')['result']['capabilities']) == {'tools', 'events'}
    assert {tool['name'] for tool in rpc(gateway, 'tools/list')['result']['tools']} == {'identity', 'read_delta', 'post_message'}
    assert rpc(gateway, 'events/list')['result']['events'][0]['name'] == cloud.EVENT_NAME
    identity = rpc(gateway, 'tools/call', {'name': 'identity'})['result']['structuredContent']
    assert identity['worker_id'] == 'chatgpt-pilot' and identity['latest_sequence'] == pilot.hub.sequence
    for name, arguments in [('read_delta', {'after_sequence': 0, 'project_id': 'foreign'}),
                            ('post_message', {'body': 'test', 'idempotency_key': 'a', 'session_id': 'b' * 32}),
                            ('memory_call', {'name': 'approve_memory_change'})]:
        assert 'error' in rpc(gateway, 'tools/call', {'name': name, 'arguments': arguments})
    assert pilot.hub.posts == [] and pilot.hub.reads == []
    result = rpc(gateway, 'tools/call', {'name': 'post_message', 'arguments': {'body': 'hello', 'idempotency_key': 'once'}})
    assert result['result']['structuredContent']['sequence'] == pilot.hub.sequence
    assert pilot.hub.posts == [('hello', 'once')]


def test_first_subscription_starts_now_signed_and_encrypted(pilot):
    pilot.hub.add(body='historical text must not be delivered')
    receipt = pilot.gateway.subscribe(subscription())
    message = pilot.hub.add(body='new confidential body')
    pilot.gateway.tick()
    delivered = pilot.sent[-1]
    assert delivered[1]['data']['sequence'] == message['sequence']
    assert delivered[1]['data']['preview'] == 'new confidential body'
    headers, body = delivered[2:]
    expected = base64.b64encode(hmac.new(base64.b64decode(SECRET[6:]),
        (headers['webhook-id'] + '.' + headers['webhook-timestamp'] + '.').encode() + body,
        hashlib.sha256).digest()).decode()
    assert headers['webhook-signature'] == 'v1,' + expected
    assert headers['X-MCP-Subscription-Id'] == receipt['id']
    row = pilot.gateway.db.execute('SELECT * FROM subscriptions').fetchone()
    outbox = pilot.gateway.db.execute('SELECT * FROM outbox').fetchone()
    assert SECRET.encode() not in row['destination'] and URL.encode() not in row['destination']
    assert b'new confidential body' not in outbox['body'] and outbox['state'] == 'received'
    for path in Path(pilot.config['state_path']).parent.glob('private.sqlite*'):
        assert SECRET.encode() not in path.read_bytes()
        assert b'new confidential body' not in path.read_bytes()
    pilot.gateway.tick()
    assert len(pilot.sent) == 2  # verification + one message, no polling duplication.


def test_failed_verification_does_not_activate_or_leak_data(pilot):
    pilot.gateway.sender = lambda *args: (200, b'{"challenge":"wrong"}')
    with pytest.raises(cloud.GatewayError) as exc:
        pilot.gateway.subscribe(subscription())
    assert exc.value.code == -32015
    assert pilot.gateway.db.execute('SELECT count(*) FROM subscriptions').fetchone()[0] == 0
    assert pilot.hub.reads == []


def test_shared_pause_revocation_and_local_stop_fail_closed(pilot):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.hub.pause = True
    pilot.gateway.tick()
    assert len(pilot.sent) == 1
    assert 'error' in rpc(pilot.gateway, 'tools/call', {'name': 'post_message',
        'arguments': {'body': 'blocked', 'idempotency_key': 'blocked'}})
    pilot.hub.pause = 'unavailable'
    with pytest.raises(cloud.GatewayError): pilot.gateway.tick()
    pilot.hub.pause = False
    pilot.hub.revoked = True
    with pytest.raises(cloud.GatewayError): pilot.gateway.tick()
    pilot.hub.revoked = False
    pilot.gateway.stop()
    pilot.gateway.tick()
    assert len(pilot.sent) == 1 and pilot.hub.posts == []
    with pytest.raises(cloud.GatewayError): pilot.gateway.subscribe(subscription())
    pilot.gateway.resume()
    pilot.gateway.tick()
    assert len(pilot.sent) == 1  # resume requires another explicit subscription.


def test_pause_rechecked_after_read_before_dispatch(pilot):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    read = pilot.hub.read
    def pause_during_read(*args, **kwargs):
        result = read(*args, **kwargs)
        pilot.hub.pause = True
        return result
    pilot.hub.read = pause_during_read
    pilot.gateway.tick()
    assert len(pilot.sent) == 1
    assert pilot.gateway.db.execute('SELECT state FROM outbox').fetchone()[0] == 'queued'


def test_own_messages_suppressed_and_unsubscribe_idempotent(pilot):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add(sender='chatgpt-pilot')
    pilot.gateway.tick()
    assert len(pilot.sent) == 1
    assert pilot.gateway.unsubscribe(unsubscribe()) == {}
    assert pilot.gateway.unsubscribe(unsubscribe()) == {}
    pilot.hub.add()
    pilot.gateway.tick()
    assert len(pilot.sent) == 1


def test_pending_delivery_survives_restart_and_retry_keeps_event_id(pilot):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.result['status'] = 503
    pilot.gateway.tick()
    first = pilot.sent[-1]
    pilot.gateway.db.close()
    pilot.now[0] += 5
    pilot.result['status'] = 202
    gateway = cloud.Gateway(pilot.config, pilot.hub, box=cloud.SecretBox(KEY), sender=pilot.sender, clock=lambda: pilot.now[0])
    gateway.tick()
    second = pilot.sent[-1]
    assert first[1] == second[1] and first[2]['webhook-id'] == second[2]['webhook-id']
    assert first[2]['webhook-timestamp'] != second[2]['webhook-timestamp']
    assert gateway.db.execute('SELECT state,attempts FROM outbox').fetchone()[:] == ('received', 2)


@pytest.mark.parametrize('status', [410, 413, 401, 302])
def test_permanent_delivery_errors_stop_or_bounded_retry(pilot, status):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.result['status'] = status
    for _ in range(5):
        pilot.gateway.tick()
        pilot.now[0] += 10
    row = pilot.gateway.db.execute('SELECT state,attempts FROM outbox').fetchone()
    if status == 302:
        assert row['attempts'] <= 5  # redirect is never followed by the sender.
    else:
        assert row[:] == ('failed', 1)
        assert len(pilot.sent) == 2


def test_event_budget_refresh_and_expiry_do_not_restart_old_history(pilot):
    pilot.config['max_events_per_subscription'] = 2
    pilot.gateway.subscribe(subscription())
    for _ in range(3): pilot.hub.add()
    pilot.gateway.tick()
    pilot.gateway.subscribe(subscription())  # refresh preserves cursor/count.
    notification = pilot.sent[-1][1]['data']['notification_id']
    pilot.gateway.call('read_delta', {'notification_id': notification})
    pilot.gateway.call('post_message', {'notification_id': notification, 'body': 'First bounded reply'})
    pilot.hub.add()
    pilot.gateway.tick()
    pilot.gateway.tick()
    assert len([item for item in pilot.sent if 'eventId' in item[1]]) == 2
    with pytest.raises(cloud.GatewayError, match='budget'):
        pilot.gateway.subscribe(subscription())
    notification = pilot.sent[-1][1]['data']['notification_id']
    pilot.gateway.call('read_delta', {'notification_id': notification})
    pilot.gateway.call('post_message', {'notification_id': notification, 'body': 'Last bounded reply'})
    pilot.gateway.unsubscribe(unsubscribe())
    pilot.gateway.subscribe(subscription())
    pilot.gateway.tick()
    assert len([item for item in pilot.sent if 'eventId' in item[1]]) == 2


@pytest.mark.parametrize('poll_before_refresh', [True, False])
def test_expired_subscription_does_not_send_old_queue_after_refresh(pilot, poll_before_refresh):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.result['status'] = 503
    pilot.gateway.tick()
    pilot.now[0] += 61
    if poll_before_refresh:
        pilot.gateway.tick()
        assert pilot.gateway.db.execute('SELECT status FROM subscriptions').fetchone()[0] == 'expired'
    pilot.result['status'] = 202
    with pytest.raises(cloud.GatewayError, match='unsubscribe'):
        pilot.gateway.subscribe(subscription())
    pilot.gateway.unsubscribe(unsubscribe())
    pilot.gateway.subscribe(subscription())
    pilot.gateway.tick()
    assert pilot.gateway.db.execute('SELECT state FROM outbox ORDER BY rowid').fetchone()[0] == 'cancelled'
    assert pilot.sent[-1][1]['data']['notification_id'] != pilot.sent[1][1]['data']['notification_id']


def test_refresh_rotates_encrypted_secret_with_overlap(pilot):
    first = pilot.gateway.subscribe(subscription())
    second_secret = 'whsec_' + base64.b64encode(b'another-synthetic-signing-key-32x').decode()
    second = pilot.gateway.subscribe(subscription(second_secret))
    assert first['id'] == second['id']
    pilot.hub.add()
    pilot.gateway.tick()
    assert pilot.sent[-1][2]['webhook-signature'].count('v1,') == 2


@pytest.mark.parametrize('url', ['http://callback.example.test/path', 'https://evil.example.test/path',
    'https://u:secret@callback.example.test/path', 'https://callback.example.test:444/path',
    'https://callback.example.test/path#secret', 'https://callback.example.test/path\n'])
def test_callback_url_rejects_unlisted_or_unsafe_destination(url):
    with pytest.raises(cloud.GatewayError): cloud.callback_url(url, ['callback.example.test'])


@pytest.mark.parametrize('addresses', [['127.0.0.1'], ['10.0.0.1'], ['::1'], ['169.254.169.254'],
    ['8.8.8.8', '192.168.1.8'], ['100.64.0.1'], []])
def test_dns_rebinding_and_private_answers_fail_closed(addresses, monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(0, 0, 0, '', (ip, 443)) for ip in addresses])
    with pytest.raises(cloud.GatewayError): cloud.public_addresses('callback.example.test')


def test_callback_connects_to_validated_ip_with_original_tls_hostname(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud, 'public_addresses', lambda host: ['8.8.8.8'])
    stream = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(socket, 'create_connection', lambda address, **kw: calls.append(address) or stream)
    connection = cloud.PublicHTTPSConnection('callback.example.test')
    connection._context = SimpleNamespace(wrap_socket=lambda raw, **kw: calls.append(kw['server_hostname']) or raw)
    connection.connect()
    assert calls == [('8.8.8.8', 443), 'callback.example.test']


@pytest.mark.parametrize('secret', ['not-a-key', 'whsec_', 'whsec_invalid%=', 'whsec_' + base64.b64encode(b'short').decode()])
def test_invalid_signing_secrets_rejected_before_network(pilot, secret):
    with pytest.raises(cloud.GatewayError): pilot.gateway.subscribe(subscription(secret))
    assert pilot.sent == []


def test_state_cannot_be_rebound_to_other_identity(pilot):
    with pytest.raises(cloud.GatewayError, match='another room'):
        cloud.Gateway({**pilot.config, 'worker_id': 'someone-else'}, pilot.hub, box=cloud.SecretBox(KEY))


def test_single_runtime_lock_and_stopped_state_survive_other_connection(pilot):
    with cloud.runtime_lock(pilot.config['state_path']):
        with pytest.raises(OSError):
            with cloud.runtime_lock(pilot.config['state_path']): pass
        other = cloud.Gateway(pilot.config, None, box=cloud.SecretBox(KEY))
        other.stop()
        assert pilot.gateway.stopped()


def test_stdio_only_emits_jsonrpc_and_generic_errors(pilot, monkeypatch):
    incoming = b'{invalid\n' + cloud.compact({'jsonrpc': '2.0', 'id': 7, 'method': 'server/discover'}) + b'\n'
    output = io.BytesIO()
    monkeypatch.setattr('sys.stdin', SimpleNamespace(buffer=io.BytesIO(incoming)))
    monkeypatch.setattr('sys.stdout', SimpleNamespace(buffer=output))
    cloud.serve(pilot.gateway)
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    assert lines[0]['error']['code'] == -32700 and lines[1]['id'] == 7
    assert SECRET.encode() not in output.getvalue()


def test_hub_transport_scope_identity_pause_and_bounded_results(tmp_path, monkeypatch):
    config = {'hub_url': 'https://hub.example.test', 'project_id': 'pilot', 'session_id': 'a' * 32,
              'worker_id': 'chatgpt-pilot', 'ca_file': str(tmp_path / 'public-ca.crt'), 'ca_sha256': 'a' * 64}
    calls = []
    response = {'worker_id': 'chatgpt-pilot'}
    status = [200]
    def handler(request):
        calls.append(request)
        return httpx.Response(status[0], json=response)
    monkeypatch.setattr(cloud, 'verified_context', lambda value: True)
    client = cloud.HubClient(config, 'synthetic-worker-token')
    client.http.close()
    client.http = httpx.Client(transport=httpx.MockTransport(handler), headers={'Authorization': 'Bearer synthetic-worker-token'})
    assert client.identity()['worker_id'] == 'chatgpt-pilot'
    assert json.loads(calls[-1].content)['arguments'] == {'project_id': 'pilot'}
    response.clear()
    response.update(session={'project_id': 'pilot', 'session_id': 'a' * 32, 'latest_sequence': 101}, items=[])
    assert client.latest() == 101
    arguments = json.loads(calls[-1].content)['arguments']
    assert arguments['session_id'] == 'a' * 32 and arguments['after_sequence'] == cloud.MAX_SEQUENCE
    response['session']['session_id'] = 'b' * 32
    with pytest.raises(cloud.GatewayError, match='room differs'): client.read(0)
    response.clear()
    with pytest.raises(cloud.GatewayError, match='control unavailable'): client.paused()
    response.update(control={'paused': True})
    assert client.paused() is True
    assert calls[-1].url.params['project_id'] == 'pilot' and calls[-1].url.params['session_id'] == 'a' * 32
    response.clear()
    response.update(worker_id='unrelated-worker')
    with pytest.raises(cloud.GatewayError, match='identity differs'): client.identity()
    response.clear()
    response['large'] = 'x' * 65537
    with pytest.raises(cloud.GatewayError, match='too large'): client.identity()
    status[0] = 302
    with pytest.raises(cloud.GatewayError, match='unavailable'): client.identity()


def test_config_is_exact_private_and_no_token_is_accepted(tmp_path):
    path = tmp_path / 'config.json'
    (tmp_path / 'ca.crt').write_text('fixture-public-ca')
    config = {'hub_url': 'https://hub.example.test', 'ca_file': 'ca.crt', 'ca_sha256': 'a' * 64,
              'project_id': 'pilot', 'session_id': 'a' * 32, 'worker_id': 'pilot-worker',
              'state_path': 'private/state.sqlite', 'callback_hosts': ['callback.example.test']}
    path.write_text(json.dumps(config))
    parsed = cloud.load_config(path)
    assert parsed['max_events_per_subscription'] == 20 and parsed['subscription_ttl'] == 1800
    assert Path(parsed['state_path']) == tmp_path / 'private/state.sqlite'
    path.write_text(json.dumps({**config, 'callback_hosts': []}))
    assert cloud.load_config(path)['callback_hosts'] == []
    for change in [{'token': 'never-save-me'}, {'callback_hosts': ['*']}, {'callback_hosts': ['127.0.0.1']},
                   {'subscription_ttl': 0}, {'max_events_per_subscription': 21},
                   {'hub_url': 'https://user:secret@hub.example.test'}, {'hub_url': 'https://hub.example.test?'},
                   {'session_id': '../another-project'}]:
        path.write_text(json.dumps({**config, **change}))
        with pytest.raises((cloud.GatewayError, ValueError)): cloud.load_config(path)


def test_subscription_filters_ttl_cache_and_secret_cipher_integrity(pilot):
    for change in [{'arguments': {'session_id': 'foreign'}}, {'name': 'unexpected'}, {'cursor': 'old'}, {'ttlMs': 0}]:
        with pytest.raises(cloud.GatewayError): pilot.gateway.subscribe({**subscription(), **change})
    first = pilot.gateway.subscribe({**subscription(), 'ttlMs': 5000})
    assert first['refreshBefore'] == cloud.iso(1005)
    pilot.gateway.subscribe({**subscription(), 'ttlMs': 5000})
    assert len(pilot.sent) == 1  # verified URL + unchanged secret uses a bounded cache.
    cipher = pilot.gateway.db.execute('SELECT destination FROM subscriptions').fetchone()[0]
    with pytest.raises(Exception):
        pilot.gateway.box.decrypt(cipher[:-1] + bytes([cipher[-1] ^ 1]))
    pilot.now[0] = 1006
    pilot.hub.add()
    pilot.gateway.tick()
    assert len(pilot.sent) == 1


def test_notification_errors_do_not_create_jsonrpc_responses(pilot):
    assert pilot.gateway.dispatch({'jsonrpc': '2.0', 'method': 'unknown_notification'}) is None


def test_tools_only_mode_never_calls_unconfigured_callback(pilot):
    pilot.config['callback_hosts'] = []
    assert rpc(pilot.gateway, 'tools/call', {'name': 'identity'})['result']['structuredContent']['worker_id'] == 'chatgpt-pilot'
    with pytest.raises(cloud.GatewayError, match='allowlist'):
        pilot.gateway.subscribe(subscription())
    assert pilot.sent == []


def test_cli_argument_error_does_not_repeat_accidental_secret(monkeypatch, capsys):
    monkeypatch.setattr(cloud.sys, 'argv', ['cloud-gateway', '--config', 'config.json', '--token', 'synthetic-do-not-echo'])
    with pytest.raises(SystemExit) as exc:
        cloud.main()
    assert exc.value.code == 2
    assert 'synthetic-do-not-echo' not in capsys.readouterr().err


@pytest.mark.skipif(os.name != 'nt', reason='Windows current-user DPAPI')
def test_gateway_dpapi_secret_box_roundtrip():
    box = cloud.SecretBox()
    value = {'secret': SECRET, 'url': URL}
    cipher = box.encrypt(value)
    assert cipher[:2] == b'D1' and box.decrypt(cipher) == value
    assert SECRET.encode() not in cipher


def active_binding(pilot):
    row = pilot.gateway.db.execute("SELECT binding FROM subscriptions WHERE status='active'").fetchone()
    return pilot.gateway.box.decrypt(row['binding'])['receipt']


def notification(pilot):
    return [packet[1]['data']['notification_id'] for packet in pilot.sent if 'eventId' in packet[1]][-1]


def read_batch(pilot, identifier):
    args = {'notification_id': identifier, 'limit': 1}
    pages = []
    for _ in range(20):
        page = pilot.gateway.call('read_delta', args)
        pages.append(page)
        if not page['delivery_receipt']['unread_message_ids']:
            return pages
        args['after_sequence'] = page['next_after_sequence']
    raise AssertionError('Batch did not complete within 20 events')


def test_protocol_success_envelopes_and_callback_diagnostic_are_bounded(pilot, capsys):
    for method in ['server/discover', 'tools/list', 'events/list', 'ping']:
        assert rpc(pilot.gateway, method)['result']['resultType'] == 'complete'
    discovered = rpc(pilot.gateway, 'server/discover')['result']
    assert discovered['_meta']['io.modelcontextprotocol/serverInfo']['name']
    assert rpc(pilot.gateway, 'tools/call', {'name':'identity'})['result']['resultType'] == 'complete'
    host = 'unlisted-fixture.example.test'
    with pytest.raises(cloud.GatewayError):
        cloud.callback_url('https://' + host + '/private-callback?secret=do-not-log', [])
    diagnostic = capsys.readouterr().err
    assert json.loads(diagnostic.splitlines()[-1]) == {'event':'callback_host_not_allowed', 'hostname':host}
    assert 'private-callback' not in diagnostic and 'do-not-log' not in diagnostic


@pytest.mark.parametrize('message,category', [
    ('Notification lease expired', 'notification_expired'),
    ('Notification lease was superseded', 'notification_superseded'),
    ('Subscription is not active; old notifications cannot write', 'subscription_inactive')])
def test_rpc_failure_diagnostic_categories_and_fingerprint_are_private(pilot, capsys, monkeypatch, message, category):
    def failed(*args):
        raise cloud.GatewayError(message, -32001)
    monkeypatch.setattr(pilot.gateway, 'call', failed)
    identifier = 'synthetic-private-notification'
    result = rpc(pilot.gateway, 'tools/call', {'name': 'read_delta', 'arguments': {
        'notification_id': identifier, 'body': 'synthetic-private-body', 'token': SECRET, 'url': URL}})
    log = capsys.readouterr().err
    record = json.loads(log.splitlines()[-1])
    assert result['error']['code'] == -32001
    assert record == {'event': 'gateway_request_error', 'timestamp': cloud.iso(pilot.now[0]),
                      'method': 'tools/call', 'tool': 'read_delta', 'error_code': category,
                      'notification_fingerprint': hashlib.sha256(identifier.encode()).hexdigest()[:16]}
    assert all(value not in log for value in (identifier, 'synthetic-private-body', SECRET, URL))
    assert len(log) < 512


def test_untrusted_method_tool_exception_and_id_are_never_logged(pilot, capsys, monkeypatch):
    marker = 'synthetic-secret-do-not-log'
    result = pilot.gateway.dispatch({'jsonrpc': '2.0', 'id': marker, 'method': marker,
                                     'params': {'name': marker, 'arguments': {'body': marker}}})
    assert result['error']['code'] == -32601
    log = capsys.readouterr().err
    assert marker not in log and json.loads(log.splitlines()[-1])['method'] == 'unknown'
    def failed(*args):
        raise RuntimeError(marker)
    monkeypatch.setattr(pilot.gateway, 'call', failed)
    result = rpc(pilot.gateway, 'tools/call', {'name': marker, 'arguments': {'notification_id': marker * 1000}})
    log = capsys.readouterr().err
    assert result['error']['code'] == -32603 and marker not in log
    assert json.loads(log.splitlines()[-1])['tool'] == 'unknown'
    assert 'notification_fingerprint' not in json.loads(log.splitlines()[-1])


@pytest.mark.parametrize('tool,status', [('read_delta', 'partial_tool_read'),
                                      ('read_delta', 'tool_read'), ('post_message', 'replied')])
def test_success_diagnostics_preserve_wire_and_only_report_receipt_milestone(pilot, capsys, monkeypatch, tool, status):
    value = {'body': 'synthetic-private-reply', 'delivery_receipt': {'status': status}}
    monkeypatch.setattr(pilot.gateway, 'call', lambda *args: value)
    result = rpc(pilot.gateway, 'tools/call', {'name': tool, 'arguments': {'body': SECRET}})
    log = capsys.readouterr().err
    assert result['result']['structuredContent'] == value
    record = json.loads(log.splitlines()[-1])
    assert record['event'] == 'gateway_tool_completed' and record['receipt_status'] == status
    assert SECRET not in log and value['body'] not in log


def test_diagnostic_write_failure_never_retries_or_changes_committed_post(pilot, monkeypatch):
    class BrokenStderr:
        def write(self, text): raise OSError('synthetic-output-unavailable')
    calls = []
    monkeypatch.setattr(cloud.sys, 'stderr', BrokenStderr())
    monkeypatch.setattr(pilot.gateway, 'call', lambda *args: calls.append(args) or {'delivery_receipt': {'status': 'replied'}})
    result = rpc(pilot.gateway, 'tools/call', {'name': 'post_message', 'arguments': {'body': 'fixture'}})
    assert result['result']['isError'] is False and len(calls) == 1


def test_real_expired_notification_logs_rejection_without_read_or_cursor_change(pilot, capsys):
    pilot.config['subscription_ttl'] = 600
    pilot.gateway.subscribe(subscription())
    pilot.hub.add(body='synthetic-private-source')
    pilot.gateway.tick()
    identifier = notification(pilot)
    binding = active_binding(pilot)
    pilot.gateway.call('read_delta', {'notification_id': identifier, 'limit': 1})
    before = pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])
    capsys.readouterr()
    pilot.now[0] += 301
    result = rpc(pilot.gateway, 'tools/call', {'name': 'read_delta',
                 'arguments': {'notification_id': identifier}})
    record = json.loads(capsys.readouterr().err.splitlines()[-1])
    assert record['error_code'] == 'notification_expired'
    assert result['error']['code'] == -32001
    after = pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])
    assert after['processed_sequence'] == before['processed_sequence']
    assert after['latest_delivery']['read_at'] == before['latest_delivery']['read_at']


def test_native_batch_pages_full_escaped_message_receipts_and_stable_reply(pilot):
    pilot.gateway.subscribe(subscription())
    huge = 'boundary-' + chr(1) * 7980 + '-END'
    pilot.hub.add(body=huge)
    for _ in range(4): pilot.hub.add(body='second page ' * 300)
    pilot.gateway.tick()
    identifier = notification(pilot)
    binding = active_binding(pilot)
    state = pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])
    assert state['latest_delivery'] is None
    assert state['turns_used'] == 0
    assert state['processed_sequence'] == binding['processed_sequence']
    with pytest.raises(cloud.GatewayError, match='Read this notification'):
        pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Complete reply'})
    pages = read_batch(pilot, identifier)
    assert len(pages) == 5 and pages[0]['items'][0]['body'] == huge
    assert all(page['returned_bytes'] <= 65536 for page in pages)
    assert pages[0]['returned_bytes'] > 16384  # The escaped message used the one-event fallback.
    result = pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Complete reply'})
    assert result['delivery_receipt']['status'] == 'replied'
    assert pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Complete reply'}) == result
    assert len(pilot.hub.posts) == 1
    written = pilot.hub.read(result['sequence'] - 1, 1, full_text=True)['items'][0]
    assert written['automatic_reply_depth'] == 1
    with pytest.raises(cloud.GatewayError):
        pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'A different reply'})
    with pytest.raises(cloud.GatewayError):
        pilot.gateway.call('post_message', {'body':'Drop metadata to bypass', 'idempotency_key':'ordinary'})


def test_cloud_and_other_ai_causal_depth_stops_then_human_restarts(pilot):
    from memory_hub.session_service import SessionActor
    pilot.gateway.subscribe(subscription())
    root = pilot.hub.add()
    pilot.gateway.tick()
    identifier = notification(pilot)
    read_batch(pilot, identifier)
    pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Cloud depth one'})
    other_actor = SessionActor.from_principal(pilot.hub.other)
    common = {'project_id':'pilot', 'session_id':pilot.config['session_id']}
    other = pilot.hub.real.delivery.call('join', {**common, 'client':'claude', 'display_name':'Other AI',
        'native_session_id':'synthetic-other', 'after_sequence':root['sequence'], 'idempotency_key':'other'}, other_actor)
    delivery = pilot.hub.real.delivery.call('claim', {'project_id':'pilot', 'binding_id':other['binding_id']}, other_actor)['delivery']
    args = {**common, 'delivery_id':delivery['delivery_id'], 'lease_id':delivery['lease_id']}
    pilot.hub.real.call('read_session', {**args, 'after_sequence':delivery['after_sequence'], 'full_text':True}, pilot.hub.other)
    reply = pilot.hub.real.call('post_session_message', {**args, 'body':'Other depth two',
        'idempotency_key':delivery['reply_idempotency_key']}, pilot.hub.other)
    assert pilot.hub.read(reply['sequence'] - 1, 1)['items'][0]['automatic_reply_depth'] == 2
    before = len(pilot.sent)
    pilot.gateway.tick()
    assert len(pilot.sent) == before  # A depth-2 AI reply is visible but cannot wake the cloud.
    pilot.hub.add(body='A new human root')
    pilot.gateway.tick()
    assert len(pilot.sent) == before + 1
    identifier = notification(pilot)
    read_batch(pilot, identifier)
    again = pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Fresh depth one'})
    assert pilot.hub.read(again['sequence'] - 1, 1)['items'][0]['automatic_reply_depth'] == 1


def test_pause_fences_old_notification_and_never_rebinds_it_to_new_batch(pilot):
    from memory_hub.session_service import SessionActor
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    old = notification(pilot)
    read_batch(pilot, old)
    admin = SessionActor('human', 'admin', 'Admin', ('pilot',), 'admin')
    common = {'project_id':'pilot', 'session_id':pilot.config['session_id']}
    pilot.hub.real.delivery.call('pause', {**common, 'paused':True, 'expected_version':1}, admin)
    with pytest.raises(cloud.GatewayError):
        pilot.gateway.call('post_message', {'notification_id':old, 'body':'Late reply'})
    pilot.hub.real.delivery.call('pause', {**common, 'paused':False, 'expected_version':2}, admin)
    pilot.gateway.tick()
    assert notification(pilot) == old
    assert pilot.gateway.db.execute('SELECT status FROM subscriptions').fetchone()[0] == 'admission_failed'
    with pytest.raises(cloud.GatewayError):
        pilot.gateway.call('read_delta', {'notification_id':old})


def test_reservation_response_loss_replays_exact_queue_without_turn_charge(pilot):
    pilot.config['subscription_ttl'] = 900
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    relay = pilot.hub.relay
    dropped = [False]
    def lose_reserve(operation, **kwargs):
        result = relay(operation, **kwargs)
        if operation == 'reserve' and result['status'] == 'queued' and not dropped[0]:
            dropped[0] = True
            raise cloud.GatewayError('Synthetic response lost')
        return result
    pilot.hub.relay = lose_reserve
    with pytest.raises(cloud.GatewayError): pilot.gateway.tick()
    binding = active_binding(pilot)
    assert relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 0
    pilot.gateway.tick()
    assert len(pilot.sent) == 2
    pilot.now[0] += 301
    pilot.gateway.tick()
    assert len(pilot.sent) == 2
    read_batch(pilot, notification(pilot))
    assert relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 1


def test_reply_response_loss_reconciles_and_retries_without_duplicate(pilot):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    identifier = notification(pilot)
    read_batch(pilot, identifier)
    post = pilot.hub.post
    dropped = [False]
    def lose_reply(*args, **kwargs):
        result = post(*args, **kwargs)
        if not dropped[0]:
            dropped[0] = True
            raise cloud.GatewayError('Synthetic response lost')
        return result
    pilot.hub.post = lose_reply
    with pytest.raises(cloud.GatewayError):
        pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Exactly once'})
    pilot.gateway.db.close()
    pilot.gateway = cloud.Gateway(pilot.config, pilot.hub, box=cloud.SecretBox(KEY), sender=pilot.sender, clock=lambda:pilot.now[0])
    pilot.gateway.tick()
    result = pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Exactly once'})
    events = pilot.hub.read(result['sequence'] - 1, 10, full_text=True)['items']
    assert sum(x.get('body') == 'Exactly once' for x in events) == 1
    assert result['delivery_receipt']['status'] == 'replied'


def test_unsubscribe_and_stop_disconnect_only_owned_generation(pilot):
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    old = notification(pilot)
    first = active_binding(pilot)
    pilot.gateway.unsubscribe(unsubscribe())
    assert pilot.hub.relay('heartbeat', binding_id=first['binding_id'])['status'] == 'disconnected'
    with pytest.raises(cloud.GatewayError): pilot.gateway.call('read_delta', {'notification_id':old})
    another = URL + '-another'
    pilot.gateway.subscribe(subscription(url=another))
    second = active_binding(pilot)
    assert second['generation'] > first['generation']
    assert second['processed_sequence'] == first['processed_sequence']
    pilot.gateway.stop()
    assert pilot.hub.relay('heartbeat', binding_id=second['binding_id'])['status'] == 'disconnected'


def test_hub_http_budget_error_retries_one_full_event_only(tmp_path, monkeypatch):
    config = {'hub_url':'https://hub.example.test', 'project_id':'pilot', 'session_id':'a'*32,
        'ca_file':str(tmp_path/'ca.crt'), 'ca_sha256':'a'*64}
    monkeypatch.setattr(cloud, 'verified_context', lambda value: True)
    client = cloud.HubClient(config, 'synthetic-worker-token')
    client.http.close()
    calls = []
    def handler(request):
        args = json.loads(request.content)['arguments']
        calls.append(args)
        if len(calls) == 1:
            return httpx.Response(422, json={'error':'response_budget_too_small', 'message':'bounded fixture'})
        return httpx.Response(200, json={'session':{'project_id':'pilot', 'session_id':'a'*32}, 'items':[]})
    client.http = httpx.Client(transport=httpx.MockTransport(handler))
    client.read(12, 10, full_text=True, delivery={'delivery_id':'d'*32, 'lease_id':'e'*32})
    assert [x['max_bytes'] for x in calls] == [16384,65536]
    assert [x['limit'] for x in calls] == [10,1]
    assert all(x['full_text'] and x['delivery_id']=='d'*32 and x['lease_id']=='e'*32 for x in calls)


def test_expired_execution_is_terminal_without_retargeting_notification(pilot):
    pilot.config['subscription_ttl'] = 900
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    old = notification(pilot)
    read_batch(pilot, old)
    binding = active_binding(pilot)
    pilot.now[0] += 301
    with pytest.raises(cloud.GatewayError, match='expired'):
        pilot.gateway.call('post_message', {'notification_id':old, 'body':'Late reply'})
    pilot.gateway.tick()
    assert notification(pilot) == old
    assert pilot.gateway.db.execute('SELECT status FROM subscriptions').fetchone()[0] == 'admission_failed'
    assert pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 1
    assert not pilot.hub.posts


def test_ambiguous_join_reuses_key_and_never_resets_cursor_or_budget(pilot):
    relay = pilot.hub.relay
    dropped = [False]
    def lose_join(operation, **kwargs):
        result = relay(operation, **kwargs)
        if operation == 'join' and not dropped[0]:
            dropped[0] = True
            raise cloud.GatewayError('Synthetic join response lost')
        return result
    pilot.hub.relay = lose_join
    with pytest.raises(cloud.GatewayError): pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.subscribe(subscription())
    binding = active_binding(pilot)
    assert binding['generation'] == 1
    pilot.gateway.tick()
    assert relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 0
    assert len(pilot.sent[-1][1]['data']['message_ids']) == 1


def test_manual_read_has_full_text_path_before_monitoring(pilot):
    before = pilot.hub.sequence
    body = 'Full message ' * 300
    pilot.hub.add(body=body)
    page = pilot.gateway.call('read_delta', {'after_sequence':before})
    assert page['items'][0]['body'] == body and not page['items'][0]['body_truncated']
    assert 'delivery_receipt' not in page


def test_ack_queue_restart_delayed_activation_exact_range_and_no_redelivery(pilot):
    pilot.config['subscription_ttl'] = 1800
    pilot.gateway.subscribe(subscription())
    first = pilot.hub.add(body='reserved first')
    pilot.gateway.tick()
    identifier = notification(pilot)
    binding = active_binding(pilot)
    original = pilot.sent[-1][1]
    pilot.gateway.db.close()
    pilot.now[0] += 420
    later = pilot.hub.add(body='outside immutable range')
    pilot.gateway = cloud.Gateway(pilot.config, pilot.hub, box=cloud.SecretBox(KEY), sender=pilot.sender, clock=lambda:pilot.now[0])
    pilot.gateway.tick()
    assert len(pilot.sent) == 2
    assert pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 0
    pages = read_batch(pilot, identifier)
    assert [i['message_id'] for p in pages for i in p['items'] if i['type']=='message'] == [first['message_id']]
    result = pilot.gateway.call('post_message', {'notification_id':identifier, 'body':'Exact reserved reply'})
    assert result['delivery_receipt']['processed_sequence'] == original['data']['through_sequence'] < later['sequence']
    pilot.gateway.tick()
    assert len(pilot.sent) == 3
    read_batch(pilot, notification(pilot))
    assert pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 2


def test_activation_response_loss_restart_replays_one_lease_and_turn(pilot):
    pilot.config['subscription_ttl'] = 900
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    identifier = notification(pilot)
    binding = active_binding(pilot)
    relay = pilot.hub.relay
    dropped = [False]
    def lose_activate(operation, **kwargs):
        result = relay(operation, **kwargs)
        if operation == 'activate' and not dropped[0]:
            dropped[0] = True
            raise cloud.GatewayError('Synthetic activation response lost')
        return result
    pilot.hub.relay = lose_activate
    with pytest.raises(cloud.GatewayError): read_batch(pilot, identifier)
    first = relay('heartbeat', binding_id=binding['binding_id'])
    pilot.gateway.db.close()
    pilot.gateway = cloud.Gateway(pilot.config, pilot.hub, box=cloud.SecretBox(KEY), sender=pilot.sender, clock=lambda:pilot.now[0])
    read_batch(pilot, identifier)
    second = relay('heartbeat', binding_id=binding['binding_id'])
    assert first['latest_delivery']['delivery_id'] == second['latest_delivery']['delivery_id']
    assert first['turns_used'] == second['turns_used'] == 1
    assert len(pilot.sent) == 2


def test_queue_expiry_terminal_no_replacement_or_cursor_change(pilot):
    pilot.config['subscription_ttl'] = 3600
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    binding = active_binding(pilot)
    identifier = notification(pilot)
    pilot.now[0] += 1801
    with pytest.raises(cloud.GatewayError, match='queue expired'):
        pilot.gateway.call('read_delta', {'notification_id':identifier})
    pilot.gateway.tick()
    pilot.gateway.tick()
    assert len(pilot.sent) == 2
    assert pilot.gateway.db.execute('SELECT status FROM subscriptions').fetchone()[0] == 'queue_expired'
    state = pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])
    assert state['turns_used'] == 0 and state['processed_sequence'] == binding['processed_sequence']
    assert state['latest_delivery'] is None


def test_ambiguous_callback_restart_uses_same_event_id_without_admission(pilot):
    pilot.config['subscription_ttl'] = 900
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    def receipt_lost(*args):
        pilot.sender(*args)
        raise cloud.GatewayError('Synthetic remote receipt/local response loss')
    pilot.gateway.sender = receipt_lost
    pilot.gateway.tick()
    first = pilot.sent[-1]
    binding = active_binding(pilot)
    pilot.gateway.db.close()
    pilot.now[0] += 5
    pilot.gateway = cloud.Gateway(pilot.config, pilot.hub, box=cloud.SecretBox(KEY), sender=pilot.sender, clock=lambda:pilot.now[0])
    pilot.gateway.tick()
    second = pilot.sent[-1]
    assert first[1] == second[1]
    assert first[2]['webhook-id'] == second[2]['webhook-id']
    assert first[2]['webhook-timestamp'] != second[2]['webhook-timestamp']
    assert pilot.hub.relay('heartbeat', binding_id=binding['binding_id'])['turns_used'] == 0
    pilot.gateway.tick()
    assert len(pilot.sent) == 3  # verification + ambiguous receipt + identical retry.


@pytest.mark.parametrize('status', [202, 429, 410, 0])
def test_event_trace_correlates_native_ingress_and_preserves_retry(pilot, capsys, status):
    pilot.gateway.subscribe(subscription())
    verification = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [r['event'] for r in verification] == ['callback_verification_dispatch', 'callback_verification_completed']
    assert verification[-1]['http_status'] == 200
    pilot.hub.add(body='canary-private-body')
    pilot.result['status'] = status
    if status == 0:
        def failed(*args):
            raise RuntimeError('canary-private-exception')
        pilot.gateway.sender = failed
    pilot.gateway.tick()
    identifier = pilot.gateway.db.execute('SELECT event_id FROM outbox').fetchone()[0]
    logs = capsys.readouterr().err
    records = [json.loads(line) for line in logs.splitlines()]
    assert len(records) == 2
    assert records[0]['event'] == 'gateway_event_dispatch'
    assert records[1]['event'] == ('gateway_event_received' if status == 202 else 'gateway_event_failed')
    assert records[1]['http_status'] == status and records[1]['attempt'] == 1
    expected = hashlib.sha256(identifier.encode()).hexdigest()[:16]
    assert all(r['notification_fingerprint'] == expected and r['timestamp'] == cloud.iso(pilot.now[0]) for r in records)
    assert all(value not in logs for value in [identifier, URL, SECRET, 'canary-private-body', 'canary-private-exception'])
    row = pilot.gateway.db.execute('SELECT state, attempts FROM outbox').fetchone()
    assert tuple(row) == ('received' if status == 202 else 'failed' if status == 410 else 'queued', 1)
    pilot.gateway.dispatch({'jsonrpc':'2.0', 'id':'canary-request-id', 'method':'tools/call',
        'params':{'name':'read_delta', 'arguments':{'notification_id':identifier}}})
    native = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert native[0]['event'] == 'gateway_request_ingress'
    assert native[0]['notification_fingerprint'] == expected
    assert native[-1]['event'] == ('gateway_request_error' if status == 410 else 'gateway_tool_completed')
    assert native[-1]['notification_fingerprint'] == expected
    if status != 410:
        assert native[-1]['receipt_status'] == 'tool_read'


@pytest.mark.parametrize('failure', ['transport', 'challenge', 'http'])
def test_verification_failure_trace_is_redacted_and_does_not_join(pilot, capsys, failure):
    def failed(*args):
        if failure == 'transport':
            raise RuntimeError('canary-private-exception')
        return (500 if failure == 'http' else 200), cloud.compact({'challenge':'canary-private-challenge'})
    pilot.gateway.sender = failed
    with pytest.raises(cloud.GatewayError, match='Callback verification failed'):
        pilot.gateway.subscribe(subscription())
    logs = capsys.readouterr().err
    records = [json.loads(line) for line in logs.splitlines()]
    assert [r['event'] for r in records] == ['callback_verification_dispatch', 'callback_verification_failed']
    assert records[-1]['http_status'] == (0 if failure == 'transport' else 500 if failure == 'http' else 200)
    assert records[0]['notification_fingerprint'] == records[1]['notification_fingerprint']
    assert all(value not in logs for value in [URL, SECRET, 'canary-private-exception', 'canary-private-challenge'])
    assert pilot.gateway.db.execute('SELECT count(*) FROM subscriptions').fetchone()[0] == 0


def test_delivery_logging_failure_preserves_receipt_and_dedup(pilot, monkeypatch):
    class BrokenStderr:
        def write(self, text):
            raise OSError('synthetic-unavailable')
    monkeypatch.setattr(cloud.sys, 'stderr', BrokenStderr())
    pilot.gateway.subscribe(subscription())
    pilot.hub.add()
    pilot.gateway.tick()
    pilot.gateway.tick()
    assert len(pilot.sent) == 2
    assert tuple(pilot.gateway.db.execute('SELECT state,attempts FROM outbox').fetchone()) == ('received', 1)
    assert pilot.gateway.db.execute('SELECT delivered FROM subscriptions').fetchone()[0] == 1


def test_event_read_metadata_declares_delivery_state_effects(pilot):
    tool = next(t for t in pilot.gateway.tools() if t['name'] == 'read_delta')
    assert tool['annotations']['readOnlyHint'] is False
    assert 'event.data.notification_id' in tool['description']
    assert 'delivery lease' in tool['description']
    assert 'notification_id' not in tool['inputSchema'].get('required', [])


def test_trace_retry_recovery_reuses_fingerprint_and_does_not_redeliver(pilot, capsys):
    pilot.gateway.subscribe(subscription())
    capsys.readouterr()
    pilot.hub.add()
    pilot.result['status'] = 429
    pilot.gateway.tick()
    failed = [json.loads(line) for line in capsys.readouterr().err.splitlines()][-1]
    pilot.now[0] += 5
    pilot.result['status'] = 202
    pilot.gateway.tick()
    recovered = [json.loads(line) for line in capsys.readouterr().err.splitlines()][-1]
    assert failed['notification_fingerprint'] == recovered['notification_fingerprint']
    assert failed['attempt'] == 1 and failed['terminal'] is False
    assert recovered['attempt'] == 2 and recovered['event'] == 'gateway_event_received'
    pilot.gateway.tick()
    assert capsys.readouterr().err == ''
    assert tuple(pilot.gateway.db.execute('SELECT state, attempts FROM outbox').fetchone()) == ('received', 2)
    assert len(pilot.sent) == 3
