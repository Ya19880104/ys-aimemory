import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text, func, create_engine, inspect
from sqlalchemy.engine import make_url
from memory_hub.service import Hub
from memory_hub.store import Store, HubError, projects, events, WEB_TABLES
from test_hub import hub, call, ADMIN, A, B, prepare, ready, evidence, error


def source(source_id,content):
    return {"source_id":source_id,"content":content,"uri":"git:docs/"+source_id,"commit":"fixture-commit"}


def revision(h):
    return call(h,"get_project_summary")["context_revision"]


def import_sources(h,sources,key="batch-one",expected_revision=None,actor=ADMIN):
    return call(h,"import_sources",actor,sources=sources,idempotency_key=key,expected_revision=revision(h) if expected_revision is None else expected_revision)


def test_import_atomic_idempotency_and_conflict(hub):
    rev=revision(hub)
    batch=[source("one","First source"),source("two","Second source")]
    result=import_sources(hub,batch,expected_revision=rev)
    assert result["context_revision"]==rev+1
    audit_count=call(hub,"audit_log")["latest_sequence"]
    replay=import_sources(hub,batch,expected_revision=rev)
    assert replay==result
    assert call(hub,"audit_log")["latest_sequence"]==audit_count
    error("idempotency_conflict",lambda:import_sources(hub,[source("one","Different")],expected_revision=rev))
    assert call(hub,"get_source_metadata",source_id="one")["version_count"]==1
    error("stale_context",lambda:import_sources(hub,batch,key="new-key",expected_revision=rev))
    error("forbidden",lambda:import_sources(hub,batch,key="worker",actor=A))


def test_batch_validation_is_all_or_nothing(hub):
    before=revision(hub)
    for batch in ([source("same","a"),source("same","b")], [source("fine","a"),source("bad","")], [source(str(i),"x"*200000) for i in range(4)]):
        with pytest.raises(ValidationError):
            import_sources(hub,batch)
    assert revision(hub)==before
    assert call(hub,"list_sources")["items"][0]["source_id"]=="spec"


def test_source_cas_and_identical_upsert(hub):
    old=revision(hub)
    changed=source("spec","  new exact content\n")
    error("revision_required",lambda:call(hub,"register_source",ADMIN,**changed))
    result=call(hub,"register_source",ADMIN,**changed,expected_revision=old)
    assert result["sha256"]==hashlib.sha256(changed["content"].encode()).hexdigest()
    assert result["changed"]
    count=call(hub,"audit_log")["latest_sequence"]
    retry=call(hub,"register_source",ADMIN,**changed,expected_revision=old)
    assert retry["changed"] is False
    assert call(hub,"audit_log")["latest_sequence"]==count
    assert call(hub,"get_source_metadata",source_id="spec")["version_count"]==2
    error("stale_context",lambda:call(hub,"register_source",ADMIN,**source("spec","other"),expected_revision=old))


def test_incremental_fts_replaces_old_content_and_handles_chinese(hub):
    import_sources(hub,[source("english","retiredword punctuation"),source("zh","這是中央記憶系統的交接文件")])
    assert call(hub,"search_knowledge",query="retiredword")["matches"]
    zh=call(hub,"search_knowledge",query="中央記憶")
    assert zh["search"]=="cjk_literal_fallback"
    assert zh["matches"][0]["source_id"]=="zh"
    import_sources(hub,[source("english","freshword updated")],key="batch-two")
    assert not call(hub,"search_knowledge",query="retiredword")["matches"]
    fresh=call(hub,"search_knowledge",query="freshword")
    assert fresh["search"] in {"sqlite_fts5","postgresql_fts_gin"}
    assert fresh["matches"][0]["source_id"]=="english"
    assert call(hub,"index_health")["fresh"]
    assert call(hub,"index_health")["pending_jobs"]==0


def test_proposals_remain_labeled_until_approval(hub):
    packet,gate=ready(hub)
    proposal=call(hub,"propose_memory_change",**gate,text="uniqueproposal",evidence=evidence(packet))
    assert call(hub,"search_knowledge",query="uniqueproposal")["matches"][0]["status"]=="proposed"
    call(hub,"approve_memory_change",ADMIN,decision_id=proposal["decision_id"],expected_revision=revision(hub))
    assert call(hub,"search_knowledge",query="uniqueproposal")["matches"][0]["status"]=="approved"


def test_index_failure_rolls_back_source_outbox_and_audit(hub,monkeypatch):
    before=revision(hub)
    count=call(hub,"audit_log")["latest_sequence"]
    original=hub.store.index.drain
    def fail(*args,**kwargs):
        raise RuntimeError("simulated index failure")
    monkeypatch.setattr(hub.store.index,"drain",fail)
    with pytest.raises(RuntimeError):
        import_sources(hub,[source("should-not-exist","lostwrite")],expected_revision=before)
    monkeypatch.setattr(hub.store.index,"drain",original)
    assert revision(hub)==before
    assert call(hub,"audit_log")["latest_sequence"]==count
    assert not call(hub,"search_knowledge",query="lostwrite")["matches"]
    assert call(hub,"index_health")["pending_jobs"]==0
    # Same idempotency key can succeed after rollback; no orphan request record.
    assert import_sources(hub,[source("should-not-exist","lostwrite")],expected_revision=before)["context_revision"]==before+1


