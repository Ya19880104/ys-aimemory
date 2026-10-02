"""Real-PostgreSQL version/isolation and logical-backup recovery evidence.

Run only against a disposable cluster (local runner or official CI service).
The regular suite still collects these tests, but skips without that opt-in.
"""
import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import Store

pytestmark = pytest.mark.skipif(
    os.environ.get("HUB_TEST_RUNTIME") != "1",
    reason="requires explicit HUB_TEST_RUNTIME=1 disposable PostgreSQL cluster",
)


def run(*command, data=None):
    container = os.environ.get("HUB_TEST_PG_CONTAINER")
    if container:
        # The explicitly selected disposable CI service holds its own libpq tools.
        # No host client installation or production credential is needed.
        url = make_url(os.environ["HUB_TEST_DATABASE_URL"])
        command = ("docker", "exec", "-i", "-e", f"PGUSER={url.username}",
                   "-e", f"PGDATABASE={url.database}", container, *command)
    return subprocess.run(command, input=data, check=True, capture_output=True).stdout


@pytest.fixture
def postgres_url():
    url = os.environ["HUB_TEST_DATABASE_URL"]
    assert make_url(url).drivername == "postgresql+psycopg"
    return url


def test_postgres_version_and_optional_local_socket_isolation(postgres_url):
    engine = create_engine(postgres_url)
    try:
        with engine.connect() as conn:
            version = int(conn.exec_driver_sql("SHOW server_version_num").scalar_one())
            assert version // 10000 == int(os.environ.get("HUB_TEST_POSTGRES_MAJOR", "18"))
            if os.environ.get("HUB_TEST_SOCKET_ONLY") == "1":
                assert conn.exec_driver_sql("SHOW listen_addresses").scalar_one() == ""
                assert conn.exec_driver_sql("SELECT inet_server_addr()").scalar_one() is None
            assert conn.exec_driver_sql("SHOW data_checksums").scalar_one() == "on"
    finally:
        engine.dispose()


