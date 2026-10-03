"""Real REST/service transactions with dropped replies, not native model acceptance."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from memory_hub.app import create_app
from memory_hub.client_watch import watch
from test_delivery import read_delivery, reply
from test_index import _migration_db
from test_sessions import collaboration, room, post, values, A, B


@pytest.mark.parametrize('client_kind', ['claude', 'codex'])
@pytest.mark.parametrize('lost_operation', ['claim', 'dispatched'])
def test_real_rest_commit_then_response_loss_recovers_one_lease(
        collaboration, tmp_path, client_kind, lost_operation):
    hub, url, sqlite = collaboration
    session = room(hub)
    message = post(hub, session, B)
    token = 'synthetic-claim-recovery-test-token'
    app = create_app(database_url=url, auth_tokens=json.dumps({token: A.model_dump()}), allow_sqlite=sqlite)
    clock = [1000.0]
    app.state.hub.clock = hub.clock = lambda: clock[0]
    config = values(session, worker_id=A.worker_id, client=client_kind,
        display_name='Test receiver', native_session_id='fixture-native',
        after_sequence=0, max_turns=1, idempotency_key='fixture-join',
        ttl_seconds=60, expires_at=1060, language='en')
    requests, dropped, turns = [], [], []

    def sleep(seconds):
        clock[0] += seconds

    with TestClient(app, headers={'Authorization': 'Bearer '+token}) as transport:
        class DropAfterCommit:
            def post(self, path, *, json):
                response = transport.post(path, json=json)
                requests.append((path, json, response))
                if path.endswith('/'+lost_operation) and response.status_code == 200 and not dropped:
                    dropped.append(response.json())
                    raise httpx.ReadError('Synthetic reply lost after the server committed', request=response.request)
                return response

        if client_kind == 'claude':
            reminder = watch(config, {'hook_event_name': 'Stop', 'session_id': 'fixture-native'},
                DropAfterCommit(), tmp_path/'status.json', now=lambda: clock[0], sleep=sleep)
            assert reminder and 'chat_read' in reminder
        else:
            spec = importlib.util.spec_from_file_location('integration_codex_receiver',
                Path(__file__).parents[1]/'scripts/run-codex-chat.py')
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)

            def simulated_turn(config, delivery, directory, heartbeat, stop):
                # Exercise the actual read/reply transaction but do not assert
                # that this test called a native client or model.
                turns.append(delivery['delivery_id'])
                read_delivery(hub, session, delivery)
                reply(hub, session, delivery)
                return {'status': 'passed'}

            result = runner.receiver(config, DropAfterCommit(), tmp_path,
                turn=simulated_turn, now=lambda: clock[0], sleep=sleep)
            assert result['state'] == 'local_budget_exhausted' and len(turns) == 1

        participant = transport.get('/v1/chat/status', params=values(session)).json()['participants'][0]
        assert participant['turns_used'] == participant['latest_delivery']['attempts'] == 1
        assert participant['latest_delivery']['status'] == ('dispatched' if client_kind == 'claude' else 'replied')
        grants = [(args, response.json()['delivery']) for path, args, response in requests
                  if path.endswith('/claim') and response.json().get('status') == 'ready']
        assert len(grants) == (2 if lost_operation == 'claim' else 1)
        assert all(args == grants[0][0] and grant == grants[0][1] for args, grant in grants)
        assert grants[0][1]['message_ids'] == [message['message_id']]
        assert grants[0][1]['lease_until'] == 1060  # Retrying did not extend the lease.
        assert clock[0] == 1002  # Backoff only; no 300-second lease wait.