def test_reindex_guard_repair_and_source_pagination(hub):
    import_sources(hub,[source("a","sharedterm"),source("b","sharedterm"),source("c","sharedterm")])
    page=call(hub,"list_sources",limit=2)
    assert [item["source_id"] for item in page["items"]]==["a","b"]
    assert all("content" not in item for item in page["items"])
    assert call(hub,"list_sources",after_id=page["next_after_id"],limit=2)["items"][0]["source_id"]=="c"
    search=call(hub,"search_knowledge",query="sharedterm",limit=2)
    assert search["next_offset"]==2
    assert len(call(hub,"search_knowledge",query="sharedterm",limit=2,offset=2)["matches"])==1
    error("forbidden",lambda:call(hub,"reindex_project",expected_revision=revision(hub)))
    error("stale_context",lambda:call(hub,"reindex_project",ADMIN,expected_revision=1))
    result=call(hub,"reindex_project",ADMIN,expected_revision=revision(hub))
    assert result["fresh"] and result["indexed_documents"]==4
    assert len(call(hub,"search_knowledge",query="sharedterm")["matches"])==3


def test_concurrent_import_cas_has_one_winner(hub):
    current=revision(hub)
    def update(number):
        try:
            return import_sources(hub,[source("race",f"value{number}")],key=f"race-{number}",expected_revision=current)
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as executor:
        result=list(executor.map(update,[1,2]))
    assert sum(isinstance(item,dict) for item in result)==1
    assert "stale_context" in result
    assert call(hub,"get_source_metadata",source_id="race")["version_count"]==1


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.environ.get("HUB_TEST_DATABASE_URL") else []))
def _migration_db(tmp_path, request, monkeypatch):
    cleanup_engine = None
    schema_created = False
    engines = []

    def tracked_engine(*args, **kwargs):
        engine = create_engine(*args, **kwargs)
        engines.append(engine)
        return engine

    # Track real engines even when Store.__init__ raises before returning.
    monkeypatch.setattr("memory_hub.store.create_engine", tracked_engine)
    try:
        if request.param == "postgresql":
            base = os.environ["HUB_TEST_DATABASE_URL"]
            if not base.startswith("postgresql+psycopg://"):
                pytest.fail("HUB_TEST_DATABASE_URL must use postgresql+psycopg://")
            schema = "index_migration_" + uuid.uuid4().hex
            cleanup_engine = create_engine(base)
            with cleanup_engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            url = make_url(base).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
        else:
            url = f"sqlite:///{tmp_path}/migration.db"
        engine = tracked_engine(url)
        yield url, request.param == "sqlite", engine
    finally:
        try:
            for engine in engines:
                engine.dispose()
        finally:
            if cleanup_engine is not None:
                try:
                    if schema_created:
                        with cleanup_engine.begin() as conn:
                            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                finally:
                    cleanup_engine.dispose()


def test_additive_migration_and_concurrent_start_preserves_v01(_migration_db):
    url, allow_sqlite, engine = _migration_db
    old_source={"source_id":"spec","content":"legacyword\n","uri":"git:legacy","commit":"old","sha256":hashlib.sha256(b"legacyword\n").hexdigest(),"registered_by":"operator","registered_at":1}
    state={"revision":2,"sources":{"spec":{"current":old_source,"versions":[old_source]}},"tasks":{},"packets":{},"decisions":{},"sequence":0}
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(128) PRIMARY KEY,state JSON NOT NULL)")
        conn.execute(projects.insert().values(id="p", state=state))
    def start(_):
        store=Store(url,allow_sqlite=allow_sqlite)
        h=Hub(store,principals=[ADMIN,A])
        return call(h,"search_knowledge",query="legacyword")
    with ThreadPoolExecutor(3) as executor:
        assert all(result["matches"] for result in executor.map(start,range(3)))
    store=Store(url,allow_sqlite=allow_sqlite)
    with store.engine.connect() as conn:
        preserved=conn.execute(select(projects.c.state).where(projects.c.id=="p")).scalar_one()
        assert preserved==state
        assert conn.execute(select(func.count()).select_from(store.index.migrations)).scalar_one()==4