def test_logical_backup_restore_preserves_hub_state_and_audit(postgres_url, tmp_path):
    """Restore a custom dump into a newly created database; never overwrite one."""
    schema = "runtime_backup_" + uuid.uuid4().hex
    target = "runtime_restore_" + uuid.uuid4().hex
    engine = create_engine(postgres_url)
    source_store = restored_store = None
    target_created = False
    url = make_url(postgres_url)
    admin = Principal(worker_id="runtime_admin", projects=["backup-proof"], role="admin")
    sender = Principal(worker_id="runtime_sender", projects=["backup-proof"])
    recipient = Principal(worker_id="runtime_recipient", projects=["backup-proof"])
    principals = [admin, sender, recipient]
    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    archive = tmp_path / "hub-runtime.dump"
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        source_store = Store(scoped_url.render_as_string(hide_password=False))
        hub = Hub(source_store, clock=lambda: 1000.0, principals=principals)
        hub.call("create_project", {"project_id": "backup-proof"}, admin)
        hub.call("register_source", {
            "project_id": "backup-proof", "source_id": "backup-spec",
            "content": "Restore proof: PostgreSQL persists central memory. 還原證據。",
            "uri": "test:backup-spec", "commit": "test-backup-commit",
        }, admin)
        hub.call("create_task", {
            "project_id": "backup-proof", "task_id": "restore-proof",
            "goal": "Verify logical restore", "allowed_paths": ["tests/**"],
            "acceptance_criteria": ["State and audit survive restore"],
            "source_ids": ["backup-spec"],
        }, admin)
        packet = hub.call("prepare_task", {
            "project_id": "backup-proof", "task_id": "restore-proof",
            "workspace": "fixture-no-filesystem-access",
            "branch": "fixture/runtime-sender", "commit": "fixture-base-commit",
        }, sender)
        lease = hub.call("claim_task", {
            "project_id": "backup-proof", "task_id": "restore-proof",
        }, sender)
        packet_args = {"project_id": "backup-proof", "packet_id": packet["packet_id"]}
        for source_id, sha256 in packet["required_sources"].items():
            read = hub.call("read_source", {**packet_args, "source_id": source_id}, sender)
            assert read["sha256"] == sha256
        assert hub.call("acknowledge_context", packet_args, sender)["acknowledged"]
        gate = {**packet_args, "fence": lease["fence"]}
        assert hub.call("accept_handoff", gate, sender)["accepted"]
        assert hub.call("validate_task_context", gate, sender)["valid"]
        evidence = [
            {"source_id": source_id, "sha256": sha256}
            for source_id, sha256 in packet["required_sources"].items()
        ]
        handoff = hub.call("handoff_task", {
            **gate, "to_worker": recipient.worker_id,
            "summary": "Restore proof: 交接還原證據。",
            "evidence": evidence, "changed_artifacts": [],
            "result_commit": "fixture-result-commit",
            "test_results": [{
                "command": "fixture handoff metadata", "status": "not_run",
                "details": "Synthetic metadata; no external test result is claimed.",
            }],
            "blockers": [],
            "next_steps": ["Read restored context and review the fixture"],
        }, sender)
        before_inbox = hub.call("get_worker_inbox", {"project_id": "backup-proof"}, recipient)
        assert before_inbox["worker_id"] == recipient.worker_id
        assert len(before_inbox["pending_handoffs"]) == 1
        pending = before_inbox["pending_handoffs"][0]
        assert pending["task_id"] == "restore-proof"
        assert pending["pending_recipient"] == recipient.worker_id
        assert pending["owner"] is None
        latest_handoff = pending["latest_handoff"]
        assert latest_handoff["checkpoint_id"] == handoff["checkpoint_id"]
        assert latest_handoff["to_worker"] == recipient.worker_id
        assert latest_handoff["evidence"] == evidence
        assert latest_handoff["result_commit"] == "fixture-result-commit"
        assert latest_handoff["test_results"][0]["status"] == "not_run"
        with source_store.transaction("backup-proof") as (state, conn):
            before_state = state.copy()
            before_audit = source_store.read_audit(conn, "backup-proof")
        assert before_state["tasks"]["restore-proof"]["handoffs"]
        assert any(event["operation"] == "handoff_task" for event in before_audit)
        archive.write_bytes(run("pg_dump", "--format=custom", "--no-owner", "--no-acl", "--schema", schema))
        assert archive.stat().st_size > 0
        listing = run("pg_restore", "--list", data=archive.read_bytes()).decode()
        assert "projects" in listing and "audit_events" in listing
        run("createdb", target)
        target_created = True
        run("pg_restore", "--dbname", target, "--no-owner", "--no-acl",
            "--exit-on-error", "--single-transaction", data=archive.read_bytes())
        restored_url = scoped_url.set(database=target)
        restored_store = Store(restored_url.render_as_string(hide_password=False))
        with restored_store.transaction("backup-proof") as (state, conn):
            assert state == before_state
            assert restored_store.read_audit(conn, "backup-proof") == before_audit
        # Confirm application reads, including Unicode JSON, after restoration.
        restored_hub = Hub(restored_store, clock=lambda: 1000.0, principals=principals)
        restored_inbox = restored_hub.call(
            "get_worker_inbox", {"project_id": "backup-proof"}, recipient
        )
        assert restored_inbox == before_inbox
        assert restored_hub.call(
            "get_worker_inbox", {"project_id": "backup-proof"}, sender
        )["pending_handoffs"] == []
        matches = restored_hub.call("search_knowledge", {
            "project_id": "backup-proof", "query": "Restore proof",
        }, admin)["matches"]
        assert matches
        assert "還原證據" in str(matches)
    finally:
        if source_store is not None:
            source_store.engine.dispose()
        if restored_store is not None:
            restored_store.engine.dispose()
        if target_created:
            run("dropdb", target)
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
