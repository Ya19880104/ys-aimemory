"""Persistent human identities; all changes share the browser-auth DB lock.

The environment is a one-time bootstrap, never an account synchronization feed.
User IDs are distinct from worker identities and browser cookies are not tokens.
"""
from dataclasses import dataclass
import secrets
import unicodedata
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .credential_store import identifier
from .store import WEB_TABLES, CREDENTIAL_TABLES, HubError, projects as project_table
from .web_password import hash_password, verify_password, valid_hash


@dataclass(frozen=True)
class WebPrincipal:
    user_id: str
    username: str
    display_name: str
    projects: tuple[str, ...]
    role: str
    can_manage_users: bool
    security_version: int
    version: int


def text(value, limit=128):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(unicodedata.category(c).startswith('C') for c in value):
        raise HubError('invalid_account', '名稱不可空白、過長或含控制字元。', 400)
    return value.strip()


def username_key(value):
    key = unicodedata.normalize('NFKC', text(value)).casefold()
    if len(key) > 256:
        raise HubError('invalid_account', '正規化後的登入名稱過長。', 400)
    return key


def account_values(display_name, role, scopes, manager):
    if role not in {'admin', 'member', 'read_only'} or type(manager) is not bool:
        raise HubError('invalid_account', '帳號角色或權限格式不正確。', 400)
    if not isinstance(scopes, (tuple, list)) or len(scopes) > 100:
        raise HubError('invalid_account', '專案範圍格式不正確，最多 100 項。', 400)
    return text(display_name), role, tuple(sorted({identifier(p) for p in scopes})), manager


def password_digest(password):
    if not isinstance(password, str) or not 10 <= len(password) <= 1024 or '\x00' in password:
        raise HubError('invalid_password', '密碼必須為 10–1024 字元且不得含 NUL。', 400)
    return hash_password(password)


def user_identifier(value):
    try:
        canonical = str(UUID(value))
        if value != canonical:
            raise ValueError('Non-canonical ID')
        return canonical
    except (ValueError, TypeError, AttributeError):
        raise HubError('invalid_account', '帳號識別格式不正確。', 400) from None


