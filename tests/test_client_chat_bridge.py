import asyncio
import json
import pytest
from memory_hub.client_chat_bridge import RoomGate, ScopeError, result, chat_status
from mcp import types


def test_status_missing_binding_is_inactive_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr('memory_hub.client_chat_bridge.httpx.Client',
                        lambda **kwargs: pytest.fail('Missing binding reached transport'))
    with pytest.raises(ScopeError, match='^chat_not_active$'):
        chat_status(tmp_path, {}, None)
    assert not (tmp_path/'chat-binding.json').exists()


def test_status_malformed_binding_is_not_reported_as_inactive(tmp_path, monkeypatch):
    (tmp_path/'chat-binding.json').write_text('{broken')
    monkeypatch.setattr('memory_hub.client_chat_bridge.httpx.Client',
                        lambda **kwargs: pytest.fail('Malformed JSON reached transport'))
    with pytest.raises(json.JSONDecodeError):
        chat_status(tmp_path, {}, None)


@pytest.mark.parametrize('inactive', [False, True])
def test_status_retains_authenticated_identity_and_active_semantics(joined, monkeypatch, inactive):
    import httpx
    from types import SimpleNamespace
    import memory_hub.client_chat_bridge as module
    gate,config,_=joined
    if inactive:
        config['expires_at']=0
        (gate.directory/'chat-binding.json').write_text(json.dumps(config))
    calls=[]
    def handle(request):
        calls.append(request)
        assert request.url.path=='/v1/tools/get_worker_inbox'
        assert json.loads(request.content)=={'arguments':{'project_id':'p'}}
        assert request.headers['Authorization']=='Bearer synthetic-status-token'
        return httpx.Response(200,json={'worker_id':'own'})
    real_client=httpx.Client
    monkeypatch.setattr(module.httpx,'Client',lambda **kwargs:real_client(
        **kwargs,transport=httpx.MockTransport(handle)))
    monkeypatch.setenv('YS_AIMEMORY_TOKEN','synthetic-status-token')
    observed=chat_status(gate.directory,{'endpoint':'https://hub.test/mcp'},
        SimpleNamespace(verified_context=lambda _:True),clock=lambda:100).structuredContent
    assert observed=={'worker_id':'own','project_id':'p','session_id':'room','active':not inactive}
    assert len(calls)==1


@pytest.fixture
def joined(tmp_path):
    config = {'native_session_id':'native','expires_at':1000,'project_id':'p','session_id':'room','worker_id':'own','idempotency_key':'join'}
    delivery = {'delivery_id':'d','lease_id':'lease','lease_until':500,'after_sequence':10,
        'through_sequence':12,'reply_idempotency_key':'once','join_key':'join'}
    (tmp_path/'chat-binding.json').write_text(json.dumps(config))
    (tmp_path/'chat-delivery.json').write_text(json.dumps(delivery))
    return RoomGate(tmp_path,clock=lambda:100), config, delivery


def complete_read(delivery):
    return result({'session':{'project_id':'p','session_id':'room'},'items':[{'type':'message','body':'Full text'}],
        'next_after_sequence':delivery['through_sequence'],'delivery_receipt':{'delivery_id':delivery['delivery_id'],
        'status':'tool_read','unread_message_ids':[]}})


def silent_result(delivery):
    return result({'project_id':'p','session_id':'room','worker_id':'own','delivery_receipt':{
        'delivery_id':delivery['delivery_id'],'status':'no_reply','processed_sequence':delivery['through_sequence']}})


def test_no_reply_forwards_only_after_full_read_and_is_not_a_post(joined):
    gate, config, delivery = joined; calls=[]
    async def upstream(name, wire):
        calls.append((name,wire))
        if name=='read_session':return complete_read(delivery)
        assert name=='complete_session_delivery'
        assert wire=={'arguments':{'project_id':'p','session_id':'room','delivery_id':'d','lease_id':'lease','idempotency_key':'once'}}
        return silent_result(delivery)
    with pytest.raises(ScopeError,match='read_entire_delivery_first'):asyncio.run(gate.call('chat_no_reply',{},upstream))
    asyncio.run(gate.call('chat_read',{},upstream))
    completed=asyncio.run(gate.call('chat_no_reply',{},upstream))
    assert asyncio.run(gate.call('chat_no_reply',{},upstream)) is completed
    assert completed.structuredContent['delivery_receipt']['status']=='no_reply'
    with pytest.raises(ScopeError,match='already_completed'):asyncio.run(gate.call('chat_reply',{'body':'ack'},upstream))
    assert len(calls)==2


