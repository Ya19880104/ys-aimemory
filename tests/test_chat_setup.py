"""Project-local setup, disconnect and retry preserve unrelated configuration."""
import importlib.util
import json
from pathlib import Path
import sys
import httpx
import pytest

spec=importlib.util.spec_from_file_location('chat_setup',Path(__file__).parents[1]/'scripts/setup-chat.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


@pytest.fixture
def installation(tmp_path):
    project=tmp_path/'project';project.mkdir()
    client=tmp_path/'client';client.mkdir()
    launcher=client/'launcher.py'
    launcher.write_text("def transform(data, decrypt=False):\n    return data[4:] if decrypt else b'ENC:'+data\n")
    (client/'worker.dpapi').write_bytes(b'encrypted-fixture')
    (client/'bridge.py').write_text("def load_connection(path):\n    return {'endpoint':'https://hub.test/mcp'}\n")
    (client/'install-receipt.json').write_text(json.dumps({'project':str(project),'client_directory':str(client)}))
    mcp={'mcpServers':{'ys_memory':{'command':sys.executable,'args':['-B',str(launcher)]},
        'other':{'command':'do-not-change','args':['--fixture']}}}
    (project/'.mcp.json').write_text(json.dumps(mcp))
    (project/'.claude').mkdir()
    settings={'permissions':{'allow':['Read','mcp__ys_memory__chat_status']},
        'hooks':{'Stop':[{'hooks':[{'type':'command','command':'preserve-this-hook'}]}]}}
    (project/'.claude/settings.local.json').write_text(json.dumps(settings))
    return project,client,mcp,settings


def test_setup_is_scoped_and_disconnect_preserves_other_user_changes(installation):
    project,client,original,settings=installation
    receipt=setup.configure(project,'project-a','a'*32)
    assert receipt['activation_prompt'] and not receipt['native_session_id']
    binding=json.loads((client/'chat-binding.json').read_text())
    assert binding['after_sequence'] is None and binding['language']=='en'
    mcp=json.loads((project/'.mcp.json').read_text())
    assert mcp['mcpServers']['other']==original['mcpServers']['other']
    assert mcp['mcpServers']['ys_memory']['args']==[str(client/'chat-bridge.py')]
    mcp['mcpServers']['later']={'command':'user-added'}
    (project/'.mcp.json').write_text(json.dumps(mcp))
    current=json.loads((project/'.claude/settings.local.json').read_text())
    assert len(current['hooks']['Stop'])==2
    assert set(current['permissions']['allow'])=={'Read',*(('mcp__ys_memory__'+n) for n in ('chat_status','chat_read','chat_reply'))}
    current['permissions']['allow'].append('user-later-rule')
    (project/'.claude/settings.local.json').write_text(json.dumps(current))
    result=setup.disconnect(project)
    assert result['status']=='disconnected' and (client/'STOP').exists()
    restored=json.loads((project/'.mcp.json').read_text())
    assert restored['mcpServers']['ys_memory']==original['mcpServers']['ys_memory']
    assert 'later' in restored['mcpServers']
    restored_settings=json.loads((project/'.claude/settings.local.json').read_text())
    assert restored_settings['hooks']['Stop']==settings['hooks']['Stop']
    assert restored_settings['permissions']['allow']==['Read','mcp__ys_memory__chat_status','user-later-rule']
    setup.configure(project,'project-a','a'*32,language='zh-TW')
    assert not (client/'STOP').exists()
    assert list(client.glob('chat-binding.retired-*.json'))
    assert json.loads((client/'chat-binding.json').read_text())['language']=='zh-TW'


def test_refuses_duplicate_active_binding_and_preserves_bytes(installation):
    project,client,_,_=installation
    setup.configure(project,'project-a','a'*32)
    before=(project/'.mcp.json').read_bytes(),(project/'.claude/settings.local.json').read_bytes()
    with pytest.raises((ValueError,IndexError)):
        setup.configure(project,'project-a','b'*32)
    assert before==((project/'.mcp.json').read_bytes(),(project/'.claude/settings.local.json').read_bytes())


def test_concurrent_settings_edit_survives_failed_setup(installation,monkeypatch):
    project,client,original,_=installation
    actual=setup.write_checked
    def raced(path,before,candidate):
        if path.name=='settings.local.json':
            path.write_text('{"user_change":true}')
        return actual(path,before,candidate)
    monkeypatch.setattr(setup,'write_checked',raced)
    with pytest.raises(ValueError,match='configuration_changed_preserved'):
        setup.configure(project,'project-a','a'*32)
    assert json.loads((project/'.mcp.json').read_text())==original
    assert json.loads((project/'.claude/settings.local.json').read_text())=={'user_change':True}
    assert (client/'STOP').exists()


@pytest.fixture
def hub_bound_installation(installation):
    """A disposable local installation with an already registered Hub binding."""
    project, client, original_mcp, original_settings = installation
    setup.configure(project, 'project-a', 'a'*32)
    (client/'chat-status.json').write_text(json.dumps({'binding_id':'fixture-binding'}))
    (client/'bridge.py').write_text(
        "def load_connection(path):\n    return {'endpoint':'https://hub.test/mcp'}\n"
        "def verified_context(connection):\n    return True\n")
    return project, client, original_mcp, original_settings


def mock_disconnect_hub(monkeypatch, handler):
    """Exercise real HTTP response/error handling without any network access."""
    client_class = httpx.Client
    requests = []
    def dispatch(request):
        requests.append(request)
        return handler(request, len(requests))
    def client(**kwargs):
        assert kwargs['trust_env'] is False and kwargs['follow_redirects'] is False
        assert kwargs['verify'] is True
        return client_class(**kwargs, transport=httpx.MockTransport(dispatch))
    monkeypatch.setattr(httpx, 'Client', client)
    return requests


def hub_participants(status, version=7):
    return {'participants':[
        # Another binding's successful disconnect must not authorize ours.
        {'binding_id':'another-binding','status':'disconnected','version':99},
        {'binding_id':'fixture-binding','status':status,'version':version},
    ]}


@pytest.mark.parametrize('post_failure', ['lost_response','stale_cas'])
def test_disconnect_reconciles_lost_response_and_stale_cas(hub_bound_installation, monkeypatch, post_failure):
    project, client, original_mcp, original_settings = hub_bound_installation
    def handler(request, number):
        if request.method == 'GET':
            assert request.url.path == '/v1/chat/status'
            assert dict(request.url.params) == {'project_id':'project-a','session_id':'a'*32}
            return httpx.Response(200, json=hub_participants('waiting' if number == 1 else 'disconnected', 7 if number == 1 else 8))
        assert request.url.path == '/v1/chat/disconnect'
        assert json.loads(request.content) == {'project_id':'project-a','binding_id':'fixture-binding','expected_version':7}
        if post_failure == 'lost_response':
            raise httpx.ReadError('synthetic response lost after server commit', request=request)
        return httpx.Response(409, json={'error':'version_conflict'})
    requests = mock_disconnect_hub(monkeypatch, handler)
    result = setup.disconnect(project)
    assert result['status'] == 'disconnected'
    assert [request.method for request in requests] == ['GET','POST','GET']
    assert (client/'STOP').exists()
    assert json.loads((project/'.mcp.json').read_text()) == original_mcp
    assert json.loads((project/'.claude/settings.local.json').read_text()) == original_settings
    assert json.loads((client/'chat-binding.json').read_text())['disconnected_at'] > 0


def test_disconnect_already_fenced_hub_binding_does_not_post(hub_bound_installation, monkeypatch):
    project, client, original_mcp, original_settings = hub_bound_installation
    def handler(request, number):
        assert request.method == 'GET' and number == 1
        return httpx.Response(200, json=hub_participants('disconnected',8))
    requests = mock_disconnect_hub(monkeypatch, handler)
    assert setup.disconnect(project)['status'] == 'disconnected'
    assert len(requests) == 1
    assert (client/'STOP').exists()
    assert json.loads((project/'.mcp.json').read_text()) == original_mcp
    assert json.loads((project/'.claude/settings.local.json').read_text()) == original_settings


@pytest.mark.parametrize('confirmation', ['still_active','http_failure'])
def test_failed_disconnect_confirmation_preserves_stop_and_configuration(hub_bound_installation, monkeypatch, confirmation):
    project, client, _, _ = hub_bound_installation
    paths = [project/'.mcp.json', project/'.claude/settings.local.json', client/'chat-binding.json', client/'chat-status.json']
    before = {path:path.read_bytes() for path in paths}
    def handler(request, number):
        if request.method == 'POST':
            return httpx.Response(409, json={'error':'version_conflict'})
        assert request.method == 'GET'
        if number == 3 and confirmation == 'http_failure':
            return httpx.Response(503, json={'error':'temporarily_unavailable'})
        return httpx.Response(200, json=hub_participants('waiting',7))
    requests = mock_disconnect_hub(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError) as failure:
        setup.disconnect(project)
    assert failure.value.response.status_code == (409 if confirmation == 'still_active' else 503)
    assert [request.method for request in requests] == ['GET','POST','GET']
    assert (client/'STOP').exists()
    assert {path:path.read_bytes() for path in paths} == before
    assert 'disconnected_at' not in json.loads((client/'chat-binding.json').read_text())
