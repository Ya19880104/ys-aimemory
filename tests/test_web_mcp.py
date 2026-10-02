import json
import re
from html import unescape

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import Store, projects
from memory_hub.web import WebConfig, install_web
from memory_hub.web_password import hash_password

OWNER = '2d4444b8-f908-4651-9493-9f711283ae17'


@pytest.fixture
def generator(tmp_path, monkeypatch):
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL', 'https://memory.example.test')
    store = Store('sqlite:///' + str(tmp_path / 'generator.db'), allow_sqlite=True)
    operator = Principal(worker_id='operator', projects=['visible', 'private'], role='admin')
    hub = Hub(store, principals=[operator])
    for project in operator.projects:
        hub.call('create_project', {'project_id': project}, operator)
    password = hash_password('fixture-password-for-generator')
    bootstrap_app = FastAPI()
    bootstrap = install_web(bootstrap_app, hub, WebConfig('fixture', password, ('visible',), False, 300, 'admin', True, OWNER))
    bootstrap.start_session('fixture-admin-session', 'fixture-csrf', '', bootstrap.users.authenticate('fixture', 'fixture-password-for-generator'))
    bootstrap.users.create(bootstrap.session('fixture-admin-session'), 'fixture-reader', 'Reader', 'fixture-password-for-generator', 'read_only', ('visible',))

    def make(role='admin', enabled=True, username='fixture'):
        app = FastAPI()
        config = WebConfig(username, password, ('visible',), False, 300, role,
                           mcp_enabled=enabled, owner_id=OWNER)
        install_web(app, hub, config)
        client = TestClient(app)
        csrf = re.search('name="csrf" value="([^"]+)"', client.get('/login').text)[1]
        client.post('/login', data={'csrf': csrf, 'username': 'fixture-reader' if role == 'read_only' else 'fixture',
                                  'password': 'fixture-password-for-generator'})
        return client

    yield make, hub
    store.engine.dispose()


