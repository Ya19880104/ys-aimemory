"""Database-backed MCP worker credentials; raw tokens are returned only on creation.

The web boundary owns session, role, scope and CSRF authorization. This registry
enforces identity invariants and commits each mutation with its project audit.
Revocation rejects subsequent authentication; it does not cancel requests that
were already authenticated and are in flight.
"""
import hashlib
import math
import re
import secrets
import uuid

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Integer, String, Table, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .models import Principal


def define_tables(metadata):
    return {
        'projects': Table('mcp_managed_projects', metadata,
            Column('project_id', String(128), ForeignKey('projects.id'), primary_key=True),
            Column('owner_id', String(36), nullable=False, index=True),
            Column('created_at', Float, nullable=False)),
        'identities': Table('mcp_worker_identities', metadata,
            Column('worker_id', String(128), primary_key=True),
            Column('kind', String(16), nullable=False),
            CheckConstraint("kind IN ('env', 'managed')", name='mcp_worker_identity_kind')),
        'credentials': Table('mcp_credentials', metadata,
            Column('token_id', String(32), primary_key=True),
            Column('token_hash', String(64), nullable=False, unique=True),
            Column('worker_id', String(128), ForeignKey('mcp_worker_identities.worker_id'), nullable=False, unique=True),
            Column('project_id', String(128), ForeignKey('projects.id'), nullable=False, index=True),
            Column('role', String(16), nullable=False),
            Column('version', Integer, nullable=False),
            Column('created_by', String(128), nullable=False),
            Column('created_at', Float, nullable=False),
            Column('rotated_at', Float),
            Column('revoked_at', Float),
            CheckConstraint("role = 'worker'", name='mcp_credential_worker_role'),
            CheckConstraint('version >= 1', name='mcp_credential_positive_version')),
    }


def require(condition, code, message, status=409):
    if not condition:
        # The store imports define_tables while registering the shared metadata.
        from .store import HubError
        raise HubError(code, message, status)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', value),
            'invalid_credentials', 'Expected a valid project or worker identifier', 400)
    return value


