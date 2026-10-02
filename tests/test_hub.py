import json
import os
import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from memory_hub.app import create_app
from memory_hub.models import Principal
from memory_hub.service import Hub
from memory_hub.store import Store, HubError

ADMIN = Principal(worker_id="operator", projects=["p"], role="admin")
A = Principal(worker_id="ai-a", projects=["p"])
B = Principal(worker_id="ai-b", projects=["p"])
TOKEN_A = "test-only-worker-a-token-00000000"
TOKEN_ADMIN = "test-only-operator-token-00000000"

@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.environ.get("HUB_TEST_DATABASE_URL") else []))
def hub(tmp_path, request):
    clock = [1000.0]
    cleanup_engine = None
    if request.param == "postgresql":
        base = os.environ["HUB_TEST_DATABASE_URL"]
        if not base.startswith("postgresql+psycopg://"):
            pytest.fail("HUB_TEST_DATABASE_URL must use postgresql+psycopg://")
        schema = "hub_test_" + uuid.uuid4().hex
        cleanup_engine = create_engine(base)
        with cleanup_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        url = make_url(base).update_query_dict({"options":f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    else:
        url = f"sqlite:///{tmp_path}/hub.db"
    h = Hub(Store(url, allow_sqlite=request.param == "sqlite"), clock=lambda:clock[0], principals=[ADMIN,A,B])
    h.test_clock = clock
    h.call("create_project", {"project_id":"p"}, ADMIN)
    h.call("register_source", {"project_id":"p","source_id":"spec","content":"Build a memory hub","uri":"git:docs/spec.md","commit":"abc123"}, ADMIN)
    h.call("create_task", {"project_id":"p","task_id":"t","goal":"Build","allowed_paths":["src/**"],"acceptance_criteria":["Tests pass"],"source_ids":["spec"]}, ADMIN)
    yield h
    h.store.engine.dispose()
    if cleanup_engine:
        with cleanup_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        cleanup_engine.dispose()

def call(h, name, actor=A, **args):
    if name == "handoff_task":
        args = {"changed_artifacts":["src/hub.py"],"result_commit":"def456","test_results":[{"command":"pytest","status":"passed","details":"Unit tests passed"}],"blockers":[],"next_steps":["Review changes"], **args}
    return h.call(name, {"project_id":"p", **args}, actor)

def prepare(h, actor=A):
    return call(h,"prepare_task",actor,task_id="t",workspace=f"/work/{actor.worker_id}",branch=actor.worker_id,commit="abc123")

def read_ack(h, packet, actor=A):
    for source_id in packet["required_sources"]:
        call(h,"read_source",actor,packet_id=packet["packet_id"],source_id=source_id)
    call(h,"acknowledge_context",actor,packet_id=packet["packet_id"])

def ready(h, actor=A):
    packet=prepare(h,actor)
    lease=call(h,"claim_task",actor,task_id="t")
    read_ack(h,packet,actor)
    gate={"packet_id":packet["packet_id"],"fence":lease["fence"]}
    call(h,"accept_handoff",actor,**gate)
    return packet, gate

def evidence(packet):
    return [{"source_id":k,"sha256":v} for k,v in packet["required_sources"].items()]

def error(code, fn):
    with pytest.raises(HubError) as e:
        fn()
    assert e.value.code == code

def test_read_ack_and_accept_gates(hub):
    packet=prepare(hub); lease=call(hub,"claim_task",task_id="t")
    gate={"packet_id":packet["packet_id"],"fence":lease["fence"]}
    error("unread_context",lambda:call(hub,"acknowledge_context",packet_id=packet["packet_id"]))
    error("unread_context",lambda:call(hub,"accept_handoff",**gate))
    read_ack(hub,packet)
    error("handoff_not_accepted",lambda:call(hub,"validate_task_context",**gate))
    call(hub,"accept_handoff",**gate)
    assert call(hub,"validate_task_context",**gate)["valid"]

def test_proposals_need_approval_and_invalidate_context(hub):
    packet,gate=ready(hub)
    proposal=call(hub,"propose_memory_change",**gate,text="Use SQL",evidence=evidence(packet))
    assert proposal["status"] == "proposed"
    assert prepare(hub)["approved_decisions"] == []
    error("forbidden",lambda:call(hub,"approve_memory_change",decision_id=proposal["decision_id"],expected_revision=packet["context_revision"]))
    call(hub,"approve_memory_change",ADMIN,decision_id=proposal["decision_id"],expected_revision=packet["context_revision"])
    error("stale_context",lambda:call(hub,"record_checkpoint",**gate,summary="Work",evidence=evidence(packet)))
    assert len(prepare(hub)["approved_decisions"]) == 1

def test_source_update_invalidates_reads_and_stale_proposals(hub):
    packet,gate=ready(hub)
    proposal=call(hub,"propose_memory_change",**gate,text="Use SQL",evidence=evidence(packet))
    update=call(hub,"register_source",ADMIN,source_id="spec",content="Changed",uri="git:docs/spec.md",commit="def456",expected_revision=packet["context_revision"])
    error("stale_context",lambda:call(hub,"read_source",packet_id=packet["packet_id"],source_id="spec"))
    error("stale_proposal",lambda:call(hub,"approve_memory_change",ADMIN,decision_id=proposal["decision_id"],expected_revision=update["context_revision"]))

def test_identity_and_project_isolation(hub):
    packet,gate=ready(hub)
    error("invalid_packet",lambda:call(hub,"validate_task_context",B,**gate))
    outsider=Principal(worker_id="outsider",projects=["other"])
    error("forbidden",lambda:call(hub,"search_knowledge",outsider,query="Build"))
    error("forbidden",lambda:call(hub,"register_source",source_id="x",content="x",uri="x",commit="x"))

def test_concurrent_claim_only_one_wins(hub):
    def claim(actor):
        try:
            return call(hub,"claim_task",actor,task_id="t")
        except HubError as e:
            return e.code
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(claim,[A,B]))
    assert sum(isinstance(x,dict) for x in results) == 1
    assert "lease_busy" in results

def test_expired_fence_and_renewal(hub):
    packet,gate=ready(hub)
    hub.test_clock[0] += 301
    error("invalid_lease",lambda:call(hub,"renew_lease",**gate))
    packet_b,gate_b=ready(hub,B)
    assert gate_b["fence"] > gate["fence"]
    error("invalid_lease",lambda:call(hub,"validate_task_context",**gate))
    assert call(hub,"renew_lease",B,**gate_b)["lease_until"] > hub.test_clock[0]

def test_handoff_requires_fresh_packet_and_recipient(hub):
    packet,gate=ready(hub)
    old=prepare(hub,B); read_ack(hub,old,B)
    error("unknown_recipient",lambda:call(hub,"handoff_task",**gate,to_worker="missing",summary="Next",evidence=evidence(packet)))
    call(hub,"handoff_task",**gate,to_worker=B.worker_id,summary="Next",evidence=evidence(packet))
    error("wrong_recipient",lambda:call(hub,"claim_task",task_id="t"))
    lease=call(hub,"claim_task",B,task_id="t")
    error("stale_task",lambda:call(hub,"accept_handoff",B,packet_id=old["packet_id"],fence=lease["fence"]))
    fresh=prepare(hub,B); read_ack(hub,fresh,B)
    gate_b={"packet_id":fresh["packet_id"],"fence":lease["fence"]}
    assert fresh["task"]["handoffs"][-1]["summary"] == "Next"
    call(hub,"accept_handoff",B,**gate_b)
    assert call(hub,"validate_task_context",B,**gate_b)["valid"]

def test_invalid_evidence_rolls_back_and_completion(hub):
    packet,gate=ready(hub)
    count=len(call(hub,"audit_log")["events"])
    error("invalid_evidence",lambda:call(hub,"record_checkpoint",**gate,summary="Bad",evidence=[{"source_id":"spec","sha256":"0"*64}]))
    assert len(call(hub,"audit_log")["events"]) == count
    call(hub,"complete_task",**gate,summary="Tests passed",evidence=evidence(packet))
    error("completed",lambda:call(hub,"claim_task",B,task_id="t"))
    audit=call(hub,"audit_log")
    assert audit["events"][-1]["operation"] == "complete_task"
    assert [x["sequence"] for x in audit["events"]] == list(range(1,audit["latest_sequence"]+1))

def test_search_does_not_count_as_read(hub):
    packet=prepare(hub)
    assert call(hub,"search_knowledge",query="memory")["matches"]
    error("unread_context",lambda:call(hub,"acknowledge_context",packet_id=packet["packet_id"]))

@pytest.fixture
def app(tmp_path):
    return create_app(database_url=f"sqlite:///{tmp_path}/app.db",allow_sqlite=True,auth_tokens=json.dumps({TOKEN_A:A.model_dump(),TOKEN_ADMIN:ADMIN.model_dump()}))

def test_rest_auth_fail_closed_and_schema(app):
    with TestClient(app) as client:
        assert client.get("/healthz").json()["backend"] == "sqlite-demo-only"
        assert client.post("/v1/tools/create_project",json={"arguments":{"project_id":"p"}}).status_code == 401
        headers={"Authorization":f"Bearer {TOKEN_ADMIN}"}
        assert client.post("/v1/tools/create_project",headers=headers,json={"arguments":{"project_id":"p"}}).status_code == 200
        assert client.post("/v1/tools/search_knowledge",headers=headers,json={"arguments":{"project_id":"p","query":"x","worker_id":"spoof"}}).status_code == 422
        assert client.post("/mcp",json={}).status_code == 401
        assert client.get("/healthz",headers={"host":"evil.example"}).status_code == 400

def test_mcp_initialize_and_tools_list(app):
    with TestClient(app) as client:
        headers={"Authorization":f"Bearer {TOKEN_A}","Accept":"application/json, text/event-stream"}
        r=client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1"}}})
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "Project Memory Hub"
        r=client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        assert r.status_code == 200, r.text
        assert "prepare_task" in {t["name"] for t in r.json()["result"]["tools"]}

def test_missing_auth_and_sqlite_require_explicit_opt_in(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(database_url=f"sqlite:///{tmp_path}/app.db",auth_tokens="",allow_sqlite=True)
    with pytest.raises(RuntimeError):
        Store(f"sqlite:///{tmp_path}/x.db")


def test_worker_inbox_finds_handoff(hub):
    assert call(hub, "get_worker_inbox", B)["available_tasks"][0]["task_id"] == "t"
    packet, gate = ready(hub)
    assert call(hub, "get_worker_inbox")["owned_tasks"][0]["task_id"] == "t"
    call(hub,"handoff_task",**gate,to_worker=B.worker_id,summary="Review",evidence=evidence(packet))
    inbox = call(hub, "get_worker_inbox", B)
    assert inbox["worker_id"] == "ai-b"
    assert inbox["pending_handoffs"][0]["latest_handoff"]["next_steps"] == ["Review changes"]
    assert call(hub, "get_worker_inbox")["pending_handoffs"] == []


def test_mcp_tool_call_enforces_authenticated_scope(app):
    with TestClient(app) as client:
        headers={"Authorization":f"Bearer {TOKEN_A}","Accept":"application/json, text/event-stream"}
        result=client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"create_project","arguments":{"arguments":{"project_id":"p"}}}})
        assert result.status_code == 200
        assert result.json()["result"]["isError"]
        headers["Authorization"] = f"Bearer {TOKEN_ADMIN}"
        result=client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":8,"method":"tools/call","params":{"name":"create_project","arguments":{"arguments":{"project_id":"p"}}}})
        assert result.status_code == 200
        assert not result.json()["result"].get("isError",False)


