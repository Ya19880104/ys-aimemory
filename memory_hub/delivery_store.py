"""Additive v6 durable relay state, isolated from existing room events."""
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Float,
                        ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Table,
                        UniqueConstraint)


def define_tables(metadata):
    def room_fk():
        return ForeignKeyConstraint(['project_id', 'session_id'],
                                    ['collab_sessions.project_id', 'collab_sessions.session_id'])
    controls = Table('collab_room_control', metadata,
        Column('project_id', String(128), primary_key=True), Column('session_id', String(32), primary_key=True),
        Column('paused', Boolean, nullable=False), Column('version', Integer, nullable=False), room_fk())
    bindings = Table('collab_bindings', metadata,
        Column('binding_id', String(32), primary_key=True),
        Column('project_id', String(128), nullable=False), Column('session_id', String(32), nullable=False),
        Column('worker_id', String(128), nullable=False), Column('client', String(16), nullable=False),
        Column('display_name', String(80), nullable=False), Column('native_session_hash', String(64), nullable=False),
        Column('generation', Integer, nullable=False), Column('version', Integer, nullable=False),
        Column('enabled', Boolean, nullable=False), Column('created_at', Float, nullable=False),
        Column('released_at', Float),
        Column('expires_at', Float, nullable=False), Column('last_seen_at', Float, nullable=False),
        Column('processed_sequence', BigInteger, nullable=False), Column('max_turns', Integer, nullable=False),
        Column('turns_used', Integer, nullable=False), room_fk(),
        UniqueConstraint('project_id', 'session_id', 'worker_id', name='collab_binding_worker_room'),
        CheckConstraint('processed_sequence >= 0 AND turns_used >= 0 AND max_turns > 0', name='collab_binding_budget'))
    deliveries = Table('collab_deliveries', metadata,
        Column('delivery_id', String(32), primary_key=True),
        Column('binding_id', String(32), ForeignKey('collab_bindings.binding_id'), nullable=False),
        Column('generation', Integer, nullable=False), Column('after_sequence', BigInteger, nullable=False),
        Column('through_sequence', BigInteger, nullable=False), Column('messages', JSON, nullable=False),
        Column('read_message_ids', JSON, nullable=False), Column('status', String(24), nullable=False),
        Column('lease_id', String(32), nullable=False), Column('lease_until', Float, nullable=False),
        Column('attempts', Integer, nullable=False), Column('created_at', Float, nullable=False),
        Column('dispatched_at', Float), Column('read_at', Float), Column('replied_at', Float),
        Column('reply_message_id', String(32)), Column('reply_sequence', BigInteger),
        Index('collab_binding_delivery', 'binding_id', 'generation', 'created_at'),
        CheckConstraint('through_sequence > after_sequence AND attempts >= 0', name='collab_delivery_range'))
    joins = Table('collab_binding_requests', metadata,
        Column('project_id', String(128), ForeignKey('projects.id'), primary_key=True),
        Column('operation', String(16), primary_key=True), Column('actor_kind', String(16), primary_key=True),
        Column('worker_id', String(128), primary_key=True), Column('request_key', String(128), primary_key=True),
        Column('payload_hash', String(64), nullable=False), Column('result', JSON, nullable=False))
    return {'controls': controls, 'bindings': bindings, 'deliveries': deliveries, 'joins': joins}
