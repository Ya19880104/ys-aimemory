"""Human cookie and worker bearer share only explicitly shared Sessions."""
import base64
from html import unescape
import json
import re

from fastapi.testclient import TestClient
import pytest

from memory_hub.app import create_app
from memory_hub.models import Principal
from memory_hub.web_password import hash_password


@pytest.fixture
def room(tmp_path, monkeypatch):
    monkeypatch.setenv('HUB_WEB_USERNAME', 'human-room-admin')
    monkeypatch.setenv('HUB_WEB_PASSWORD_HASH', hash_password('synthetic-room-password'))
    monkeypatch.setenv('HUB_WEB_PROJECTS', 'shared')
    monkeypatch.setenv('HUB_WEB_ROLE', 'admin')
    monkeypatch.setenv('HUB_WEB_COOKIE_SECURE', 'false')
    monkeypatch.setenv('HUB_WEB_MCP_ENABLED', 'false')
    monkeypatch.setenv('HUB_WORKER_DISPLAY_NAMES', json.dumps({'ai-a': 'Codex 測試端'}))
    app = create_app(database_url='sqlite:///' + str(tmp_path / 'room.db'), allow_sqlite=True,
        auth_tokens=json.dumps({'synthetic-room-worker-token-1234': {
            'worker_id': 'ai-a', 'projects': ['shared'], 'role': 'worker'}}))
    hub = app.state.hub
    admin = Principal(worker_id='setup', projects=['shared', 'private'], role='admin')
    for project in admin.projects:
        hub.call('create_project', {'project_id': project}, admin)
    with TestClient(app) as client:
        login_page = client.get('/login')
        csrf = re.search('name="csrf" value="([^"]+)"', login_page.text)[1]
        assert client.post('/login', data={'csrf': csrf, 'username': 'human-room-admin',
                            'password': 'synthetic-room-password'}, follow_redirects=False).status_code == 303
        yield client, hub, admin


def action(client, name, arguments, key='test-action'):
    page = client.get('/ui/chat?project=shared')
    match = re.search('id="room-config"[^>]*data-csrf="([^"]+)"', page.text)
    assert match, page.text
    csrf = unescape(match[1])
    nonce = client.get('/ui/chat/data', params={'op': 'nonce', 'action': name,
        'project': arguments.get('project_id', ''), 'session': arguments.get('session_id', '')})
    assert nonce.status_code == 200, nonce.text
    return client.post('/ui/chat/action', headers={'X-CSRF-Token': csrf}, json={
        'action': name, 'arguments': {**arguments, 'idempotency_key': key}, 'nonce': nonce.json()['nonce']})


def test_chat_page_and_incremental_human_worker_conversation(room):
    client, hub, _ = room
    page = client.get('/ui/chat?project=shared')
    assert page.status_code == 200
    assert '共享對話' in page.text and '以 管理員 ' in page.text
    assert '人類管理員' not in page.text
    assert 'Enter 傳送' in page.text and 'Shift+Enter 換行' in page.text
    assert "connect-src 'self'" in page.headers['content-security-policy']
    created = action(client, 'create_session', {'project_id': 'shared', 'title': '<script>room</script>'})
    assert created.status_code == 200, created.text
    sid = created.json()['session_id']
    posted = action(client, 'post_session_message', {'project_id': 'shared', 'session_id': sid,
        'body': '<img src=x onerror=alert(1)> Human decision'}, 'human-message')
    assert posted.status_code == 200, posted.text
    assert posted.json()['actor']['kind'] == 'human'
    assert posted.json()['actor']['id'] != 'web-operator'
    hub.call('post_session_message', {'project_id': 'shared', 'session_id': sid,
        'body': 'AI received it', 'idempotency_key': 'worker-reply'},
        Principal(worker_id='ai-a', projects=['shared'], role='worker'))
    data = client.get('/ui/chat/data', params={'op': 'read', 'project': 'shared', 'session': sid}).json()
    messages = [item for item in data['items'] if item['type'] == 'message']
    assert [item['actor']['kind'] for item in messages] == ['human', 'worker']
    assert messages[1]['actor']['display_name'] == 'Codex 測試端'
    assert messages[1]['actor']['id'] == 'ai-a'
    assert messages[0]['body'].startswith('<img')  # JSON data, rendered by textContent.
    empty = client.get('/ui/chat/data', params={'op': 'read', 'project': 'shared',
        'session': sid, 'after': data['next_after_sequence']}).json()
    assert empty['items'] == []


def test_latest_artifacts_index_is_scoped_bounded_and_omits_contents(room):
    client, hub, admin = room
    sid = action(client, 'create_session', {'project_id': 'shared', 'title': 'Index'}).json()['session_id']
    for index in range(12):
        hub.call('create_session_artifact', {'project_id': 'shared', 'session_id': sid,
            'kind': 'plan', 'title': f'Plan {index}', 'content': 'private full content',
            'covered_through_sequence': 0, 'idempotency_key': f'plan-{index}'}, admin)
    data = client.get('/ui/chat/data', params={'op': 'artifacts', 'project': 'shared', 'session': sid})
    assert data.status_code == 200
    result = data.json()
    assert [item['title'] for item in result['items']] == [f'Plan {i}' for i in range(11, 1, -1)]
    assert result['has_more'] and 'private full content' not in data.text
    assert all('content' not in item and 'reference_message_ids' not in item for item in result['items'])
    assert client.get('/ui/chat/data', params={'op': 'artifacts', 'project': 'private', 'session': sid}).status_code == 404
    assert client.get('/ui/chat/data', params={'op': 'artifacts', 'project': 'shared', 'session': '0'*32}).status_code == 404
    client.cookies.clear()
    assert client.get('/ui/chat/data', params={'op': 'artifacts', 'project': 'shared', 'session': sid}).status_code == 401


