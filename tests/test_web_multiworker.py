"""Shared-database auth tests; credentials are synthetic and ephemeral."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
import uuid
import re
import secrets
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select,func,create_engine,text
from sqlalchemy.engine import make_url
from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import Store,WEB_TABLES
from memory_hub.web import install_web,WebConfig,COOKIE,LOGIN_COOKIE
from memory_hub.web_auth import WebAuthStore
from memory_hub.web_password import hash_password

@pytest.fixture(params=['sqlite']+(['postgresql'] if os.environ.get('HUB_TEST_DATABASE_URL') else []))
def shared(tmp_path,request):
    cleanup_engine=None
    url='sqlite:///'+str(tmp_path/'shared-auth.db')
    if request.param=='postgresql':
        base=os.environ['HUB_TEST_DATABASE_URL']
        if not base.startswith('postgresql+psycopg://'): pytest.fail('Use disposable PostgreSQL database')
        cleanup_engine=create_engine(base)
        schema='web_auth_test_'+uuid.uuid4().hex
        with cleanup_engine.begin() as conn: conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        url=make_url(base).update_query_dict({'options':f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    stores=[];clients=[];now=[1000]
    config=WebConfig('fixture',hash_password('fixture-shared-password'),('one','two'),False,3600,'admin')
    def make(custom=None):
        store=Store(url,allow_sqlite=request.param=='sqlite');stores.append(store)
        hub=Hub(store,principals=[Principal(worker_id='ai-a',projects=['one','two'])])
        app=FastAPI();install_web(app,hub,custom or config,clock=lambda:now[0])
        client=TestClient(app);clients.append(client)
        return client,hub
    one,hub1=make();two,hub2=make()
    yield one,two,hub1,hub2,make,config,now
    for client in clients:client.close()
    for store in stores:store.engine.dispose()
    if cleanup_engine:
        with cleanup_engine.begin() as conn: conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        cleanup_engine.dispose()

def token(response):return re.search('name="csrf" value="([^"]+)"',response.text)[1]
def login(client,password='fixture-shared-password'):
    csrf=token(client.get('/login'))
    return client.post('/login',data={'csrf':csrf,'username':'fixture','password':password},follow_redirects=False)

def test_session_and_login_csrf_survive_instance_handoff_and_logout(shared):
    one,two,hub,_,_,_,_=shared
    csrf=token(one.get('/login'))
    two.cookies.update(one.cookies)
    response=two.post('/login',data={'csrf':csrf,'username':'fixture','password':'fixture-shared-password'},follow_redirects=False)
    assert response.status_code==303
    one.cookies.update(two.cookies)
    assert one.get('/ui').status_code==200
    raw_token=one.cookies.get(COOKIE)
    with hub.store.engine.connect() as conn:
        rows=conn.execute(select(WEB_TABLES['entries'])).mappings().all()
        stored=json.dumps([dict(row) for row in rows])
    assert raw_token not in stored and 'fixture-shared-password' not in stored
    csrf=token(one.get('/ui'))
    two.post('/logout',data={'csrf':csrf},follow_redirects=False)
    assert one.get('/ui',follow_redirects=False).headers['location']=='/login'

def test_shared_throttling_and_no_forwarded_ip_trust(shared):
    one,two,*_=shared
    for index in range(5):
        client=[one,two][index%2]
        response=login(client,password='incorrect')
        assert response.status_code==401
    csrf=token(two.get('/login'))
    response=two.post('/login',data={'csrf':csrf,'username':'fixture','password':'fixture-shared-password'},headers={'X-Forwarded-For':'8.8.8.8'},follow_redirects=False)
    assert response.status_code==429

def test_changed_role_scope_password_and_expiry_invalidate_session(shared):
    one,two,_,_,make,config,now=shared
    assert login(one).status_code==303
    for changed in [replace(config,role='read_only'),replace(config,projects=('one',)),replace(config,password_hash=hash_password('changed-fixture-password')),replace(config,username='renamed')]:
        other,_=make(changed);other.cookies.update(one.cookies)
        assert other.get('/ui',follow_redirects=False).headers['location']=='/login'
    restored,_=make(config)
    restored.cookies.update(one.cookies)
    assert restored.get('/ui',follow_redirects=False).headers['location']=='/login'
    assert login(restored).status_code==303
    now[0]+=3601
    assert restored.get('/ui',follow_redirects=False).headers['location']=='/login'

def test_cross_instance_nonce_and_flash_are_shared(shared):
    one,two,hub,_,_,_,_=shared
    login(one);two.cookies.update(one.cookies)
    html=one.get('/ui/manage?project=one').text
    form=re.search('<form method="post" action="/ui/action/project">(.*?)</form>',html,re.S)[1]
    values=dict(re.findall('<input type="hidden" name="([^"]+)" value="([^"]*)">',form))
    assert two.post('/ui/action/project',data=values,follow_redirects=False).status_code==303
    assert '操作成功' in one.get('/ui/manage?project=one').text
    assert one.post('/ui/action/project',data=values,follow_redirects=False).status_code==303
    assert '已送出或已過期' in two.get('/ui/manage?project=one').text

def test_atomic_parallel_throttle_and_nonce(shared):
    _,_,hub1,hub2,_,config,now=shared
    auths=[WebAuthStore(hub1.store,config,lambda:now[0]),WebAuthStore(hub2.store,config,lambda:now[0])]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda i:auths[i%2].allow_attempt('parallel-peer'),range(20)))
    assert sum(results)==5
    session_token=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(24)
    auths[0].start_session(session_token,'csrf','')
    current=auths[0].session(session_token)
    auths[0].start_nonce(nonce,current,'project','one')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda i:auths[i%2].consume_nonce(nonce,current,'project','one'),range(10)))
    assert sum(results)==1

def test_expired_nonce_and_bounded_entry_cleanup(shared):
    _,_,hub,_,_,config,now=shared
    auth=WebAuthStore(hub.store,config,lambda:now[0])
    raw=secrets.token_urlsafe(32);auth.start_session(raw,'csrf','');current=auth.session(raw)
    auth.start_nonce('nonce',current,'project','one')
    now[0]+=901
    assert not auth.consume_nonce('nonce',current,'project','one')
    with auth.transaction() as conn:
        for i in range(8):auth._put(conn,auth.key('bounded'+str(i)),'fixture',{},now[0]+50,cap=3)
        assert conn.execute(select(func.count()).select_from(auth.entries).where(auth.entries.c.kind=='fixture')).scalar_one()==3
    now[0]+=51
    with auth.transaction() as conn:
        assert conn.execute(select(func.count()).select_from(auth.entries).where(auth.entries.c.kind=='fixture')).scalar_one()==0