def test_additive_v3_migration_preserves_v2_web_sessions(_migration_db):
    url, allow_sqlite, _ = _migration_db
    store=Store(url,allow_sqlite=allow_sqlite)
    session_key='a'*64
    with store.engine.begin() as conn:
        # Recreate the v2 boundary without editing any external schema.
        conn.execute(text('DROP TABLE IF EXISTS project_messages'))
        conn.execute(text('DROP TABLE IF EXISTS mcp_credentials'))
        conn.execute(text('DROP TABLE IF EXISTS mcp_managed_projects'))
        conn.execute(text('DROP TABLE IF EXISTS mcp_worker_identities'))
        conn.execute(store.index.migrations.delete().where(store.index.migrations.c.version>2))
        conn.execute(WEB_TABLES['entries'].insert().values(token_hash=session_key,kind='session',expires=123456,
                                                        fingerprint='b'*64,payload={'csrf':'synthetic-v2-csrf'}))
    upgraded=Store(url,allow_sqlite=allow_sqlite)
    with upgraded.engine.connect() as conn:
        assert conn.execute(select(upgraded.index.migrations.c.version).order_by(upgraded.index.migrations.c.version)).scalars().all()==[1,2,3,4]
        row=conn.execute(select(WEB_TABLES['entries']).where(WEB_TABLES['entries'].c.token_hash==session_key)).mappings().one()
        assert row['payload']=={'csrf':'synthetic-v2-csrf'} and row['expires']==123456
        assert conn.execute(text('SELECT count(*) FROM mcp_credentials')).scalar_one()==0
        assert conn.execute(text('SELECT count(*) FROM mcp_managed_projects')).scalar_one()==0
        assert conn.execute(text('SELECT count(*) FROM mcp_worker_identities')).scalar_one()==0
        assert conn.execute(text('SELECT count(*) FROM project_messages')).scalar_one()==0


def test_additive_v4_migration_preserves_v3_credentials_and_project(_migration_db):
    url, allow_sqlite, _ = _migration_db
    original=Hub(Store(url,allow_sqlite=allow_sqlite),principals=[ADMIN,A])
    original.credentials.create_project('managed','559765bf-e98a-43c8-8b6b-0880c69d92c6','operator',1.0)
    issued=original.credentials.issue('managed','message-worker','operator',2.0)
    with original.store.engine.begin() as conn:
        previous=conn.execute(select(projects.c.state).where(projects.c.id=='managed')).scalar_one()
        conn.execute(text('DROP TABLE IF EXISTS project_messages'))
        conn.execute(original.store.index.migrations.delete().where(original.store.index.migrations.c.version>3))
    upgraded=Hub(Store(url,allow_sqlite=allow_sqlite),principals=[ADMIN,A])
    assert upgraded.credentials.authenticate(issued['token']).worker_id=='message-worker'
    assert upgraded.credentials.owned_projects('559765bf-e98a-43c8-8b6b-0880c69d92c6')==('managed',)
    with upgraded.store.engine.connect() as conn:
        assert conn.execute(select(projects.c.state).where(projects.c.id=='managed')).scalar_one()==previous
        assert conn.execute(select(upgraded.store.index.migrations.c.version).order_by(upgraded.store.index.migrations.c.version)).scalars().all()==[1,2,3,4]
        assert conn.execute(text('SELECT count(*) FROM project_messages')).scalar_one()==0


def test_index_health_detects_missing_documents_and_reindex_repairs(hub):
    with hub.store.engine.begin() as conn:
        conn.execute(hub.store.index.documents.delete().where(hub.store.index.documents.c.project_id=="p"))
    assert call(hub,"index_health")["fresh"] is False
    call(hub,"reindex_project",ADMIN,expected_revision=revision(hub))
    assert call(hub,"index_health")["fresh"] is True
    assert call(hub,"search_knowledge",query="memory")["matches"]
    if hub.store.sqlite:
        with hub.store.engine.begin() as conn:
            conn.execute(text("DELETE FROM knowledge_fts WHERE project_id='p'"))
        assert call(hub,"index_health")["fresh"] is False
        call(hub,"reindex_project",ADMIN,expected_revision=revision(hub))
        assert call(hub,"index_health")["fresh"] is True


def test_source_history_pagination_preserves_version_provenance(hub):
    for number in range(3):
        call(hub,"register_source",ADMIN,**source("spec",f"version-{number}\n"),expected_revision=revision(hub))
    recent=call(hub,"get_source_metadata",source_id="spec",limit=2)
    assert recent["version_count"]==4
    assert [item["version"] for item in recent["versions"]]==[4,3]
    older=call(hub,"get_source_metadata",source_id="spec",before_version=recent["next_before_version"],limit=2)
    assert [item["version"] for item in older["versions"]]==[2,1]
    assert older["next_before_version"] is None
    assert all("content" not in item for item in recent["versions"])


def test_future_schema_version_refuses_startup_without_reset(_migration_db):
    url, allow_sqlite, engine = _migration_db
    store=Store(url,allow_sqlite=allow_sqlite)
    with store.engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS project_messages'))
        conn.execute(text('DROP TABLE IF EXISTS mcp_credentials'))
        conn.execute(text('DROP TABLE IF EXISTS mcp_managed_projects'))
        conn.execute(text('DROP TABLE IF EXISTS mcp_worker_identities'))
        conn.execute(store.index.migrations.insert().values(version=5,applied_at=1.0))
    with pytest.raises(RuntimeError,match="newer"):
        Store(url,allow_sqlite=allow_sqlite)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar_one()==5
        assert not inspect(conn).has_table('project_messages')
        assert not inspect(conn).has_table('mcp_credentials')
        assert not inspect(conn).has_table('mcp_managed_projects')
        assert not inspect(conn).has_table('mcp_worker_identities')
