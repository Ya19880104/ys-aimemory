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
    # Exactly the identity-free keys scripts/setup-chat.py writes; never a local worker_id.
    config = {'native_session_id':'native','expires_at':1000,'project_id':'p','session_id':'room','idempotency_key':'join'}
    delivery = {'delivery_id':'d','lease_id':'lease','lease_until':500,'after_sequence':10,
        'through_sequence':12,'reply_idempotency_key':'once','join_key':'join'}
    (tmp_path/'chat-binding.json').write_text(json.dumps(config))
    (tmp_path/'chat-delivery.json').write_text(json.dumps(delivery))
    return RoomGate(tmp_path,clock=lambda:100), config, delivery


def complete_read(delivery):
    return result({'session':{'project_id':'p','session_id':'room'},'items':[{'type':'message','body':'Full text'}],
        'next_after_sequence':delivery['through_sequence'],'delivery_receipt':{'delivery_id':delivery['delivery_id'],
        'status':'tool_read','unread_message_ids':[]}})


def silent_result(delivery, worker='own'):
    return result({'project_id':'p','session_id':'room','worker_id':worker,'delivery_receipt':{
        'delivery_id':delivery['delivery_id'],'status':'no_reply','processed_sequence':delivery['through_sequence']}})


def inbox(worker='own'):
    return result({'worker_id':worker,'context_revision':1,'pending_handoffs':[],'owned_tasks':[],'available_tasks':[]})


def verified(upstream, worker='own'):
    """Answer the bridge's non-mutating identity check; every other call reaches upstream."""
    async def forward(name, wire):
        if name == 'get_worker_inbox':
            assert wire == {'arguments':{'project_id':'p'}}
            return inbox(worker)
        return await upstream(name, wire)
    return forward


def test_no_reply_forwards_only_after_full_read_and_is_not_a_post(joined):
    gate, config, delivery = joined; calls=[]
    assert 'worker_id' not in config
    async def upstream(name, wire):
        calls.append((name,wire))
        if name=='get_worker_inbox':return inbox()
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
    # The own authenticated identity is verified once, before any Hub mutation.
    assert [name for name,_ in calls]==['get_worker_inbox','read_session','complete_session_delivery']


@pytest.mark.parametrize('ambiguous', [False,True])
def test_no_reply_intent_survives_error_and_restart_without_disposition_fallback(joined,ambiguous):
    gate, _, delivery=joined; calls=[]
    async def fail(name,wire):
        calls.append((name,wire))
        if name=='read_session':return complete_read(delivery)
        assert name=='complete_session_delivery'
        if ambiguous:raise TimeoutError('committed response lost')
        return types.CallToolResult(isError=True,content=[])
    asyncio.run(gate.call('chat_read',{},verified(fail)))
    with pytest.raises((ScopeError,TimeoutError)):asyncio.run(gate.call('chat_no_reply',{},verified(fail)))
    raw=next(gate.directory.glob('chat-completion-intent-*.json')).read_text()
    assert 'body' not in json.loads(raw) and json.loads(raw)['disposition']=='no_reply'
    restarted=RoomGate(gate.directory,clock=lambda:100)
    with pytest.raises(ScopeError,match='already_completed'):asyncio.run(restarted.call('chat_reply',{'body':'fallback'},fail))
    order=[]
    async def retry(name,wire):
        order.append(name)
        if name=='get_worker_inbox':return inbox()
        assert name=='complete_session_delivery';calls.append((name,wire));return silent_result(delivery)
    assert asyncio.run(restarted.call('chat_no_reply',{},retry)).structuredContent['delivery_receipt']['status']=='no_reply'
    assert order==['get_worker_inbox','complete_session_delivery']  # A restarted process re-verifies first.
    assert calls[1]==calls[2]  # Same completion intent and stable upstream arguments.


def test_ambiguous_reply_intent_blocks_no_reply_and_changed_body_across_restart(joined):
    gate,_,delivery=joined; calls=[]; body='Private generated reply'
    async def upstream(name,wire):
        calls.append((name,wire))
        if name=='read_session':return complete_read(delivery)
        raise TimeoutError('unknown post')
    upstream=verified(upstream)
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
    @verified
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
    @verified
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
    @verified
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


@pytest.mark.parametrize('failure', [
    types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='forbidden: response_budget_too_small')]),
    types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='not_response_budget_too_small')]),
    types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='response_budget_too_small_suffix')]),
    types.CallToolResult(isError=True, structuredContent={'error':'forbidden', 'body':'response_budget_too_small'}, content=[]),
])
def test_error_budget_mentions_do_not_authorize_retry(joined, failure):
    gate, _, _ = joined
    calls=[]
    @verified
    async def upstream(name, wire):
        calls.append(wire['arguments'])
        return failure
    with pytest.raises(ScopeError, match='^hub_read_failed$'):
        asyncio.run(gate.call('chat_read', {}, upstream))
    assert len(calls)==1 and calls[0]['max_bytes']==16384
    assert gate.cursor==10 and not gate.read_complete


