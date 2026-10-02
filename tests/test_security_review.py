"""Independent security review regressions; all credentials/data are synthetic."""
import json
import re

from fastapi.testclient import TestClient

from memory_hub.app import create_app
from memory_hub.web_password import hash_password


def test_mcp_actual_calls_and_request_identity(tmp_path, monkeypatch):
    for key in ('HUB_WEB_USERNAME', 'HUB_WEB_PASSWORD_HASH', 'HUB_WEB_PROJECTS'):
        monkeypatch.delenv(key, raising=False)
    identities = {
        actor + '-synthetic-token-000000000000': {
            'worker_id': actor, 'projects': ['other'] if actor == 'outsider' else ['review'],
            'role': 'admin' if actor == 'operator' else 'worker',
        }
        for actor in ('operator', 'worker-a', 'worker-b', 'outsider')
    }
    app = create_app(database_url=f'sqlite:///{tmp_path}/protocol.db', allow_sqlite=True, auth_tokens=json.dumps(identities))
    with TestClient(app) as client:
        def invoke(actor, name, arguments, error=False):
            response = client.post('/mcp', headers={
                'Authorization': f'Bearer {actor}-synthetic-token-000000000000',
                'Accept': 'application/json, text/event-stream',
            }, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                'name': name, 'arguments': {'arguments': {'project_id': 'review', **arguments}},
            }})
            assert response.status_code == 200, response.text
            # Stateless transport must not grant a reusable cross-identity session.
            assert 'mcp-session-id' not in response.headers
            result = response.json()['result']
            assert result['isError'] is error, result
            return result if error else json.loads(result['content'][0]['text'])

        invoke('operator', 'create_project', {})
        invoke('operator', 'register_source', dict(source_id='spec', content='Review fixture', uri='fixture:spec', commit='abc'))
        invoke('operator', 'create_task', dict(task_id='task', goal='Review', allowed_paths=['src/'], acceptance_criteria=['Pass'], source_ids=['spec']))
        packet = invoke('worker-a', 'prepare_task', dict(task_id='task', workspace='/fixture/a', branch='a', commit='abc'))
        lease = invoke('worker-a', 'claim_task', dict(task_id='task'))
        gate = {'packet_id': packet['packet_id'], 'fence': lease['fence']}
        invoke('worker-b', 'read_source', dict(packet_id=packet['packet_id'], source_id='spec'), error=True)
        invoke('worker-a', 'read_source', dict(packet_id=packet['packet_id'], source_id='spec'))
        invoke('worker-a', 'acknowledge_context', dict(packet_id=packet['packet_id']))
        invoke('worker-a', 'accept_handoff', gate)
        invoke('worker-a', 'record_checkpoint', {**gate, 'summary': 'Verified', 'evidence': [{'source_id': 'spec', 'sha256': packet['required_sources']['spec']}]})
        invoke('outsider', 'search_knowledge', dict(query='fixture'), error=True)
        invoke('worker-a', 'search_knowledge', dict(query='fixture', worker_id='operator'), error=True)
        invoke('worker-a', 'register_source', dict(source_id='bad', content='Not authorized', uri='fixture:x', commit='x'), error=True)


def test_integrated_cookie_isolation_rotation_and_logout_replay(tmp_path, monkeypatch):
    monkeypatch.setenv('HUB_WEB_USERNAME', 'review-user')
    monkeypatch.setenv('HUB_WEB_PASSWORD_HASH', hash_password('synthetic-review-password'))
    monkeypatch.setenv('HUB_WEB_PROJECTS', 'review')
    monkeypatch.setenv('HUB_WEB_COOKIE_SECURE', 'false')
    token = 'synthetic-review-operator-token-0000000'
    app = create_app(database_url=f'sqlite:///{tmp_path}/web.db', allow_sqlite=True, auth_tokens=json.dumps({token: {'worker_id': 'operator', 'projects': ['review'], 'role': 'admin'}}))
    with TestClient(app) as client:
        login = client.get('/login')
        csrf = re.search('name="csrf" value="([^"]+)"', login.text)[1]
        client.cookies.set('hub_web_session', 'attacker-chosen', domain='testserver.local', path='/')
        response = client.post('/login', data={'username': 'review-user', 'password': 'synthetic-review-password', 'csrf': csrf}, follow_redirects=False)
        assert response.status_code == 303
        assert 'attacker-chosen' not in response.headers.get_list('set-cookie')[0]
        dashboard = client.get('/ui', follow_redirects=False)
        assert dashboard.status_code == 200
        assert token not in dashboard.text
        assert dashboard.headers['cache-control'] == 'no-store'
        assert client.post('/mcp', json={}).status_code == 401
        assert client.post('/v1/tools/create_project', json={'arguments': {'project_id': 'review'}}).status_code == 401
        old_cookie = client.cookies.get('hub_web_session', domain='testserver.local', path='/')
        csrf = re.search('name="csrf" value="([^"]+)"', dashboard.text)[1]
        assert client.post('/logout', data={'csrf': 'wrong'}).status_code == 403
        assert client.post('/logout', data={'csrf': csrf}, follow_redirects=False).status_code == 303
        client.cookies.set('hub_web_session', old_cookie, domain='testserver.local', path='/')
        assert client.get('/ui', follow_redirects=False).headers['location'] == '/login'
