"""Pydantic models for request/response payloads."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class RecordingStatus(BaseModel):
    active: bool
    run_id: str | None = None
    samples: int = 0
    state: str
