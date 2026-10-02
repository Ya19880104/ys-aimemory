"""Shared rooms are explicit, scoped and independent of private/task authority."""
import base64
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text

from memory_hub.app import create_app
from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import HubError, Store, projects
from test_index import _migration_db


ADMIN = Principal(worker_id='operator', projects=['p', 'q'], role='admin')
A = Principal(worker_id='worker-a', projects=['p'])
B = Principal(worker_id='worker-b', projects=['p'])
Q = Principal(worker_id='worker-q', projects=['q'])
IDENTITIES = [ADMIN, A, B, Q]


@pytest.fixture
def collaboration(_migration_db):
    url, sqlite, _ = _migration_db
    hub = Hub(Store(url, allow_sqlite=sqlite), clock=lambda:1000.0, principals=IDENTITIES)
    for project in ('p', 'q'):
        hub.call('create_project', {'project_id':project}, ADMIN)
    return hub, url, sqlite


def room(hub, project='p', key=None):
    return hub.call('create_session', {'project_id':project, 'title':'Shared room',
                                     'idempotency_key':key or uuid.uuid4().hex}, ADMIN)


def human(role='member', projects=('p',), identity='worker-a'):
    from memory_hub.session_service import SessionActor
    return SessionActor(kind='human', id=identity, display_name='Human fixture', projects=projects, role=role)


def values(session, **kwargs):
    return {'project_id':session['project_id'], 'session_id':session['session_id'], **kwargs}


def post(hub, session, principal=A, **kwargs):
    return hub.call('post_session_message', values(session, **{'body':'Hello',
                    'idempotency_key':uuid.uuid4().hex, **kwargs}), principal)


def read(hub, session, principal=A, **kwargs):
    return hub.call('read_session', values(session, **kwargs), principal)


def reject(code, function):
    with pytest.raises(HubError) as caught:
        function()
    assert caught.value.code == code


def test_human_and_two_workers_share_room_without_changing_old_private_visibility(collaboration):
    hub, _, _ = collaboration
    session = room(hub)
    assert session['visibility']=='project_shared' and session['status']=='open'
    one = post(hub, session)
    two = post(hub, session, B, reply_to_message_id=one['message_id'])
    three = hub.sessions.call('post_session_message', values(session, body='Human joins',
                              idempotency_key='human-one'), human())
    assert 'body' not in one
    timeline = read(hub, session, ADMIN, full_text=True)['items']
    messages = [event for event in timeline if event['type']=='message']
    assert [event['actor']['kind'] for event in messages]==['worker','worker','human']
    assert [event['actor']['id'] for event in messages]==['worker-a','worker-b','worker-a']
    assert [event['message_id'] for event in messages]==[one['message_id'],two['message_id'],three['message_id']]
    assert messages[-1]['body']=='Human joins'
    private = hub.call('send_message', {'project_id':'p','recipient_worker_id':B.worker_id,
        'thread_id':session['session_id'],'body':'old private secret','idempotency_key':'old'}, A)
    assert hub.call('list_messages', {'project_id':'p'}, ADMIN)['items']==[]
    assert 'old private secret' not in json.dumps(read(hub, session, ADMIN, full_text=True))
    assert hub.call('list_messages', {'project_id':'p'}, B)['items']==[private]


def test_discovery_is_scoped_and_has_no_global_active_room(collaboration):
    hub, _, _ = collaboration
    first, second, hidden = room(hub), room(hub), room(hub, 'q')
    found = hub.call('list_sessions', {'limit':1}, A)
    assert len(found['items'])==1 and found['has_more']
    rest = hub.call('list_sessions', {'after_id':found['next_after_id'],'limit':1}, A)
    assert {found['items'][0]['session_id'],rest['items'][0]['session_id']}=={first['session_id'],second['session_id']}
    assert not rest['has_more']
    assert all('body' not in item for item in found['items'])
    post(hub, first, body='first-room')
    post(hub, second, body='second-room')
    assert 'second-room' not in json.dumps(read(hub, first, full_text=True))
    reject('forbidden', lambda: read(hub, hidden))
    reject('not_found', lambda: hub.call('read_session', values(first, session_id=hidden['session_id']), A))
    assert hub.sessions.call('list_sessions', {}, human(projects=()))['items']==[]


