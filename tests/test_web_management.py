import json
import re
from html import unescape
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from memory_hub.web import WebConfig, install_web
from memory_hub.web_password import hash_password
from memory_hub.store import Store, projects
from memory_hub.service import Hub
from memory_hub.models import Principal
from sqlalchemy import select

@pytest.fixture
def managed(tmp_path):
    store=Store('sqlite:///'+str(tmp_path/'management.db'),allow_sqlite=True)
    admin=Principal(worker_id='fixture-admin',projects=['visible','new','private'],role='admin')
    worker=Principal(worker_id='ai-a',projects=['visible'],role='worker')
    hub=Hub(store,principals=[admin,worker])
    for project in ['visible','private']:hub.call('create_project',{'project_id':project},admin)
    password_hash=hash_password('fixture-management-password')
    now=[1000]
    def client_for(role):
        app=FastAPI()
        install_web(app,hub,WebConfig('fixture',password_hash,('visible','new'),False,300,role),clock=lambda:now[0])
        client=TestClient(app)
        token=re.search('name="csrf" value="([^"]+)"',client.get('/login').text)[1]
        client.post('/login',data={'csrf':token,'username':'fixture','password':'fixture-management-password'})
        return client
    yield client_for,hub,admin,now
    store.engine.dispose()

def fields(client,action,url='/ui/manage?project=visible'):
    html=client.get(url).text
    body=re.search('<form method="post" action="/ui/action/'+action+'">(.*?)</form>',html,re.S)[1]
    return {name:unescape(value) for name,value in re.findall('<input type="hidden" name="([^"]+)" value="([^"]*)">',body)}

def submit(client,action,values):return client.post('/ui/action/'+action,data=values,follow_redirects=False)

def state(hub,p='visible'):
    with hub.store.engine.connect() as conn:return conn.execute(select(projects.c.state).where(projects.c.id==p)).scalar_one()

def source_form(client,source_id='guide'):
    return {**fields(client,'source'),'source_id':source_id,'uri':'repo://docs/guide','commit':'abc','content':'協作 memory searchable content'}

def task_form(client):
    return {**fields(client,'task'),'task_id':'task-a','goal':'Build memory hub','allowed_paths':'src/**\ntests/**','acceptance_criteria':'Tests pass','source_ids':'guide'}

def test_create_project_source_task_and_double_submission(managed):
    make,hub,_,_=managed; client=make('admin')
    values=fields(client,'project','/ui/manage?project=new')
    assert submit(client,'project',values).status_code==303
    assert state(hub,'new')['revision']==1
    values=source_form(client)
    assert submit(client,'source',values).status_code==303
    assert '操作成功' in client.get('/ui/manage?project=visible').text
    assert len(state(hub)['sources']['guide']['versions'])==1
    assert submit(client,'source',values).status_code==303
    assert '已送出或已過期' in client.get('/ui/manage?project=visible').text
    assert len(state(hub)['sources']['guide']['versions'])==1
    assert submit(client,'task',task_form(client)).status_code==303
    task=state(hub)['tasks']['task-a']
    assert task['allowed_paths']==['src/**','tests/**']
    assert 'task-a' in client.get('/ui/inbox?project=visible').text
    assert 'Build memory hub' in client.get('/ui/task?project=visible&task=task-a').text

def test_scope_role_csrf_and_unavailable_actions(managed):
    make,hub,_,_=managed; reader=make('read_only')
    assert reader.post('/ui/action/project',data={'project_id':'new','role':'admin'}).status_code==403
    assert '此帳號為唯讀' in reader.get('/ui/manage?project=visible').text
    for route in ['manage','search','task','inbox']:
        assert reader.get('/ui/'+route+'?project=private').status_code==403
    admin=make('admin')
    values=source_form(admin); values['csrf']='壞掉'
    assert submit(admin,'source',values).status_code==403
    assert not state(hub)['sources']
    values=source_form(admin); values['project_id']='private'
    assert submit(admin,'source',values).status_code==403
    assert admin.post('/ui/action/complete_task',data={}).status_code==404

def test_stale_source_update_and_import_validation(managed):
    make,hub,_,_=managed; client=make('admin')
    first=source_form(client); second=source_form(client)
    submit(client,'source',first)
    second['content']='must not replace newer snapshot'
    submit(client,'source',second)
    assert '未儲存' in client.get('/ui/manage?project=visible').text
    assert state(hub)['sources']['guide']['current']['content']!='must not replace newer snapshot'
    invalid={**fields(client,'import'),'sources_json':'not-json'}
    assert submit(client,'import',invalid).status_code==303
    assert '格式不正確' in client.get('/ui/manage?project=visible').text
    valid={**fields(client,'import'),'sources_json':json.dumps([{'source_id':'two','content':'batch imported','uri':'repo://two','commit':'abc'}])}
    submit(client,'import',valid)
    assert 'two' in state(hub)['sources']
    invalid_batch={**fields(client,'import'),'sources_json':json.dumps([{'source_id':'three','content':'valid','uri':'repo://three','commit':'abc'},{'source_id':'bad'}])}
    submit(client,'import',invalid_batch)
    assert 'three' not in state(hub)['sources']

