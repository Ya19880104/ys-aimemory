"""Project-local setup, disconnect and retry preserve unrelated configuration."""
import importlib.util
import json
from pathlib import Path
import sys
import httpx
import pytest

from memory_hub.client_watch import exclusive

spec=importlib.util.spec_from_file_location('chat_setup',Path(__file__).parents[1]/'scripts/setup-chat.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


@pytest.fixture
def installation(tmp_path):
    project=tmp_path/'project';project.mkdir()
    client=tmp_path/'client';client.mkdir()
    launcher=client/'launcher.py'
    launcher.write_text("def transform(data, decrypt=False):\n    return data[4:] if decrypt else b'ENC:'+data\n")
    (client/'worker.dpapi').write_bytes(b'encrypted-fixture')
    (client/'bridge.py').write_text(
        "def load_connection(path):\n    return {'endpoint':'https://hub.test/mcp'}\n"
        "def verified_context(connection):\n    return True\n")
    (client/'install-receipt.json').write_text(json.dumps({'project':str(project),'client_directory':str(client)}))
    mcp={'mcpServers':{'ys_memory':{'command':sys.executable,'args':['-B',str(launcher)]},
        'other':{'command':'do-not-change','args':['--fixture']}}}
    (project/'.mcp.json').write_text(json.dumps(mcp))
    (project/'.claude').mkdir()
    settings={'permissions':{'allow':['Read','mcp__ys_memory__chat_status']},
        'hooks':{'Stop':[{'hooks':[{'type':'command','command':'preserve-this-hook'}]}]}}
    (project/'.claude/settings.local.json').write_text(json.dumps(settings))
    return project,client,mcp,settings


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


def hub(handler=None, worker='worker-b'):
    """Answer the non-mutating own-identity check; room status/disconnect go to handler."""
    def dispatch(request, number):
        if request.url.path == '/v1/tools/get_worker_inbox':
            assert request.method == 'POST'
            assert json.loads(request.content) == {'arguments':{'project_id':'project-a'}}
            return httpx.Response(200, json={'worker_id':worker,'context_revision':1,
                'pending_handoffs':[],'owned_tasks':[],'available_tasks':[]})
        assert request.url.path in {'/v1/chat/status','/v1/chat/disconnect'}
        if request.method == 'GET':
            assert dict(request.url.params) == {'project_id':'project-a','session_id':'a'*32}
        return handler(request, number)
    return dispatch


def participant(binding_id, worker, *, released, generation, version):
    return {'binding_id':binding_id,'project_id':'project-a','session_id':'a'*32,'worker_id':worker,
            'generation':generation,'version':version,'enabled':not released,
            'released_at':123.0 if released else None,'status':'disconnected' if released else 'waiting'}


def hub_participants(released, generation=1, version=7, *, own=True, has_more=False):
    # Another worker's live binding must never be selected, fenced or used as proof.
    rows=[participant('another-binding','worker-other',released=False,generation=4,version=99)]
    if own:
        rows.append(participant('fixture-binding','worker-b',released=released,generation=generation,version=version))
    return {'project_id':'project-a','session_id':'a'*32,'participants':rows,'has_more':has_more}


def operations(requests):
    return [(request.method, request.url.path) for request in requests]


IDENTITY = ('POST','/v1/tools/get_worker_inbox')
STATUS = ('GET','/v1/chat/status')
FENCE = ('POST','/v1/chat/disconnect')


def test_setup_is_scoped_and_disconnect_preserves_other_user_changes(installation, monkeypatch):
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
    assert set(current['permissions']['allow'])=={'Read',*(('mcp__ys_memory__'+n) for n in ('chat_status','chat_read','chat_reply','chat_no_reply'))}
    current['permissions']['allow'].append('user-later-rule')
    (project/'.claude/settings.local.json').write_text(json.dumps(current))
    # Never activated: absence of an own Hub binding is proven, not assumed.
    requests=mock_disconnect_hub(monkeypatch, hub(lambda request, number: httpx.Response(200, json=hub_participants(False, own=False))))
    result=setup.disconnect(project)
    assert result['status']=='disconnected' and result['hub_binding']=='absent' and (client/'STOP').exists()
    assert operations(requests)==[IDENTITY,STATUS]
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
    (client/'chat-status.json').write_text(json.dumps({'state':'idle','binding_id':'fixture-binding','generation':1}))
    return project, client, original_mcp, original_settings


@pytest.mark.parametrize('post_failure', ['lost_response','stale_cas'])
def test_disconnect_reconciles_lost_response_and_stale_cas(hub_bound_installation, monkeypatch, post_failure):
    project, client, original_mcp, original_settings = hub_bound_installation
    reads = []
    def handler(request, number):
        if request.method == 'GET':
            reads.append(request)
            fenced = len(reads) > 1
            return httpx.Response(200, json=hub_participants(fenced, 2 if fenced else 1, 8 if fenced else 7))
        assert json.loads(request.content) == {'project_id':'project-a','binding_id':'fixture-binding','expected_version':7}
        if post_failure == 'lost_response':
            raise httpx.ReadError('synthetic response lost after server commit', request=request)
        return httpx.Response(409, json={'error':'version_conflict'})
    requests = mock_disconnect_hub(monkeypatch, hub(handler))
    result = setup.disconnect(project)
    assert result['status'] == 'disconnected' and result['hub_binding'] == 'released'
    assert operations(requests) == [IDENTITY,STATUS,FENCE,STATUS]
    assert (client/'STOP').exists()
    assert json.loads((project/'.mcp.json').read_text()) == original_mcp
    assert json.loads((project/'.claude/settings.local.json').read_text()) == original_settings
    assert json.loads((client/'chat-binding.json').read_text())['disconnected_at'] > 0


def test_disconnect_already_fenced_hub_binding_does_not_post(hub_bound_installation, monkeypatch):
    project, client, original_mcp, original_settings = hub_bound_installation
    def handler(request, number):
        assert request.method == 'GET'
        return httpx.Response(200, json=hub_participants(True, 2, 8))
    requests = mock_disconnect_hub(monkeypatch, hub(handler))
    assert setup.disconnect(project)['hub_binding'] == 'released'
    assert operations(requests) == [IDENTITY,STATUS]
    assert (client/'STOP').exists()
    assert json.loads((project/'.mcp.json').read_text()) == original_mcp
    assert json.loads((project/'.claude/settings.local.json').read_text()) == original_settings


def preserved(project, client):
    paths = [project/'.mcp.json', project/'.claude/settings.local.json', client/'chat-binding.json', client/'chat-status.json']
    return {path:path.read_bytes() if path.exists() else None for path in paths}


def outcome(project):
    try:
        return 'returned:' + setup.disconnect(project)['status']
    except Exception as exc:
        return type(exc).__name__ + ':' + str(exc)


@pytest.mark.parametrize('confirmation', ['still_active','http_failure'])
def test_failed_disconnect_confirmation_preserves_stop_and_configuration(hub_bound_installation, monkeypatch, confirmation):
    project, client, _, _ = hub_bound_installation
    before = preserved(project, client)
    reads = []
    def handler(request, number):
        if request.method == 'POST':
            return httpx.Response(409, json={'error':'version_conflict'})
        reads.append(request)
        if len(reads) == 2 and confirmation == 'http_failure':
            return httpx.Response(503, json={'error':'temporarily_unavailable'})
        return httpx.Response(200, json=hub_participants(False))
    requests = mock_disconnect_hub(monkeypatch, hub(handler))
    assert outcome(project) == 'ChatSetupError:disconnect_not_confirmed'
    assert operations(requests) == [IDENTITY,STATUS,FENCE,STATUS]
    assert (client/'STOP').exists()
    assert preserved(project, client) == before
    assert 'disconnected_at' not in json.loads((client/'chat-binding.json').read_text())


@pytest.mark.parametrize('state', [None, {'state':'failed','error_type':'HTTPStatusError','at':1.0},
                                   {'state':'stopped','at':1.0}])
def test_disconnect_without_binding_id_locates_own_binding_and_fences_generation(installation, monkeypatch, state):
    """Older watchers dropped binding_id on failure/stop writes; never report a live binding as disconnected."""
    project, client, original_mcp, original_settings = installation
    setup.configure(project, 'project-a', 'a'*32)
    if state is not None:
        (client/'chat-status.json').write_text(json.dumps(state))
    reads = []
    def handler(request, number):
        # The listener lock is held, so no watcher join can race this fence.
        with exclusive(client/'chat-listener.lock') as acquired:
            assert not acquired
        if request.method == 'GET':
            reads.append(request)
            fenced = len(reads) > 1
            return httpx.Response(200, json=hub_participants(fenced, 2 if fenced else 1, 8 if fenced else 7))
        assert json.loads(request.content) == {'project_id':'project-a','binding_id':'fixture-binding','expected_version':7}
        return httpx.Response(200, json=participant('fixture-binding','worker-b',released=True,generation=2,version=8))
    requests = mock_disconnect_hub(monkeypatch, hub(handler))
    result = setup.disconnect(project)
    assert result['status'] == 'disconnected' and result['hub_binding'] == 'released'
    assert operations(requests) == [IDENTITY,STATUS,FENCE,STATUS]
    assert json.loads((project/'.mcp.json').read_text()) == original_mcp
    assert json.loads((project/'.claude/settings.local.json').read_text()) == original_settings
    assert json.loads((client/'chat-binding.json').read_text())['disconnected_at'] > 0


@pytest.mark.parametrize('case,code,expected', [
    ('identity_rejected', 'chat_identity_unverified', [IDENTITY]),
    ('foreign_binding', 'binding_ownership_mismatch', [IDENTITY,STATUS]),
    ('generation_changed', 'binding_generation_changed', [IDENTITY,STATUS]),
    ('incomplete_listing', 'disconnect_not_confirmed', [IDENTITY,STATUS]),
    ('not_released', 'disconnect_not_confirmed', [IDENTITY,STATUS,FENCE,STATUS]),
])
def test_disconnect_fails_closed_without_hub_proof(installation, monkeypatch, case, code, expected):
    project, client, _, _ = installation
    setup.configure(project, 'project-a', 'a'*32)
    known = {'foreign_binding':{'binding_id':'another-binding','generation':4},
             'generation_changed':{'binding_id':'fixture-binding','generation':1}}.get(case)
    if known:
        (client/'chat-status.json').write_text(json.dumps({'state':'idle', **known}))
    before = preserved(project, client)
    def handler(request, number):
        if request.method == 'POST':
            return httpx.Response(200, json=participant('fixture-binding','worker-b',released=False,generation=1,version=7))
        if case == 'generation_changed':
            return httpx.Response(200, json=hub_participants(False, generation=2, version=9))
        return httpx.Response(200, json=hub_participants(False, own=case != 'incomplete_listing',
                                                         has_more=case == 'incomplete_listing'))
    identity = hub(handler)
    def dispatch(request, number):
        if case == 'identity_rejected':
            return httpx.Response(401, json={'error':'unauthorized'})
        return identity(request, number)
    requests = mock_disconnect_hub(monkeypatch, dispatch)
    assert outcome(project) == 'ChatSetupError:' + code
    assert operations(requests) == expected
    assert (client/'STOP').exists() and preserved(project, client) == before
    assert 'disconnected_at' not in json.loads((client/'chat-binding.json').read_text())


def test_cli_reports_only_fixed_disconnect_code(installation, monkeypatch, capsys):
    project, client, _, _ = installation
    setup.configure(project, 'project-a', 'a'*32)
    mock_disconnect_hub(monkeypatch, hub(lambda request, number: httpx.Response(503, json={'error':'secret-detail'})))
    monkeypatch.setattr(sys, 'argv', ['setup-chat.py', '--project', str(project), '--disconnect'])
    assert setup.main() == 1
    captured = capsys.readouterr()
    assert captured.out == '' and captured.err == 'chat_setup_failed: disconnect_not_confirmed\n'
