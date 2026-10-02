"""Explicit sandbox mutation demo. Requires operator-provisioned credentials."""
import json
import os
import urllib.request
import uuid
from urllib.parse import urlparse


def main():
    base = os.environ["HUB_URL"].rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        raise SystemExit("Use HTTPS, or HTTP only on loopback")
    project = os.environ["HUB_PROJECT"]
    admin, a, b = [os.environ[k] for k in (
        "HUB_ADMIN_TOKEN", "HUB_WORKER_A_TOKEN", "HUB_WORKER_B_TOKEN")]
    recipient = os.environ["HUB_WORKER_B_ID"]
    suffix = uuid.uuid4().hex[:12]
    task, source = "demo-" + suffix, "requirements-" + suffix

    def call(token, name, **arguments):
        body = json.dumps({"arguments": {"project_id": project, **arguments}}).encode()
        req = urllib.request.Request(base + "/v1/tools/" + name, data=body,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)

    call(admin, "create_project")
    call(admin, "register_source", source_id=source,
         content="Sandbox acceptance: demonstrate explicit handoff without editing files.",
         uri="local://sandbox/requirements", commit="sandbox-demo-no-code-change")
    call(admin, "create_task", task_id=task, goal="Demonstrate A to B handoff",
         allowed_paths=["docs/"], acceptance_criteria=["B accepts fresh context and completes"],
         source_ids=[source])

    def start(token, branch):
        packet = call(token, "prepare_task", task_id=task,
                      workspace="sandbox-demo-no-filesystem-access", branch=branch,
                      commit="sandbox-demo-no-code-change")
        claim = call(token, "claim_task", task_id=task)
        fields = {"packet_id": packet["packet_id"]}
        for source_id in packet["required_sources"]:
            result = call(token, "read_source", **fields, source_id=source_id)
            assert result["sha256"] == packet["required_sources"][source_id]
        call(token, "acknowledge_context", **fields)
        fields["fence"] = claim["fence"]
        call(token, "accept_handoff", **fields)
        assert call(token, "validate_task_context", **fields)["valid"]
        evidence = [{"source_id": key, "sha256": value}
                    for key, value in packet["required_sources"].items()]
        return fields, evidence

    fields, evidence = start(a, "demo/a")
    call(a, "record_checkpoint", **fields, summary="No files edited; ready to hand off", evidence=evidence)
    call(a, "handoff_task", **fields, to_worker=recipient,
         summary="Please read fresh context and complete this sandbox demonstration", evidence=evidence,
         changed_artifacts=[], result_commit="sandbox-demo-no-code-change",
         test_results=[{"command":"workflow demonstration", "status":"not_run", "details":"No application code test is claimed"}],
         blockers=[], next_steps=["Read fresh context, accept and complete the sandbox task"])
    inbox = call(b, "get_worker_inbox")
    assert any(item["task_id"] == task for item in inbox["pending_handoffs"])
    fields, evidence = start(b, "demo/b")
    result = call(b, "complete_task", **fields,
                  summary="B read fresh context and accepted; workflow demo only, no code tests claimed", evidence=evidence)
    assert result["status"] == "completed"
    print(json.dumps({"project_id": project, "task_id": task, "status": result["status"]}))


if __name__ == "__main__":
    main()
