"""Bounded official-sidecar receiver. Transport completion never proves native idle.

Caller supplies an authenticated scoped HTTP client and fresh native admission.
No provider credentials, histories, global configuration, or model APIs are read.
"""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from .client_watch import exclusive, reminder


TERMINAL = {'paused', 'disabled', 'disconnected', 'expired', 'revoked', 'archived',
            'budget_exhausted', 'failed'}


def durable(path, value):
    """Atomic replace after flushing content; never discard an attempt on restart."""
    pending = path.with_name(path.name + '.pending')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)
    if os.name != 'nt':
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def admitted(config, event, now):
    if not isinstance(event, dict):
        return False
    if (event.get('conversationId') != config['native_session_id'] or
            event.get('workspacePaths') != [str(Path(config['project']).resolve())] or
            type(event.get('observed_at')) not in (int, float) or
            not 0 <= now - event['observed_at'] <= 60):
        return False
    if event.get('kind') == 'native_stop':
        return event.get('fullyIdle') is True and event.get('terminationReason') == 'model_stop'
    return (config.get('admission_mode') == 'manually_admitted_dedicated_test' and
            event.get('kind') == 'manual_initial' and event.get('ui_idle_confirmed') is True and
            event.get('exclusive_test_conversation') is True)


def run(config, client, directory, executable, admission, *, now=time.time,
        sleep=time.sleep, execute=subprocess.run, on_state=lambda state: None):
    """Resume same binding only. `admission()` returns observed metadata, never guesses.

    Manual admission admits only the initial send. Later sends need fresh native
    Stop metadata. The callable must supply unique event_id values for real events.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (config.get('client') != 'gemini' or
            str(uuid.UUID(config['native_session_id'])) != config['native_session_id'] or
            type(config.get('max_sends')) is not int or not 1 <= config['max_sends'] <= 100 or
            not now() < config['expires_at'] <= now() + 86400 or
            not Path(config['project']).resolve(strict=True).is_dir()):
        raise ValueError('invalid_receiver_scope')
    path = directory / 'receiver-journal.json'
    scope = {key: config[key] for key in ('project_id', 'session_id', 'binding_id',
                                         'generation', 'native_session_id')}
    with exclusive(directory / 'receiver-process.lock') as acquired:
        if not acquired:
            return 'already_running'
        journal = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'scope': scope, 'attempts': [], 'used_events': [], 'claim_request': None}
        if journal['scope'] != scope:
            return 'scope_mismatch'

        def call(operation, data):
            response = (client.get('/v1/chat/status', params=data) if operation == 'status'
                        else client.post('/v1/chat/' + operation, json=data))
            response.raise_for_status()
            return response.json()

        ref = {key: config[key] for key in ('project_id', 'binding_id')}
        while now() < config['expires_at'] and not (directory / 'STOP').exists():
            # Never claim before reconciling the durable notification attempt.
            status = call('status', {key: config[key] for key in ('project_id', 'session_id')})
            binding = next((item for item in status['participants']
                            if item['binding_id'] == config['binding_id']), None)
            if binding is None or binding['generation'] != config['generation']:
                return 'disconnected'
            if binding['project_id'] != config['project_id'] or binding['session_id'] != config['session_id']:
                return 'scope_mismatch'
            active = next((item for item in journal['attempts'] if item['state'] != 'replied'), None)
            if active:
                latest = binding.get('latest_delivery') or {}
                if latest.get('delivery_id') == active['delivery_id'] and latest.get('status') == 'replied':
                    active['state'] = 'replied'
                    durable(path, journal)
                elif now() >= active['lease_until']:
                    return 'unresolved'
                elif binding['status'] in TERMINAL:
                    return binding['status']
                else:
                    sleep(min(3, max(0, config['expires_at'] - now())))
                    continue
            if binding['status'] in TERMINAL:
                return binding['status']
            if len(journal['attempts']) >= config['max_sends']:
                return 'budget_exhausted'
            event = admission()
            event_id = event.get('event_id') if isinstance(event, dict) else None
            if (not isinstance(event_id, str) or not event_id or event_id in journal['used_events'] or
                    not admitted(config, event, now()) or
                    (event.get('kind') == 'manual_initial' and journal['attempts'])):
                on_state('needs_native_idle')
                sleep(min(3, max(0, config['expires_at'] - now())))
                continue
            if journal['claim_request'] is None:
                journal['claim_request'] = uuid.uuid4().hex
                durable(path, journal)
            call('heartbeat', ref)
            claimed = call('claim', ref | {'generation': config['generation'],
                           'request_id': journal['claim_request'], 'lease_seconds': 300})
            if claimed['status'] == 'idle':
                sleep(min(3, max(0, config['expires_at'] - now())))
                continue
            if claimed['status'] != 'ready':
                return claimed['status']
            delivery = claimed['delivery']
            if any(item['delivery_id'] == delivery['delivery_id'] for item in journal['attempts']):
                return 'unresolved'
            # Preserve intent BEFORE dispatch or external notification. A crash
            # at any later point becomes unresolved, never an automatic resend.
            journal['attempts'].append({'delivery_id': delivery['delivery_id'],
                'lease_until': delivery['lease_until'], 'state': 'intent'})
            journal['used_events'].append(event_id)
            journal['claim_request'] = None
            durable(path, journal)
            if now() >= min(config['expires_at'], delivery['lease_until']) or (directory / 'STOP').exists():
                return 'unresolved'
            call('dispatched', ref | {key: delivery[key] for key in ('delivery_id', 'lease_id')})
            durable(directory / 'chat-delivery.json', delivery | {'join_key': config['idempotency_key']})
            # Fresh admission rechecked immediately before invoking the official CLI.
            if (not admitted(config, event, now()) or (directory / 'STOP').exists() or
                    now() >= min(config['expires_at'], delivery['lease_until'])):
                return 'unresolved'
            try:
                result = execute([executable, 'send-message', config['native_session_id'], reminder(config, delivery)],
                    shell=False, capture_output=True, timeout=max(.001, min(10,
                    config['expires_at'] - now(), delivery['lease_until'] - now())),
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                journal['attempts'][-1].update(state='returned', returncode=result.returncode)
            except (OSError, subprocess.TimeoutExpired) as exc:
                journal['attempts'][-1].update(state='unknown', error_type=type(exc).__name__)
            durable(path, journal)
        return 'stopped' if (directory / 'STOP').exists() else 'expired'
