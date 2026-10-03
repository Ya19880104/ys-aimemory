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
from memory_hub.store import HubError


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


def test_delivery_browser_adapter_preserves_csrf_nonce_scope_and_version(room, monkeypatch):
    client, hub, _ = room
    sid = action(client, 'create_session', {'project_id': 'shared', 'title': 'Delivery'}).json()['session_id']
    calls = []

    class DeliveryContract:
        """Contract double: backend delivery behavior has its own service tests."""
        def call(self, name, args, actor):
            calls.append((name, args, actor))
            assert actor.kind == 'human' and actor.role == 'admin'
            if name == 'status':
                return {'control': {'paused': False, 'version': 4}, 'participants': [
                    {'worker_id': 'ai-a', 'display_name': 'Original alias', 'status': 'offline'}]}
            if args['expected_version'] != 4:
                raise HubError('stale_control', 'Room control changed', 409)
            return {'paused': args['paused'], 'version': 5, 'running_turns_cancelled': False}

    monkeypatch.setattr(hub, 'delivery', DeliveryContract(), raising=False)
    response = client.get('/ui/chat/data', params={'op': 'delivery', 'project': 'shared', 'session': sid})
    assert response.status_code == 200
    assert response.json()['participants'][0] == {'worker_id': 'ai-a', 'display_name': 'Codex 測試端', 'status': 'offline'}
    assert client.get('/ui/chat/data', params={'op': 'delivery', 'project': 'private', 'session': sid}).status_code == 404
    assert len(calls) == 1
    args = {'project_id': 'shared', 'session_id': sid, 'paused': True, 'expected_version': 4}
    denied = client.post('/ui/chat/action', json={'action': 'set_session_delivery_paused', 'arguments': args})
    assert denied.status_code == 403 and len(calls) == 1
    result = action(client, 'set_session_delivery_paused', args, 'pause-once')
    assert result.status_code == 200 and result.json()['running_turns_cancelled'] is False
    assert calls[-1][1]['idempotency_key'] == 'pause-once'
    stale = action(client, 'set_session_delivery_paused', {**args, 'expected_version': 3}, 'stale-pause')
    assert stale.status_code == 409
    client.cookies.clear()
    assert client.get('/ui/chat/data', params={'op': 'delivery', 'project': 'shared', 'session': sid}).status_code == 401


def test_delivery_missing_service_reports_unavailable_not_disconnected(room, monkeypatch):
    client, hub, _ = room
    monkeypatch.delattr(hub, 'delivery', raising=False)
    result = client.get('/ui/chat/data?op=delivery&project=shared&session=' + 'a'*32)
    assert result.status_code == 503
    assert result.json()['error'] == 'unavailable'


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


@pytest.fixture(autouse=True)
def traditional_interface(monkeypatch):
    """Retain legacy copy assertions as explicit Traditional Chinese coverage."""
    monkeypatch.setenv("HUB_WEB_LANGUAGE", "zh-TW")


def test_automatic_setup_uses_configured_origin_and_public_ca(room, monkeypatch):
    from types import SimpleNamespace
    import memory_hub.web_sessions as sessions
    client, _, _ = room
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL', 'https://hub.example.com')
    monkeypatch.setenv('HUB_DOCS_BASE_URL', '/offline/docs')
    monkeypatch.setattr(sessions, '_public_ca', lambda path: SimpleNamespace(fingerprint='AB:' * 31 + 'AB'))
    page = client.get('/ui/chat?project=shared&lang=en', headers={'X-Forwarded-Host': 'attacker.example'})
    assert page.status_code == 200
    assert 'Set up automatic replies' in page.text
    assert 'data-setup-base="https://hub.example.com"' in page.text
    assert 'data-claude-guide="/offline/docs/AUTOMATIC_CHAT.md"' in page.text
    assert 'data-codex-guide="/offline/docs/CODEX_CHAT_SETUP.md"' in page.text
    assert 'attacker.example' not in page.text
    assert 'synthetic-room-worker-token-1234' not in page.text
    assert page.text.count('id="auto-setup"') == 1
    assert '/ui/mcp?' in page.text
    monkeypatch.setattr(sessions, '_public_ca', lambda path: None)
    assert 'data-setup-base=""' in client.get('/ui/chat?project=shared').text