class WebUsers:
    def __init__(self, auth):
        self.auth, self.store = auth, auth.store
        self.users, self.grants = WEB_TABLES['users'], WEB_TABLES['grants']
        self.bootstrap_table, self.audit_table = WEB_TABLES['bootstrap'], WEB_TABLES['user_audit']
        # Unknown usernames still pay the same password-verification cost.
        self.dummy_hash = hash_password(secrets.token_urlsafe(32))

    def _audit(self, conn, actor_id, target_id, operation, details=None):
        conn.execute(self.audit_table.insert().values(actor_id=actor_id, target_id=target_id,
            operation=operation, at=self.auth.clock(), details=details or {}))

    def _load(self, conn, user_id):
        return conn.execute(select(self.users).where(self.users.c.user_id == user_id)).mappings().one_or_none()

    def _identity(self, conn, row):
        scopes = tuple(conn.execute(select(self.grants.c.project_id).where(
            self.grants.c.user_id == row['user_id']).order_by(self.grants.c.project_id)).scalars())
        return WebPrincipal(**{k: row[k] for k in ('user_id', 'username', 'display_name', 'role',
            'can_manage_users', 'security_version', 'version')}, projects=scopes)

    def bootstrap(self, conn, config):
        if conn.execute(select(self.bootstrap_table.c.id).where(self.bootstrap_table.c.id == 1)).scalar_one_or_none() is not None:
            return
        if not config or not getattr(config, 'username', ''):
            return
        if not valid_hash(config.password_hash):
            raise ValueError('A valid bootstrap password hash is required')
        user_id = str(UUID(config.owner_id)) if config.owner_id else str(uuid4())
        scopes = set(config.projects)
        # Existing ownership is migration data, independent of the MCP UI flag.
        if config.owner_id and config.role == 'admin':
            scopes.update(conn.execute(select(CREDENTIAL_TABLES['projects'].c.project_id).where(
                CREDENTIAL_TABLES['projects'].c.owner_id == user_id)).scalars())
        display, role, scopes, manager = account_values(config.username, config.role, tuple(scopes), config.role == 'admin')
        now = self.auth.clock()
        conn.execute(self.users.insert().values(user_id=user_id, username=config.username,
            username_key=username_key(config.username), display_name=display, password_hash=config.password_hash,
            role=role, enabled=True, can_manage_users=manager, security_version=1, version=1,
            created_at=now, updated_at=now))
        self._grants(conn, user_id, scopes)
        conn.execute(self.bootstrap_table.insert().values(id=1, user_id=user_id, created_at=now))
        self._audit(conn, user_id, user_id, 'bootstrap', {'role': role, 'can_manage_users': manager})

    def configured(self, conn):
        return conn.execute(select(self.bootstrap_table.c.id).where(self.bootstrap_table.c.id == 1)).scalar_one_or_none() is not None

    def _grants(self, conn, user_id, scopes):
        conn.execute(self.grants.delete().where(self.grants.c.user_id == user_id))
        if scopes:
            conn.execute(self.grants.insert(), [{'user_id': user_id, 'project_id': p} for p in scopes])

    def authenticate(self, username, password):
        try:
            key = username_key(username)
        except HubError:
            key = ''
        with self.store.engine.connect() as conn:
            row = conn.execute(select(self.users).where(self.users.c.username_key == key)).mappings().one_or_none()
        verified = verify_password(password, row['password_hash'] if row else self.dummy_hash)
        if not verified or not row or not row['enabled']:
            return None
        # start_session rechecks security_version after the expensive hash.
        with self.store.engine.connect() as conn:
            latest = self._load(conn, row['user_id'])
            if not latest or not latest['enabled'] or latest['security_version'] != row['security_version']:
                return None
            return self._identity(conn, latest)

    def _actor(self, conn, current, *, manager=True):
        record = self.auth._get(conn, (current or {}).get('_key', ''), 'session')
        if not record:
            raise HubError('unauthorized', '登入已失效，請重新登入。', 401)
        row = self._load(conn, record['user_id'])
        if manager and not row['can_manage_users']:
            raise HubError('forbidden', '此帳號沒有使用者管理權限。', 403)
        return row

    def _target(self, conn, target_id, expected_version):
        row = self._load(conn, user_identifier(target_id))
        if row is None:
            raise HubError('not_found', '找不到帳號。', 404)
        if type(expected_version) is not int or expected_version != row['version']:
            raise HubError('account_conflict', '帳號已更新，請重新載入。', 409)
        return row

    def _last_manager(self, conn, row, enabled, manager):
        if row['enabled'] and row['can_manage_users'] and not (enabled and manager):
            count = conn.execute(select(func.count()).select_from(self.users).where(
                self.users.c.enabled.is_(True), self.users.c.can_manage_users.is_(True))).scalar_one()
            if count <= 1:
                raise HubError('last_manager', '必須保留至少一位啟用中的帳號管理員。', 409)

    def _update(self, conn, row, **values):
        values.update(version=row['version'] + 1, security_version=row['security_version'] + 1,
                      updated_at=self.auth.clock())
        conn.execute(self.users.update().where(self.users.c.user_id == row['user_id']).values(**values))

    def list(self, current, after='', limit=20):
        if not 1 <= limit <= 50 or len(after) > 36:
            raise HubError('invalid_page', '分頁格式不正確。', 400)
        if after: after = user_identifier(after)
        with self.auth.transaction() as conn:
            self._actor(conn, current)
            rows = conn.execute(select(self.users).where(self.users.c.user_id > after).order_by(
                self.users.c.user_id).limit(limit + 1)).mappings().all()
            return {'items': [self._public(conn, row) for row in rows[:limit]],
                    'next_after': rows[limit - 1]['user_id'] if len(rows) > limit else None}

    def _public(self, conn, row):
        identity = self._identity(conn, row)
        return {**identity.__dict__, 'enabled': row['enabled']}

    def get(self, current, user_id):
        user_id = user_identifier(user_id)
        with self.auth.transaction() as conn:
            self._actor(conn, current)
            row = self._load(conn, user_id)
            if row is None:
                raise HubError('not_found', '找不到帳號。', 404)
            return self._public(conn, row)

    def create(self, current, username, display_name, password, role, projects, can_manage_users=False):
        key = username_key(username)
        display, role, scopes, manager = account_values(display_name, role, projects, can_manage_users)
        digest = password_digest(password)
        user_id, now = str(uuid4()), self.auth.clock()
        try:
            with self.auth.transaction() as conn:
                actor = self._actor(conn, current)
                conn.execute(self.users.insert().values(user_id=user_id, username=text(username), username_key=key,
                    display_name=display, password_hash=digest, role=role, enabled=True, can_manage_users=manager,
                    security_version=1, version=1, created_at=now, updated_at=now))
                self._grants(conn, user_id, scopes)
                self._audit(conn, actor['user_id'], user_id, 'create', {'role': role, 'projects': list(scopes), 'can_manage_users': manager})
        except IntegrityError:
            raise HubError('account_exists', '使用者名稱已存在。', 409) from None
        return user_id

    def update(self, current, target_id, expected_version, display_name, role, projects, can_manage_users=False):
        display, role, scopes, manager = account_values(display_name, role, projects, can_manage_users)
        with self.auth.transaction() as conn:
            actor = self._actor(conn, current)
            row = self._target(conn, target_id, expected_version)
            self._last_manager(conn, row, row['enabled'], manager)
            self._grants(conn, target_id, scopes)
            self._update(conn, row, display_name=display, role=role, can_manage_users=manager)
            self._audit(conn, actor['user_id'], target_id, 'update', {'role': role, 'projects': list(scopes), 'can_manage_users': manager})

    def set_enabled(self, current, target_id, expected_version, enabled):
        if type(enabled) is not bool:
            raise HubError('invalid_account', '啟用狀態格式不正確。', 400)
        with self.auth.transaction() as conn:
            actor = self._actor(conn, current)
            row = self._target(conn, target_id, expected_version)
            self._last_manager(conn, row, enabled, row['can_manage_users'])
            self._update(conn, row, enabled=enabled)
            self._audit(conn, actor['user_id'], target_id, 'enable' if enabled else 'disable')

    def password(self, current, target_id, expected_version, password, *, current_password=None):
        # Verify/hash without holding the global DB lock. Recheck both actors and CAS below.
        if current_password is not None:
            with self.auth.transaction() as conn:
                actor = self._actor(conn, current, manager=False)
                if actor['user_id'] != target_id:
                    raise HubError('forbidden', '只能變更自己的密碼。', 403)
                row = self._target(conn, target_id, expected_version)
                digest = row['password_hash']
            if not verify_password(current_password, digest):
                raise HubError('invalid_current_password', '目前密碼不正確。', 403)
        digest = password_digest(password)
        with self.auth.transaction() as conn:
            actor = self._actor(conn, current, manager=current_password is None)
            row = self._target(conn, target_id, expected_version)
            if current_password is not None and actor['user_id'] != target_id:
                raise HubError('forbidden', '只能變更自己的密碼。', 403)
            self._update(conn, row, password_hash=digest)
            self._audit(conn, actor['user_id'], target_id, 'self_password' if current_password is not None else 'reset_password')

    def create_project(self, current, project_id, registry):
        """Create ownership and explicit creator grant atomically on one connection."""
        project_id = identifier(project_id)
        with self.auth.transaction() as conn:
            actor = self._actor(conn, current, manager=False)
            if actor['role'] != 'admin':
                raise HubError('forbidden', '此帳號沒有專案管理權限。', 403)
            scopes = self._identity(conn, actor).projects
            if len(scopes) >= 100 and project_id not in scopes:
                raise HubError('scope_limit', '每個帳號最多授權 100 個專案。', 409)
            state = {'revision': 1, 'sources': {}, 'tasks': {}, 'packets': {}, 'decisions': {}, 'sequence': 0}
            insert = sqlite_insert if self.store.sqlite else pg_insert
            inserted = conn.execute(insert(project_table).values(id=project_id, state=state).on_conflict_do_nothing().returning(project_table.c.id)).scalar_one_or_none()
            if inserted is None:
                raise HubError('project_exists', 'Project already exists')
            self.store.index.initialize_project(conn, project_id, state)
            conn.execute(registry.projects.insert().values(project_id=project_id, owner_id=actor['user_id'], created_at=self.auth.clock()))
            conn.execute(insert(self.grants).values(user_id=actor['user_id'], project_id=project_id).on_conflict_do_nothing())
            registry._audit(conn, project_id, state, 'create_managed_project', 'human:' + actor['user_id'], self.auth.clock(), {'owner_id': actor['user_id']})
            conn.execute(project_table.update().where(project_table.c.id == project_id).values(state=state))
            self._update(conn, actor)
            # The authenticated creator keeps this session; all its other sessions expire.
            record = conn.execute(select(self.auth.entries.c.payload).where(self.auth.entries.c.token_hash == current['_key'])).scalar_one()
            conn.execute(self.auth.entries.update().where(self.auth.entries.c.token_hash == current['_key']).values(
                payload={**record, 'security_version': actor['security_version'] + 1}))
        return project_id