def test_readonly_and_admin_roles_are_enforced_by_service(collaboration):
    hub, _, _ = collaboration
    session = room(hub)
    reader = human('read_only')
    assert hub.sessions.call('read_session', values(session), reader)['session']['session_id']==session['session_id']
    reject('forbidden', lambda: hub.sessions.call('post_session_message', values(session, body='No',idempotency_key='x'), reader))
    reject('forbidden', lambda: hub.call('create_session', {'project_id':'p','title':'No','idempotency_key':'x'}, A))
    reject('forbidden', lambda: hub.call('archive_session', values(session, archived=True,expected_version=1,idempotency_key='x'), A))
    with pytest.raises(ValidationError):
        post(hub, session, sender={'kind':'human','id':'operator'})


@pytest.mark.parametrize('changes', [{'body':''},{'body':' \t\n'}, {'body':'x\x00y'}, {'body':'字'*2667},
    {'idempotency_key':'bad\x00key'}, {'reply_to_message_id':'bad\x00id'}, {'attachment_ids':['../bad'] }])
def test_invalid_message_does_not_append_event(collaboration, changes):
    hub, _, _ = collaboration
    session = room(hub)
    before = read(hub, session)
    with pytest.raises(ValidationError):
        post(hub, session, **changes)
    assert read(hub, session)==before


def test_reply_and_attachment_references_cannot_cross_rooms(collaboration):
    hub, _, _ = collaboration
    first, other = room(hub), room(hub)
    original = post(hub, other)
    attachment = hub.call('upload_session_attachment', values(other, filename='a.txt',content_base64='YQ==',idempotency_key='a'), A)
    reject('not_found', lambda: post(hub, first, reply_to_message_id=original['message_id']))
    reject('not_found', lambda: post(hub, first, attachment_ids=[attachment['attachment_id']]))


def test_incremental_compact_full_reads_and_byte_budget_never_skip(collaboration):
    hub, _, _ = collaboration
    session = room(hub)
    sent = [post(hub, session, body=('字'*2600)+str(i)) for i in range(5)]
    compact = read(hub, session, after_sequence=session['latest_sequence'], limit=2)
    assert compact['has_more'] and len(compact['items'])==2
    assert all(event['body_truncated'] and len(event['body'].encode())<=512 for event in compact['items'])
    assert compact['next_after_sequence']==sent[1]['sequence']
    assert compact['returned_bytes']<=16384
    full = read(hub, session, after_sequence=sent[0]['sequence']-1, limit=1, full_text=True,max_bytes=65536)
    assert full['items'][0]['body']=='字'*2600+'0' and not full['items'][0]['body_truncated']
    budgeted = read(hub, session, after_sequence=session['latest_sequence'],full_text=True,max_bytes=16384)
    assert 1<=len(budgeted['items'])<5 and budgeted['has_more']
    assert budgeted['next_after_sequence']==budgeted['items'][-1]['sequence']
    empty = read(hub, session, after_sequence=sent[-1]['sequence'])
    assert empty['items']==[] and empty['next_after_sequence']==sent[-1]['sequence'] and not empty['has_more']


def test_same_key_namespace_separates_actor_kind_room_and_operation(collaboration):
    hub, _, _ = collaboration
    first, second = room(hub), room(hub)
    args = values(first, body='Exact ', idempotency_key='same')
    one = hub.call('post_session_message', args, A)
    assert hub.call('post_session_message', args, A)==one
    reject('idempotency_conflict', lambda: hub.call('post_session_message', {**args,'body':'Exact'}, A))
    human_result = hub.sessions.call('post_session_message', args, human())
    other = hub.call('post_session_message', {**args,'session_id':second['session_id']}, A)
    assert len({one['message_id'],human_result['message_id'],other['message_id']})==3


def test_archive_reopen_uses_cas_and_preserves_replay(collaboration):
    hub, _, _ = collaboration
    session = room(hub)
    args = values(session, body='Saved',idempotency_key='saved')
    saved = hub.call('post_session_message', args, A)
    closed = hub.call('archive_session', values(session,archived=True,expected_version=1,idempotency_key='close'), ADMIN)
    assert closed['status']=='archived' and closed['version']==2
    assert hub.call('post_session_message', args, A)==saved
    reject('session_archived', lambda: post(hub, session))
    reject('stale_session', lambda: hub.call('archive_session',values(session,archived=False,expected_version=1,idempotency_key='stale'),ADMIN))
    reopened = hub.call('archive_session',values(session,archived=False,expected_version=2,idempotency_key='open'),ADMIN)
    assert reopened['status']=='open' and reopened['version']==3
    assert post(hub,session)['sequence']>closed['latest_sequence']


