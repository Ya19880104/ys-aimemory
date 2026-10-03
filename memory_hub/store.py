"""Single-project serialized transactions. PostgreSQL is the deployment backend.

The JSON project aggregate is intentionally simple for the first vertical slice.
It is not an unbounded production-scale event store. Audit events are separate,
append-only through the application. DB owners can of course alter their DB.
"""
from contextlib import contextmanager
from copy import deepcopy
import time
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, JSON, select, text, inspect
from .index import KnowledgeIndex, index_tables
from .web_store import define_tables
from .credential_store import define_tables as define_credential_tables
from .message_store import define_table as define_message_table
from .session_store import define_tables as define_session_tables
from .delivery_store import define_tables as define_delivery_tables
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

metadata = MetaData()
projects = Table("projects", metadata, Column("id", String(128), primary_key=True), Column("state", JSON, nullable=False))
events = Table("audit_events", metadata, Column("project_id", String(128), primary_key=True), Column("sequence", Integer, primary_key=True), Column("event", JSON, nullable=False))

index_schema = index_tables(metadata)
WEB_TABLES = define_tables(metadata)
CREDENTIAL_TABLES = define_credential_tables(metadata)
messages = define_message_table(metadata)
SESSION_TABLES = define_session_tables(metadata)
DELIVERY_TABLES = define_delivery_tables(metadata)
requests = Table("idempotent_requests", metadata, Column("project_id", String(128), primary_key=True), Column("worker_id", String(128), primary_key=True), Column("request_key", String(128), primary_key=True), Column("payload_hash", String(64), nullable=False), Column("result", JSON, nullable=False))

class HubError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

class Store:
    def __init__(self, url, allow_sqlite=False):
        if not url.startswith("postgresql+psycopg://") and not (allow_sqlite and url.startswith("sqlite")):
            raise RuntimeError("HUB_DATABASE_URL must use postgresql+psycopg; SQLite requires explicit demo/test opt-in")
        self.engine = create_engine(url, pool_pre_ping=True, connect_args={"timeout":30} if url.startswith("sqlite") else {})
        self.sqlite = self.engine.dialect.name == "sqlite"
        self.index = KnowledgeIndex(self.sqlite, index_schema)
        # Serialize non-destructive additive migrations across concurrent starts.
        with self.engine.connect() as conn:
            if self.sqlite:
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
                conn.execute(text("SELECT pg_advisory_xact_lock(761981234)"))
            try:
                versions = (conn.execute(select(self.index.migrations.c.version)).scalars().all()
                            if inspect(conn).has_table(self.index.migrations.name) else [])
                if versions and max(versions) > 6:
                    raise RuntimeError("Database schema is newer than this server; use a compatible version")
                metadata.create_all(conn)
                self.index.install(conn)
                insert = sqlite_insert if self.sqlite else pg_insert
                for version in (1, 2, 3, 4, 5, 6):
                    conn.execute(insert(self.index.migrations).values(version=version,applied_at=time.time()).on_conflict_do_nothing())
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextmanager
    def transaction(self, project_id, create=False, *, initialize_index=True):
        with self.engine.connect() as conn:
            if self.sqlite:
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
            try:
                if create:
                    insert = sqlite_insert if self.sqlite else pg_insert
                    result = conn.execute(insert(projects).values(id=project_id, state={"revision":1,"sources":{},"tasks":{},"packets":{},"decisions":{},"sequence":0}).on_conflict_do_nothing().returning(projects.c.id)).scalar_one_or_none()
                    if result is None:
                        raise HubError("project_exists", "Project already exists")
                statement = select(projects.c.state).where(projects.c.id == project_id)
                if not self.sqlite:
                    statement = statement.with_for_update()
                state = conn.execute(statement).scalar_one_or_none()
                if state is None:
                    raise HubError("not_found", "Project not found", 404)
                original = state
                state = deepcopy(state)
                if initialize_index:
                    self.index.initialize_project(conn,project_id,state)
                yield state, conn
                if state != original:
                    conn.execute(projects.update().where(projects.c.id == project_id).values(state=state))
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def audit(self, conn, project_id, state, event):
        state["sequence"] += 1
        conn.execute(events.insert().values(project_id=project_id, sequence=state["sequence"], event=event))

    def read_audit(self, conn, project_id):
        rows = conn.execute(select(events.c.sequence, events.c.event).where(events.c.project_id == project_id).order_by(events.c.sequence.desc()).limit(200)).all()
        return [{"sequence":r.sequence, **r.event} for r in reversed(rows)]
