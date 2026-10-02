"""Transactionally derived full-text index; canonical evidence remains project snapshots.

Index outbox rows are inserted and drained in the same transaction as source or
proposal changes. A failed index write rolls the whole mutation back. Reindex is
an explicit repair operation, not an asynchronous freshness promise.
"""
import re
import uuid
from sqlalchemy import Table, Column, String, Integer, Float, JSON, Text, select, text, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


def index_tables(metadata):
    documents = Table("knowledge_documents", metadata,
        Column("project_id", String(128), primary_key=True),
        Column("kind", String(16), primary_key=True),
        Column("entity_id", String(128), primary_key=True),
        Column("body", Text, nullable=False), Column("details", JSON, nullable=False),
        Column("revision", Integer, nullable=False))
    jobs = Table("index_outbox", metadata, Column("id", String(32), primary_key=True),
        Column("project_id", String(128), index=True, nullable=False),
        Column("kind", String(16), nullable=False), Column("entity_id", String(128), nullable=False),
        Column("revision", Integer, nullable=False), Column("status", String(16), nullable=False))
    state = Table("knowledge_index_state", metadata, Column("project_id", String(128), primary_key=True),
        Column("revision", Integer, nullable=False))
    migrations = Table("schema_migrations", metadata, Column("version", Integer, primary_key=True), Column("applied_at", Float, nullable=False))
    return documents, jobs, state, migrations

