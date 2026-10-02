from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Principal(Model):
    worker_id: str = Field(min_length=1, max_length=128)
    projects: list[str] = Field(min_length=1)
    role: Literal["worker", "approver", "admin"] = "worker"

class Project(Model):
    project_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")

class SourceEntry(Model):
    source_id: str = Field(min_length=1, max_length=128)
    content: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=200000)
    uri: str = Field(min_length=1, max_length=2048)
    commit: str = Field(min_length=1, max_length=128)

class Source(SourceEntry, Project):
    expected_revision: int | None = Field(default=None, ge=1)

class SourceImport(Project):
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    sources: list[SourceEntry] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_batch(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("Source IDs must be unique within a batch")
        if sum(len(source.content.encode("utf-8")) for source in self.sources) > 750000:
            raise ValueError("Batch source content exceeds 750000 UTF-8 bytes")
        return self

class Page(Project):
    after_id: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=50, ge=1, le=100)

class SourceMetadata(Project):
    source_id: str = Field(min_length=1, max_length=128)
    before_version: int | None = Field(default=None, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

class Reindex(Project):
    expected_revision: int = Field(ge=1)

class Task(Project):
    task_id: str = Field(min_length=1, max_length=128)

class CreateTask(Task):
    goal: str = Field(min_length=1, max_length=10000)
    allowed_paths: list[str] = Field(min_length=1, max_length=100)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    source_ids: list[str] = Field(min_length=1, max_length=100)

class Prepare(Task):
    workspace: str = Field(min_length=1, max_length=2048)
    branch: str = Field(min_length=1, max_length=256)
    commit: str = Field(min_length=1, max_length=128)

class Claim(Task):
    lease_seconds: int = Field(default=300, ge=30, le=3600)

class RecoverTask(Task):
    expected_revision: int = Field(ge=1)
    expected_generation: int = Field(ge=0)
    expected_fence: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=4000)
    to_worker: str | None = Field(default=None, min_length=1, max_length=128)

class Packet(Project):
    packet_id: str = Field(min_length=1, max_length=128)

class ReadSource(Packet):
    source_id: str = Field(min_length=1, max_length=128)

class Gate(Packet):
    fence: int = Field(ge=1)

class Renew(Gate):
    lease_seconds: int = Field(default=300, ge=30, le=3600)

class Evidence(Model):
    source_id: str = Field(min_length=1, max_length=128)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

class Checkpoint(Gate):
    summary: str = Field(min_length=1, max_length=20000)
    evidence: list[Evidence] = Field(min_length=1, max_length=100)

class Proposal(Gate):
    text: str = Field(min_length=1, max_length=20000)
    evidence: list[Evidence] = Field(min_length=1, max_length=100)

class Approve(Project):
    decision_id: str
    expected_revision: int = Field(ge=1)

class TestResult(Model):
    command: str = Field(min_length=1, max_length=2000)
    status: Literal["passed", "failed", "not_run"]
    details: str = Field(min_length=1, max_length=10000)

class Handoff(Checkpoint):
    changed_artifacts: list[str] = Field(max_length=100)
    result_commit: str = Field(min_length=1, max_length=128)
    test_results: list[TestResult] = Field(min_length=1, max_length=100)
    blockers: list[str] = Field(max_length=100)
    next_steps: list[str] = Field(min_length=1, max_length=100)
    to_worker: str = Field(min_length=1, max_length=128)

class Search(Project):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)


ThreadId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r'^[a-zA-Z0-9_.-]+$')]


class SendMessage(Project):
    recipient_worker_id: str = Field(min_length=1, max_length=128)
    thread_id: ThreadId
    body: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(min_length=1, max_length=8000,
        description='Exact text, including whitespace; nonblank and at most 8000 UTF-8 bytes. NUL is not supported.')
    idempotency_key: str = Field(min_length=1, max_length=128)
    reply_to_message_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode='after')
    def validate_body(self):
        identifiers = (self.recipient_worker_id, self.idempotency_key, self.reply_to_message_id)
        if any(value is not None and '\x00' in value for value in identifiers):
            raise ValueError('Message identifiers must not contain NUL')
        if not self.body.strip() or '\x00' in self.body or len(self.body.encode('utf-8'))>8000:
            raise ValueError('Message body must be nonblank, without NUL, and fit within 8000 UTF-8 bytes')
        return self


class ListMessages(Project):
    thread_id: ThreadId | None = None
    after_sequence: int = Field(default=0, ge=0, le=9223372036854775807)
    limit: int = Field(default=20, ge=1, le=50)


MODELS = {
    "send_message":SendMessage, "list_messages":ListMessages,
    "import_sources":SourceImport, "list_sources":Page, "get_source_metadata":SourceMetadata,
    "get_project_summary":Project, "list_tasks":Page, "index_health":Project, "reindex_project":Reindex,
    "create_project": Project, "register_source": Source, "create_task": CreateTask,
    "recover_task": RecoverTask, "prepare_task": Prepare, "claim_task": Claim, "read_source": ReadSource,
    "acknowledge_context": Packet, "accept_handoff": Gate, "validate_task_context": Gate,
    "record_checkpoint": Checkpoint, "propose_memory_change": Proposal,
    "approve_memory_change": Approve, "handoff_task": Handoff,
    "renew_lease": Renew, "complete_task": Checkpoint,
    "get_worker_inbox": Project, "search_knowledge": Search, "audit_log": Project,
}