@pytest.mark.parametrize('language', ['en', 'zh-TW'])
def test_automatic_setup_commands_escape_values_and_do_not_activate(language, monkeypatch):
    import shutil
    import subprocess
    from memory_hub.web_chat_assets import CHAT_JS
    from memory_hub.i18n import CATALOG, script_catalog
    monkeypatch.setenv('HUB_WEB_LANGUAGE', language)
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable for generated command execution')
    handler = CHAT_JS[CHAT_JS.index("  $('auto-client').onchange="):CHAT_JS.index("  $('copy-invite').onclick=")]
    harness = script_catalog(CHAT_JS) + 'const expected=' + json.dumps({
        'claude': CATALOG['ui_aa001011'][language],
        'codex': CATALOG['ui_aa001012'][language],
    }) + ';' + r"""
const fields = { 'auto-worker':{value:"worker'o"}, 'auto-hours':{value:'1'}, 'auto-turns':{value:'6'}, 'auto-client':{value:'codex'}, 'auto-instructions':{}, 'auto-setup-status':{} };
const $=id=>fields[id]||(fields[id]={});
const state={project:"project'o",room:{session_id:'a'.repeat(32)}};
const cfg={dataset:{setupBase:'https://hub.example.com',setupCa:'AB'.repeat(32),claudeGuide:'/help?lang=en',codexGuide:'https://docs.example.test/CODEX_CHAT_SETUP.md'}};
const location={href:'https://hub.example.com/ui/chat'};
let copied=''; const navigator={clipboard:{writeText:async text=>{copied=text;}}};
""" + handler + r"""
(async()=>{ $('auto-client').onchange(); if(!$('auto-project-hint').hidden)throw Error('Codex path hint'); await $('copy-auto-setup').onclick();
if(!copied.includes("-WorkerId 'worker''o'")||!copied.includes("-ProjectId 'project''o'")||copied.includes(' -Run')||!copied.includes('F5E622AC3BC21CA06B311238C4B49491324FDD01C40F84FC97081913A4EBFDD7'))throw Error('Codex command');
if(!copied.includes('# https://docs.example.test/CODEX_CHAT_SETUP.md'))throw Error('Codex guide');
if(copied.includes('# undefined')||!copied.includes('# '+expected.codex))throw Error('Codex translated instructions');
fields['auto-client'].value='claude';$('auto-client').onchange();if($('auto-project-hint').hidden)throw Error('Claude path hint');await $('copy-auto-setup').onclick();
if(!copied.includes("-Project 'REPLACE_WITH_EXACT_LOCAL_PROJECT'")||copied.includes(' -WorkerId')||!copied.includes('BBE80FCE04A2707C84C4F0501DE1DA8359205EDC89D00A179EF4AE7851A28E89'))throw Error('Claude command');
if(!copied.includes('# https://hub.example.com/help?lang=en'))throw Error('Claude offline guide');
if(copied.includes('# undefined')||!copied.includes('# '+expected.claude))throw Error('Claude translated instructions');
copied='';fields['auto-hours'].value='9';await $('copy-auto-setup').onclick();if(copied)throw Error('invalid budget copied');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run([node, '-e', harness], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_complete_installation_payload_is_safe_powershell_with_hostile_worker():
    import shutil
    import subprocess
    from memory_hub.web_chat_assets import CHAT_JS
    from memory_hub.i18n import CATALOG
    node = shutil.which('node')
    powershell = shutil.which('pwsh') or shutil.which('powershell')
    if not node or not powershell:
        pytest.skip('Node.js and PowerShell required for generated payload parser check')
    worker = "worker;$(Write-Output 'SHOULD_NOT_EXECUTE')"
    handler = CHAT_JS[CHAT_JS.index("  $('auto-client').onchange="):CHAT_JS.index("  $('copy-invite').onclick=")]
    harness = "const CATALOG=" + json.dumps({key: value for key, value in CATALOG.items() if key.startswith("ui_aa001") or key in ("ui_872bc28ee946", "ui_ce0fe4db3088")}, ensure_ascii=True) + ";" + r"""
