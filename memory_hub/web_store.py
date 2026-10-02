"""Web authentication schema, registered in the core's locked migration."""
from sqlalchemy import Table, Column, String, Float, Integer, JSON


def define_tables(metadata):
    return {
        'entries': Table('web_auth_entries',metadata,
            Column('token_hash',String(64),primary_key=True),
            Column('kind',String(16),nullable=False,index=True),
            Column('expires',Float,nullable=False,index=True),
            Column('fingerprint',String(64),nullable=False),
            Column('payload',JSON,nullable=False)),
        'lock': Table('web_auth_lock',metadata,Column('id',Integer,primary_key=True)),
    }
