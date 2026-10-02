"""Managed credentials: all secrets, projects and databases here are disposable."""
import asyncio
import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from memory_hub.app import create_app
from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import HubError, Store, events, projects
from test_index import _migration_db


OWNER = '559765bf-e98a-43c8-8b6b-0880c69d92c6'
ADMIN = Principal(worker_id='operator', projects=['existing', 'other'], role='admin')
ENV = Principal(worker_id='env-worker', projects=['existing'], role='worker')


@pytest.fixture
def registry_hub(_migration_db):
    url, sqlite, _ = _migration_db
    hub = Hub(Store(url, allow_sqlite=sqlite), principals=[ADMIN, ENV])
    for name in ADMIN.projects:
        hub.call('create_project', {'project_id': name}, ADMIN)
    return hub, url, sqlite


def rejected(code, action):
    with pytest.raises(HubError) as caught:
        action()
    assert caught.value.code == code


def test_new_project_owner_and_audit_are_atomic(registry_hub, monkeypatch):
    hub, _, _ = registry_hub
    assert getattr(hub, 'credentials', None) is not None
    registry = hub.credentials
    registry.create_project('managed', OWNER, 'web-user', 100)
    assert registry.owned_projects(OWNER) == ('managed',)
    assert registry.owned_projects(str(uuid.uuid4())) == ()
    rejected('project_exists', lambda: registry.create_project('existing', OWNER, 'web-user', 101))
    assert registry.owned_projects(OWNER) == ('managed',)
    with hub.store.engine.connect() as conn:
        audit = conn.execute(select(events.c.event).where(events.c.project_id == 'managed')).scalar_one()
    assert audit['operation'] == 'create_managed_project'
    assert audit['worker_id'] == 'web-user'

    def unavailable(*args, **kwargs):
        raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(hub.store, 'audit', unavailable)
    with pytest.raises(RuntimeError, match='synthetic audit'):
        registry.create_project('rolled-back', OWNER, 'web-user', 102)
    assert registry.owned_projects(OWNER) == ('managed',)
    with hub.store.engine.connect() as conn:
        assert conn.execute(select(projects.c.id).where(projects.c.id == 'rolled-back')).first() is None


def test_create_project_race_and_invalid_owner_leave_no_orphans(registry_hub):
    hub, _, _ = registry_hub
    rejected('invalid_credentials', lambda: hub.credentials.create_project('invalid-owner', 'not-a-uuid', 'web-user', 100))
    def create(_):
        try:
            return hub.credentials.create_project('same-project', OWNER, 'web-user', 100)
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(create, range(2)))
    assert sum(isinstance(item, dict) for item in results) == 1
    assert 'project_exists' in results
    assert hub.credentials.owned_projects(OWNER) == ('same-project',)
    with hub.store.engine.connect() as conn:
        assert conn.execute(select(events.c.event).where(events.c.project_id == 'same-project')).one()
        assert conn.execute(select(projects.c.id).where(projects.c.id == 'invalid-owner')).first() is None


def test_issue_stores_hash_only_and_never_reveals_it_in_metadata(registry_hub):
    hub, _, _ = registry_hub
    issued = hub.credentials.issue('existing', 'managed-worker', 'web-user', 100)
    assert len(issued['token']) >= 43
    assert issued['version'] == 1
    assert issued['worker_id'] == 'managed-worker' and issued['project_id'] == 'existing'
    principal = hub.credentials.authenticate(issued['token'])
    assert principal.model_dump() == {'worker_id': 'managed-worker', 'projects': ['existing'], 'role': 'worker'}
    rows = hub.credentials.list_credentials(['existing'])
    assert len(rows) == 1 and rows[0]['token_id'] == issued['token_id']
    assert 'token' not in rows[0] and 'token_hash' not in rows[0]
    assert hub.credentials.list_credentials(['other']) == []
    with hub.store.engine.connect() as conn:
        stored = conn.execute(text('SELECT token_hash FROM mcp_credentials')).scalar_one()
        audit = [row[0] for row in conn.execute(select(events.c.event))]
    assert stored == hashlib.sha256(issued['token'].encode()).hexdigest()
    serialized = json.dumps(rows + audit)
    assert issued['token'] not in serialized and stored not in serialized


@pytest.mark.parametrize('worker', ['operator', 'env-worker', 'web-operator'])
def test_reserved_worker_cannot_be_issued(registry_hub, worker):
    hub, _, _ = registry_hub
    rejected('worker_reserved', lambda: hub.credentials.issue('existing', worker, 'web-user', 100))
    assert hub.credentials.list_credentials(['existing']) == []


@pytest.mark.parametrize('project,worker', [('bad/id', 'valid'), ('existing', ''), ('existing', 'bad worker')])
def test_invalid_identifiers_never_create_credentials(registry_hub, project, worker):
    hub, _, _ = registry_hub
    rejected('invalid_credentials', lambda: hub.credentials.issue(project, worker, 'web-user', 100))
    assert hub.credentials.list_credentials(['existing']) == []