const fields={'auto-worker':{value:WORKER},'auto-hours':{value:'1'},'auto-turns':{value:'6'},'auto-client':{value:'codex'},'auto-instructions':{},'auto-setup-status':{}};
const $=id=>fields[id]||(fields[id]={});
const state={project:'shared',room:{session_id:'a'.repeat(32)}};
const cfg={dataset:{setupBase:'https://hub.example.com',setupCa:'AB'.repeat(32),claudeGuide:'/help?lang=en',codexGuide:'https://docs.example.test/CODEX_CHAT_SETUP.md'}};
const location={href:'https://hub.example.com/ui/chat'};
let UI_LANGUAGE='en';const uiText=key=>CATALOG[key][UI_LANGUAGE];let copied='';
const navigator={clipboard:{writeText:async text=>{copied=text;}}};
""".replace('WORKER', json.dumps(worker)) + handler + r"""
(async()=>{const payloads=[];for(const lang of ['en','zh-TW'])for(const client of ['claude','codex']){UI_LANGUAGE=lang;fields['auto-client'].value=client;await $('copy-auto-setup').onclick();payloads.push({text:copied,worker:fields['auto-worker'].value,client});}console.log(JSON.stringify(payloads));})().catch(e=>{console.error(e);process.exitCode=1});
"""
    generated = subprocess.run([node, '-e', harness], capture_output=True, text=True, encoding='utf-8')
    assert generated.returncode == 0, generated.stderr
    parser = r"""
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
$items = [Console]::In.ReadToEnd() | ConvertFrom-Json
foreach ($item in $items) {
    $tokens=$null; $errors=$null
    $ast=[System.Management.Automation.Language.Parser]::ParseInput($item.text,[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw 'Complete guide failed PowerShell parsing' }
    $commands=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true))
    foreach ($command in $commands) { if ($command.GetCommandName() -notin @('Join-Path','Invoke-WebRequest','Get-FileHash','notepad')) { throw 'Unexpected executable command in complete guide' } }
    $line=@($item.text -split "`n" | Where-Object { $_.StartsWith('# powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Installer ') })
    if ($line.Count -ne 1) { throw 'Missing separate commented installation command' }
    $install=[System.Management.Automation.Language.Parser]::ParseInput($line[0].Substring(2),[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw 'Installation command failed parsing' }
    $calls=@($install.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true))
    if ($calls.Count -ne 1) { throw 'Worker added an executable command' }
    if ($calls[0].GetCommandName() -ne 'powershell.exe') { throw 'Expected process-scoped installer invocation' }
    if ($item.client -eq 'codex') {
        $literal=@($install.FindAll({param($n) $n -is [System.Management.Automation.Language.StringConstantExpressionAst] -and $n.Value -eq $item.worker},$true))
        if ($literal.Count -ne 1) { throw 'Worker is not an exact literal parameter' }
    }
}
"""
    checked = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', parser], input=generated.stdout, capture_output=True, text=True, encoding='utf-8')
    assert checked.returncode == 0, checked.stderr


def test_room_invite_survives_login_and_wrong_password_without_secret_queries(room):
    client, _, _ = room
    client.cookies.clear()
    target = '/ui/chat?project=shared&session=' + '1' * 32 + '&lang=en'
    response = client.get(target + '&token=DO_NOT_RETAIN&password=DO_NOT_RETAIN', follow_redirects=False)
    assert response.status_code == 303
    assert 'DO_NOT_RETAIN' not in response.headers['location']
    page = client.get(response.headers['location'])
    assert 'DO_NOT_RETAIN' not in page.text
    token = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    failed = client.post('/login', data={'csrf': token, 'username': 'human-room-admin',
        'password': 'wrong', 'return_to': 'https://evil.test'}, follow_redirects=False)
    assert failed.status_code == 401
    token = re.search('name="csrf" value="([^"]+)"', failed.text)[1]
    success = client.post('/login', data={'csrf': token, 'username': 'human-room-admin',
        'password': 'synthetic-room-password', 'return_to': '/ui/chat?project=private'},
        follow_redirects=False)
    assert success.status_code == 303 and success.headers['location'] == target
    assert client.get(success.headers['location']).status_code == 200


@pytest.mark.parametrize('target', [
    'https://evil.test/ui/chat', '//evil.test/ui/chat', '/\\evil.test/ui/chat',
    '/ui/chat/../action', '/ui/chat%2f..%2faction', '/logout',
    '/ui/chat?project=shared&project=private', '/ui/chat?session=invalid',
    '/ui/chat?project=shared%0d%0aLocation%3Aevil', '/ui/chat#secret',
])
def test_login_rejects_unsafe_return_targets(room, target):
    client, _, _ = room
    client.cookies.clear()
    page = client.get('/login', params={'return_to': target})
    token = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post('/login', data={'csrf': token, 'username': 'human-room-admin',
        'password': 'synthetic-room-password'}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/ui/chat'


def test_room_return_does_not_grant_project_access(room):
    client, _, _ = room
    client.cookies.clear()
    response = client.get('/ui/chat?project=private&session=' + '1' * 32, follow_redirects=False)
    page = client.get(response.headers['location'])
    token = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post('/login', data={'csrf': token, 'username': 'human-room-admin',
        'password': 'synthetic-room-password'}, follow_redirects=False)
    assert client.get(response.headers['location']).status_code == 404
