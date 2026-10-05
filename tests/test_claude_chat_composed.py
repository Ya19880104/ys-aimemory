"""Composed Claude chat lifecycle against an in-process Hub.

Real setup-chat.py configure output drives the installed watch.py and
chat-bridge.py copies; no test fixture supplies a local worker_id. Every
client httpx.Client reaches the Hub app in-process, never the network.
"""
import asyncio
import importlib.util
import io
import json
from pathlib import Path
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import types

from memory_hub.app import create_app
from test_index import _migration_db
from test_sessions import collaboration, room, post, A, B

spec = importlib.util.spec_from_file_location('composed_chat_setup', Path(__file__).parents[1] / 'scripts/setup-chat.py')
setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)
CLAUDE = 'synthetic-composed-claude-worker-token'
PEER = 'synthetic-composed-peer-worker-token'
NATIVE = 'native-claude-conversation'


def load(name, path):
    found = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(found); found.loader.exec_module(module)
    return module


@pytest.fixture
def live(collaboration, monkeypatch):
    _, url, sqlite = collaboration
    app = create_app(database_url=url, auth_tokens=json.dumps({CLAUDE: B.model_dump(), PEER: A.model_dump()}),
                     allow_sqlite=sqlite)
    real, seen, faults = httpx.Client, [], {}
    with TestClient(app) as http:
        def relay(request):
            seen.append((request.method, request.url.path))
            fault = faults.get((request.method, request.url.path))
            if fault is not None:
                return fault(request)
            return http.request(request.method, request.url.path, params=request.url.params, content=request.content,
                headers={'Authorization': request.headers['Authorization'], 'Content-Type': 'application/json'})
        def client(**kwargs):
            assert kwargs.pop('verify') is True and kwargs['trust_env'] is False
            return real(**kwargs, transport=httpx.MockTransport(relay))
        monkeypatch.setattr(httpx, 'Client', client)
        yield app.state.hub, http, seen, faults


@pytest.fixture
def claude(tmp_path):
    """The verified per-project install that setup-claude.py leaves behind."""
    project, client = tmp_path / 'project', tmp_path / 'client'
    project.mkdir(); (project / '.claude').mkdir(); client.mkdir()
    (client / 'launcher.py').write_text("def transform(data, decrypt=False):\n    return data[4:] if decrypt else b'ENC:'+data\n")
    (client / 'worker.dpapi').write_bytes(b'ENC:' + CLAUDE.encode())
    (client / 'bridge.py').write_text("def load_connection(path):\n    return {'endpoint':'https://hub.test/mcp'}\n"
                                      "def verified_context(connection):\n    return True\n")
    (client / 'install-receipt.json').write_text(json.dumps({'project': str(project), 'client_directory': str(client)}))
    (project / '.mcp.json').write_text(json.dumps({'mcpServers': {'ys_memory': {
        'command': sys.executable, 'args': ['-B', str(client / 'launcher.py')]}}}))
    return project, client


def configured(project, client, session, **kwargs):
    setup.configure(project, 'p', session['session_id'], NATIVE, **kwargs)
    binding = json.loads((client / 'chat-binding.json').read_text())
    assert 'worker_id' not in binding  # configure never writes a local identity.
    return binding


def run_watcher(client, monkeypatch):
    watcher = load('composed_installed_watch', client / 'watch.py')
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'hook_event_name': 'Stop', 'session_id': NATIVE})))
    return watcher.main()


def own_binding(http, session):
    response = http.get('/v1/chat/status', params={'project_id': 'p', 'session_id': session['session_id']},
                        headers={'Authorization': 'Bearer ' + CLAUDE})
    return next(p for p in response.json()['participants'] if p['worker_id'] == B.worker_id)


def tool_forward(http, names):
    """The scoped bridge's upstream MCP call, carried by the same authenticated tool route."""
    async def forward(name, wire):
        names.append(name)
        response = http.post('/v1/tools/' + name, json=wire, headers={'Authorization': 'Bearer ' + CLAUDE})
        if response.status_code != 200:
            return types.CallToolResult(isError=True, content=[types.TextContent(type='text', text=response.json()['error'])])
        return types.CallToolResult(structuredContent=response.json(),
                                    content=[types.TextContent(type='text', text=response.text)])
    return forward


def served(bridge, gate, name, forward):
    """Mirror serve(): the model sees only a fixed code for any gate exception."""
    try:
        return 'ok', asyncio.run(gate.call(name, {}, forward)).structuredContent
    except Exception as exc:
        return 'error', str(exc) if isinstance(exc, bridge.ScopeError) else 'chat_operation_unavailable'