def artifact_args(session, message, **changes):
    return values(session,**{'kind':'summary','title':'Reviewed summary','content':'Summary body 中文',
        'covered_through_sequence':message['sequence'],'reference_message_ids':[message['message_id']],
        'idempotency_key':'summary',**changes})


def test_immutable_summary_references_watermark_and_explicit_artifact_chunks(collaboration):
    hub, _, _ = collaboration
    session = room(hub)
    msg = post(hub,session)
    args = artifact_args(session,msg)
    artifact = hub.call('create_session_artifact',args,A)
    assert artifact['covered_through_sequence']==msg['sequence'] and 'content' not in artifact
    assert hub.call('create_session_artifact',args,A)==artifact
    reject('idempotency_conflict', lambda: hub.call('create_session_artifact',{**args,'content':'Rewritten'},A))
    post(hub,session,body='Later message')
    summary = hub.call('list_sessions',{},B)['items'][0]['latest_summary']
    assert summary['artifact_id']==artifact['artifact_id'] and summary['covered_through_sequence']==msg['sequence']
    assert 'content' not in summary
    chunks=[]; offset=0
    while True:
        page=hub.call('get_session_artifact',values(session,artifact_id=artifact['artifact_id'],offset=offset,limit_chars=3),B)
        chunks.append(page['content'])
        if not page['has_more']: break
        assert page['next_offset']>offset
        offset=page['next_offset']
    assert ''.join(chunks)==args['content']
    assert page['content_bytes']==len(args['content'].encode()) and page['content_chars']==len(args['content'])
    with hub.store.engine.connect() as conn:
        audit=hub.store.read_audit(conn,'p')
    assert args['content'] not in json.dumps(audit)


def test_summary_cannot_claim_future_or_reference_uncovered_or_other_room(collaboration):
    hub, _, _ = collaboration
    session,other=room(hub),room(hub)
    msg=post(hub,session); foreign=post(hub,other)
    args=artifact_args(session,msg)
    reject('invalid_coverage',lambda:hub.call('create_session_artifact',{**args,'covered_through_sequence':msg['sequence']+100},A))
    reject('not_found',lambda:hub.call('create_session_artifact',{**args,'reference_message_ids':[foreign['message_id']]},A))
    reject('invalid_coverage',lambda:hub.call('create_session_artifact',{**args,'covered_through_sequence':0},A))


def test_search_returns_only_scoped_snippets_and_reference_ids(collaboration):
    hub,_,_=collaboration
    session,hidden=room(hub),room(hub,'q')
    msg=post(hub,session,body='needle '+'x'*2000)
    post(hub,hidden,ADMIN,body='needle hidden project')
    result=hub.call('search_sessions',{'project_id':'p','query':'needle','limit':1},A)
    assert len(result['items'])==1
    found=result['items'][0]
    assert found['message_id']==msg['message_id'] and found['session_id']==session['session_id']
    assert len(found['snippet'].encode())<=512 and 'body' not in found
    reject('forbidden',lambda:hub.call('search_sessions',{'project_id':'q','query':'needle'},A))


def test_response_byte_budget_counts_metadata_and_cursor_without_skipping(collaboration):
    hub,_,_=collaboration
    session=room(hub)
    messages=[post(hub,session,body='needle '+('字'*1500)) for _ in range(6)]
    from memory_hub.session_service import compact
    for name,args in [('read_session',values(session,after_sequence=session['latest_sequence'])),
                      ('search_sessions',{'project_id':'p','query':'needle'})]:
        page=hub.call(name,{**args,'max_bytes':2048},A)
        assert len(compact(page))==page['returned_bytes']<=2048
        assert page['has_more'] and page['items']
        assert page['next_after_sequence']==page['items'][-1]['sequence']
        next_page=hub.call(name,{**args,'after_sequence':page['next_after_sequence'],'max_bytes':2048},A)
        assert next_page['items'][0]['sequence']>page['items'][-1]['sequence']
    reject('response_budget_too_small',lambda:read(hub,session,after_sequence=messages[0]['sequence']-1,
            full_text=True,max_bytes=2048,limit=1))


