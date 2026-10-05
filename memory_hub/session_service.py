"""Project-shared discussion; authenticated actors, no implicit task authority."""
import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import time
import uuid

from sqlalchemy import func, select
from .session_models import SESSION_MODELS
from .store import HubError, SESSION_TABLES, projects


def require(ok, code, message, status=409):
    if not ok:
        raise HubError(code, message, status)


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def snippet(value, size=512):
    return value.encode('utf-8')[:size].decode('utf-8', errors='ignore')


@dataclass(frozen=True)
class SessionActor:
    kind: str
    id: str
    display_name: str
    projects: tuple[str, ...]
    role: str

    def __post_init__(self):
        roles = {'human': {'admin', 'member', 'read_only'},
                 'worker': {'admin', 'worker', 'approver', 'read_only'}}
        if self.kind not in roles or self.role not in roles[self.kind]:
            raise ValueError('Invalid server-derived session actor')
        if (not isinstance(self.projects, tuple) or
                any(not isinstance(item, str) or not item or '\x00' in item for item in self.projects)):
            raise ValueError('Invalid server-derived project scope')
        for value, maximum in ((self.id, 128), (self.display_name, 200)):
            if not isinstance(value, str) or not value.strip() or len(value) > maximum or '\x00' in value:
                raise ValueError('Invalid server-derived actor identity')
            value.encode('utf-8')

    @classmethod
    def from_principal(cls, principal):
        return cls('worker', principal.worker_id, principal.worker_id, tuple(principal.projects), principal.role)

    def public(self):
        return {'kind': self.kind, 'id': self.id, 'display_name': self.display_name}