class KnowledgeIndex:
    def __init__(self, sqlite, tables):
        self.sqlite = sqlite
        self.documents, self.jobs, self.state, self.migrations = tables
        self.insert = sqlite_insert if sqlite else pg_insert

    def install(self, conn):
        if self.sqlite:
            conn.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(project_id UNINDEXED, kind UNINDEXED, entity_id UNINDEXED, body, tokenize='unicode61')")
        else:
            conn.exec_driver_sql("ALTER TABLE knowledge_documents ADD COLUMN IF NOT EXISTS search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', body)) STORED")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS knowledge_documents_search_gin ON knowledge_documents USING GIN(search_vector)")

    def queue(self, conn, project_id, kind, entity_id, revision):
        conn.execute(self.jobs.insert().values(id=uuid.uuid4().hex,project_id=project_id,kind=kind,entity_id=entity_id,revision=revision,status="pending"))

    def initialize_project(self, conn, project_id, state):
        if conn.execute(select(self.state.c.revision).where(self.state.c.project_id==project_id)).scalar_one_or_none() is None:
            self.rebuild(conn, project_id, state)

    def rebuild(self, conn, project_id, state):
        conn.execute(self.documents.delete().where(self.documents.c.project_id==project_id))
        if self.sqlite:
            conn.execute(text("DELETE FROM knowledge_fts WHERE project_id=:p"), {"p":project_id})
        for source_id in state["sources"]:
            self.queue(conn,project_id,"source",source_id,state["revision"])
        for decision_id in state["decisions"]:
            self.queue(conn,project_id,"decision",decision_id,state["revision"])
        self.drain(conn,project_id,state,force_revision=True)

    def drain(self, conn, project_id, state, force_revision=False):
        rows = conn.execute(select(self.jobs).where(self.jobs.c.project_id==project_id,self.jobs.c.status=="pending")).mappings().all()
        for row in rows:
            kind, entity_id = row["kind"], row["entity_id"]
            if kind == "source":
                source = state["sources"][entity_id]["current"]
                body = entity_id + "\n" + source["content"]
                details = {k:source[k] for k in ("source_id","sha256","uri","commit")}
            else:
                decision = state["decisions"][entity_id]
                body = decision["text"]
                details = {k:decision[k] for k in ("decision_id","status","evidence","binding")}
            values={"project_id":project_id,"kind":kind,"entity_id":entity_id,"body":body,"details":details,"revision":state["revision"]}
            statement=self.insert(self.documents).values(**values)
            conn.execute(statement.on_conflict_do_update(index_elements=["project_id","kind","entity_id"],set_={k:values[k] for k in ("body","details","revision")}))
            if self.sqlite:
                conn.execute(text("DELETE FROM knowledge_fts WHERE project_id=:p AND kind=:k AND entity_id=:e"), {"p":project_id,"k":kind,"e":entity_id})
                conn.execute(text("INSERT INTO knowledge_fts(project_id,kind,entity_id,body) VALUES (:p,:k,:e,:b)"), {"p":project_id,"k":kind,"e":entity_id,"b":body})
            conn.execute(self.jobs.update().where(self.jobs.c.id==row["id"]).values(status="processed"))
        if rows or force_revision:
            statement=self.insert(self.state).values(project_id=project_id,revision=state["revision"])
            conn.execute(statement.on_conflict_do_update(index_elements=["project_id"],set_={"revision":state["revision"]}))

    def health(self, conn, project_id, revision, expected_documents=None):
        count=conn.execute(select(func.count()).select_from(self.documents).where(self.documents.c.project_id==project_id)).scalar_one()
        pending=conn.execute(select(func.count()).select_from(self.jobs).where(self.jobs.c.project_id==project_id,self.jobs.c.status=="pending")).scalar_one()
        indexed=conn.execute(select(self.state.c.revision).where(self.state.c.project_id==project_id)).scalar_one_or_none()
        fts_count=conn.execute(text("SELECT COUNT(*) FROM knowledge_fts WHERE project_id=:p"),{"p":project_id}).scalar_one() if self.sqlite else count
        return {"backend":"sqlite_fts5" if self.sqlite else "postgresql_fts_gin","indexed_documents":count,"pending_jobs":pending,"current_revision":revision,"indexed_revision":indexed,"fresh":indexed==revision and pending==0 and count==fts_count and (expected_documents is None or count==expected_documents),"expected_documents":expected_documents,"fts_documents":fts_count,"integrity_scope":"revision_and_row_counts_not_full_content_verification","mode":"transactional_sync_outbox","schema_version":2}

    def search(self, conn, project_id, query, limit, offset):
        # CJK has no bundled linguistic segmentation. Use escaped literal substring
        # matching instead of pretending simple/unicode61 tokenization understands it.
        cjk=bool(re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]",query))
        terms=re.findall(r"\w+",query,flags=re.UNICODE)
        literal=cjk or not terms
        params={"p":project_id,"q":query,"limit":limit+1,"offset":offset}
        if literal:
            pattern="%"+query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
            statement=select(self.documents).where(self.documents.c.project_id==project_id,self.documents.c.body.ilike(pattern,escape="\\")).order_by(self.documents.c.kind,self.documents.c.entity_id).limit(limit+1).offset(offset)
            rows=conn.execute(statement).mappings().all()
        elif self.sqlite:
            params["q"]=" AND ".join('"'+term.replace('"','""')+'"' for term in terms)
            rows=conn.execute(text("SELECT d.* FROM knowledge_fts JOIN knowledge_documents d ON d.project_id=knowledge_fts.project_id AND d.kind=knowledge_fts.kind AND d.entity_id=knowledge_fts.entity_id WHERE knowledge_fts MATCH :q AND d.project_id=:p ORDER BY bm25(knowledge_fts), d.kind, d.entity_id LIMIT :limit OFFSET :offset"),params).mappings().all()
        else:
            rows=conn.execute(text("SELECT project_id,kind,entity_id,body,details,revision FROM knowledge_documents WHERE project_id=:p AND search_vector @@ plainto_tsquery('simple',:q) ORDER BY ts_rank(search_vector,plainto_tsquery('simple',:q)) DESC,kind,entity_id LIMIT :limit OFFSET :offset"),params).mappings().all()
        import json
        results=[]
        for row in rows[:limit]:
            details=row["details"] if isinstance(row["details"],dict) else json.loads(row["details"])
            results.append({"kind":row["kind"],**details,"excerpt":row["body"][:500],"indexed_revision":row["revision"],"trust":"untrusted_reference_data" if row["kind"]=="source" else "approved_decision" if details.get("status")=="approved" else "unapproved_proposal"})
        return {"matches":results,"search":"cjk_literal_fallback" if cjk else "literal_fallback" if literal else "sqlite_fts5" if self.sqlite else "postgresql_fts_gin","next_offset":offset+limit if len(rows)>limit and offset+limit<=10000 else None,"truncated":len(rows)>limit and offset+limit>10000,"limit":limit,"offset":offset}