def form(client, action, project='visible', token_id=None):
    html = client.get('/ui/mcp', params={'project': project}).text
    forms = re.findall(r'<form method="post" action="/ui/mcp/' + action + r'">(.*?)</form>', html, re.S)
    for body in forms:
        fields = {name: unescape(value) for name, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', body)}
        if token_id is None or fields.get('token_id') == token_id:
            return fields
    raise AssertionError('Missing form: ' + action)


def post(client, action, values):
    return client.post('/ui/mcp/' + action, data=values, follow_redirects=False)


def token(response):
    assert response.status_code == 200
    return unescape(re.search(r'<textarea id="issued-token"[^>]*>(.*?)</textarea>', response.text, re.S)[1])


def test_create_library_scope_and_issue_once(generator):
    make, hub = generator
    client = make()
    response = post(client, 'project', {**form(client, 'project'), 'new_project_id': 'new-memory'})
    assert response.status_code == 303
    assert 'new-memory' in client.get('/ui').text
    assert client.get('/ui/manage?project=new-memory').status_code == 200
    assert 'href="/ui/mcp?project=new-memory"' in client.get('/ui?project=new-memory').text
    assert 'href="/ui/chat?project=new-memory"' in client.get('/ui/mcp?project=new-memory').text
    fields = {**form(client, 'issue', 'new-memory'), 'worker_id': 'claude-library'}
    issued = post(client, 'issue', fields)
    raw = token(issued)
    assert len(raw) >= 43 and issued.headers['cache-control'] == 'no-store'
    assert hub.credentials.authenticate(raw).projects == ['new-memory']
    assert raw not in client.get('/ui/mcp?project=new-memory').text
    assert raw not in client.get('/ui').text
    assert post(client, 'issue', fields).status_code == 409
    assert raw not in post(client, 'issue', fields).text
    # Every downloadable template contains an env reference, not the secret.
    configs = re.findall(r'<textarea id="config-[^"]+"[^>]*>(.*?)</textarea>', issued.text, re.S)
    assert len(configs) >= 2
    assert all(raw not in unescape(value) for value in configs)
    assert 'YS_AIMEMORY_TOKEN' in issued.text
    assert 'https://memory.example.test/mcp' in issued.text


def test_rotate_revoke_scope_and_no_secret_in_state(generator):
    make, hub = generator
    client = make()
    first = token(post(client, 'issue', {**form(client, 'issue'), 'worker_id': 'codex-test'}))
    metadata = hub.credentials.list_credentials(['visible'])[0]
    second = token(post(client, 'rotate', form(client, 'rotate', token_id=metadata['token_id'])))
    assert hub.credentials.authenticate(first) is None
    assert hub.credentials.authenticate(second).worker_id == 'codex-test'
    revoke = form(client, 'revoke', token_id=metadata['token_id'])
    assert post(client, 'revoke', revoke).status_code == 303
    assert hub.credentials.authenticate(second) is None
    assert post(client, 'revoke', revoke).status_code == 409
    assert '已撤銷' in client.get('/ui/mcp').text
    with hub.store.engine.connect() as conn:
        state = conn.execute(select(projects.c.state).where(projects.c.id == 'visible')).scalar_one()
        audit = hub.store.read_audit(conn, 'visible')
    assert first not in json.dumps([state, audit]) and second not in json.dumps([state, audit])


def test_role_scope_csrf_and_cannot_claim_existing_library(generator):
    make, hub = generator
    client = make()
    bad = {**form(client, 'issue'), 'worker_id': 'bad', 'csrf': 'wrong'}
    assert post(client, 'issue', bad).status_code == 403
    bad = {**form(client, 'issue'), 'worker_id': 'bad', 'project_id': 'private'}
    assert post(client, 'issue', bad).status_code == 403
    assert client.get('/ui/mcp?project=private').status_code == 403
    assert post(client, 'project', {**form(client, 'project'), 'new_project_id': 'private'}).status_code == 409
    assert 'private' not in hub.credentials.owned_projects(OWNER)
    assert post(client, 'issue', {**form(client, 'issue'), 'worker_id': 'operator'}).status_code in (400, 409)
    assert post(client, 'issue', {**form(client, 'issue'), 'worker_id': '<script>'}).status_code in (400, 422)
    # The role comes from the separate DB account, not the bootstrap environment.
    for settings in ({'role':'read_only'}, {'enabled':False}):
        client = make(**settings)
        assert client.get('/ui/mcp').status_code == 403
        assert post(client, 'issue', {'project_id': 'visible', 'role': 'admin'}).status_code == 403


def test_owner_and_explicit_grants_survive_environment_change_but_reader_gets_no_owned_scope(generator):
    make, hub = generator
    client = make()
    post(client, 'project', {**form(client, 'project'), 'new_project_id': 'stable-owner'})
    renamed = make(username='renamed')
    assert renamed.get('/ui/manage?project=stable-owner').status_code == 200
    reader = make('read_only', username='renamed')
    assert reader.get('/ui/manage?project=stable-owner').status_code == 403


def test_enabled_generator_requires_uuid_owner():
    with pytest.raises(ValueError):
        WebConfig('user', 'hash', ('visible',), mcp_enabled=True, owner_id='')
    with pytest.raises(ValueError):
        WebConfig('user', 'hash', ('visible',), mcp_enabled=True, owner_id='username')


def test_real_app_middleware_managed_bearer_and_cookie_isolation(tmp_path, monkeypatch):
    from memory_hub.app import create_app
    for key, value in {'HUB_WEB_USERNAME':'fixture', 'HUB_WEB_PASSWORD_HASH':hash_password('fixture-password'),
                       'HUB_WEB_PROJECTS':'visible', 'HUB_WEB_ROLE':'admin', 'HUB_WEB_COOKIE_SECURE':'false',
                       'HUB_WEB_MCP_ENABLED':'true', 'HUB_WEB_OWNER_ID':OWNER,
                       'HUB_PUBLIC_BASE_URL':'https://memory.example.test'}.items():
        monkeypatch.setenv(key,value)
    env_token = 'fixture-operator-long-token-123456789'
    app = create_app(database_url='sqlite:///'+str(tmp_path/'full-app.db'), allow_sqlite=True,
        auth_tokens=json.dumps({env_token:{'worker_id':'operator','projects':['visible'],'role':'admin'}}))
    with TestClient(app) as client:
        assert client.get('/ui/mcp',follow_redirects=False).headers['location']=='/login'
        assert client.get('/help').status_code==200
        csrf=re.search('name="csrf" value="([^"]+)"',client.get('/login').text)[1]
        client.post('/login',data={'csrf':csrf,'username':'fixture','password':'fixture-password'})
        values={**form(client,'project'),'new_project_id':'mcp-isolated'}
        assert post(client,'project',values).status_code==303
        raw=token(post(client,'issue',{**form(client,'issue','mcp-isolated'),'worker_id':'native-client'}))
        endpoint='/v1/tools/get_worker_inbox'
        args={'arguments':{'project_id':'mcp-isolated'}}
        assert client.post(endpoint,json=args).status_code==401
        headers={'Authorization':'Bearer '+raw}
        result=client.post(endpoint,json=args,headers=headers)
        assert result.status_code==200 and result.json()['worker_id']=='native-client'
        assert client.post(endpoint,json={'arguments':{'project_id':'visible'}},headers=headers).status_code==403
        assert client.post('/v1/tools/create_project',json=args,headers=headers).status_code==403
        init={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'generator-test','version':'1'}}}
        mcp_headers={**headers,'Accept':'application/json, text/event-stream'}
        assert client.post('/mcp',json=init).status_code==401
        initialized=client.post('/mcp',json=init,headers=mcp_headers)
        assert initialized.status_code==200 and 'result' in initialized.json()
        meta=app.state.hub.credentials.list_credentials(['mcp-isolated'])[0]
        replacement=token(post(client,'rotate',form(client,'rotate','mcp-isolated',meta['token_id'])))
        assert client.post('/mcp',json=init,headers=mcp_headers).status_code==401
        mcp_headers['Authorization']='Bearer '+replacement
        assert client.post('/mcp',json=init,headers=mcp_headers).status_code==200
        assert post(client,'revoke',form(client,'revoke','mcp-isolated',meta['token_id'])).status_code==303
        assert client.post('/mcp',json=init,headers=mcp_headers).status_code==401
        assert client.post('/v1/tools/create_project',json={'arguments':{'project_id':'visible'}},headers={'Authorization':'Bearer '+env_token}).status_code==200