def test_body_limit_and_cookie_cannot_authorize_mcp(app):
    with TestClient(app) as client:
        headers={"Authorization":f"Bearer {TOKEN_A}","content-type":"application/json"}
        assert client.post("/v1/tools/prepare_task", headers=headers, content=b"x"*1048577).status_code == 413
        assert client.post("/mcp", cookies={"session":"fake"},json={}).status_code == 401


def test_source_content_preserves_exact_whitespace(hub):
    import hashlib
    content = "  indentation\ntrailing newline\n"
    saved = call(hub,"register_source",ADMIN,source_id="spec",content=content,uri="git:spec",commit="123",expected_revision=call(hub,"get_project_summary")["context_revision"])
    packet = prepare(hub)
    source = call(hub,"read_source",packet_id=packet["packet_id"],source_id="spec")
    assert source["content"] == content
    assert saved["sha256"] == hashlib.sha256(content.encode()).hexdigest()


def recovery_args(h, **overrides):
    packet = prepare(h, ADMIN)
    return {"task_id":"t", "expected_revision":packet["context_revision"],
            "expected_generation":packet["task_generation"], "expected_fence":packet["task"]["fence"],
            "reason":"Assigned worker is unavailable", **overrides}


def test_admin_recovery_revokes_live_lease_and_requires_fresh_packet(hub):
    packet, gate = ready(hub)
    old_b = prepare(hub, B); read_ack(hub, old_b, B)
    args = recovery_args(hub, to_worker=B.worker_id)
    result = call(hub,"recover_task",ADMIN,**args)
    assert result["generation"] == args["expected_generation"] + 1
    assert result["fence"] == args["expected_fence"] + 1
    error("stale_task",lambda:call(hub,"record_checkpoint",**gate,summary="Late write",evidence=evidence(packet)))
    error("stale_task",lambda:call(hub,"renew_lease",**gate))
    error("wrong_recipient",lambda:call(hub,"claim_task",task_id="t"))
    lease = call(hub,"claim_task",B,task_id="t")
    error("stale_task",lambda:call(hub,"accept_handoff",B,packet_id=old_b["packet_id"],fence=lease["fence"]))
    fresh = prepare(hub,B)
    assert fresh["task"]["recoveries"][-1]["reason"] == args["reason"]
    assert fresh["task"]["recoveries"][-1]["previous"]["owner"] == A.worker_id
    new_gate = {"packet_id":fresh["packet_id"],"fence":lease["fence"]}
    error("unread_context",lambda:call(hub,"accept_handoff",B,**new_gate))
    read_ack(hub,fresh,B)
    call(hub,"accept_handoff",B,**new_gate)
    assert call(hub,"validate_task_context",B,**new_gate)["valid"]
    events = call(hub,"audit_log")["events"]
    audit = [event for event in events if event["operation"] == "recover_task"]
    assert len(audit) == 1
    assert audit[0]["worker_id"] == ADMIN.worker_id
    assert audit[0]["references"]["recovery_id"] == result["recovery_id"]


