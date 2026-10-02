#!/usr/bin/env python3
"""Verify real PostgreSQL SQL without sockets; NOT a driver/integration test.

Usage: PG_TEST_RUNTIME_ROOT=/tmp/pg18/root .venv/bin/python scripts/postgres-test-single-user.py
For hosts where local server sockets are unavailable. Uses only a fresh temp DB.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from memory_hub.store import metadata, index_schema
from memory_hub.index import KnowledgeIndex


def main():
    root = os.environ.get("PG_TEST_RUNTIME_ROOT")
    bindir = Path(root) / "usr/lib/postgresql/18/bin" if root else Path(os.environ["PG_TEST_BINDIR"])
    env = os.environ.copy()
    if root:
        env["LD_LIBRARY_PATH"] = str(Path(root) / "usr/lib/x86_64-linux-gnu") + (
            ":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    version_text = subprocess.check_output([str(bindir / "postgres"), "--version"], env=env, text=True).strip()
    dialect = postgresql.dialect()
    statements = [
        "DO $$ BEGIN ASSERT current_setting('server_version_num')::integer / 10000 = 18; END $$",
        "CREATE SCHEMA runtime_sql_smoke", "SET search_path TO runtime_sql_smoke",
        "BEGIN", "SELECT pg_advisory_xact_lock(761981234)",
    ]
    for table in metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)))
        statements.extend(str(CreateIndex(index).compile(dialect=dialect)) for index in table.indexes)

    class Capture:
        def exec_driver_sql(self, statement):
            statements.append(statement)

    index = KnowledgeIndex(False, index_schema)
    index.install(Capture())
    for _ in range(2):
        for version in (1, 2):
            migration = postgresql.insert(index.migrations).values(version=version, applied_at=0.0).on_conflict_do_nothing()
            statements.append(str(migration.compile(dialect=dialect, compile_kwargs={"literal_binds": True})))
    statements.append("DO $$ BEGIN ASSERT (SELECT count(*)=2 FROM schema_migrations); END $$")
    # Repeat additive install, as restart migration should do.
    index.install(Capture())

    class CaptureSearch:
        def execute(self, statement, params=None):
            if params:
                statement = statement.bindparams(**params)
            self.sql = str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
            return self
        def mappings(self):
            return self
        def all(self):
            return []

    search = CaptureSearch()
    index.search(search, "p", "memory", 10, 0)
    english_sql = search.sql
    index.search(search, "p", "中央記憶", 10, 0)
    cjk_sql = search.sql
    statements += [
        "INSERT INTO knowledge_documents VALUES ('p','source','english','central memory durable index','{}',1), ('p','source','cjk','中央記憶與四個客戶端','{}',1), ('other','source','isolation','private memory','{}',1)",
        "DO $$ BEGIN ASSERT (SELECT count(*)=1 FROM knowledge_documents WHERE project_id='p' AND search_vector @@ plainto_tsquery('simple','memory')); END $$",
        english_sql,
        f"DO $$ BEGIN ASSERT (SELECT count(*)=1 FROM ({english_sql}) AS actual_english_query); END $$",
        cjk_sql,
        f"DO $$ BEGIN ASSERT (SELECT count(*)=1 FROM ({cjk_sql}) AS actual_cjk_query); END $$",
        "DO $$ BEGIN ASSERT (SELECT count(*)=1 FROM knowledge_documents WHERE project_id='p' AND body ILIKE '%中央記憶%' ESCAPE E'\\\\'); END $$",
        "DO $$ BEGIN ASSERT (SELECT count(*)=1 FROM pg_indexes WHERE tablename='knowledge_documents' AND indexname='knowledge_documents_search_gin' AND indexdef LIKE '%USING gin%'); END $$",
        "UPDATE knowledge_documents SET body='updated source evidence' WHERE project_id='p' AND entity_id='english'",
        "DO $$ BEGIN ASSERT (SELECT count(*)=0 FROM knowledge_documents WHERE project_id='p' AND search_vector @@ plainto_tsquery('simple','memory')); ASSERT (SELECT count(*)=1 FROM knowledge_documents WHERE project_id='p' AND search_vector @@ plainto_tsquery('simple','updated')); END $$",
        "COMMIT",
        "BEGIN",
        "INSERT INTO knowledge_documents VALUES ('p','source','rollback','must disappear','{}',2)",
        "ROLLBACK",
        "DO $$ BEGIN ASSERT (SELECT count(*)=0 FROM knowledge_documents WHERE entity_id='rollback'); END $$",
        "SELECT 'YS_AIMEMORY_PG18_SQL_SMOKE_OK' AS result",
    ]
    with tempfile.TemporaryDirectory(prefix="ys-pg-single-") as directory:
        data = Path(directory) / "data"
        command = [str(bindir / "initdb"), "-D", str(data), "--locale=C", "--encoding=UTF8", "--auth-local=trust", "--auth-host=reject"]
        if root:
            command += ["-L", str(Path(root) / "usr/share/postgresql/18")]
        subprocess.run(command, env=env, check=True, capture_output=True, text=True)
        result = subprocess.run([str(bindir / "postgres"), "--single", "-D", str(data), "-c", "exit_on_error=on", "postgres"],
            input="\n".join(" ".join(s.split()) + ";" for s in statements) + "\n", env=env, capture_output=True, text=True)
        if result.returncode or "YS_AIMEMORY_PG18_SQL_SMOKE_OK" not in result.stdout or any(x in result.stderr for x in ("ERROR:", "FATAL:", "PANIC:")):
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode or 1)
    print(version_text)
    print(f"PASS: {len(statements)} SQL statements, generated TSV/GIN, English search, CJK literal fallback, project filter, update freshness, rollback, additive DDL restart")
    print("Single-user SQL verification only; psycopg connections, concurrent transactions, pg_dump/pg_restore, and network server startup were NOT tested.")


if __name__ == "__main__":
    main()