def test_rotation_revocation_and_permanent_identity(registry_hub):
    hub, _, _ = registry_hub
    registry = hub.credentials
    first = registry.issue('existing', 'managed-worker', 'web-user', 100)
    rejected('credential_not_found', lambda: registry.rotate('other', first['token_id'], 1, 'web-user', 101))
    second = registry.rotate('existing', first['token_id'], 1, 'web-user', 101)
    assert second['token_id'] == first['token_id'] and second['version'] == 2
    assert second['token'] != first['token']
    assert registry.authenticate(first['token']) is None
    assert registry.authenticate(second['token']).worker_id == 'managed-worker'
    rejected('credential_conflict', lambda: registry.revoke('existing', first['token_id'], 1, 'web-user', 102))
    registry.revoke('existing', first['token_id'], 2, 'web-user', 103)
    assert registry.authenticate(second['token']) is None
    assert registry.list_credentials(['existing'])[0]['revoked_at'] == 103
    rejected('credential_revoked', lambda: registry.rotate('existing', first['token_id'], 3, 'web-user', 104))
    rejected('worker_exists', lambda: registry.issue('other', 'managed-worker', 'web-user', 105))


@pytest.mark.parametrize('revoked', [False, True])
def test_environment_cannot_reassign_managed_identity(registry_hub, revoked):
    hub, _, _ = registry_hub
    issued = hub.credentials.issue('existing', 'permanent-worker', 'web-user', 100)
    if revoked:
        hub.credentials.revoke('existing', issued['token_id'], 1, 'web-user', 101)
    replacement = Principal(worker_id='permanent-worker', projects=['other'], role='admin')
    with pytest.raises(RuntimeError, match='managed credential'):
        Hub(hub.store, principals=[ADMIN, ENV, replacement])


def test_other_instance_cannot_issue_previously_reserved_env_identity(registry_hub):
    one, url, sqlite = registry_hub
    two = Hub(Store(url, allow_sqlite=sqlite), principals=[ADMIN])
    rejected('worker_reserved', lambda: two.credentials.issue('existing', ENV.worker_id, 'web-user', 100))
    assert one.credentials.list_credentials(['existing']) == []


def test_env_startup_and_managed_issue_compete_for_same_namespace(registry_hub):
    hub, url, sqlite = registry_hub
    env_identity = Principal(worker_id='racing-identity', projects=['existing'])
    def claim(kind):
        try:
            if kind == 'env':
                Hub(Store(url, allow_sqlite=sqlite), principals=[ADMIN, ENV, env_identity])
            else:
                hub.credentials.issue('existing', 'racing-identity', 'web-user', 100)
            return ('ok', kind)
        except HubError as exc:
            assert exc.code == 'worker_reserved'
            return ('rejected', kind)
        except RuntimeError as exc:
            assert 'managed credential' in str(exc)
            return ('rejected', kind)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, ['env', 'managed']))
    assert sum(item[0] == 'ok' for item in results) == 1


def test_recipient_validation_reuses_project_transaction_connection(registry_hub):
    hub, url, sqlite = registry_hub
    hub.credentials.issue('existing', 'dynamic-worker', 'web-user', 100)
    hub.call('register_source', {'project_id': 'existing', 'source_id': 'spec', 'content': 'Fixture',
                                'uri': 'fixture:spec', 'commit': 'fixture'}, ADMIN)
    hub.call('create_task', {'project_id': 'existing', 'task_id': 't', 'goal': 'fixture',
                           'allowed_paths': ['fixture/**'], 'acceptance_criteria': ['pass'], 'source_ids': ['spec']}, ADMIN)
    original = hub.store.engine
    limited = create_engine(url, pool_size=1, max_overflow=0, pool_timeout=0.2,
                            connect_args={'timeout': 30} if sqlite else {})
    hub.store.engine = limited
    try:
        result = hub.call('recover_task', {'project_id': 'existing', 'task_id': 't', 'to_worker': 'dynamic-worker',
                          'reason': 'fixture', 'expected_revision': 2, 'expected_generation': 0, 'expected_fence': 0}, ADMIN)
        assert result['pending_recipient'] == 'dynamic-worker'
    finally:
        limited.dispose()
        hub.store.engine = original


def test_independent_instances_see_issue_and_revoke_immediately(registry_hub):
    one, url, sqlite = registry_hub
    two = Hub(Store(url, allow_sqlite=sqlite), principals=[ADMIN, ENV])
    issued = one.credentials.issue('existing', 'dynamic-worker', 'web-user', 100)
    assert two.credentials.authenticate(issued['token']).worker_id == 'dynamic-worker'
    assert any(p.worker_id == 'dynamic-worker' for p in two.principals)
    one.call('register_source', {'project_id': 'existing', 'source_id': 'spec', 'content': 'Fixture',
                                'uri': 'fixture:spec', 'commit': 'fixture'}, ADMIN)
    one.call('create_task', {'project_id': 'existing', 'task_id': 't', 'goal': 'fixture',
                           'allowed_paths': ['fixture/**'], 'acceptance_criteria': ['pass'], 'source_ids': ['spec']}, ADMIN)
    args = {'project_id': 'existing', 'task_id': 't', 'to_worker': 'dynamic-worker', 'reason': 'fixture',
            'expected_revision': 2, 'expected_generation': 0, 'expected_fence': 0}
    assert two.call('recover_task', args, ADMIN)['pending_recipient'] == 'dynamic-worker'
    one.credentials.revoke('existing', issued['token_id'], 1, 'web-user', 102)
    assert two.credentials.authenticate(issued['token']) is None
    assert not any(p.worker_id == 'dynamic-worker' for p in two.principals)
    args.update(expected_generation=1, expected_fence=1)
    rejected('unknown_recipient', lambda: two.call('recover_task', args, ADMIN))