@pytest.mark.parametrize('ambiguous', [False,True])
def test_no_reply_intent_survives_error_and_restart_without_disposition_fallback(joined,ambiguous):
    gate, _, delivery=joined; calls=[]
    async def fail(name,wire):
        calls.append((name,wire))
        if name=='read_session':return complete_read(delivery)
        assert name=='complete_session_delivery'
        if ambiguous:raise TimeoutError('committed response lost')
        return types.CallToolResult(isError=True,content=[])
    asyncio.run(gate.call('chat_read',{},fail))
    with pytest.raises((ScopeError,TimeoutError)):asyncio.run(gate.call('chat_no_reply',{},fail))
    raw=next(gate.directory.glob('chat-completion-intent-*.json')).read_text()
    assert 'body' not in json.loads(raw) and json.loads(raw)['disposition']=='no_reply'
    restarted=RoomGate(gate.directory,clock=lambda:100)
    with pytest.raises(ScopeError,match='already_completed'):asyncio.run(restarted.call('chat_reply',{'body':'fallback'},fail))
    async def retry(name,wire):
        assert name=='complete_session_delivery';calls.append((name,wire));return silent_result(delivery)
    assert asyncio.run(restarted.call('chat_no_reply',{},retry)).structuredContent['delivery_receipt']['status']=='no_reply'
    assert calls[1]==calls[2]  # Same completion intent and stable upstream arguments.


def test_ambiguous_reply_intent_blocks_no_reply_and_changed_body_across_restart(joined):
    gate,_,delivery=joined; calls=[]; body='Private generated reply'
    async def upstream(name,wire):
        calls.append((name,wire))
        if name=='read_session':return complete_read(delivery)
        raise TimeoutError('unknown post')
    asyncio.run(gate.call('chat_read',{},upstream))
    with pytest.raises(TimeoutError):asyncio.run(gate.call('chat_reply',{'body':body},upstream))
    assert body not in next(gate.directory.glob('chat-completion-intent-*.json')).read_text()
    restarted=RoomGate(gate.directory,clock=lambda:100)
    with pytest.raises(ScopeError,match='already_completed'):asyncio.run(restarted.call('chat_no_reply',{},upstream))
    with pytest.raises(ScopeError,match='intent_changed'):asyncio.run(restarted.call('chat_reply',{'body':'changed'},upstream))
    with pytest.raises(TimeoutError):asyncio.run(restarted.call('chat_reply',{'body':body},upstream))
    assert calls[1]==calls[2]


def test_persisted_intent_never_authorizes_a_new_lease(joined):
    gate,config,delivery=joined
    async def upstream(name,wire):
        if name=='read_session':return complete_read(delivery)
        raise TimeoutError('unknown completion')
    asyncio.run(gate.call('chat_read',{},upstream))
    with pytest.raises(TimeoutError):asyncio.run(gate.call('chat_no_reply',{},upstream))
    delivery['lease_id']='new-lease'
    (gate.directory/'chat-delivery.json').write_text(json.dumps(delivery))
    with pytest.raises(ScopeError,match='read_entire_delivery_first'):
        asyncio.run(RoomGate(gate.directory,clock=lambda:100).call('chat_no_reply',{},upstream))


def test_scoped_tools_cannot_choose_room_cursor_tool_or_write_key(joined):
    gate, _, _ = joined
    async def forbidden(*args):
        pytest.fail('invalid argument reached upstream')
    for name,args in [('memory_call',{'name':'create_task'}),('chat_read',{'session_id':'other'}),
                      ('chat_read',{'after_sequence':0}),('chat_reply',{'body':'hi','idempotency_key':'other'}),
                      ('chat_reply',{'body':'not read yet'})]:
        with pytest.raises(ScopeError):
            asyncio.run(gate.call(name,args,forbidden))


