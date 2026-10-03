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


class Hub:
    def __init__(self, config):
        self.config, self.messages, self.pause, self.revoked = config, [], False, False
        self.sequence, self.posts, self.reads = 100, [], []

    def identity(self):
        if self.revoked:
            raise cloud.GatewayError('Hub unavailable')
        return {'worker_id': self.config['worker_id'], 'project_id': self.config['project_id'],
                'session_id': self.config['session_id']}

    def paused(self):
        if self.pause == 'unavailable':
            raise cloud.GatewayError('Pause unavailable')
        return self.pause

    def latest(self): return self.sequence

    def read(self, after, limit=5):
        self.reads.append(after)
        items = [item for item in self.messages if item['sequence'] > after][:limit]
        return {'items': items, 'next_after_sequence': items[-1]['sequence'] if items else after,
                'has_more': False, 'session': {'latest_sequence': self.sequence,
                'session_id': self.config['session_id'], 'project_id': self.config['project_id']}}

    def add(self, sender='human-admin', body='new test message'):
        self.sequence += 1
        identifier = f'{self.sequence:032x}'
        self.messages.append({'type': 'message', 'event_id': identifier, 'message_id': identifier,
            'sequence': self.sequence, 'created_at': 1000.0, 'actor': {'id': sender, 'display_name': sender}, 'body': body})

    def post(self, body, key):
        self.posts.append((body, key))
        self.add(self.config['worker_id'], body)
        return {'message_id': self.messages[-1]['event_id'], 'sequence': self.sequence}


@pytest.fixture
def pilot(tmp_path):
    config = {'hub_url': 'https://hub.example.test', 'project_id': 'pilot', 'session_id': 'a' * 32,
        'worker_id': 'chatgpt-pilot', 'state_path': str(tmp_path / 'private.sqlite'),
        'callback_hosts': ['callback.example.test'], 'poll_interval': 60,
        'max_events_per_subscription': 20, 'subscription_ttl': 60}
    hub = Hub(config)
    sent, now = [], [1000.0]
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
    assert identity['worker_id'] == 'chatgpt-pilot' and identity['latest_sequence'] == 100
    for name, arguments in [('read_delta', {'after_sequence': 0, 'project_id': 'foreign'}),
                            ('post_message', {'body': 'test', 'idempotency_key': 'a', 'session_id': 'b' * 32}),
                            ('memory_call', {'name': 'approve_memory_change'})]:
        assert 'error' in rpc(gateway, 'tools/call', {'name': name, 'arguments': arguments})
    assert pilot.hub.posts == [] and pilot.hub.reads == []
    result = rpc(gateway, 'tools/call', {'name': 'post_message', 'arguments': {'body': 'hello', 'idempotency_key': 'once'}})
    assert result['result']['structuredContent']['sequence'] == 101
    assert pilot.hub.posts == [('hello', 'once')]


def test_first_subscription_starts_now_signed_and_encrypted(pilot):
    pilot.hub.add(body='historical text must not be delivered')
    receipt = pilot.gateway.subscribe(subscription())
    pilot.hub.add(body='new confidential body')
    pilot.gateway.tick()
    delivered = pilot.sent[-1]
    assert delivered[1]['data']['sequence'] == 102
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
    def pause_during_read(*args):
        result = read(*args)
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
    pilot.gateway.tick()
    pilot.gateway.tick()
    assert len([item for item in pilot.sent if 'eventId' in item[1]]) == 2
    with pytest.raises(cloud.GatewayError, match='budget'):
        pilot.gateway.subscribe(subscription())
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
    pilot.gateway.subscribe(subscription())
    pilot.gateway.tick()
    assert pilot.gateway.db.execute('SELECT state FROM outbox').fetchone()[0] == 'cancelled'


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