def test_list_budget_and_summary_metadata_do_not_expand_reference_history(collaboration):
    hub,_,_=collaboration
    for _ in range(5):
        session=room(hub)
        msg=post(hub,session)
        hub.call('create_session_artifact',artifact_args(session,msg),A)
    from memory_hub.session_service import compact
    page=hub.call('list_sessions',{'max_bytes':2048},A)
    assert page['has_more'] and len(page['items'])<5
    assert len(compact(page))==page['returned_bytes']<=2048
    for item in page['items']:
        assert item['latest_summary']['reference_count']==1
        assert 'reference_message_ids' not in item['latest_summary']
    rest=hub.call('list_sessions',{'after_id':page['next_after_id']},A)
    assert len(rest['items'])+len(page['items'])==5


def test_attachment_exact_limit_hash_chunks_and_public_upload_event(collaboration):
    hub,_,_=collaboration
    session=room(hub)
    data=bytes(range(256))*2048
    args=values(session,filename='sample.bin',content_base64=base64.b64encode(data).decode(),idempotency_key='file')
    attachment=hub.call('upload_session_attachment',args,A)
    assert attachment['size']==524288 and attachment['sha256']==hashlib.sha256(data).hexdigest()
    assert 'content_base64' not in attachment and hub.call('upload_session_attachment',args,A)==attachment
    received=bytearray(); offset=0
    while True:
        chunk=hub.call('read_session_attachment',values(session,attachment_id=attachment['attachment_id'],offset=offset),B)
        received.extend(base64.b64decode(chunk['content_base64']))
        if not chunk['has_more']: break
        assert chunk['next_offset']>offset
        offset=chunk['next_offset']
    assert received==data
    assert any(event['type']=='attachment' for event in read(hub,session,ADMIN)['items'])
    for change in ({'filename':'../secret.txt'},{'filename':'bad\x00file'},{'content_base64':'not-base64!'},
                   {'content_base64':base64.b64encode(data+b'x').decode()}):
        with pytest.raises((ValidationError,HubError)):
            hub.call('upload_session_attachment',{**args,**change,'idempotency_key':uuid.uuid4().hex},A)


def test_attachment_quota_is_atomic_and_duplicate_does_not_charge_twice(collaboration):
    hub,_,_=collaboration
    session=room(hub)
    args=values(session,filename='bounded.bin',content_base64=base64.b64encode(b'x'*524288).decode(),idempotency_key='0')
    for index in range(50):
        hub.call('upload_session_attachment',{**args,'idempotency_key':str(index)},A)
    assert hub.call('upload_session_attachment',args,A)['size']==524288
    reject('session_quota',lambda:hub.call('upload_session_attachment',{**args,'idempotency_key':'overflow'},A))
    assert read(hub,session)['session']['attachment_bytes']==25*1024*1024


def test_audit_failure_rolls_back_event_quota_and_idempotency(collaboration,monkeypatch):
    hub,_,_=collaboration
    session=room(hub)
    before=read(hub,session)
    original=hub.store.audit
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('synthetic rollback')
    args=values(session,filename='small.txt',content_base64='YQ==',idempotency_key='retry')
    with monkeypatch.context() as patch:
        patch.setattr(hub.store,'audit',fail)
        with pytest.raises(RuntimeError):hub.call('upload_session_attachment',args,A)
    assert read(hub,session)==before
    assert hub.call('upload_session_attachment',args,A)['size']==1


def test_concurrent_instances_dedupe_and_committed_cursor_order(collaboration):
    hub,url,sqlite=collaboration
    session=room(hub)
    other=Hub(Store(url,allow_sqlite=sqlite),clock=hub.clock,principals=IDENTITIES)
    args=values(session,body='concurrent',idempotency_key='race')
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda n:(hub if n%2 else other).call('post_session_message',args,A),range(8)))
    assert len({row['message_id'] for row in results})==1
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda n:post(hub if n%2 else other,session,body=str(n)),range(12)))
    events=read(other,session,full_text=True)['items']
    sequences=[event['sequence'] for event in events]
    assert sequences==sorted(set(sequences)) and len(events)==14
    assert {row['message_id'] for row in results}<= {row.get('message_id') for row in events}


def test_sessions_leave_task_state_and_knowledge_revision_unchanged(collaboration):
    hub,_,_=collaboration
    with hub.store.engine.connect() as conn:
        before=conn.execute(select(projects.c.state).where(projects.c.id=='p')).scalar_one()
    session=room(hub); post(hub,session)
    with hub.store.engine.connect() as conn:
        after=conn.execute(select(projects.c.state).where(projects.c.id=='p')).scalar_one()
    assert {k:v for k,v in after.items() if k!='sequence'}=={k:v for k,v in before.items() if k!='sequence'}


