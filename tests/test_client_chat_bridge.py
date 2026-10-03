import asyncio
import json
import pytest
from memory_hub.client_chat_bridge import RoomGate, ScopeError, result
from mcp import types


@pytest.fixture
def joined(tmp_path):
    config = {'native_session_id':'native','expires_at':1000,'project_id':'p','session_id':'room','idempotency_key':'join'}
    delivery = {'delivery_id':'d','lease_id':'lease','lease_until':500,'after_sequence':10,
        'through_sequence':12,'reply_idempotency_key':'once','join_key':'join'}
    (tmp_path/'chat-binding.json').write_text(json.dumps(config))
    (tmp_path/'chat-delivery.json').write_text(json.dumps(delivery))
    return RoomGate(tmp_path,clock=lambda:100), config, delivery


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
