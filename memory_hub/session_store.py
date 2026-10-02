"""Separate shared-room tables; private worker messages are never migrated here."""
from sqlalchemy import BigInteger, CheckConstraint, Column, Float, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, LargeBinary, String, Table, Text, UniqueConstraint


def define_tables(metadata):
    sessions = Table('collab_sessions', metadata,
        Column('project_id', String(128), ForeignKey('projects.id'), primary_key=True),
        Column('session_id', String(32), primary_key=True),
        Column('title', String(200), nullable=False), Column('status', String(16), nullable=False),
        Column('version', Integer, nullable=False), Column('created_at', Float, nullable=False),
        Column('created_by', JSON, nullable=False), Column('latest_sequence', BigInteger, nullable=False),
        Column('attachment_bytes', Integer, nullable=False),
        UniqueConstraint('session_id', name='collab_session_id_unique'),
        CheckConstraint('attachment_bytes >= 0 AND attachment_bytes <= 26214400', name='collab_session_quota'))
    def room_fk():
        return ForeignKeyConstraint(['project_id','session_id'], ['collab_sessions.project_id','collab_sessions.session_id'])
    events = Table('collab_events', metadata,
        Column('project_id', String(128), primary_key=True), Column('sequence', BigInteger, primary_key=True),
        Column('session_id', String(32), nullable=False), Column('event_id', String(32), nullable=False),
        Column('type', String(16), nullable=False), Column('payload', JSON, nullable=False),
        Column('search_text', Text, nullable=False), room_fk(),
        UniqueConstraint('project_id','event_id', name='collab_event_id_unique'),
        Index('collab_room_sequence','project_id','session_id','sequence'))
    artifacts = Table('collab_artifacts', metadata,
        Column('project_id', String(128), primary_key=True), Column('session_id', String(32), primary_key=True),
        Column('artifact_id', String(32), primary_key=True), Column('kind', String(32), nullable=False),
        Column('sequence', BigInteger, nullable=False), Column('metadata', JSON, nullable=False),
        Column('content', Text, nullable=False), room_fk(),
        Index('collab_summary_sequence','project_id','session_id','kind','sequence'))
    attachments = Table('collab_attachments', metadata,
        Column('project_id', String(128), primary_key=True), Column('session_id', String(32), primary_key=True),
        Column('attachment_id', String(32), primary_key=True), Column('metadata', JSON, nullable=False),
        Column('content', LargeBinary, nullable=False), room_fk())
    requests = Table('collab_requests', metadata,
        Column('project_id', String(128), ForeignKey('projects.id'), primary_key=True),
        Column('session_id', String(32), primary_key=True), Column('actor_kind', String(16), primary_key=True),
        Column('actor_id', String(128), primary_key=True), Column('operation', String(40), primary_key=True),
        Column('request_key', String(128), primary_key=True), Column('payload_hash', String(64), nullable=False),
        Column('result', JSON, nullable=False))
    return {'sessions':sessions, 'events':events, 'artifacts':artifacts, 'attachments':attachments, 'requests':requests}