def test_full_pages_are_required_and_scope_is_server_injected(joined):
    gate, config, delivery = joined
    calls=[]
    async def upstream(name,wire):
        calls.append((name,wire))
        args=wire['arguments']
        assert args['project_id']=='p' and args['session_id']=='room'
        assert args['delivery_id']=='d' and args['lease_id']=='lease'
        if name=='read_session':
            after=args['after_sequence']
            assert after in (10,11) and args['max_bytes']==16384 and args['full_text'] is True
            return result({'session':{'project_id':'p','session_id':'room'},'items':[{'type':'message','body':'test'}],
                'next_after_sequence':after+1,'delivery_receipt':{'delivery_id':'d',
                'status':'tool_read' if after==11 else 'partial_tool_read','unread_message_ids':[] if after==11 else ['m']}})
        assert args['idempotency_key']=='once'
        return result({'project_id':'p','session_id':'room','message_id':'m','actor':{'kind':'worker','id':'own'},
            'delivery_receipt':{'delivery_id':'d','status':'replied'}})
    first=asyncio.run(gate.call('chat_read',{},upstream))
    assert first.structuredContent['ready_to_reply'] is False
    with pytest.raises(ScopeError,match='read_entire_delivery_first'):
        asyncio.run(gate.call('chat_reply',{'body':'early'},upstream))
    second=asyncio.run(gate.call('chat_read',{},upstream))
    assert second.structuredContent['ready_to_reply'] is True
    posted=asyncio.run(gate.call('chat_reply',{'body':'one reply'},upstream))
    assert asyncio.run(gate.call('chat_reply',{'body':'one reply'},upstream)) is posted
    with pytest.raises(ScopeError,match='reply_already_committed'):
        asyncio.run(gate.call('chat_reply',{'body':'another reply'},upstream))
    assert len(calls)==3


@pytest.mark.parametrize('change',['stop','expired','unbound','wrong_join','stale_lease'])
def test_local_stop_and_binding_fences_prevent_forwarding(joined,change):
    gate,config,delivery=joined
    if change=='stop':(gate.directory/'STOP').touch()
    if change=='expired':config['expires_at']=99
    if change=='unbound':config['native_session_id']=None
    if change=='wrong_join':delivery['join_key']='older-join'
    if change=='stale_lease':delivery['lease_until']=99
    (gate.directory/'chat-binding.json').write_text(json.dumps(config))
    (gate.directory/'chat-delivery.json').write_text(json.dumps(delivery))
    async def forbidden(*args):pytest.fail('stopped gate reached upstream')
    with pytest.raises(ScopeError):asyncio.run(gate.call('chat_read',{},forbidden))


def test_new_lease_requires_new_complete_read(joined):
    gate,_,delivery=joined
    gate.scope();gate.read_complete=True
    delivery['lease_id']='replacement'
    (gate.directory/'chat-delivery.json').write_text(json.dumps(delivery))
    async def forbidden(*args):pytest.fail('old proof used new lease')
    with pytest.raises(ScopeError,match='read_entire_delivery_first'):
        asyncio.run(gate.call('chat_reply',{'body':'stale turn'},forbidden))


def test_large_escaped_message_retries_same_cursor_once_with_bounded_budget(joined):
    gate,_,_=joined
    calls=[]
    async def upstream(name,wire):
        args=wire['arguments'];calls.append(args)
        assert name=='read_session' and args['after_sequence']==10
        if len(calls)==1:
            return types.CallToolResult(isError=True,content=[types.TextContent(type='text',text='response_budget_too_small')])
        return result({'session':{'project_id':'p','session_id':'room'},'items':[{'body':'large escaped content'}],
            'next_after_sequence':12,'delivery_receipt':{'delivery_id':'d','status':'tool_read','unread_message_ids':[]}})
    response=asyncio.run(gate.call('chat_read',{},upstream))
    assert response.structuredContent['ready_to_reply']
    assert [a['max_bytes'] for a in calls]==[16384,65536]
