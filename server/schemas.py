"""Pydantic models for request/response payloads."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class SDPOffer(BaseModel):
    sdp: str
    type: str = "offer"


class SDPAnswer(BaseModel):
    sdp: str
    type: str = "answer"


class ICECandidate(BaseModel):
    candidate: str
    sdp_mid: str | None = None
    sdp_m_line_index: int | None = None
