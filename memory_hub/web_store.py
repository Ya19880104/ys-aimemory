"""Web authentication schema, registered in the core's locked migration."""
from sqlalchemy import Table, Column, String, Float, Integer, JSON, Boolean, ForeignKey, CheckConstraint


def define_tables(metadata):
    return {
        'users': Table('web_users', metadata,
            Column('user_id', String(36), primary_key=True),
            Column('username', String(128), nullable=False),
            Column('username_key', String(256), nullable=False, unique=True),
            Column('display_name', String(128), nullable=False),
            Column('password_hash', String(256), nullable=False),
            Column('role', String(16), nullable=False),
            Column('enabled', Boolean, nullable=False),
            Column('can_manage_users', Boolean, nullable=False),
            Column('security_version', Integer, nullable=False),
            Column('version', Integer, nullable=False),
            Column('created_at', Float, nullable=False),
            Column('updated_at', Float, nullable=False),
            CheckConstraint("role IN ('admin', 'member', 'read_only')", name='web_user_role'),
            CheckConstraint('security_version > 0 AND version > 0', name='web_user_versions')),
        'grants': Table('web_user_projects', metadata,
            Column('user_id', String(36), ForeignKey('web_users.user_id'), primary_key=True),
            # A configured grant may precede creation of the project.
            Column('project_id', String(128), primary_key=True)),
        'bootstrap': Table('web_account_bootstrap', metadata,
            Column('id', Integer, primary_key=True),
            Column('user_id', String(36), ForeignKey('web_users.user_id'), nullable=False),
            Column('created_at', Float, nullable=False)),
        'user_audit': Table('web_user_audit', metadata,
            Column('id', Integer, primary_key=True, autoincrement=True),
            Column('actor_id', String(36), nullable=False),
            Column('target_id', String(36), nullable=False),
            Column('operation', String(32), nullable=False),
            Column('at', Float, nullable=False),
            Column('details', JSON, nullable=False)),
        'entries': Table('web_auth_entries',metadata,
            Column('token_hash',String(64),primary_key=True),
            Column('kind',String(16),nullable=False,index=True),
            Column('expires',Float,nullable=False,index=True),
            Column('fingerprint',String(64),nullable=False),
            Column('payload',JSON,nullable=False)),
        'lock': Table('web_auth_lock',metadata,Column('id',Integer,primary_key=True)),
    }