def test_search_pagination_escaping(managed):
    make,hub,admin,_=managed; client=make('admin')
    for i in range(21):hub.call('register_source',{'project_id':'visible','source_id':f's{i:02d}','content':'memory <script>alert(1)</script>','uri':'repo://guide','commit':'abc'},admin)
    response=client.get('/ui/search?project=visible&q=memory')
    assert response.status_code==200 and '下一頁' in response.text
    assert '<script>' not in response.text
    assert '&lt;script&gt;' in response.text
    response=client.get('/ui/search?project=visible&q=memory&offset=20')
    assert '上一頁' in response.text and '下一頁' not in response.text
    assert '沒有符合' in client.get('/ui/search?project=visible&q=nomatch').text
    assert client.get('/ui/search?project=visible&q=memory&offset=oops').status_code==400

def test_recovery_cas_and_session_expiry(managed):
    make,hub,_,now=managed; client=make('admin')
    submit(client,'source',source_form(client));submit(client,'task',task_form(client))
    url='/ui/task?project=visible&task=task-a'
    one=fields(client,'recover',url);two=fields(client,'recover',url)
    one.update(reason='Review fixture recovery',to_worker='ai-a');two.update(reason='stale recovery',to_worker='')
    submit(client,'recover',one)
    assert state(hub)['tasks']['task-a']['pending_recipient']=='ai-a'
    submit(client,'recover',two)
    assert '未儲存' in client.get('/ui/manage?project=visible').text
    assert state(hub)['tasks']['task-a']['pending_recipient']=='ai-a'
    now[0]+=301
    assert client.get('/ui/manage',follow_redirects=False).headers['location']=='/login'

def test_web_role_config_validation():
    with pytest.raises(ValueError):WebConfig('user','hash',('project',),role='superuser')

def test_approve_proposal_and_stale_tab(managed):
    make,hub,admin,_=managed; client=make('admin')
    submit(client,'source',source_form(client));submit(client,'task',task_form(client))
    packet=hub.call('prepare_task',{'project_id':'visible','task_id':'task-a','workspace':'/fixture','branch':'fixture','commit':'abc'},admin)
    claim=hub.call('claim_task',{'project_id':'visible','task_id':'task-a'},admin)
    args={'project_id':'visible','packet_id':packet['packet_id']}
    source=hub.call('read_source',{**args,'source_id':'guide'},admin)
    hub.call('acknowledge_context',args,admin)
    args['fence']=claim['fence'];hub.call('accept_handoff',args,admin)
    proposal=hub.call('propose_memory_change',{**args,'text':'<b>Approve audited decision</b>','evidence':[{'source_id':'guide','sha256':source['sha256']}]},admin)
    one=fields(client,'approve');two=fields(client,'approve')
    assert '<b>Approve' not in client.get('/ui/manage?project=visible').text
    submit(client,'approve',one)
    assert state(hub)['decisions'][proposal['decision_id']]['status']=='approved'
    revision=state(hub)['revision']
    submit(client,'approve',two)
    assert '未儲存' in client.get('/ui/manage?project=visible').text
    assert state(hub)['revision']==revision

def test_task_list_cursor(managed):
    make,hub,admin,_=managed;client=make('admin')
    submit(client,'source',source_form(client))
    for i in range(21):
        hub.call('create_task',{'project_id':'visible','task_id':f'task-{i:02d}','goal':'Fixture task','allowed_paths':['src/**'],'acceptance_criteria':['tests'],'source_ids':['guide']},admin)
    response=client.get('/ui/manage?project=visible')
    assert '下一頁任務' in response.text and 'task-20' not in response.text
    response=client.get('/ui/manage?project=visible&after=task-19')
    assert 'task-20' in response.text and '下一頁任務' not in response.text

def test_integrated_app_cookie_isolation_and_management(monkeypatch,tmp_path):
    from memory_hub.app import create_app
    import secrets
    monkeypatch.setenv('HUB_WEB_USERNAME','fixture')
    monkeypatch.setenv('HUB_WEB_PASSWORD_HASH',hash_password('fixture-integration-password'))
    monkeypatch.setenv('HUB_WEB_PROJECTS','project')
    monkeypatch.setenv('HUB_WEB_ROLE','admin')
    monkeypatch.setenv('HUB_WEB_COOKIE_SECURE','false')
    token=secrets.token_urlsafe(32)
    app=create_app(database_url='sqlite:///'+str(tmp_path/'integrated.db'),allow_sqlite=True,auth_tokens=json.dumps({token:{'worker_id':'ai-a','projects':['project'],'role':'worker'}}))
    with TestClient(app) as client:
        csrf=re.search('name="csrf" value="([^"]+)"',client.get('/login').text)[1]
        client.post('/login',data={'csrf':csrf,'username':'fixture','password':'fixture-integration-password'})
        data=fields(client,'project','/ui/manage?project=project')
        assert submit(client,'project',data).status_code==303
        assert client.get('/ui/manage?project=project').status_code==200
        assert client.post('/mcp',json={}).status_code==401
        assert client.post('/v1/tools/create_project',json={'arguments':{'project_id':'project'}}).status_code==401
        assert client.post('/ui/action/unknown',data={}).status_code==401
        response=client.post('/ui/action/task',data={})
        assert response.status_code==403
        assert token not in client.get('/ui/manage?project=project').text