class SessionService:
    READS = {'list_sessions', 'read_session', 'search_sessions',
             'get_session_artifact', 'read_session_attachment'}

    def __init__(self, store, clock=time.time):
        self.store, self.clock, self.tables = store, clock, SESSION_TABLES
        self.delivery = None

    def call(self, name, arguments, actor: SessionActor):
        require(isinstance(actor, SessionActor), 'forbidden', 'Authenticated actor required', 403)
        require(name in SESSION_MODELS, 'unknown_tool', 'Unknown session tool', 404)
        a = SESSION_MODELS[name].model_validate(arguments).model_dump()
        # Preserve pre-v6 mutation hashes for requests without delivery metadata.
        if name in {'read_session', 'post_session_message'} and a.get('delivery_id') is None:
            a.pop('delivery_id', None)
            a.pop('lease_id', None)
        project = a.get('project_id')
        if project is not None:
            require(project in actor.projects, 'forbidden', 'Project not authorized', 403)
        if name not in self.READS:
            require(actor.role != 'read_only', 'forbidden', 'This role cannot write shared discussions', 403)
        if name in {'create_session', 'archive_session'}:
            require(actor.role == 'admin', 'forbidden', 'Admin role required', 403)
        if name in self.READS:
            if name == 'read_session' and a.get('delivery_id') is not None:
                require(self.delivery is not None, 'delivery_unavailable', 'Delivery service unavailable', 503)
                with self.store.transaction(project, initialize_index=False) as (_, conn):
                    reserve, through = self.delivery.prepare_tool_read(conn, a, actor)
                    result = self._read(name, a, actor, conn, reserve=reserve, through_sequence=through)
                    self.delivery.record_tool_read(conn, a, actor, result)
                    return result
            with self.store.engine.connect() as conn:
                return self._read(name, a, actor, conn)
        with self.store.transaction(project, initialize_index=False) as (state, conn):
            room = self._room(conn, project, a['session_id']) if 'session_id' in a else None
            requests = self.tables['requests']
            key = {'project_id': project, 'session_id': a.get('session_id', ''),
                   'actor_kind': actor.kind, 'actor_id': actor.id,
                   'operation': name, 'request_key': a['idempotency_key']}
            digest = hashlib.sha256(compact(a)).hexdigest()
            previous = conn.execute(select(requests).where(
                *(requests.c[k] == v for k, v in key.items()))).mappings().one_or_none()
            if previous is not None:
                require(previous['payload_hash'] == digest, 'idempotency_conflict',
                        'Idempotency key was used for different arguments')
                return previous['result']
            if room is not None and name != 'archive_session':
                require(room['status'] == 'open', 'session_archived', 'Session is archived')
            if name == 'post_session_message' and a.get('delivery_id') is not None:
                require(self.delivery is not None, 'delivery_unavailable', 'Delivery service unavailable', 503)
                a['_automatic_reply_depth'], actor = self.delivery.validate_tool_reply(conn, a, actor)
            elif name == 'post_session_message' and self.delivery is not None:
                self.delivery.guard_unbound_post(conn, a, actor)
            if name == 'complete_session_delivery':
                require(self.delivery is not None, 'delivery_unavailable', 'Delivery service unavailable', 503)
                result = self.delivery.complete_tool_no_reply(conn, a, actor)
                self.store.audit(conn, project, state, {'operation': name, 'worker_id': actor.id,
                    'actor_kind': actor.kind, 'at': self.clock(), 'context_revision': state['revision'],
                    'references': {'session_id': a['session_id'], 'delivery_id': a['delivery_id']}})
            else:
                result = self._write(name, a, actor, conn, state, room, self.clock())
            if name == 'post_session_message' and a.get('delivery_id') is not None:
                self.delivery.record_tool_reply(conn, a, actor, result)
            conn.execute(requests.insert().values(**key, payload_hash=digest, result=result))
            return result

    def _room(self, conn, project, session):
        table = self.tables['sessions']
        row = conn.execute(select(table).where(table.c.project_id == project,
                                               table.c.session_id == session)).mappings().one_or_none()
        require(row is not None, 'not_found', 'Session or reference not found', 404)
        return dict(row)

    def latest_artifacts(self, project_id, session_id, actor: SessionActor, limit=10):
        """Small web sidebar index, independent of the loaded message window.

        Keep this out of MCP read/list metadata: browser convenience must not
        make every model poll pay for the same artifact index again.
        """
        require(isinstance(actor, SessionActor), 'forbidden', 'Authenticated actor required', 403)
        require(project_id in actor.projects, 'forbidden', 'Project not authorized', 403)
        require(type(limit) is int and 1 <= limit <= 20, 'invalid_arguments', 'Invalid index limit', 422)
        with self.store.engine.connect() as conn:
            room = self._room(conn, project_id, session_id)
            artifacts = self.tables['artifacts']
            rows = conn.execute(select(artifacts.c.metadata).where(
                artifacts.c.project_id == project_id, artifacts.c.session_id == session_id,
                artifacts.c.sequence <= room['latest_sequence']
            ).order_by(artifacts.c.sequence.desc()).limit(limit + 1)).scalars().all()
            keys = ('artifact_id', 'kind', 'title', 'sequence', 'covered_through_sequence', 'actor', 'created_at')
            return {'items': [{key: row[key] for key in keys} for row in rows[:limit]],
                    'has_more': len(rows) > limit}

    def _metadata(self, conn, room):
        artifacts = self.tables['artifacts']
        summary = conn.execute(select(artifacts.c.metadata).where(
            artifacts.c.project_id == room['project_id'], artifacts.c.session_id == room['session_id'],
            artifacts.c.kind == 'summary', artifacts.c.sequence <= room['latest_sequence']
        ).order_by(artifacts.c.sequence.desc()).limit(1)).scalar_one_or_none()
        latest = None if summary is None else {key: summary[key] for key in (
            'artifact_id', 'title', 'covered_through_sequence', 'sha256')}
        if latest is not None:
            latest['reference_count'] = len(summary['reference_message_ids'])
        return {**room, 'visibility': 'project_shared', 'latest_summary': latest}

    def _attachments(self, conn, a):
        table, result = self.tables['attachments'], []
        for identifier in a['attachment_ids']:
            row = conn.execute(select(table.c.metadata).where(
                table.c.project_id == a['project_id'], table.c.session_id == a['session_id'],
                table.c.attachment_id == identifier)).scalar_one_or_none()
            require(row is not None, 'not_found', 'Session or reference not found', 404)
            result.append(row)
        return result

    def _message(self, conn, a, identifier):
        events = self.tables['events']
        row = conn.execute(select(events.c.sequence).where(
            events.c.project_id == a['project_id'], events.c.session_id == a['session_id'],
            events.c.type == 'message', events.c.event_id == identifier)).scalar_one_or_none()
        require(row is not None, 'not_found', 'Session or reference not found', 404)
        return row

    def _record(self, conn, state, name, room, actor, now, kind, payload, search_text=''):
        sequence = state['sequence'] + 1
        event = {'project_id': room['project_id'], 'session_id': room['session_id'],
                 'event_id': uuid.uuid4().hex, 'sequence': sequence, 'type': kind,
                 'actor': actor.public(), 'created_at': now, **payload}
        if kind == 'message':
            event['message_id'] = event['event_id']
        conn.execute(self.tables['events'].insert().values(
            project_id=room['project_id'], session_id=room['session_id'], sequence=sequence,
            event_id=event['event_id'], type=kind, payload=event, search_text=search_text))
        self.store.audit(conn, room['project_id'], state, {
            'operation': name, 'worker_id': actor.id if actor.kind == 'worker' else 'human:' + actor.id,
            'actor_kind': actor.kind, 'at': now, 'context_revision': state['revision'],
            'references': {k: event[k] for k in ('session_id', 'event_id', 'message_id',
                'artifact_id', 'attachment_id') if k in event}})
        table = self.tables['sessions']
        conn.execute(table.update().where(table.c.project_id == room['project_id'],
                                          table.c.session_id == room['session_id']).values(latest_sequence=sequence))
        room['latest_sequence'] = sequence
        return event

    def _write(self, name, a, actor, conn, state, room, now):
        sessions = self.tables['sessions']
        if name == 'create_session':
            room = {'project_id': a['project_id'], 'session_id': uuid.uuid4().hex,
                    'title': a['title'], 'status': 'open', 'version': 1, 'created_at': now,
                    'created_by': actor.public(), 'latest_sequence': state['sequence'], 'attachment_bytes': 0}
            conn.execute(sessions.insert().values(**room))
            self._record(conn, state, name, room, actor, now, 'state', {'status': 'open', 'version': 1})
            return self._metadata(conn, room)
        if name == 'archive_session':
            require(room['version'] == a['expected_version'], 'stale_session', 'Session version changed')
            room['status'] = 'archived' if a['archived'] else 'open'
            room['version'] += 1
            conn.execute(sessions.update().where(sessions.c.project_id == a['project_id'],
                sessions.c.session_id == a['session_id']).values(status=room['status'], version=room['version']))
            self._record(conn, state, name, room, actor, now, 'state',
                         {'status': room['status'], 'version': room['version']})
            return self._metadata(conn, room)
        if name == 'post_session_message':
            if a['reply_to_message_id'] is not None:
                self._message(conn, a, a['reply_to_message_id'])
            attachments = self._attachments(conn, a)
            event = self._record(conn, state, name, room, actor, now, 'message',
                {'body': a['body'], 'body_bytes': len(a['body'].encode('utf-8')),
                 'automatic_reply_depth': a.get('_automatic_reply_depth', 0),
                 'reply_to_message_id': a['reply_to_message_id'], 'attachments': attachments}, a['body'])
            return {key: event[key] for key in ('project_id', 'session_id', 'event_id', 'message_id',
                                               'sequence', 'actor', 'created_at')}
        if name == 'create_session_artifact':
            require(a['covered_through_sequence'] <= room['latest_sequence'], 'invalid_coverage',
                    'Coverage cannot include future events')
            for identifier in a['reference_message_ids']:
                sequence = self._message(conn, a, identifier)
                require(sequence <= a['covered_through_sequence'], 'invalid_coverage',
                        'Reference exceeds declared coverage')
            content = a['content']
            metadata = {'project_id': a['project_id'], 'session_id': a['session_id'],
                        'artifact_id': uuid.uuid4().hex, 'kind': a['kind'], 'title': a['title'],
                        'sha256': hashlib.sha256(content.encode('utf-8')).hexdigest(),
                        'content_bytes': len(content.encode('utf-8')), 'content_chars': len(content),
                        'covered_through_sequence': a['covered_through_sequence'],
                        'reference_message_ids': a['reference_message_ids'],
                        'attachments': self._attachments(conn, a), 'sequence': state['sequence'] + 1,
                        'actor': actor.public(), 'created_at': now}
            conn.execute(self.tables['artifacts'].insert().values(
                project_id=a['project_id'], session_id=a['session_id'], artifact_id=metadata['artifact_id'],
                kind=a['kind'], sequence=metadata['sequence'], metadata=metadata, content=content))
            self._record(conn, state, name, room, actor, now, 'artifact', metadata, a['title'] + '\n' + content)
            return metadata
        if name == 'upload_session_attachment':
            try:
                content = base64.b64decode(a['content_base64'], validate=True)
            except (ValueError, binascii.Error):
                raise HubError('invalid_attachment', 'Attachment must be valid base64', 422) from None
            require(0 < len(content) <= 524288, 'invalid_attachment', 'Attachment must be 1 to 524288 bytes', 422)
            require(room['attachment_bytes'] + len(content) <= 26214400, 'session_quota',
                    'Session attachment quota exceeded')
            metadata = {'project_id': a['project_id'], 'session_id': a['session_id'],
                        'attachment_id': uuid.uuid4().hex, 'filename': a['filename'],
                        'media_type': 'application/octet-stream', 'size': len(content),
                        'sha256': hashlib.sha256(content).hexdigest(), 'sequence': state['sequence'] + 1,
                        'actor': actor.public(), 'created_at': now}
            conn.execute(self.tables['attachments'].insert().values(
                project_id=a['project_id'], session_id=a['session_id'],
                attachment_id=metadata['attachment_id'], metadata=metadata, content=content))
            room['attachment_bytes'] += len(content)
            conn.execute(sessions.update().where(sessions.c.project_id == a['project_id'],
                sessions.c.session_id == a['session_id']).values(attachment_bytes=room['attachment_bytes']))
            self._record(conn, state, name, room, actor, now, 'attachment', metadata)
            return metadata
        raise AssertionError('Unhandled session mutation')

    @staticmethod
    def _page(items, a, envelope, *, listing=False, reserve=0):
        # Account for the entire compact UTF-8 JSON result, including metadata
        # and returned_bytes itself. This is not a tokenizer-specific estimate.
        def response(returned):
            field, cursor, source = ('next_after_id', 'after_id', 'session_id') if listing else (
                'next_after_sequence', 'after_sequence', 'sequence')
            page = {**envelope, 'items': returned,
                    field: returned[-1][source] if returned else a[cursor],
                    'has_more': len(items) > len(returned), 'returned_bytes': 0}
            size = len(compact(page))
            while page['returned_bytes'] != size:
                page['returned_bytes'] = size
                size = len(compact(page))
            return page
        returned = []
        page = response(returned)
        require(page['returned_bytes'] + reserve <= a['max_bytes'], 'response_budget_too_small',
                'Increase max_bytes to include session metadata', 422)
        for item in items[:a['limit']]:
            candidate = response([*returned, item])
            if candidate['returned_bytes'] + reserve > a['max_bytes']:
                require(bool(returned), 'response_budget_too_small',
                        'Increase max_bytes or request a compact event', 422)
                break
            returned.append(item)
            page = candidate
        return page

    def _read(self, name, a, actor, conn, *, reserve=0, through_sequence=None):
        sessions, events = self.tables['sessions'], self.tables['events']
        if name == 'list_sessions':
            statement = select(sessions).where(sessions.c.project_id.in_(actor.projects))
            if a['project_id'] is not None:
                statement = statement.where(sessions.c.project_id == a['project_id'])
            if a['after_id'] is not None:
                statement = statement.where(sessions.c.session_id > a['after_id'])
            if a['status'] != 'all':
                statement = statement.where(sessions.c.status == a['status'])
            rows = conn.execute(statement.order_by(sessions.c.session_id).limit(a['limit'] + 1)).mappings().all()
            items = [self._metadata(conn, dict(row)) for row in rows]
            return self._page(items, a, {}, listing=True)
        room = self._room(conn, a['project_id'], a['session_id']) if a.get('session_id') else None
        if name == 'search_sessions':
            # Literal case-sensitive matching, never regex/wildcards or SQL text.
            position = func.instr(events.c.search_text, a['query']) if self.store.sqlite else func.strpos(events.c.search_text, a['query'])
            highwater = conn.execute(select(projects.c.state).where(projects.c.id == a['project_id'])).scalar_one_or_none()
            require(highwater is not None, 'not_found', 'Project not found', 404)
            statement = select(events.c.sequence, events.c.session_id, events.c.event_id, events.c.type,
                func.substr(events.c.search_text, position, 512).label('excerpt')).where(
                events.c.project_id == a['project_id'], events.c.sequence > a['after_sequence'],
                events.c.sequence <= highwater['sequence'], position > 0)
            if room is not None:
                statement = statement.where(events.c.session_id == room['session_id'])
            rows = conn.execute(statement.order_by(events.c.sequence).limit(a['limit'] + 1)).mappings().all()
            items = [{'project_id': a['project_id'], 'session_id': row['session_id'],
                      'event_id': row['event_id'], 'sequence': row['sequence'], 'type': row['type'],
                      **({'message_id': row['event_id']} if row['type'] == 'message' else {}),
                      'snippet': snippet(row['excerpt'])} for row in rows]
            artifacts = self.tables['artifacts']
            for item in items:
                if item['type'] == 'artifact':
                    item['artifact_id'] = conn.execute(select(artifacts.c.artifact_id).where(
                        artifacts.c.project_id == a['project_id'], artifacts.c.session_id == item['session_id'],
                        artifacts.c.sequence == item['sequence'])).scalar_one()
            return self._page(items, a, {'project_id': a['project_id']})
        if name == 'read_session':
            ceiling = room['latest_sequence'] if through_sequence is None else min(room['latest_sequence'], through_sequence)
            rows = conn.execute(select(events.c.payload).where(
                events.c.project_id == a['project_id'], events.c.session_id == a['session_id'],
                events.c.sequence > a['after_sequence'], events.c.sequence <= ceiling
            ).order_by(events.c.sequence).limit(a['limit'] + 1)).scalars().all()
            for event in rows:
                if event['type'] == 'message':
                    if not a['full_text']:
                        event['body'] = snippet(event['body'])
                    event['body_truncated'] = len(event['body'].encode('utf-8')) < event['body_bytes']
            return self._page(rows, a, {'session': self._metadata(conn, room)}, reserve=reserve)
        if name == 'get_session_artifact':
            table = self.tables['artifacts']
            row = conn.execute(select(table.c.metadata, func.substr(table.c.content, a['offset'] + 1,
                a['limit_chars']).label('chunk')).where(table.c.project_id == a['project_id'],
                table.c.session_id == a['session_id'], table.c.artifact_id == a['artifact_id'])).mappings().one_or_none()
            require(row is not None, 'not_found', 'Session or reference not found', 404)
            end = a['offset'] + len(row['chunk'])
            return {**row['metadata'], 'content': row['chunk'], 'offset': a['offset'],
                    'next_offset': end, 'has_more': end < row['metadata']['content_chars']}
        if name == 'read_session_attachment':
            table = self.tables['attachments']
            row = conn.execute(select(table.c.metadata, func.substr(table.c.content, a['offset'] + 1,
                a['limit_bytes']).label('chunk')).where(table.c.project_id == a['project_id'],
                table.c.session_id == a['session_id'], table.c.attachment_id == a['attachment_id'])).mappings().one_or_none()
            require(row is not None, 'not_found', 'Session or reference not found', 404)
            data = bytes(row['chunk'])
            end = a['offset'] + len(data)
            return {**row['metadata'], 'content_base64': base64.b64encode(data).decode('ascii'), 'offset': a['offset'],
                    'next_offset': end, 'has_more': end < row['metadata']['size']}
        raise AssertionError('Unhandled session read')