def test_recovery_unassigns_retired_recipient_and_preserves_history(hub):
    packet, gate = ready(hub)
    call(hub,"handoff_task",**gate,to_worker=B.worker_id,summary="Continue",evidence=evidence(packet))
    hub = Hub(hub.store, clock=hub.clock, principals=[ADMIN, A])  # Worker retired on configuration reload.
    error("wrong_recipient",lambda:call(hub,"claim_task",task_id="t"))
    result = call(hub,"recover_task",ADMIN,**recovery_args(hub),to_worker=None)
    assert result["pending_recipient"] is None
    inbox = call(hub,"get_worker_inbox")
    assert inbox["available_tasks"][0]["latest_recovery"]["to_worker"] is None
    assert inbox["available_tasks"][0]["latest_handoff"]["summary"] == "Continue"
    fresh, new_gate = ready(hub)
    assert len(fresh["task"]["handoffs"]) == 1
    assert call(hub,"validate_task_context",**new_gate)["valid"]


def test_recovery_requires_admin_scope_nonempty_reason_and_verified_recipient(hub):
    from pydantic import ValidationError
    args = recovery_args(hub)
    approver = Principal(worker_id="reviewer",projects=["p"],role="approver")
    outsider = Principal(worker_id="external-admin",projects=["elsewhere"],role="admin")
    for identity in (A, B, approver, outsider):
        error("forbidden",lambda identity=identity:call(hub,"recover_task",identity,**args))
    with pytest.raises(ValidationError):
        call(hub,"recover_task",ADMIN,**{**args,"reason":"  \n "})
    with pytest.raises(ValidationError):
        call(hub,"recover_task",ADMIN,**{k:v for k,v in args.items() if k != "reason"})
    error("unknown_recipient",lambda:call(hub,"recover_task",ADMIN,**args,to_worker="not-configured"))
    hub = Hub(hub.store, clock=hub.clock, principals=[*hub.principals, Principal(worker_id="different-project",projects=["elsewhere"])])
    error("unknown_recipient",lambda:call(hub,"recover_task",ADMIN,**args,to_worker="different-project"))
    after = prepare(hub,ADMIN)
    assert after["task"]["recoveries"] == []
    assert after["task"]["fence"] == args["expected_fence"]
    assert not any(e["operation"] == "recover_task" for e in call(hub,"audit_log")["events"])


