"""Relay-only contracts; these APIs never run a model or grant task authority."""
from typing import Literal
from pydantic import Field, model_validator
from .session_models import SessionModel, SessionRef, ProjectId, ObjectId, Key


class JoinDelivery(SessionRef):
    client: Literal['claude', 'codex', 'chatgpt', 'gemini', 'grok', 'other']
    display_name: str = Field(min_length=1, max_length=80)
    native_session_id: str = Field(min_length=1, max_length=256)
    after_sequence: int | None = Field(default=None, ge=0, le=9223372036854775807)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    max_turns: int = Field(default=20, ge=1, le=100)
    idempotency_key: Key


class BindingRef(SessionModel):
    project_id: ProjectId
    binding_id: ObjectId


class ClaimDelivery(BindingRef):
    lease_seconds: int = Field(default=120, ge=15, le=300)
    request_id: ObjectId | None = None
    generation: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def recovery_identity_is_paired(self):
        if (self.request_id is None) != (self.generation is None):
            raise ValueError('request_id and generation must be supplied together')
        return self


class DispatchDelivery(BindingRef):
    delivery_id: ObjectId
    lease_id: ObjectId


class PauseDelivery(SessionRef):
    paused: bool
    expected_version: int = Field(ge=1)
    idempotency_key: Key | None = None


class ControlBinding(BindingRef):
    enabled: bool
    expected_version: int = Field(ge=1)


class DisconnectBinding(BindingRef):
    expected_version: int = Field(ge=1)


DELIVERY_MODELS = {'join': JoinDelivery, 'heartbeat': BindingRef, 'claim': ClaimDelivery,
                   'dispatched': DispatchDelivery, 'pause': PauseDelivery, 'control': ControlBinding,
                   'disconnect': DisconnectBinding, 'status': SessionRef}
