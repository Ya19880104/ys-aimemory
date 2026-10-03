"""Durable, bounded delivery. Relays can dispatch, but only tool reads/posts earn receipts.

Transport success is not evidence of model comprehension. A tool_read receipt means
the server returned complete source messages, irrespective of the calling transport.
"""
from dataclasses import replace
import hashlib
import json
import time
import uuid
from sqlalchemy import case, select
from .delivery_models import DELIVERY_MODELS
from .store import DELIVERY_TABLES, SESSION_TABLES, HubError


# Registered client types are presentation labels, not provider attestations.
# Never use a worker-submitted display_name as an administrator-authored alias.
CLIENT_LABELS = {'claude': 'Claude', 'codex': 'Codex', 'chatgpt': 'ChatGPT',
                 'gemini': 'Gemini', 'grok': 'Grok'}


def require(ok, code, message, status=409):
    if not ok:
        raise HubError(code, message, status)


class DeliveryService:
    def __init__(self, store, clock=time.time, principals=None):
        self.store, self.clock, self.tables = store, clock, DELIVERY_TABLES
        self.principals = principals

    def call(self, name, arguments, actor):
        from .session_service import SessionActor
        require(isinstance(actor, SessionActor), 'forbidden', 'Authenticated actor required', 403)
        require(name in DELIVERY_MODELS, 'unknown_delivery_operation', 'Unknown delivery operation', 404)
        a = DELIVERY_MODELS[name].model_validate(arguments).model_dump()
        require(a['project_id'] in actor.projects, 'forbidden', 'Project not authorized', 403)
        if name == 'status':
            with self.store.engine.connect() as conn:
                return self._status(conn, a, actor)
        require(actor.role != 'read_only', 'forbidden', 'Read-only identity', 403)
        if name == 'pause':
            require(actor.role == 'admin', 'forbidden', 'Admin role required', 403)
        elif name not in {'control', 'disconnect'}:
            require(actor.kind == 'worker', 'forbidden', 'Worker identity required', 403)
        with self.store.transaction(a['project_id'], initialize_index=False) as (state, conn):
            now = self.clock()
            if name == 'join':
                return self._join(conn, state, a, actor, now)
            if name == 'pause':
                req, replay_key, digest = self._pause_request(conn, a, actor)
                if req is not None:
                    return req
                room = self._room(conn, a['project_id'], a['session_id'])
                control = self._control(conn, room, create=True)
                require(a['expected_version'] == control['version'], 'stale_control', 'Room control changed')
                value = {**control, 'paused': a['paused'], 'version': control['version'] + 1}
                t = self.tables['controls']
                conn.execute(t.update().where(t.c.project_id == a['project_id'],
                    t.c.session_id == a['session_id']).values(paused=value['paused'], version=value['version']))
                if a['paused']:
                    # Fence already-dispatched turns too: unpausing must not make
                    # an old in-flight reply valid again.
                    b, d = self.tables['bindings'], self.tables['deliveries']
                    ids = select(b.c.binding_id).where(b.c.project_id == a['project_id'],
                                                     b.c.session_id == a['session_id'])
                    self._fence_administrative(conn, d.c.binding_id.in_(ids), now)
                self._audit(conn, state, a, actor, 'pause', now)
                result = {**value, 'running_turns_cancelled': False}
                if replay_key is not None:
                    conn.execute(self.tables['joins'].insert().values(**replay_key, payload_hash=digest, result=result))
                return result
            binding = self._binding(conn, a['project_id'], a['binding_id'])
            require(actor.kind == 'worker' and actor.id == binding['worker_id'] or
                    name in {'control', 'disconnect'} and actor.role == 'admin', 'forbidden', 'Binding belongs to another worker', 403)
            room = self._room(conn, binding['project_id'], binding['session_id'])
            if name == 'disconnect':
                require(a['expected_version'] == binding['version'], 'stale_binding', 'Binding changed')
                binding.update(enabled=False, released_at=now, generation=binding['generation'] + 1,
                               version=binding['version'] + 1)
                self._save_binding(conn, binding, 'enabled', 'released_at', 'generation', 'version')
                d = self.tables['deliveries']
                conn.execute(d.update().where(d.c.binding_id == binding['binding_id'],
                    d.c.status.in_(['leased', 'dispatched', 'tool_read', 'failed', 'retry_ready'])).values(
                        status='released', lease_until=now))
                self._audit(conn, state, {**a, 'session_id': binding['session_id']}, actor, 'disconnect', now)
                return self._public_binding(conn, binding, room, now)
            if name == 'control':
                require(a['expected_version'] == binding['version'], 'stale_binding', 'Binding changed')
                require(binding['released_at'] is None or not a['enabled'], 'binding_released',
                        'Join again to activate a disconnected binding')
                binding.update(enabled=a['enabled'], version=binding['version'] + 1)
                self._save_binding(conn, binding, 'enabled', 'version')
                if not a['enabled']:
                    d = self.tables['deliveries']
                    self._fence_administrative(conn, d.c.binding_id == binding['binding_id'], now)
                else:
                    d = self.tables['deliveries']
                    conn.execute(d.update().where(d.c.binding_id == binding['binding_id'],
                        d.c.generation == binding['generation'], d.c.status == 'failed').values(
                            status='retry_ready', attempts=0, lease_id=uuid.uuid4().hex, lease_until=now,
                            read_message_ids=[], read_at=None, dispatched_at=None))
                self._audit(conn, state, {**a, 'session_id': binding['session_id']}, actor, 'control', now)
                return self._public_binding(conn, binding, room, now)
            self._active_worker(conn, binding)
            binding['last_seen_at'] = now
            self._save_binding(conn, binding, 'last_seen_at')
            if name == 'heartbeat':
                return self._public_binding(conn, binding, room, now)
            if name == 'claim':
                return self._claim(conn, binding, room, a, now)
            delivery = self._owned_delivery(conn, a['delivery_id'], binding)
            self._live(conn, binding, room, delivery, a['lease_id'], now)
            if delivery['dispatched_at'] is None:
                t = self.tables['deliveries']
                conn.execute(t.update().where(t.c.delivery_id == delivery['delivery_id']).values(
                    dispatched_at=now, status='tool_read' if delivery['read_at'] is not None else 'dispatched'))
            return {'delivery_id': delivery['delivery_id'], 'status': 'handed_to_client',
                    'tool_read': delivery['read_at'] is not None}

    def status(self, arguments, actor):
        return self.call('status', arguments, actor)

    def pause(self, arguments, actor):
        return self.call('pause', arguments, actor)

    def _pause_request(self, conn, a, actor):
        if a['idempotency_key'] is None:
            return None, None, None
        key = {'project_id': a['project_id'], 'operation': 'pause', 'actor_kind': actor.kind,
               'worker_id': actor.id,
               'request_key': a['idempotency_key']}
        digest = hashlib.sha256(json.dumps(a, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        t = self.tables['joins']
        row = conn.execute(select(t).where(*(t.c[k] == v for k, v in key.items()))).mappings().one_or_none()
        if row is not None:
            require(row['payload_hash'] == digest, 'idempotency_conflict', 'Pause key was used for different arguments')
        return (row['result'] if row is not None else None), key, digest

    def _audit(self, conn, state, a, actor, operation, now):
        self.store.audit(conn, a['project_id'], state, {'operation': 'chat_' + operation,
            'worker_id': actor.id if actor.kind == 'worker' else 'human:' + actor.id, 'at': now,
            'context_revision': state['revision'],
            'references': {k: a[k] for k in ('session_id', 'binding_id') if k in a}})

    def _fence_administrative(self, conn, condition, now):
        d = self.tables['deliveries']
        # A deliberately interrupted lease is not a transport/model failure.
        # Real model starts remain charged against turns_used.
        conn.execute(d.update().where(condition,
            d.c.status.in_(['leased', 'dispatched', 'tool_read']), d.c.lease_until > now).values(
                lease_until=now, attempts=case((d.c.attempts > 0, d.c.attempts - 1), else_=0)))

    def _room(self, conn, project, session):
        t = SESSION_TABLES['sessions']
        row = conn.execute(select(t).where(t.c.project_id == project, t.c.session_id == session)).mappings().one_or_none()
        require(row is not None, 'not_found', 'Room not found', 404)
        return dict(row)

    def _control(self, conn, room, create=False):
        t = self.tables['controls']
        row = conn.execute(select(t).where(t.c.project_id == room['project_id'],
            t.c.session_id == room['session_id'])).mappings().one_or_none()
        value = dict(row) if row else {'project_id': room['project_id'], 'session_id': room['session_id'],
                                      'paused': False, 'version': 1}
        if row is None and create:
            conn.execute(t.insert().values(**value))
        return value

    def _binding(self, conn, project, identifier):
        t = self.tables['bindings']
        row = conn.execute(select(t).where(t.c.project_id == project, t.c.binding_id == identifier)).mappings().one_or_none()
        require(row is not None, 'not_found', 'Binding not found', 404)
        return dict(row)

    def _save_binding(self, conn, binding, *fields):
        t = self.tables['bindings']
        conn.execute(t.update().where(t.c.binding_id == binding['binding_id']).values(
            **{key: binding[key] for key in fields}))

    def _worker_active(self, conn, binding):
        if self.principals is None:
            return True
        return any(p.worker_id == binding['worker_id'] and binding['project_id'] in p.projects
                   and p.role != 'read_only' for p in self.principals(conn))

    def _active_worker(self, conn, binding):
        require(self._worker_active(conn, binding), 'forbidden', 'Worker is no longer authorized', 403)

    def _join(self, conn, state, a, actor, now):
        t, req = self.tables['bindings'], self.tables['joins']
        digest = hashlib.sha256(json.dumps(a, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        key = {'project_id': a['project_id'], 'operation': 'join', 'actor_kind': actor.kind,
               'worker_id': actor.id, 'request_key': a['idempotency_key']}
        old = conn.execute(select(req).where(*(req.c[k] == v for k, v in key.items()))).mappings().one_or_none()
        if old:
            require(old['payload_hash'] == digest, 'idempotency_conflict', 'Join key was used for different arguments')
            return old['result']
        room = self._room(conn, a['project_id'], a['session_id'])
        require(room['status'] == 'open', 'session_archived', 'Session is archived')
        previous = conn.execute(select(t).where(t.c.project_id == a['project_id'],
            t.c.session_id == a['session_id'], t.c.worker_id == actor.id)).mappings().one_or_none()
        if previous:
            require(not previous['enabled'] or previous['expires_at'] <= now or
                    previous['turns_used'] >= previous['max_turns'], 'binding_exists',
                    'Disable the existing binding before binding another native conversation')
            require(a['after_sequence'] is None or a['after_sequence'] == previous['processed_sequence'],
                    'cursor_conflict', 'Rejoining preserves the durable cursor')
        cursor = previous['processed_sequence'] if previous else (
            room['latest_sequence'] if a['after_sequence'] is None else a['after_sequence'])
        require(cursor <= room['latest_sequence'], 'invalid_cursor', 'Cursor cannot skip future events', 422)
        binding = {'binding_id': previous['binding_id'] if previous else uuid.uuid4().hex,
            'project_id': a['project_id'], 'session_id': a['session_id'], 'worker_id': actor.id,
            'client': a['client'], 'display_name': a['display_name'],
            'native_session_hash': hashlib.sha256(a['native_session_id'].encode()).hexdigest(),
            'generation': previous['generation'] + 1 if previous else 1,
            'version': previous['version'] + 1 if previous else 1, 'enabled': True,
            'released_at': None,
            'created_at': now, 'expires_at': now + a['ttl_seconds'], 'last_seen_at': now,
            'processed_sequence': cursor, 'max_turns': a['max_turns'], 'turns_used': 0}
        self._active_worker(conn, binding)
        if previous:
            d = self.tables['deliveries']
            conn.execute(d.update().where(d.c.binding_id == binding['binding_id'],
                d.c.status.in_(['leased', 'dispatched', 'tool_read', 'failed', 'retry_ready'])).values(status='superseded'))
            conn.execute(t.update().where(t.c.binding_id == binding['binding_id']).values(**binding))
        else:
            conn.execute(t.insert().values(**binding))
        self._control(conn, room, create=True)
        result = self._public_binding(conn, binding, room, now)
        conn.execute(req.insert().values(**key, payload_hash=digest, result=result))
        self._audit(conn, state, {**a, 'binding_id': binding['binding_id']}, actor, 'join', now)
        return result

    def _blocked(self, conn, binding, room, now):
        if not self._worker_active(conn, binding): return 'revoked'
        if binding['released_at'] is not None: return 'disconnected'
        if room['status'] != 'open': return 'archived'
        if self._control(conn, room)['paused']: return 'paused'
        if not binding['enabled']: return 'disabled'
        if binding['expires_at'] <= now: return 'expired'
        return None

    def _pending(self, conn, binding):
        t = self.tables['deliveries']
        row = conn.execute(select(t).where(t.c.binding_id == binding['binding_id'],
            t.c.generation == binding['generation'], t.c.status.in_(['leased', 'dispatched', 'tool_read', 'failed', 'retry_ready']))
            .order_by(t.c.created_at.desc()).limit(1)).mappings().one_or_none()
        return dict(row) if row else None

    def _public_delivery(self, row):
        return {k: row[k] for k in ('delivery_id', 'status', 'after_sequence', 'through_sequence',
            'attempts', 'created_at', 'dispatched_at', 'read_at', 'replied_at', 'reply_message_id', 'reply_sequence')}

    def _public_binding(self, conn, binding, room, now):
        blocked = self._blocked(conn, binding, room, now)
        pending = self._pending(conn, binding)
        online = now - binding['last_seen_at'] <= 45
        state = blocked or ('failed' if pending and pending['status'] == 'failed' else
            'processing' if pending and pending['lease_until'] > now else
            'budget_exhausted' if binding['turns_used'] >= binding['max_turns'] else
            'waiting' if online else 'offline')
        t = self.tables['deliveries']
        last = conn.execute(select(t).where(t.c.binding_id == binding['binding_id'],
            t.c.generation == binding['generation']).order_by(t.c.through_sequence.desc(),
            t.c.created_at.desc(), t.c.delivery_id.desc()).limit(1)).mappings().one_or_none()
        return {**{k: binding[k] for k in ('binding_id', 'project_id', 'session_id', 'worker_id',
            'client', 'display_name', 'generation', 'version', 'enabled', 'expires_at', 'last_seen_at',
            'processed_sequence', 'max_turns', 'turns_used', 'released_at')}, 'status': state, 'relay_online': online,
            'latest_delivery': self._public_delivery(last) if last else None}

    def _status(self, conn, a, actor):
        room = self._room(conn, a['project_id'], a['session_id'])
        t = self.tables['bindings']
        rows = conn.execute(select(t).where(t.c.project_id == a['project_id'],
            t.c.session_id == a['session_id']).order_by(t.c.worker_id).limit(101)).mappings().all()
        return {'project_id': a['project_id'], 'session_id': a['session_id'],
            'control': self._control(conn, room), 'latest_sequence': room['latest_sequence'],
            'participants': [self._public_binding(conn, dict(b), room, self.clock()) for b in rows[:100]],
            'has_more': len(rows) > 100, 'receipt_semantics': 'tool_read means complete messages returned by a tool; not proof of model comprehension'}

    def _claim(self, conn, binding, room, a, now):
        request_key, request_digest, previous = None, None, None
        if a['request_id'] is not None:
            require(a['generation'] == binding['generation'], 'stale_binding', 'Binding generation changed')
            request_key = {'project_id': binding['project_id'], 'operation': 'claim',
                           'actor_kind': 'worker', 'worker_id': binding['worker_id'],
                           'request_key': hashlib.sha256(a['request_id'].encode()).hexdigest()}
            request_digest = hashlib.sha256(json.dumps(a, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            requests = self.tables['joins']
            previous = conn.execute(select(requests).where(
                *(requests.c[key] == value for key, value in request_key.items()))).mappings().one_or_none()
            if previous is not None:
                require(previous['payload_hash'] == request_digest, 'idempotency_conflict',
                        'Claim request was used for different arguments')
        blocked = self._blocked(conn, binding, room, now)
        if blocked:
            return {'status': blocked, 'delivery': None}
        if previous is not None:
            original = previous['result']['delivery']
            current = self._owned_delivery(conn, original['delivery_id'], binding)
            require(current['lease_id'] == original['lease_id'] and current['lease_until'] > now and
                    current['status'] in {'leased', 'dispatched', 'tool_read'},
                    'stale_claim', 'Claim request no longer owns a live lease')
            # Receipt replay never restarts a model after dispatch or any recorded
            # full-message tool read, including a partial batch read before dispatch.
            if (current['status'] != 'leased' or current['dispatched_at'] is not None or
                    current['read_message_ids']):
                return {'status': 'busy', 'delivery': None}
            return previous['result']
        pending = self._pending(conn, binding)
        if pending and pending['status'] == 'failed':
            return {'status': 'failed', 'delivery': None}
        if pending and pending['lease_until'] > now:
            return {'status': 'busy', 'delivery': None}
        if binding['turns_used'] >= binding['max_turns']:
            return {'status': 'budget_exhausted', 'delivery': None}
        d = self.tables['deliveries']
        if pending and pending['attempts'] >= 3:
            conn.execute(d.update().where(d.c.delivery_id == pending['delivery_id']).values(status='failed'))
            return {'status': 'failed', 'delivery': None}
        if pending:
            # A lost dispatch never becomes processed. Retry the same delivery and
            # stable write key; a previous successful atomic reply already removed it.
            pending.update(lease_id=uuid.uuid4().hex, lease_until=min(now + a['lease_seconds'], binding['expires_at']),
                           attempts=pending['attempts'] + 1, status='leased', read_message_ids=[], read_at=None,
                           dispatched_at=None)
            conn.execute(d.update().where(d.c.delivery_id == pending['delivery_id']).values(**pending))
        else:
            e = SESSION_TABLES['events']
            rows = conn.execute(select(e.c.payload).where(e.c.project_id == binding['project_id'],
                e.c.session_id == binding['session_id'], e.c.sequence > binding['processed_sequence'])
                .order_by(e.c.sequence).limit(20)).scalars().all()
            incoming = [{'message_id': x['message_id'], 'sequence': x['sequence'],
                         'actor_kind': x['actor']['kind'], 'actor_id': x['actor']['id'],
                         'automatic_reply_depth': x.get('automatic_reply_depth', 0)}
                        for x in rows if x['type'] == 'message' and
                        x.get('automatic_reply_depth', 0) < 2 and
                        not (x['actor']['kind'] == 'worker' and x['actor']['id'] == binding['worker_id'])]
            if not incoming:
                if rows:
                    binding['processed_sequence'] = rows[-1]['sequence']
                    self._save_binding(conn, binding, 'processed_sequence')
                return {'status': 'idle', 'delivery': None,
                        'processed_sequence': binding['processed_sequence']}
            pending = {'delivery_id': uuid.uuid4().hex, 'binding_id': binding['binding_id'],
                'generation': binding['generation'], 'after_sequence': binding['processed_sequence'],
                'through_sequence': rows[-1]['sequence'], 'messages': incoming, 'read_message_ids': [],
                'status': 'leased', 'lease_id': uuid.uuid4().hex,
                'lease_until': min(now + a['lease_seconds'], binding['expires_at']), 'attempts': 1,
                'created_at': now, 'dispatched_at': None, 'read_at': None, 'replied_at': None,
                'reply_message_id': None, 'reply_sequence': None}
            conn.execute(d.insert().values(**pending))
        binding['turns_used'] += 1
        self._save_binding(conn, binding, 'turns_used')
        result = {'status': 'ready', 'delivery': {**self._public_delivery(pending),
            'lease_id': pending['lease_id'], 'lease_until': pending['lease_until'],
            'message_ids': [x['message_id'] for x in pending['messages']],
            'messages': pending['messages'], 'reply_idempotency_key': 'delivery-' + pending['delivery_id']}}
        if request_key is not None:
            conn.execute(self.tables['joins'].insert().values(
                **request_key, payload_hash=request_digest, result=result))
        return result

    def _owned_delivery(self, conn, identifier, binding):
        t = self.tables['deliveries']
        row = conn.execute(select(t).where(t.c.delivery_id == identifier,
            t.c.binding_id == binding['binding_id'], t.c.generation == binding['generation'])).mappings().one_or_none()
        require(row is not None, 'not_found', 'Delivery not found', 404)
        return dict(row)

    def _live(self, conn, binding, room, delivery, lease, now):
        blocked = self._blocked(conn, binding, room, now)
        require(blocked is None, 'delivery_stopped', 'Delivery is ' + (blocked or 'stopped'))
        require(delivery['status'] in {'leased', 'dispatched', 'tool_read'} and
                delivery['lease_id'] == lease and delivery['lease_until'] > now,
                'stale_delivery', 'Delivery lease is no longer valid')

    def _tool_delivery(self, conn, a, actor):
        require(actor.kind == 'worker', 'forbidden', 'Worker delivery required', 403)
        d, b = self.tables['deliveries'], self.tables['bindings']
        bid = conn.execute(select(d.c.binding_id).select_from(d.join(b)).where(
            d.c.delivery_id == a['delivery_id'], b.c.project_id == a['project_id'],
            b.c.session_id == a['session_id'], b.c.worker_id == actor.id)).scalar_one_or_none()
        require(bid is not None, 'not_found', 'Delivery not found', 404)
        binding = self._binding(conn, a['project_id'], bid)
        delivery = self._owned_delivery(conn, a['delivery_id'], binding)
        self._live(conn, binding, self._room(conn, a['project_id'], a['session_id']),
                   delivery, a['lease_id'], self.clock())
        return binding, delivery

    def record_tool_read(self, conn, a, actor, result):
        _, delivery = self._tool_delivery(conn, a, actor)
        expected = {m['message_id'] for m in delivery['messages']}
        observed = {x['message_id'] for x in result['items']
                    if x['type'] == 'message' and not x.get('body_truncated', True)} & expected
        seen = sorted(set(delivery['read_message_ids']) | observed)
        complete = set(seen) == expected
        t = self.tables['deliveries']
        conn.execute(t.update().where(t.c.delivery_id == delivery['delivery_id']).values(
            read_message_ids=seen, read_at=self.clock() if complete else None,
            status='tool_read' if complete else delivery['status']))
        result['delivery_receipt'] = {'delivery_id': delivery['delivery_id'],
            'status': 'tool_read' if complete else 'partial_tool_read',
            'unread_message_ids': sorted(expected - set(seen))}
        size = len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
        while result['returned_bytes'] != size:
            result['returned_bytes'] = size
            size = len(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
        require(size <= a['max_bytes'], 'response_budget_too_small',
                'Increase max_bytes to include the delivery receipt', 422)

    def prepare_tool_read(self, conn, a, actor):
        """Reserve a worst-case receipt before pagination; bound reads to the batch."""
        _, delivery = self._tool_delivery(conn, a, actor)
        receipt = {'delivery_id': delivery['delivery_id'], 'status': 'partial_tool_read',
                   'unread_message_ids': [m['message_id'] for m in delivery['messages']]}
        # Adding one JSON property to an object requires a comma, key, colon and
        # its value. Existing returned_bytes has already converged in _page.
        reserve = len(json.dumps({'delivery_receipt': receipt}, ensure_ascii=False,
                                 sort_keys=True, separators=(',', ':')).encode()) - 1 + 16
        return reserve, delivery['through_sequence']

    def validate_tool_reply(self, conn, a, actor):
        binding, delivery = self._tool_delivery(conn, a, actor)
        require(delivery['read_at'] is not None, 'delivery_not_read', 'Read complete delivery messages with the tool first')
        require(a['idempotency_key'] == 'delivery-' + delivery['delivery_id'],
                'delivery_key_required', 'Use the stable delivery reply idempotency key')
        depths = [m.get('automatic_reply_depth', 0) for m in delivery['messages']]
        # A new human/manual message is a new root. Older AI context in the same
        # batch must not consume the new root's first automatic response.
        depth = 1 if 0 in depths else max(depths) + 1
        label = CLIENT_LABELS.get(binding['client'])
        # The binding is scoped to the authenticated worker and this live
        # delivery/room. Persist this label with the new message so another
        # room or later reconnect cannot relabel its history. Actor ID, role
        # and permissions remain unchanged; web operator aliases still win.
        return depth, replace(actor, display_name=label) if label else actor

    def guard_unbound_post(self, conn, a, actor):
        if actor.kind != 'worker':
            return
        t = self.tables['bindings']
        row = conn.execute(select(t).where(t.c.project_id == a['project_id'],
            t.c.session_id == a['session_id'], t.c.worker_id == actor.id)).mappings().one_or_none()
        if row is None:
            return
        binding = dict(row)
        if binding['released_at'] is not None:
            return
        blocked = self._blocked(conn, binding, self._room(conn, a['project_id'], a['session_id']), self.clock())
        # Expiry alone restores manual discussion. Earlier safety controls in
        # _blocked (revoked/archive/pause/disable) still stop an expired binding.
        # Leases are capped at binding expiry; old delivery fields remain fenced
        # by _live, and this path never advances the durable automatic cursor.
        if blocked == 'expired':
            return
        require(blocked is None, 'delivery_stopped', 'Bound participant delivery is ' + (blocked or 'stopped'))
        pending = self._pending(conn, binding)
        # An exhausted receiver cannot retry an expired lease. Keep its unread
        # batch and cursor intact for rejoin; stronger controls were checked above.
        if (pending is not None and binding['turns_used'] >= binding['max_turns'] and
                pending['lease_until'] <= self.clock()):
            return
        require(pending is None, 'delivery_metadata_required',
                'An outstanding delivery must be answered with its delivery_id and lease_id')

    def record_tool_reply(self, conn, a, actor, result):
        binding, delivery = self._tool_delivery(conn, a, actor)
        binding['processed_sequence'] = delivery['through_sequence']
        self._save_binding(conn, binding, 'processed_sequence')
        t = self.tables['deliveries']
        conn.execute(t.update().where(t.c.delivery_id == delivery['delivery_id']).values(
            status='replied', replied_at=self.clock(), reply_message_id=result['message_id'],
            reply_sequence=result['sequence']))
        result['delivery_receipt'] = {'delivery_id': delivery['delivery_id'], 'status': 'replied',
                                     'processed_sequence': delivery['through_sequence']}