def owner_identifier(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        require(False, 'invalid_credentials', 'Owner ID must be a UUID', 400)


def actor_time(actor, now):
    require(isinstance(actor, str) and 0 < len(actor.strip()) <= 128,
            'invalid_credentials', 'An audit actor is required', 400)
    require(isinstance(now, (int, float)) and not isinstance(now, bool) and math.isfinite(now),
            'invalid_credentials', 'A finite event time is required', 400)


class Registry:
    def __init__(self, store, reserved_principals):
        from .store import CREDENTIAL_TABLES
        self.store = store
        self.projects = CREDENTIAL_TABLES['projects']
        self.identities = CREDENTIAL_TABLES['identities']
        self.credentials = CREDENTIAL_TABLES['credentials']
        self.reserved = frozenset(['web-operator', *(p.worker_id for p in reserved_principals)])
        self.metadata_columns = tuple(c for c in self.credentials.c if c.name != 'token_hash')
        self._reserve_environment()

    def _claim_identity(self, conn, worker_id, kind):
        insert = sqlite_insert if self.store.sqlite else pg_insert
        # INSERT rowcount is not preserved by all drivers after cursor close.
        inserted = conn.execute(insert(self.identities).values(worker_id=worker_id, kind=kind)
                                .on_conflict_do_nothing().returning(self.identities.c.worker_id)).scalar_one_or_none()
        actual = conn.execute(select(self.identities.c.kind).where(self.identities.c.worker_id == worker_id)).scalar_one()
        return actual, inserted is not None

    def _reserve_environment(self):
        # Persistent reservation prevents different/rolling instance configs from
        # issuing a managed token for an env identity known to another instance.
        with self.store.engine.connect() as conn:
            if self.store.sqlite:
                conn.exec_driver_sql('BEGIN IMMEDIATE')
            else:
                conn.begin()
            try:
                for worker_id in sorted(self.reserved):
                    actual, _ = self._claim_identity(conn, worker_id, 'env')
                    if actual != 'env':
                        raise RuntimeError('Configured worker identity conflicts with a managed credential')
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @staticmethod
    def _secret():
        raw = secrets.token_urlsafe(32)
        return raw, hashlib.sha256(raw.encode('ascii')).hexdigest()

    def _audit(self, conn, project_id, state, operation, actor, now, references):
        self.store.audit(conn, project_id, state, {
            'operation': operation, 'worker_id': actor, 'at': now,
            'context_revision': state['revision'], 'references': references,
        })

    def create_project(self, project_id, owner_id, actor, now):
        project_id, owner_id = identifier(project_id), owner_identifier(owner_id)
        actor_time(actor, now)
        with self.store.transaction(project_id, create=True) as (state, conn):
            conn.execute(self.projects.insert().values(project_id=project_id, owner_id=owner_id, created_at=now))
            self._audit(conn, project_id, state, 'create_managed_project', actor, now, {'owner_id': owner_id})
        return {'project_id': project_id, 'owner_id': owner_id, 'context_revision': state['revision']}

    def owned_projects(self, owner_id):
        owner_id = owner_identifier(owner_id)
        with self.store.engine.connect() as conn:
            return tuple(conn.execute(select(self.projects.c.project_id).where(
                self.projects.c.owner_id == owner_id).order_by(self.projects.c.project_id)).scalars())

    def issue(self, project_id, worker_id, actor, now):
        project_id, worker_id = identifier(project_id), identifier(worker_id)
        actor_time(actor, now)
        require(worker_id not in self.reserved, 'worker_reserved', 'Worker identity is reserved')
        raw, digest = self._secret()
        record = {'token_id': uuid.uuid4().hex, 'worker_id': worker_id, 'project_id': project_id,
                  'role': 'worker', 'version': 1, 'created_by': actor, 'created_at': now,
                  'rotated_at': None, 'revoked_at': None}
        try:
            with self.store.transaction(project_id) as (state, conn):
                actual, inserted = self._claim_identity(conn, worker_id, 'managed')
                require(actual != 'env', 'worker_reserved', 'Worker identity is reserved')
                require(inserted, 'worker_exists', 'Worker identity has already been used')
                conn.execute(self.credentials.insert().values(**record, token_hash=digest))
                self._audit(conn, project_id, state, 'issue_mcp_credential', actor, now,
                            {'token_id': record['token_id'], 'worker_id': worker_id, 'version': 1})
        except IntegrityError:
            # A competing issue on another project can win the global unique ID.
            require(False, 'worker_exists', 'Worker identity has already been used')
        return {**record, 'token': raw}

    def _mutate(self, project_id, token_id, expected_version, actor, now, revoke):
        project_id = identifier(project_id)
        actor_time(actor, now)
        require(isinstance(token_id, str) and re.fullmatch(r'[0-9a-f]{32}', token_id),
                'invalid_credentials', 'Invalid credential ID', 400)
        require(type(expected_version) is int and expected_version >= 1,
                'invalid_credentials', 'A positive credential version is required', 400)
        raw, digest = (None, None) if revoke else self._secret()
        with self.store.transaction(project_id) as (state, conn):
            statement = select(self.credentials).where(self.credentials.c.project_id == project_id,
                                                       self.credentials.c.token_id == token_id)
            if not self.store.sqlite:
                statement = statement.with_for_update()
            row = conn.execute(statement).mappings().one_or_none()
            require(row is not None, 'credential_not_found', 'Credential not found', 404)
            require(row['revoked_at'] is None, 'credential_revoked', 'Credential has been revoked')
            require(row['version'] == expected_version, 'credential_conflict', 'Credential version has changed')
            updates = {'version': expected_version + 1}
            if revoke:
                updates['revoked_at'] = now
            else:
                updates.update(token_hash=digest, rotated_at=now)
            changed = conn.execute(self.credentials.update().where(
                self.credentials.c.token_id == token_id,
                self.credentials.c.version == expected_version,
                self.credentials.c.revoked_at.is_(None)).values(**updates))
            require(changed.rowcount == 1, 'credential_conflict', 'Credential version has changed')
            self._audit(conn, project_id, state, 'revoke_mcp_credential' if revoke else 'rotate_mcp_credential',
                        actor, now, {'token_id': token_id, 'worker_id': row['worker_id'], 'version': updates['version']})
            record = {c.name: row[c.name] for c in self.metadata_columns}
            record.update({k: v for k, v in updates.items() if k != 'token_hash'})
        return None if revoke else {**record, 'token': raw}

    def rotate(self, project_id, token_id, expected_version, actor, now):
        return self._mutate(project_id, token_id, expected_version, actor, now, False)

    def revoke(self, project_id, token_id, expected_version, actor, now):
        self._mutate(project_id, token_id, expected_version, actor, now, True)

    def list_credentials(self, project_ids):
        project_ids = tuple(identifier(p) for p in project_ids)
        if not project_ids:
            return []
        with self.store.engine.connect() as conn:
            rows = conn.execute(select(*self.metadata_columns).where(
                self.credentials.c.project_id.in_(project_ids)).order_by(
                self.credentials.c.project_id, self.credentials.c.worker_id)).mappings()
            return [dict(row) for row in rows]

    def authenticate(self, raw):
        # Reject malformed/oversized credentials before hashing or a database query.
        if not isinstance(raw, str) or not 32 <= len(raw) <= 512 or not raw.isascii():
            return None
        digest = hashlib.sha256(raw.encode('ascii')).hexdigest()
        with self.store.engine.connect() as conn:
            row = conn.execute(select(self.credentials.c.worker_id, self.credentials.c.project_id).where(
                self.credentials.c.token_hash == digest, self.credentials.c.revoked_at.is_(None))).mappings().one_or_none()
        if row is None or row['worker_id'] in self.reserved:
            return None
        return Principal(worker_id=row['worker_id'], projects=[row['project_id']], role='worker')

    def principals(self, conn=None):
        if conn is None:
            with self.store.engine.connect() as connection:
                return self.principals(connection)
        rows = conn.execute(select(self.credentials.c.worker_id, self.credentials.c.project_id).where(
            self.credentials.c.revoked_at.is_(None)).order_by(self.credentials.c.worker_id)).mappings()
        return [Principal(worker_id=row['worker_id'], projects=[row['project_id']], role='worker')
                for row in rows if row['worker_id'] not in self.reserved]