def test_v5_additive_migration_preserves_private_messages_and_credentials(collaboration):
    hub,url,sqlite=collaboration
    from memory_hub.store import SESSION_TABLES
    private=hub.call('send_message',{'project_id':'p','recipient_worker_id':B.worker_id,
        'thread_id':'original','body':'Private remains private','idempotency_key':'v4'},A)
    issued=hub.credentials.issue('p','migration-worker','operator',10.0)
    with hub.store.engine.begin() as conn:
        before=conn.execute(select(projects.c.state).where(projects.c.id=='p')).scalar_one()
        for name in ('requests','attachments','artifacts','events','sessions'):
            SESSION_TABLES[name].drop(conn)
        conn.execute(hub.store.index.migrations.delete().where(hub.store.index.migrations.c.version==5))
    def start(_):
        upgraded=Hub(Store(url,allow_sqlite=sqlite),principals=IDENTITIES)
        assert upgraded.credentials.authenticate(issued['token']).worker_id=='migration-worker'
        assert upgraded.call('list_messages',{'project_id':'p'},B)['items']==[private]
        assert upgraded.call('list_sessions',{},ADMIN)['items']==[]
        with upgraded.store.engine.connect() as conn:
            assert conn.execute(select(projects.c.state).where(projects.c.id=='p')).scalar_one()==before
            assert conn.execute(select(upgraded.store.index.migrations.c.version).order_by(
                upgraded.store.index.migrations.c.version)).scalars().all()==[1,2,3,4,5]
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(start,range(3)))


def test_attachment_and_archive_concurrency_do_not_overrun_quota_or_version(collaboration):
    hub,url,sqlite=collaboration
    session=room(hub)
    other=Hub(Store(url,allow_sqlite=sqlite),principals=IDENTITIES)
    # Fill the quota to one byte below capacity through the same serialized store
    # boundary; the existing exact-limit test verifies the complete real upload path.
    from memory_hub.store import SESSION_TABLES
    table=SESSION_TABLES['sessions']
    with hub.store.transaction('p',initialize_index=False) as (_,conn):
        conn.execute(table.update().where(table.c.session_id==session['session_id']).values(attachment_bytes=26214399))
    def upload(number):
        try:
            return (hub if number%2 else other).call('upload_session_attachment',values(session,
                filename='x.txt',content_base64='YQ==',idempotency_key=str(number)),A)
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        outcomes=list(pool.map(upload,range(2)))
    assert sum(isinstance(item,dict) for item in outcomes)==1 and 'session_quota' in outcomes
    def archive(number):
        try:
            return (hub if number%2 else other).call('archive_session',values(session,
                archived=True,expected_version=1,idempotency_key=str(number)),ADMIN)
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        outcomes=list(pool.map(archive,range(2)))
    assert sum(isinstance(item,dict) for item in outcomes)==1 and 'stale_session' in outcomes


def test_session_tools_use_real_mcp_principal_and_expose_typed_schema(collaboration,monkeypatch):
    hub,url,sqlite=collaboration
    session=room(hub)
    token='session-test-worker-token-12345678'
    app=create_app(database_url=url,allow_sqlite=sqlite,auth_tokens=json.dumps({token:A.model_dump()}))
    with TestClient(app) as client:
        headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream'}
        listed=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}}).json()['result']['tools']
        tools={item['name']:item for item in listed}
        assert 'post_session_message' in tools and 'send_message' in tools
        assert 'body' in json.dumps(tools['post_session_message']['inputSchema'])
        assert len(tools)==38
        mcp_result=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/call',
            'params':{'name':'post_session_message','arguments':{'arguments':values(session,
                body='Actual MCP call',idempotency_key='mcp')}}}).json()['result']
        assert not mcp_result.get('isError')
        mcp_receipt=mcp_result.get('structuredContent') or json.loads(mcp_result['content'][0]['text'])
        assert mcp_receipt['actor']=={'kind':'worker','id':'worker-a','display_name':'worker-a'}
        result=client.post('/v1/tools/post_session_message',headers=headers,json={'arguments':values(session,body='MCP identity',idempotency_key='http')})
        assert result.status_code==200 and result.json()['actor']=={'kind':'worker','id':'worker-a','display_name':'worker-a'}
        assert client.post('/v1/tools/post_session_message',json={'arguments':values(session,body='bad',idempotency_key='bad')}).status_code==401