def test_recovery_rejects_stale_project_generation_and_claim_guards(hub):
    args = recovery_args(hub)
    call(hub,"register_source",ADMIN,source_id="spec",content="Changed",uri="git:spec",commit="456",expected_revision=args["expected_revision"])
    error("stale_context",lambda:call(hub,"recover_task",ADMIN,**args))
    args = recovery_args(hub)
    call(hub,"claim_task",task_id="t")
    error("stale_fence",lambda:call(hub,"recover_task",ADMIN,**args))
    args = recovery_args(hub)
    call(hub,"recover_task",ADMIN,**args)
    error("stale_task",lambda:call(hub,"recover_task",ADMIN,**args))
    assert len(prepare(hub,ADMIN)["task"]["recoveries"]) == 1


def test_concurrent_recovery_only_one_wins(hub):
    args = recovery_args(hub)
    def recover(_):
        try:
            return call(hub,"recover_task",ADMIN,**args)
        except HubError as exc:
            return exc.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(recover,range(2)))
    assert sum(isinstance(result,dict) for result in results) == 1
    assert "stale_task" in results
    assert len(prepare(hub,ADMIN)["task"]["recoveries"]) == 1


def test_recovery_does_not_reopen_completed_task(hub):
    packet,gate = ready(hub)
    args = recovery_args(hub)
    call(hub,"complete_task",**gate,summary="Done",evidence=evidence(packet))
    error("completed",lambda:call(hub,"recover_task",ADMIN,**args))


def test_recovery_tool_transport_exposure_and_role_enforcement(app):
    hub = app.state.hub
    call(hub,"create_project",ADMIN)
    call(hub,"register_source",ADMIN,source_id="spec",content="Spec",uri="git:spec",commit="123")
    call(hub,"create_task",ADMIN,task_id="t",goal="Test",allowed_paths=["src/**"],acceptance_criteria=["Tests pass"],source_ids=["spec"])
    args = {"project_id":"p",**recovery_args(hub)}
    with TestClient(app) as client:
        headers={"Authorization":f"Bearer {TOKEN_A}","Accept":"application/json, text/event-stream"}
        result=client.post("/mcp",headers=headers,json={"jsonrpc":"2.0","id":20,"method":"tools/list","params":{}})
        schema=next(t["inputSchema"] for t in result.json()["result"]["tools"] if t["name"] == "recover_task")
        assert "arguments" in schema["properties"]
        assert client.post("/v1/tools/recover_task",headers=headers,json={"arguments":args}).status_code == 403
        headers["Authorization"] = f"Bearer {TOKEN_ADMIN}"
        result=client.post("/v1/tools/recover_task",headers=headers,json={"arguments":args})
        assert result.status_code == 200
        assert result.json()["generation"] == 1