def test_concurrent_same_worker_issue_has_one_winner(registry_hub):
    hub, _, _ = registry_hub
    def issue(project):
        try:
            return hub.credentials.issue(project, 'race-worker', 'web-user', 100)
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(issue, ['existing', 'other']))
    assert sum(isinstance(item, dict) for item in result) == 1
    assert 'worker_exists' in result
    assert len(hub.credentials.list_credentials(['existing', 'other'])) == 1


def test_concurrent_rotation_revoke_has_one_version_winner(registry_hub):
    hub, _, _ = registry_hub
    registry = hub.credentials
    issued = registry.issue('existing', 'race-worker', 'web-user', 100)
    def mutate(kind):
        try:
            result = getattr(registry, kind)('existing', issued['token_id'], 1, 'web-user', 101)
            return ('ok', kind, result)
        except HubError as exc:
            return ('rejected', exc.code)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(mutate, ['rotate', 'revoke']))
    assert sum(item[0] == 'ok' for item in results) == 1
    assert registry.authenticate(issued['token']) is None
    assert registry.list_credentials(['existing'])[0]['version'] == 2


def test_audit_failure_does_not_issue_or_rotate(registry_hub, monkeypatch):
    hub, _, _ = registry_hub
    registry = hub.credentials
    issued = registry.issue('existing', 'original', 'web-user', 100)
    def unavailable(*args, **kwargs):
        raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(hub.store, 'audit', unavailable)
    with pytest.raises(RuntimeError): registry.issue('other', 'failed', 'web-user', 101)
    with pytest.raises(RuntimeError): registry.rotate('existing', issued['token_id'], 1, 'web-user', 101)
    assert registry.authenticate(issued['token']).worker_id == 'original'
    assert registry.list_credentials(['other']) == []
    assert registry.list_credentials(['existing'])[0]['version'] == 1


def test_managed_bearer_scope_role_rotation_and_env_priority(_migration_db, monkeypatch):
    url, sqlite, _ = _migration_db
    for key in ('HUB_WEB_USERNAME', 'HUB_WEB_PASSWORD_HASH', 'HUB_WEB_PROJECTS'):
        monkeypatch.delenv(key, raising=False)
    env_token = 'synthetic-env-operator-token-000000000'
    app = create_app(database_url=url, allow_sqlite=sqlite,
                     auth_tokens=json.dumps({env_token: ADMIN.model_dump()}))
    hub = app.state.hub
    for name in ADMIN.projects: hub.call('create_project', {'project_id': name}, ADMIN)
    issued = hub.credentials.issue('existing', 'dynamic-worker', 'web-user', 100)
    authentication_on_event_loop = []
    authenticate = hub.credentials.authenticate
    def observed_authenticate(raw):
        try:
            asyncio.get_running_loop()
            authentication_on_event_loop.append(True)
        except RuntimeError:
            authentication_on_event_loop.append(False)
        return authenticate(raw)
    monkeypatch.setattr(hub.credentials, 'authenticate', observed_authenticate)
    with TestClient(app) as client:
        def invoke(token, name='get_project_summary', project='existing'):
            return client.post('/v1/tools/' + name, headers={'Authorization': 'Bearer ' + token},
                               json={'arguments': {'project_id': project}})
        assert client.post('/v1/tools/get_project_summary', headers={'Authorization': 'Bearer ' + 'x' * 43},
                           content=b'x' * 1048577).status_code == 413
        assert invoke(issued['token']).status_code == 200
        assert authentication_on_event_loop == [False]
        assert invoke(issued['token'], project='other').status_code == 403
        assert invoke(issued['token'], name='create_project').status_code == 403
        rotated = hub.credentials.rotate('existing', issued['token_id'], 1, 'web-user', 101)
        assert invoke(issued['token']).status_code == 401
        assert invoke(rotated['token']).status_code == 200
        with hub.store.engine.begin() as conn:
            conn.execute(text('DROP TABLE mcp_credentials'))
        assert invoke(env_token).status_code == 200
        unavailable = invoke(rotated['token'])
        assert unavailable.status_code == 503
        assert unavailable.json() == {'error': 'authentication_unavailable'}
        assert invoke('x' * 10000).status_code == 401
        assert invoke('').status_code == 401