def test_chat_rejects_csrf_actor_forgery_and_cross_project(room):
    client, _, _ = room
    assert client.post('/ui/chat/action', json={'action': 'create_session',
        'arguments': {'project_id': 'shared', 'title': 'bad', 'idempotency_key': 'no-csrf'}}).status_code == 403
    assert client.get('/ui/chat/data?op=list&project=private').status_code in (403, 404)
    bad = action(client, 'create_session', {'project_id': 'shared', 'title': 'forged',
        'actor': {'kind': 'worker', 'id': 'someone-else'}}, 'forgery')
    assert bad.status_code == 422
    client.cookies.clear()
    assert client.get('/ui/chat/data?op=list').status_code == 401
    assert client.get('/ui/chat', follow_redirects=False).status_code == 303
    assert client.get('/ui/chat/unknown').status_code == 401


def test_attachment_is_authenticated_download_and_artifact_remains_proposal(room):
    client, hub, _ = room
    sid = action(client, 'create_session', {'project_id': 'shared', 'title': 'Files'}).json()['session_id']
    uploaded = action(client, 'upload_session_attachment', {'project_id': 'shared', 'session_id': sid,
        'filename': 'plan.html', 'content_base64': base64.b64encode(b'<script>untrusted</script>').decode()}, 'file')
    assert uploaded.status_code == 200, uploaded.text
    aid = uploaded.json()['attachment_id']
    url = '/ui/chat/file?project=shared&session=' + sid + '&attachment=' + aid
    file = client.get(url)
    assert file.status_code == 200 and file.content == b'<script>untrusted</script>'
    assert file.headers['content-disposition'].startswith('attachment;')
    assert file.headers['x-content-type-options'] == 'nosniff'
    assert file.headers['content-type'] == 'application/octet-stream'
    result = action(client, 'create_session_artifact', {'project_id': 'shared', 'session_id': sid,
        'kind': 'handoff_proposal', 'title': 'Draft handoff', 'content': 'Please review scope.',
        'covered_through_sequence': uploaded.json()['sequence'], 'attachment_ids': [aid]}, 'draft')
    assert result.status_code == 200, result.text
    assert hub.call('list_tasks', {'project_id': 'shared'},
        Principal(worker_id='ai-a', projects=['shared'], role='worker'))['items'] == []
    client.cookies.clear()
    assert client.get(url).status_code == 401


def test_nonce_is_bound_to_room_and_readonly_account_cannot_post(room):
    client, _, _ = room
    first = action(client, 'create_session', {'project_id':'shared','title':'First'}, 'first').json()['session_id']
    second = action(client, 'create_session', {'project_id':'shared','title':'Second'}, 'second').json()['session_id']
    page = client.get('/ui/chat?project=shared')
    csrf = unescape(re.search('id="room-config"[^>]*data-csrf="([^"]+)"', page.text)[1])
    nonce = client.get('/ui/chat/data', params={'op':'nonce','action':'post_session_message',
        'project':'shared','session':first}).json()['nonce']
    response = client.post('/ui/chat/action', headers={'X-CSRF-Token':csrf}, json={
        'action':'post_session_message','nonce':nonce,'arguments':{
            'project_id':'shared','session_id':second,'body':'wrong room','idempotency_key':'wrong-room'}})
    assert response.status_code == 409
    auth = client.app.state.web_auth
    current = auth.session(client.cookies.get('hub_web_session'))
    auth.users.create(current, 'readonly-room', '觀察者', 'synthetic-readonly-password', 'read_only', ('shared',), False)
    client.cookies.clear()
    csrf = re.search('name="csrf" value="([^"]+)"', client.get('/login').text)[1]
    assert client.post('/login', data={'csrf':csrf,'username':'readonly-room',
        'password':'synthetic-readonly-password'}, follow_redirects=False).status_code == 303
    assert client.get('/ui/chat?project=shared').status_code == 200
    assert client.get('/ui/chat/data', params={'op':'read','project':'shared','session':first}).status_code == 200
    assert client.get('/ui/chat/data', params={'op':'nonce','action':'post_session_message',
        'project':'shared','session':first}).status_code == 403
    assert client.post('/ui/chat/action', json={}).status_code == 403
    assert client.get('/ui/users').status_code == 403


def test_account_cookie_paths_are_precise_and_account_data_omits_hashes(room):
    client, _, _ = room
    response = client.get('/ui/users')
    assert response.status_code == 200 and 'scrypt$' not in response.text
    assert client.get('/ui/account/password').status_code == 200
    assert client.get('/ui/users/unknown').status_code == 401
    assert client.post('/ui/users/create', data={'username':'forged'}).status_code == 403
