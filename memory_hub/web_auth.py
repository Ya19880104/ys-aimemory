"""Database-backed opaque sessions, one-use forms and cross-instance throttles.

No bearer token, password or raw browser token is persisted. All auth state
transitions share one small DB lock; correctness precedes auth throughput.
"""
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from .store import WEB_TABLES


class WebAuthStore:
    def __init__(self, store, config, clock):
        self.store, self.config, self.clock = store, config, clock
        self.entries, self.guard = WEB_TABLES['entries'], WEB_TABLES['lock']
        encoded=json.dumps(asdict(config),sort_keys=True,separators=(',',':')) if config else 'disabled'
        self.fingerprint=hashlib.sha256(encoded.encode()).hexdigest()
        self.config_key=self.key('web-auth-active-configuration')
        with self.transaction() as conn:
            previous=conn.execute(select(self.entries.c.fingerprint).where(self.entries.c.token_hash==self.config_key)).scalar_one_or_none()
            if previous!=self.fingerprint:
                conn.execute(self.entries.delete().where(self.entries.c.kind.in_(['session','login','nonce','config'])))
                conn.execute(self.entries.insert().values(token_hash=self.config_key,kind='config',expires=1e30,fingerprint=self.fingerprint,payload={}))

    @staticmethod
    def key(token): return hashlib.sha256(token.encode()).hexdigest()

    @contextmanager
    def transaction(self):
        with self.store.engine.connect() as conn:
            if self.store.sqlite: conn.exec_driver_sql('BEGIN IMMEDIATE')
            else: conn.begin()
            try:
                insert=sqlite_insert if self.store.sqlite else pg_insert
                conn.execute(insert(self.guard).values(id=1).on_conflict_do_nothing())
                statement=select(self.guard.c.id).where(self.guard.c.id==1)
                if not self.store.sqlite: statement=statement.with_for_update()
                conn.execute(statement).one()
                conn.execute(self.entries.delete().where(self.entries.c.expires<=self.clock()))
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def _active(self,conn):
        return conn.execute(select(self.entries.c.fingerprint).where(self.entries.c.token_hash==self.config_key)).scalar_one_or_none()==self.fingerprint

    def _get(self,conn,key,kind):
        if not self._active(conn):return None
        row=conn.execute(select(self.entries).where(self.entries.c.token_hash==key,self.entries.c.kind==kind)).mappings().one_or_none()
        if row is None or row['fingerprint']!=self.fingerprint: return None
        return {**row['payload'],'expires':row['expires'],'_key':key}

    def _put(self,conn,key,kind,payload,expires,cap=1000):
        count=conn.execute(select(func.count()).select_from(self.entries).where(self.entries.c.kind==kind)).scalar_one()
        if count>=cap:
            oldest=conn.execute(select(self.entries.c.token_hash).where(self.entries.c.kind==kind).order_by(self.entries.c.expires).limit(count-cap+1)).scalars().all()
            conn.execute(self.entries.delete().where(self.entries.c.token_hash.in_(oldest)))
        conn.execute(self.entries.insert().values(token_hash=key,kind=kind,payload=payload,expires=expires,fingerprint=self.fingerprint))

    def session(self,token):
        with self.transaction() as conn: return self._get(conn,self.key(token),'session')

    def start_login(self,token,csrf):
        with self.transaction() as conn:
            if not self._active(conn):return False
            self._put(conn,self.key(token),'login',{'csrf':csrf},self.clock()+600)
            return True

    def consume_login(self,token):
        with self.transaction() as conn:
            key=self.key(token); value=self._get(conn,key,'login')
            if value: conn.execute(self.entries.delete().where(self.entries.c.token_hash==key))
            return value

    def allow_attempt(self,ip):
        with self.transaction() as conn:
            now=self.clock(); buckets=[]
            for name,limit in [('global',100),('peer:'+ip,5)]:
                key=self.key('throttle:'+name)
                row=conn.execute(select(self.entries.c.payload).where(self.entries.c.token_hash==key)).scalar_one_or_none()
                times=[at for at in (row or {}).get('times',[]) if at>now-300]
                if len(times)>=limit:return False
                buckets.append((key,times))
            for key,times in buckets:
                conn.execute(self.entries.delete().where(self.entries.c.token_hash==key))
                self._put(conn,key,'throttle',{'times':times+[now]},now+300,cap=102)
            return True

    def start_session(self,token,csrf,previous):
        with self.transaction() as conn:
            if not self._active(conn):return False
            conn.execute(self.entries.delete().where(self.entries.c.token_hash==self.key(previous),self.entries.c.kind=='session'))
            self._put(conn,self.key(token),'session',{'csrf':csrf},self.clock()+self.config.ttl)
            return True

    def logout(self,token):
        with self.transaction() as conn:conn.execute(self.entries.delete().where(self.entries.c.token_hash==self.key(token),self.entries.c.kind=='session'))

    def start_nonce(self,token,current,action,project):
        with self.transaction() as conn:
            if not self._get(conn,current['_key'],'session'):return False
            self._put(conn,self.key(token),'nonce',{'session_key':current['_key'],'action':action,'project':project},min(current['expires'],self.clock()+900),cap=2000)
            return True

    def consume_nonce(self,token,current,action,project):
        with self.transaction() as conn:
            key=self.key(token); value=self._get(conn,key,'nonce')
            if not value or not self._get(conn,current['_key'],'session'):return False
            if value['session_key']!=current['_key'] or value['action']!=action or value['project']!=project:return False
            conn.execute(self.entries.delete().where(self.entries.c.token_hash==key))
            return True

    def set_flash(self,current,message):
        with self.transaction() as conn:
            record=self._get(conn,current['_key'],'session')
            if record:
                payload={k:v for k,v in record.items() if k not in ('expires','_key')};payload['flash']=message
                conn.execute(self.entries.update().where(self.entries.c.token_hash==current['_key']).values(payload=payload))

    def pop_flash(self,current):
        with self.transaction() as conn:
            record=self._get(conn,current['_key'],'session')
            if not record:return None
            payload={k:v for k,v in record.items() if k not in ('expires','_key')};message=payload.pop('flash',None)
            conn.execute(self.entries.update().where(self.entries.c.token_hash==current['_key']).values(payload=payload))
            return message
