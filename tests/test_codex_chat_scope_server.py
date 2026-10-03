"""Exercise the actual MCP server/gate with synthetic in-memory upstream transport."""
import asyncio
from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

import anyio
from mcp import ClientSession, types
import mcp.server.stdio
import pytest

from test_codex_chat_runner import runner, CONFIG, DELIVERY, arguments, reading, reply


def result(value, *, error=False):
    return types.CallToolResult(isError=error, structuredContent=value,
        content=[types.TextContent(type='text', text=json.dumps(value))])


class Upstream:
    def __init__(self, identity=None, *, budget_retry=False):
        self.identity = identity or result({'worker_id': CONFIG['worker_id'], 'context_revision': 87,
            'available_tasks': [{'body': 'synthetic task content must not reach model'}],
            'pending_handoffs': [{'body': 'synthetic handoff content must not reach model'}]})
        self.identity = self.identity.model_copy(update={
            'meta': {'task_trace': 'synthetic task metadata must not reach model'}})
        self.calls = []
        self.budget_retry = budget_retry
        self.schemas = [types.Tool(name=name, description='Original shared tool description',
            inputSchema={'type': 'object', 'properties': {'arguments': {'type': 'object'}},
                         'required': ['arguments'], 'additionalProperties': False},
            outputSchema={'type': 'object', 'required': ['worker_id', 'available_tasks']}
                if name == 'get_worker_inbox' else {'type': 'object'}) for name in runner.TOOLS]

    async def list_tools(self):
        return types.ListToolsResult(tools=self.schemas)

    async def call_tool(self, name, wire):
        self.calls.append((name, wire))
        if name == 'get_worker_inbox':
            return self.identity
        if name == 'read_session':
            if self.budget_retry and wire['arguments']['max_bytes'] == 16384 and len(self.calls) == 2:
                return result({'error': 'response_budget_too_small'}, error=True)
            after = wire['arguments']['after_sequence']
            return result(reading(after + 1, DELIVERY['message_ids'][after - 4], after == 5))
        return result(reply())


def exercise(monkeypatch, upstream, scenario):
    """Only credentials and transport are synthetic; serve_scope and MCP dispatch are real."""
    observed = []
    real_proof = runner.NativeProof

    class RecordingProof(real_proof):
        def event(self, event):
            if event.get('type') == 'item.completed' and event['item']['tool'] == 'get_worker_inbox':
                observed.append(event['item']['result'])
            return super().event(event)

    @asynccontextmanager
    async def compact_upstream(connection):
        yield upstream

    monkeypatch.setattr(runner, 'NativeProof', RecordingProof)
    monkeypatch.setattr(runner, 'credentials', lambda config: (
        SimpleNamespace(compact_upstream=compact_upstream), {}, None, 'synthetic-worker-token'))
    monkeypatch.setenv('YS_AIMEMORY_TOKEN', 'synthetic-original')

    async def run():
        client_write, server_read = anyio.create_memory_object_stream(10)
        server_write, client_read = anyio.create_memory_object_stream(10)

        @asynccontextmanager
        async def stdio_server():
            async with server_read, server_write:
                yield server_read, server_write

        monkeypatch.setattr(mcp.server.stdio, 'stdio_server', stdio_server)
        with anyio.fail_after(10):
            async with anyio.create_task_group() as group:
                group.start_soon(runner.serve_scope, CONFIG | {'delivery': DELIVERY})
                async with client_read, client_write, ClientSession(client_read, client_write) as client:
                    await client.initialize()
                    await scenario(client, observed)
                group.cancel_scope.cancel()

    asyncio.run(run())


@pytest.mark.parametrize('budget_retry', [False, True])
def test_scoped_identity_projects_only_after_validation_and_preserves_delivery(monkeypatch, budget_retry):
    upstream = Upstream(budget_retry=budget_retry)

    async def scenario(client, observed):
        catalog = await client.list_tools()
        identity_tool = next(tool for tool in catalog.tools if tool.name == 'get_worker_inbox')
        assert identity_tool.title == 'Verify chat worker'
        assert identity_tool.description == "Return this chat receiver's authenticated worker_id only; no inbox or task contents."
        assert identity_tool.outputSchema == {'type': 'object', 'properties': {
            'worker_id': {'type': 'string', 'minLength': 1, 'maxLength': 128}},
            'required': ['worker_id'], 'additionalProperties': False}
        # Changing the receiver catalog does not mutate the shared upstream catalog.
        assert upstream.schemas[0].outputSchema['required'] == ['worker_id', 'available_tasks']
        identity = await client.call_tool('get_worker_inbox', arguments('get_worker_inbox'))
        assert not identity.isError
        assert identity.structuredContent == {'worker_id': CONFIG['worker_id']}
        assert [json.loads(block.text) for block in identity.content] == [identity.structuredContent]
        assert 'task' not in identity.model_dump_json() and 'handoff' not in identity.model_dump_json()
        assert observed == [upstream.identity.model_dump(mode='json', by_alias=True)]
        assert 'available_tasks' in observed[0]['structuredContent']
        first = await client.call_tool('read_session', arguments('read_session'))
        if budget_retry:
            assert first.isError and first.structuredContent['error'] == 'response_budget_too_small'
            first = await client.call_tool('read_session', arguments('read_session', max_bytes=65536))
        assert not first.isError and first.structuredContent['next_after_sequence'] == 5
        second = await client.call_tool('read_session', arguments('read_session', after_sequence=5))
        assert not second.isError and second.structuredContent['delivery_receipt']['status'] == 'tool_read'
        posted = await client.call_tool('post_session_message', arguments('post_session_message'))
        assert not posted.isError and posted.structuredContent['delivery_receipt']['status'] == 'replied'

    exercise(monkeypatch, upstream, scenario)
    assert len(upstream.calls) == (5 if budget_retry else 4)


@pytest.mark.parametrize('failure', ['wrong_identity', 'missing_identity', 'upstream_error'])
def test_bad_original_identity_or_error_is_never_replaced_by_configured_identity(monkeypatch, failure):
    value = {'available_tasks': [{'body': 'task must not leak'}]}
    if failure != 'missing_identity':
        value['worker_id'] = 'someone-else' if failure == 'wrong_identity' else CONFIG['worker_id']
    upstream = Upstream(result(value, error=failure == 'upstream_error'))

    async def scenario(client, observed):
        identity = await client.call_tool('get_worker_inbox', arguments('get_worker_inbox'))
        assert identity.isError and identity.structuredContent is None
        assert identity.content[0].text == 'Scoped chat operation stopped; no fallback permitted'
        assert observed == [upstream.identity.model_dump(mode='json', by_alias=True)]
        later = await client.call_tool('read_session', arguments('read_session'))
        assert later.isError

    exercise(monkeypatch, upstream, scenario)
    assert len(upstream.calls) == 1