@pytest.mark.parametrize('failure', [
    types.CallToolResult(isError=True, structuredContent={'error':'response_budget_too_small'}, content=[]),
    types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='Error executing tool read_session: response_budget_too_small: Increase max_bytes')]),
])
def test_actual_budget_error_allows_only_one_unchanged_cursor_retry(joined, failure):
    gate, _, _ = joined
    calls=[]
    @verified
    async def upstream(name, wire):
        assert name=='read_session'
        calls.append(wire['arguments'])
        return failure
    with pytest.raises(ScopeError, match='^hub_read_failed$'):
        asyncio.run(gate.call('chat_read', {}, upstream))
    assert len(calls)==2
    assert calls[1]==calls[0] | {'max_bytes':65536}
    assert gate.cursor==10 and not gate.read_complete


def test_successful_user_budget_mention_never_retries(joined):
    gate, _, delivery = joined
    calls=[]
    @verified
    async def upstream(name, wire):
        calls.append(wire)
        page=complete_read(delivery).structuredContent
        page['items'][0]['body']='response_budget_too_small: this is user data'
        return result(page)
    response=asyncio.run(gate.call('chat_read', {}, upstream))
    assert len(calls)==1 and response.structuredContent['ready_to_reply']


def served(gate, name, arguments, forward):
    """Mirror serve(): the model sees only a fixed code for any gate exception."""
    try:
        return 'ok', asyncio.run(gate.call(name, arguments, forward)).structuredContent
    except Exception as exc:
        return 'error', str(exc) if isinstance(exc, ScopeError) else 'chat_operation_unavailable'


def test_committed_no_reply_is_reported_as_completed_without_local_worker_id(joined):
    """Regression: a Hub-committed completion was reported as chat_operation_unavailable."""
    gate, config, delivery = joined; committed=[]
    async def upstream(name, wire):
        if name=='get_worker_inbox':return inbox('worker-b')
        if name=='read_session':return complete_read(delivery)
        committed.append(wire)
        return silent_result(delivery, 'worker-b')
    assert served(gate,'chat_read',{},upstream)[0]=='ok'
    outcome=served(gate,'chat_no_reply',{},upstream)
    assert len(committed)==1  # The Hub completion happened exactly once.
    assert outcome[0]=='ok', outcome
    assert outcome[1]['worker_id']=='worker-b' and outcome[1]['delivery_receipt']['status']=='no_reply'
    assert served(gate,'chat_no_reply',{},upstream)==outcome and len(committed)==1


@pytest.mark.parametrize('identity', [
    types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='forbidden')]),
    result({'context_revision':1}),
    inbox(''),
    inbox('x'*129),
])
def test_unknown_identity_fails_closed_before_read_receipt(joined, identity):
    gate, _, _ = joined; calls=[]
    async def upstream(name, wire):
        calls.append(name)
        if name=='get_worker_inbox':return identity
        pytest.fail('read receipt mutation reached the Hub without a verified identity')
    with pytest.raises(ScopeError, match='^chat_identity_unverified$'):
        asyncio.run(gate.call('chat_read',{},upstream))
    assert calls==['get_worker_inbox'] and gate.cursor==10 and not gate.read_complete


def test_unknown_identity_after_restart_never_forwards_completion(joined):
    gate, _, delivery = joined
    @verified
    async def ambiguous(name, wire):
        if name=='read_session':return complete_read(delivery)
        raise TimeoutError('completion response lost')
    asyncio.run(gate.call('chat_read',{},ambiguous))
    with pytest.raises(TimeoutError):asyncio.run(gate.call('chat_no_reply',{},ambiguous))
    calls=[]
    async def unverified(name, wire):
        calls.append(name)
        if name=='get_worker_inbox':
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='unavailable')])
        pytest.fail('completion forwarded before identity was verified')
    restarted=RoomGate(gate.directory,clock=lambda:100)
    assert served(restarted,'chat_no_reply',{},unverified)==('error','chat_identity_unverified')
    assert calls==['get_worker_inbox']


def test_each_delivery_scope_reverifies_identity_before_its_read(joined):
    gate, _, delivery = joined; calls=[]
    async def upstream(name, wire):
        calls.append(name)
        if name=='get_worker_inbox':return inbox()
        return complete_read(json.loads((gate.directory/'chat-delivery.json').read_text()))
    asyncio.run(gate.call('chat_read',{},upstream))
    (gate.directory/'chat-delivery.json').write_text(json.dumps(delivery|{'delivery_id':'d2','lease_id':'lease2'}))
    asyncio.run(gate.call('chat_read',{},upstream))
    assert calls==['get_worker_inbox','read_session','get_worker_inbox','read_session']


def test_completion_for_another_worker_is_not_accepted_as_own(joined):
    gate, _, delivery = joined
    async def upstream(name, wire):
        if name=='get_worker_inbox':return inbox('own')
        if name=='read_session':return complete_read(delivery)
        return silent_result(delivery, 'other')
    asyncio.run(gate.call('chat_read',{},upstream))
    assert served(gate,'chat_no_reply',{},upstream)==('error','invalid_completion_receipt')
