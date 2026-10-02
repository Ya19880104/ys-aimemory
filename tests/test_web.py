import re
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from memory_hub.web import WebConfig, install_web
from memory_hub.web_password import hash_password, verify_password
from memory_hub.store import Store
from memory_hub.service import Hub
from memory_hub.models import Principal

@pytest.fixture(scope='module')
def password_hash(): return hash_password('fixture-only-password')

@pytest.fixture
def setup(tmp_path,password_hash):
    store=Store('sqlite:///'+str(tmp_path/'web.db'),allow_sqlite=True)
    principal=Principal(worker_id='fixture-worker',projects=['visible','private'],role='admin')
    hub=Hub(store,principals=[principal])
    for p in principal.projects: hub.call('create_project',{'project_id':p},principal)
    hub.call('register_source',{'project_id':'visible','source_id':'guide','content':'<script>alert("bad")</script>','uri':'repo://guide','commit':'abc'},principal)
    now=[1000]
    config=WebConfig('fixture-user',password_hash,('visible',),False,300)
    app=FastAPI()
    install_web(app,hub,config,clock=lambda:now[0])
    with TestClient(app) as client: yield client,now
    store.engine.dispose()

def csrf(response):
    return re.search('name="csrf" value="([^"]+)"',response.text)[1]

def login(client,password='fixture-only-password',username='fixture-user'):
    response=client.get('/login')
    return client.post('/login',data={'csrf':csrf(response),'username':username,'password':password},follow_redirects=False)

def test_password_hash(password_hash):
    assert verify_password('fixture-only-password',password_hash)
    assert not verify_password('incorrect',password_hash)
    assert not verify_password('fixture-only-password','bad')
    with pytest.raises(ValueError): hash_password('short')
    with pytest.raises(ValueError): hash_password('x' * 1025)

def test_login_and_scope_and_xss(setup):
    client,_=setup
    assert client.get('/ui',follow_redirects=False).headers['location']=='/login'
    response=login(client)
    assert response.status_code==303
    assert response.headers['location'] == '/ui/chat'
    assert client.get('/', follow_redirects=False).headers['location'] == '/ui/chat'
    assert client.get('/login', follow_redirects=False).headers['location'] == '/ui/chat'
    cookie=response.headers.get_list('set-cookie')[0]
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Max-Age=300' in cookie
    response=client.get('/ui')
    assert response.status_code==200
    assert 'visible' in response.text and 'private' not in response.text
    assert '<script>' not in response.text and '&lt;script&gt;' in response.text
    assert 'fixture-only-password' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/ui?project=private').status_code==404
    assert client.get('/ui?project=absent').status_code==404

def test_login_csrf_and_throttle(setup):
    client,_=setup
    assert client.post('/login',data={'username':'fixture-user','password':'fixture-only-password','csrf':'無效'}).status_code==403
    for _ in range(5): assert login(client,password='wrong').status_code==401
    assert login(client).status_code==429


def test_dashboard_has_one_project_scoped_sidebar(setup):
    client, _ = setup
    login(client)
    html = client.get('/ui?project=visible').text
    sidebar, main = html.split('</aside>', 1)
    for path in ['/ui/chat', '/ui/manage', '/ui/search', '/ui/inbox']:
        href = 'href="' + path + '?project=visible"'
        assert sidebar.count(href) == 1
        assert href not in main
    assert 'href="/help"' in sidebar
    assert 'href="/ui/account/password"' in sidebar
    assert '目前專案 <strong>visible</strong>' in main
    assert '共享 Chat' not in html

def test_logout_and_expiry(setup):
    client,now=setup
    login(client)
    assert client.post('/logout',data={'csrf':'bad'}).status_code==403
    token=csrf(client.get('/ui'))
    response=client.post('/logout',data={'csrf':token},follow_redirects=False)
    assert response.status_code==303
    assert client.get('/ui',follow_redirects=False).status_code==303
    login(client)
    now[0]+=301
    assert client.get('/ui',follow_redirects=False).headers['location']=='/login'

def test_no_config_and_secure_default(monkeypatch,password_hash):
    for key in ['HUB_WEB_USERNAME','HUB_WEB_PASSWORD_HASH','HUB_WEB_PROJECTS']: monkeypatch.delenv(key,raising=False)
    assert WebConfig.from_env() is None
    monkeypatch.setenv('HUB_WEB_USERNAME','operator')
    with pytest.raises(RuntimeError): WebConfig.from_env()
    monkeypatch.setenv('HUB_WEB_PASSWORD_HASH',password_hash)
    monkeypatch.setenv('HUB_WEB_PROJECTS','one,two')
    assert WebConfig.from_env().secure
    monkeypatch.setenv('HUB_WEB_PROJECTS','*')
    with pytest.raises(RuntimeError): WebConfig.from_env()

def test_get_logout_does_not_logout(setup):
    client,_=setup
    login(client)
    assert client.get('/logout').status_code==405
    assert client.get('/ui').status_code==200
