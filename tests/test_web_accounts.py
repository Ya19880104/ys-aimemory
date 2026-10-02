"""Human accounts use disposable databases and synthetic credentials only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from html import unescape
import re
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, create_engine, text, func
from sqlalchemy.engine import make_url

from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import Store, WEB_TABLES, HubError
from memory_hub.web import WebConfig, install_web, COOKIE
from memory_hub.web_password import hash_password

OWNER = '57e148a8-9313-4126-ae63-4a23131c37cd'
PASSWORD = 'synthetic-initial-password'


def test_page_connect_is_explicit_and_trusted_css_is_nonce_bound():
    from memory_hub.web import page
    normal = page('Hello')
    assert 'connect-src' not in normal.headers['content-security-policy']
    connected = page('Hello', css='.chat{color:inherit}', connect=True)
    assert "connect-src 'self'" in connected.headers['content-security-policy']
    assert '.chat{color:inherit}' in connected.body.decode()
    assert 'unsafe-inline' not in connected.headers['content-security-policy']


@pytest.fixture(params=['sqlite'] + (['postgresql'] if os.environ.get('HUB_TEST_DATABASE_URL') else []))
def account_store(tmp_path, request):
    cleanup_engine = None
    url = 'sqlite:///' + str(tmp_path / 'accounts.db')
    if request.param == 'postgresql':
        base = os.environ['HUB_TEST_DATABASE_URL']
        assert base.startswith('postgresql+psycopg://'), 'Use a disposable PostgreSQL test database'
        cleanup_engine = create_engine(base)
        schema = 'accounts_test_' + uuid.uuid4().hex
        with cleanup_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(base).update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    store = Store(url, allow_sqlite=request.param == 'sqlite')
    try:
        yield store
    finally:
        store.engine.dispose()
        if cleanup_engine:
            with cleanup_engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            cleanup_engine.dispose()


@pytest.fixture
def bootstrap_role():
    return 'admin'


@pytest.fixture
def accounts(account_store, bootstrap_role):
    store = account_store
    worker = Principal(worker_id='fixture-worker', projects=['one', 'two'], role='admin')
    hub = Hub(store, principals=[worker])
    for project in worker.projects:
        hub.call('create_project', {'project_id': project}, worker)
    config = WebConfig('operator', hash_password(PASSWORD), ('one',), False, 3600,
                       bootstrap_role, True, OWNER)
    clients = []
    def make(custom=config):
        app = FastAPI()
        install_web(app, hub, custom)
        client = TestClient(app)
        clients.append(client)
        return client, app
    client, app = make()
    yield client, app, hub, config, make
    for item in clients:
        item.close()


def login(client, username='operator', password=PASSWORD):
    response = client.get('/login')
    csrf = re.search(r'name="csrf" value="([^"]+)"', response.text)[1]
    return client.post('/login', data={'csrf': csrf, 'username': username, 'password': password}, follow_redirects=False)


def fields(client, action, user_id=None):
    path = '/ui/account/password' if action == 'self-password' else '/ui/users'
    response = client.get(path, params={'user_id': user_id} if user_id else {})
    assert response.status_code == 200
    route = '/ui/account/password' if action == 'self-password' else '/ui/users/' + action
    body = re.search(r'<form method="post" action="' + re.escape(route) + r'">(.*?)</form>', response.text, re.S)
    assert body, action
    return {key: unescape(value) for key, value in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', body[1])}


def post(client, action, values):
    return client.post('/ui/users/' + action, data=values, follow_redirects=False)


def create(client, username='member', role='member', projects='one', manager=False):
    response = post(client, 'create', {**fields(client, 'create'), 'username': username,
                    'display_name': '<Human>', 'password': 'synthetic-member-password',
                    'role': role, 'projects': projects, 'can_manage_users': 'true' if manager else 'false'})
    assert response.status_code == 303, response.text


def lookup(hub, username):
    with hub.store.engine.connect() as conn:
        return dict(conn.execute(select(WEB_TABLES['users']).where(WEB_TABLES['users'].c.username == username)).mappings().one())


def test_create_account_live_identity_and_no_worker_token(accounts):
    client, app, hub, _, make = accounts
    assert login(client).status_code == 303
    create(client)
    other, other_app = make()
    assert login(other, 'member', 'synthetic-member-password').status_code == 303
    auth = other_app.state.web_auth
    human = auth.principal(auth.session(other.cookies.get(COOKIE)))
    assert human.user_id != OWNER and human.username == 'member'
    assert human.projects == ('one',) and human.role == 'member'
    assert not human.can_manage_users
    assert other.get('/ui/users').status_code == 403
    assert other.get('/ui/mcp').status_code == 403
    assert other.get('/ui?project=two').status_code == 404
    assert '&lt;Human&gt;' in other.get('/ui').text
    assert hub.credentials.list_credentials(['one']) == []
    assert 'synthetic-member-password' not in client.get('/ui/users').text


def test_database_changes_survive_changed_environment_restart(accounts):
    client, app, hub, config, make = accounts
    login(client)
    create(client, role='read_only')
    target = lookup(hub, 'member')
    assert post(client, 'update', {**fields(client, 'update', target['user_id']),
                'display_name': 'Renamed human', 'role': 'member', 'projects': 'two', 'can_manage_users': 'false'}).status_code == 303
    changed = replace(config, role='read_only', projects=('two',), password_hash=hash_password('ignored-environment-password'))
    restarted, new_app = make(changed)
    assert login(restarted, 'member', 'synthetic-member-password').status_code == 303
    identity = new_app.state.web_auth.principal(new_app.state.web_auth.session(restarted.cookies.get(COOKIE)))
    assert identity.projects == ('two',) and identity.role == 'member'
    root, root_app = make(changed)
    assert login(root).status_code == 303
    assert root_app.state.web_auth.principal(root_app.state.web_auth.session(root.cookies.get(COOKIE))).can_manage_users


@pytest.mark.parametrize('action', ['disable', 'password', 'update'])
def test_changes_invalidate_other_instance_cookie(accounts, action):
    client, _, hub, _, make = accounts
    login(client)
    create(client)
    other, _ = make()
    login(other, 'member', 'synthetic-member-password')
    target = lookup(hub, 'member')
    values = fields(client, action, target['user_id'])
    if action == 'password': values['password'] = 'replacement-member-password'
    if action == 'update': values.update(display_name='Member', role='read_only', projects='two', can_manage_users='false')
    assert post(client, action, values).status_code == 303
    assert other.get('/ui', follow_redirects=False).headers['location'] == '/login'
    if action == 'disable':
        assert login(other, 'member', 'synthetic-member-password').status_code == 401
        target = lookup(hub, 'member')
        assert post(client, 'enable', fields(client, 'enable', target['user_id'])).status_code == 303
        assert login(other, 'member', 'synthetic-member-password').status_code == 303
    if action == 'password':
        assert login(other, 'member', 'synthetic-member-password').status_code == 401
        assert login(other, 'member', 'replacement-member-password').status_code == 303


def test_account_forms_csrf_nonce_cas_and_password_bounds(accounts):
    client, _, hub, _, _ = accounts
    login(client)
    base = fields(client, 'create')
    data = {**base, 'username': 'member', 'password': 'synthetic-member-password', 'display_name': 'Human', 'role': 'member', 'projects': 'one'}
    assert post(client, 'create', {**data, 'csrf': 'bad'}).status_code == 403
    assert post(client, 'create', data).status_code == 303
    assert post(client, 'create', data).status_code == 409
    target = lookup(hub, 'member')
    stale = fields(client, 'update', target['user_id'])
    assert post(client, 'password', {**fields(client, 'password', target['user_id']), 'password': 'replacement-member-password'}).status_code == 303
    assert post(client, 'update', {**stale, 'display_name': 'Human', 'role': 'admin', 'projects': 'two'}).status_code == 409
    for invalid in ('short', 'x' * 1025):
        assert post(client, 'create', {**fields(client, 'create'), 'username': 'invalid', 'password': invalid, 'display_name': 'Human', 'role': 'member', 'projects': 'one'}).status_code == 400


def test_self_password_requires_current_and_invalidates_sessions(accounts):
    client, _, hub, _, make = accounts
    login(client)
    create(client)
    one, _ = make(); two, _ = make()
    login(one, 'member', 'synthetic-member-password')
    login(two, 'member', 'synthetic-member-password')
    values = {**fields(one, 'self-password'), 'current_password': 'wrong', 'password': 'new-human-password'}
    assert one.post('/ui/account/password', data=values).status_code == 403
    values = {**fields(one, 'self-password'), 'current_password': 'synthetic-member-password', 'password': 'new-human-password'}
    assert one.post('/ui/account/password', data=values, follow_redirects=False).status_code == 303
    assert two.get('/ui', follow_redirects=False).headers['location'] == '/login'
    assert login(one, 'member', 'new-human-password').status_code == 303


def test_last_manager_parallel_disable_cannot_remove_both(accounts):
    client, app, hub, _, make = accounts
    login(client)
    create(client, username='second', role='admin', manager=True)
    other, other_app = make(); login(other, 'second', 'synthetic-member-password')
    auths = [app.state.web_auth, other_app.state.web_auth]
    currents = [auth.session(c.cookies.get(COOKIE)) for auth, c in zip(auths, [client, other])]
    targets = [lookup(hub, 'operator'), lookup(hub, 'second')]
    def disable(i):
        try:
            auths[i].users.set_enabled(currents[i], targets[i]['user_id'], targets[i]['version'], False)
            return 'disabled'
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(disable, range(2)))
    assert results.count('disabled') == 1
    assert 'last_manager' in results


@pytest.mark.parametrize('bootstrap_role', ['read_only'])
def test_readonly_bootstrap_never_gets_account_management(accounts):
    client, app, _, _, _ = accounts
    assert login(client).status_code == 303
    identity = app.state.web_auth.users.authenticate('operator', PASSWORD)
    assert identity.role == 'read_only' and not identity.can_manage_users
    assert client.get('/ui/users').status_code == 403


def test_removing_bootstrap_environment_keeps_database_login(accounts, monkeypatch):
    client, _, _, _, make = accounts
    login(client)
    create(client)
    for name in ('HUB_WEB_USERNAME', 'HUB_WEB_PASSWORD_HASH', 'HUB_WEB_PROJECTS', 'HUB_WEB_OWNER_ID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('HUB_WEB_COOKIE_SECURE', 'false')
    monkeypatch.setenv('HUB_WEB_MCP_ENABLED', 'false')
    restarted, _ = make(None)
    assert login(restarted, 'member', 'synthetic-member-password').status_code == 303
    assert restarted.get('/ui').status_code == 200


def test_owned_library_grant_can_be_revoked_without_restart_resurrection(accounts, monkeypatch):
    from test_web_mcp import form, post as mcp_post
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL', 'https://memory.example.test')
    client, app, hub, _, make = accounts
    login(client)
    create(client, username='project-admin', role='admin')
    owner, owner_app = make(); login(owner, 'project-admin', 'synthetic-member-password')
    assert mcp_post(owner, 'project', {**form(owner, 'project', 'one'), 'new_project_id': 'new-owned'}).status_code == 303
    target = lookup(hub, 'project-admin')
    assert hub.credentials.owned_projects(target['user_id']) == ('new-owned',)
    assert owner.get('/ui/manage?project=new-owned').status_code == 200
    assert post(client, 'update', {**fields(client, 'update', target['user_id']),
        'display_name': 'Owner', 'role': 'admin', 'projects': 'one', 'can_manage_users': 'false'}).status_code == 303
    restarted, _ = make(); login(restarted, 'project-admin', 'synthetic-member-password')
    assert restarted.get('/ui/manage?project=new-owned').status_code == 403
    assert restarted.get('/ui/mcp?project=new-owned').status_code == 403


def test_username_collision_and_nonce_target_binding(accounts):
    client, _, hub, _, _ = accounts
    login(client)
    create(client)
    data = {**fields(client, 'create'), 'username': 'MEMBER', 'display_name': 'Another',
            'password': 'synthetic-member-password', 'role': 'member', 'projects': 'one'}
    assert post(client, 'create', data).status_code == 409
    member = lookup(hub, 'member')
    data = fields(client, 'disable', member['user_id'])
    assert post(client, 'disable', {**data, 'target_id': OWNER}).status_code == 409
    assert lookup(hub, 'operator')['enabled'] and lookup(hub, 'member')['enabled']


def test_project_creation_with_preexisting_grant_is_atomic(accounts):
    client, app, hub, _, _ = accounts
    login(client)
    create(client, username='future-admin', role='admin', projects='future-library')
    identity = app.state.web_auth.users.authenticate('future-admin', 'synthetic-member-password')
    auth = app.state.web_auth
    auth.start_session('future-session', 'csrf', '', identity)
    auth.users.create_project(auth.session('future-session'), 'future-library', hub.credentials)
    assert hub.credentials.owned_projects(identity.user_id) == ('future-library',)
    assert auth.principal(auth.session('future-session')).projects == ('future-library',)


def test_account_audit_failure_rolls_back_user_and_grants(accounts, monkeypatch):
    client, app, hub, _, _ = accounts
    login(client)
    auth = app.state.web_auth
    current = auth.session(client.cookies.get(COOKIE))
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(auth.users, '_audit', fail)
    with pytest.raises(RuntimeError, match='synthetic audit failure'):
        auth.users.create(current, 'must-rollback', 'Human', 'synthetic-member-password', 'member', ('one',))
    with hub.store.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(WEB_TABLES['users']).where(WEB_TABLES['users'].c.username == 'must-rollback')).scalar_one() == 0
        assert conn.execute(select(func.count()).select_from(WEB_TABLES['grants'])).scalar_one() == 1


def test_normalized_username_expansion_is_rejected_before_database(accounts):
    client, _, _, _, _ = accounts
    login(client)
    response = post(client, 'create', {**fields(client, 'create'), 'username': '\u0390' * 128,
        'display_name': 'Human', 'password': 'synthetic-member-password', 'role': 'member', 'projects': 'one'})
    assert response.status_code == 400


def test_runtime_mcp_disable_revokes_stale_enabled_worker(accounts):
    client, _, _, config, make = accounts
    login(client)
    disabled, _ = make(replace(config, mcp_enabled=False))
    assert client.get('/ui', follow_redirects=False).headers['location'] == '/login'
    assert client.get('/login').status_code == 503
    assert login(disabled).status_code == 303
    assert disabled.get('/ui/mcp').status_code == 403


def test_no_grants_admin_can_create_first_library_without_issue_form(accounts, monkeypatch):
    from test_web_mcp import form, post as mcp_post
    monkeypatch.setenv('HUB_PUBLIC_BASE_URL', 'https://memory.example.test')
    client, _, _, _, make = accounts
    login(client)
    create(client, username='empty-admin', role='admin', projects='')
    empty, _ = make(); login(empty, 'empty-admin', 'synthetic-member-password')
    result = empty.get('/ui/mcp')
    assert result.status_code == 200
    assert 'action="/ui/mcp/project"' in result.text
    assert 'action="/ui/mcp/issue"' not in result.text
    assert empty.get('/ui/mcp?project=one').status_code == 403
    assert mcp_post(empty, 'project', {**form(empty, 'project', ''), 'new_project_id': 'first-owned'}).status_code == 303
    assert empty.get('/ui/manage?project=first-owned').status_code == 200


@pytest.mark.parametrize('mcp_enabled', [True, False])
@pytest.mark.parametrize('role', ['admin', 'read_only'])
def test_bootstrap_imports_owner_once_and_rejects_legacy_anonymous_cookie(account_store, mcp_enabled, role):
    from memory_hub.web_auth import WebAuthStore
    store = account_store
    hub = Hub(store)
    config = WebConfig('operator', hash_password(PASSWORD), ('one',), False, 3600, role, mcp_enabled, OWNER)
    try:
        hub.credentials.create_project('legacy-owned', OWNER, 'legacy-operator', 1000)
        with store.engine.begin() as conn:
            conn.execute(WEB_TABLES['entries'].insert().values(token_hash=WebAuthStore.key('old-anonymous-cookie'),
                kind='session', expires=9999, fingerprint='legacy-v4', payload={'csrf': 'old-csrf'}))
        # All instances use the same configured bootstrap; only one import wins.
        with ThreadPoolExecutor(max_workers=2) as executor:
            auths = list(executor.map(lambda _: WebAuthStore(store, config, lambda: 1001), range(2)))
        for auth in auths:
            human = auth.users.authenticate('operator', PASSWORD)
            assert human.user_id == OWNER
            assert human.projects == (('legacy-owned', 'one') if role == 'admin' else ('one',))
            assert human.can_manage_users == (role == 'admin')
            assert auth.session('old-anonymous-cookie') is None
        with store.engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(WEB_TABLES['users'])).scalar_one() == 1
            assert conn.execute(select(func.count()).select_from(WEB_TABLES['bootstrap'])).scalar_one() == 1
            assert conn.execute(select(func.count()).select_from(WEB_TABLES['user_audit'])).scalar_one() == 1
    finally:
        store.engine.dispose()


def test_failed_project_audit_cannot_leave_ownership_or_grant(accounts, monkeypatch):
    client, app, hub, _, _ = accounts
    login(client)
    auth = app.state.web_auth
    current = auth.session(client.cookies.get(COOKIE))
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic project audit failure')
    monkeypatch.setattr(hub.credentials, '_audit', fail)
    with pytest.raises(RuntimeError, match='synthetic project audit failure'):
        auth.users.create_project(current, 'rolled-back-library', hub.credentials)
    assert hub.credentials.owned_projects(OWNER) == ()
    assert auth.principal(current).projects == ('one',)
    from memory_hub.store import projects
    with hub.store.engine.connect() as conn:
        assert conn.execute(select(projects.c.id).where(projects.c.id == 'rolled-back-library')).scalar_one_or_none() is None


def test_maximum_unicode_password_can_actually_login(accounts):
    client, _, _, _, make = accounts
    login(client)
    password = '\u5bc6\u78bc' * 512
    response = post(client, 'create', {**fields(client, 'create'), 'username': 'unicode-password',
        'display_name': 'Human', 'password': password, 'role': 'member', 'projects': 'one'})
    assert response.status_code == 303
    other, _ = make()
    assert login(other, 'unicode-password', password).status_code == 303


def test_new_library_cannot_expand_identity_beyond_bounded_grants(accounts):
    client, app, hub, _, _ = accounts
    login(client)
    auth = app.state.web_auth
    current = auth.session(client.cookies.get(COOKIE))
    auth.users.create(current, 'many-projects', 'Admin', 'synthetic-member-password', 'admin', tuple('scope-' + str(n) for n in range(100)))
    identity = auth.users.authenticate('many-projects', 'synthetic-member-password')
    auth.start_session('many-session', 'csrf', '', identity)
    with pytest.raises(HubError) as caught:
        auth.users.create_project(auth.session('many-session'), 'over-limit', hub.credentials)
    assert caught.value.code == 'scope_limit'
    assert hub.credentials.owned_projects(identity.user_id) == ()


@pytest.mark.parametrize('field', ['after', 'user_id'])
def test_user_page_rejects_invalid_id_before_database(accounts, field):
    client, _, _, _, _ = accounts
    login(client)
    assert client.get('/ui/users', params={field: '\x00'}).status_code == 400