def test_configured_watcher_and_bridge_report_committed_no_reply(live, claude, monkeypatch, capsys):
    hub, http, _, _ = live
    project, client = claude
    session = room(hub); post(hub, session, A, body='Discussion that needs no answer')
    configured(project, client, session, after_sequence=0)
    assert run_watcher(client, monkeypatch) == 2 and 'chat_read' in capsys.readouterr().err
    assert json.loads((client / 'chat-status.json').read_text())['state'] == 'handed_to_client'
    bridge = load('composed_installed_chat_bridge', client / 'chat-bridge.py')
    gate, names = bridge.RoomGate(client), []
    forward = tool_forward(http, names)
    assert served(bridge, gate, 'chat_read', forward)[0] == 'ok'
    outcome = served(bridge, gate, 'chat_no_reply', forward)
    assert own_binding(http, session)['latest_delivery']['status'] == 'no_reply'  # The Hub committed.
    assert outcome[0] == 'ok', outcome
    assert outcome[1]['worker_id'] == B.worker_id and outcome[1]['delivery_receipt']['status'] == 'no_reply'
    assert served(bridge, gate, 'chat_no_reply', forward) == outcome
    # Own identity is verified without mutation before the first Hub write; one completion only.
    assert names == ['get_worker_inbox', 'read_session', 'complete_session_delivery']


def test_watcher_failure_keeps_binding_and_disconnect_fences_it(live, claude, monkeypatch):
    hub, http, seen, faults = live
    project, client = claude
    session = room(hub)
    configured(project, client, session)
    faults[('POST', '/v1/chat/claim')] = lambda request: httpx.Response(422, json={'error': 'invalid_arguments'})
    assert run_watcher(client, monkeypatch) == 0
    joined = own_binding(http, session)
    state = json.loads((client / 'chat-status.json').read_text())
    assert state['state'] == 'failed' and joined['enabled'] and joined['released_at'] is None
    assert state.get('binding_id') == joined['binding_id'] and state.get('generation') == joined['generation']
    faults.clear()
    assert setup.disconnect(project)['hub_binding'] == 'released'
    released = own_binding(http, session)
    assert released['released_at'] is not None and released['enabled'] is False
    assert released['generation'] == joined['generation'] + 1


@pytest.mark.parametrize('legacy', ['missing', 'failed_without_binding'])
def test_disconnect_without_binding_id_fences_live_hub_binding(live, claude, monkeypatch, legacy):
    hub, http, seen, _ = live
    project, client = claude
    session = room(hub); post(hub, session, A)
    configured(project, client, session, after_sequence=0)
    assert run_watcher(client, monkeypatch) == 2
    joined = own_binding(http, session)
    assert joined['enabled'] and joined['latest_delivery']['status'] == 'dispatched'
    if legacy == 'missing':
        (client / 'chat-status.json').unlink()
    else:  # Exactly what the previous watcher wrote on an unexpected error.
        (client / 'chat-status.json').write_text(json.dumps({'state': 'failed', 'error_type': 'HTTPStatusError', 'at': 1.0}))
    seen.clear()
    result = setup.disconnect(project)
    released = own_binding(http, session)
    assert released['released_at'] is not None and released['enabled'] is False
    assert released['generation'] == joined['generation'] + 1
    assert released['latest_delivery'] is None or released['latest_delivery']['status'] != 'dispatched'
    assert result['status'] == 'disconnected' and result['hub_binding'] == 'released'
    assert seen == [('POST', '/v1/tools/get_worker_inbox'), ('GET', '/v1/chat/status'),
                    ('POST', '/v1/chat/disconnect'), ('GET', '/v1/chat/status')]


def test_unconfirmed_disconnect_fails_closed_then_retry_releases(live, claude, monkeypatch):
    hub, http, _, faults = live
    project, client = claude
    session = room(hub); post(hub, session, A)
    configured(project, client, session, after_sequence=0)
    assert run_watcher(client, monkeypatch) == 2
    (client / 'chat-status.json').unlink()
    chat_mcp = (project / '.mcp.json').read_bytes()
    faults[('POST', '/v1/chat/disconnect')] = lambda request: httpx.Response(503, json={'error': 'unavailable'})
    try:
        outcome = 'returned:' + setup.disconnect(project)['status']
    except Exception as exc:
        outcome = type(exc).__name__ + ':' + str(exc)
    assert own_binding(http, session)['enabled'] is True
    assert outcome == 'ChatSetupError:disconnect_not_confirmed'  # Never claim a live binding is disconnected.
    assert (project / '.mcp.json').read_bytes() == chat_mcp and (client / 'STOP').exists()
    assert 'disconnected_at' not in json.loads((client / 'chat-binding.json').read_text())
    faults.clear()
    assert setup.disconnect(project)['hub_binding'] == 'released'
    assert own_binding(http, session)['released_at'] is not None
