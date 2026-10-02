"""Private project dialogue, independent of task leases and knowledge revisions.

The caller holds the project transaction lock. A new message uses the sequence
of the audit event committed with it, so cursors cannot skip a later commit that
was allocated an earlier sequence. Reset the cursor when changing project,
identity or thread filters. Content is untrusted data, never task authority.
"""
import hashlib
import json
import uuid

from sqlalchemy import BigInteger, CheckConstraint, Column, Float, ForeignKey, Index, String, Table, Text, UniqueConstraint, or_, select


def define_table(metadata):
    return Table('project_messages', metadata,
        Column('project_id', String(128), ForeignKey('projects.id'), primary_key=True),
        Column('sequence', BigInteger, primary_key=True),
        Column('message_id', String(32), nullable=False),
        Column('thread_id', String(128), nullable=False),
        Column('sender_worker_id', String(128), nullable=False),
        Column('recipient_worker_id', String(128), nullable=False),
        Column('body', Text, nullable=False),
        Column('created_at', Float, nullable=False),
        Column('reply_to_message_id', String(128)),
        Column('idempotency_key', String(128), nullable=False),
        Column('payload_hash', String(64), nullable=False),
        UniqueConstraint('project_id', 'message_id', name='message_project_id_unique'),
        UniqueConstraint('project_id', 'sender_worker_id', 'idempotency_key', name='message_sender_key_unique'),
        CheckConstraint('sequence > 0', name='message_sequence_positive'),
        Index('message_sender_sequence', 'project_id', 'sender_worker_id', 'sequence'),
        Index('message_recipient_sequence', 'project_id', 'recipient_worker_id', 'sequence'))


def require(condition, code, message, status=409):
    if not condition:
        from .store import HubError
        raise HubError(code, message, status)


class MessageStore:
    def __init__(self, table):
        self.table = table
        self.public_columns = tuple(column for column in table.c if column.name not in {'idempotency_key', 'payload_hash'})

    def _public(self, row):
        return {column.name:row[column.name] for column in self.public_columns}

    def send(self, conn, state, arguments, principal, now, principals):
        a, table = arguments, self.table
        payload = {key:value for key,value in a.items() if key!='idempotency_key'}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        previous = conn.execute(select(table).where(table.c.project_id==a['project_id'],
            table.c.sender_worker_id==principal.worker_id, table.c.idempotency_key==a['idempotency_key'])).mappings().one_or_none()
        if previous is not None:
            require(previous['payload_hash']==digest, 'idempotency_conflict', 'Idempotency key was already used for different arguments')
            # A retry returns an existing result even if its recipient was retired.
            # It never inserts a new message or generates another audit event.
            return self._public(previous), True
        recipient = a['recipient_worker_id']
        require(recipient!=principal.worker_id, 'same_worker', 'Messages must target another worker')
        require(any(identity.worker_id==recipient and a['project_id'] in identity.projects for identity in principals),
                'unknown_recipient', 'Recipient must be active and authorized for this project')
        if a['reply_to_message_id'] is not None:
            parent = conn.execute(select(table.c.message_id).where(
                table.c.project_id==a['project_id'], table.c.message_id==a['reply_to_message_id'],
                table.c.thread_id==a['thread_id'], or_(
                    (table.c.sender_worker_id==principal.worker_id) & (table.c.recipient_worker_id==recipient),
                    (table.c.sender_worker_id==recipient) & (table.c.recipient_worker_id==principal.worker_id)))).scalar_one_or_none()
            require(parent is not None, 'not_found', 'Message not found', 404)
        record = {'project_id':a['project_id'], 'sequence':state['sequence']+1, 'message_id':uuid.uuid4().hex,
                  'thread_id':a['thread_id'], 'sender_worker_id':principal.worker_id,
                  'recipient_worker_id':recipient, 'body':a['body'], 'created_at':now,
                  'reply_to_message_id':a['reply_to_message_id']}
        conn.execute(table.insert().values(**record, idempotency_key=a['idempotency_key'], payload_hash=digest))
        return record, False

    def list(self, conn, arguments, principal):
        a, table = arguments, self.table
        statement = select(*self.public_columns).where(table.c.project_id==a['project_id'],
            table.c.sequence>a['after_sequence'], or_(table.c.sender_worker_id==principal.worker_id,
                                                     table.c.recipient_worker_id==principal.worker_id))
        if a['thread_id'] is not None:
            statement = statement.where(table.c.thread_id==a['thread_id'])
        rows = conn.execute(statement.order_by(table.c.sequence).limit(a['limit']+1)).mappings().all()
        items = [dict(row) for row in rows[:a['limit']]]
        return {'project_id':a['project_id'], 'worker_id':principal.worker_id, 'items':items,
                'next_after_sequence':items[-1]['sequence'] if items else a['after_sequence'],
                'has_more':len(rows)>a['limit']}
