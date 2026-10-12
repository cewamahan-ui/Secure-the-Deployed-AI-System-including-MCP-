"""Pydantic models for the triage API.

Lesson reference: Monday Lesson 3 - typed request checks; bad input earns
422 BEFORE your code runs.

The TriageRequest is what the client posts. The field constraints
(constrained strings, bounded ints, enums) are the contract that catches
malformed payloads upstream of the model call.

TriageResponse is what we promise back. Stable shape - the agent in
`agent/api.py` consumes it, so adding fields is backwards-compatible
(append-only), removing them is a breaking change (MAJOR bump).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums - these become 422 if the caller sends anything else
# ---------------------------------------------------------------------------

class Sex(str, Enum):
    M = "M"
    F = "F"
    OTHER = "OTHER"


class Acuity(str, Enum):
    """ESI-inspired 5-level scale used by AfyaPlus.

    1 = Resuscitation, 5 = Non-urgent. Lower is sicker.
    """
    ESI_1 = "ESI-1"
    ESI_2 = "ESI-2"
    ESI_3 = "ESI-3"
    ESI_4 = "ESI-4"
    ESI_5 = "ESI-5"


class Disposition(str, Enum):
    ED = "ED"                     # emergency department, immediate
    URGENT_CLINIC = "URGENT_CLINIC"
    PRIMARY_CAT = "PRIMARY_CARE"
    SELF_CAT = "SELF_CARE"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class TriageRequest(BaseModel):
    """What the client posts to /triage.

    Field constraints exist for two reasons:
      1. They keep bad input out of the LLM call (cost + safety).
      2. They are machine-checkable, so the API can answer 422 without
         invoking the model - which is the whole point of Pydantic.
    """

    # Patient identifier - non-empty, bounded so it cannot be used to
    # smuggle megabytes of text into the prompt.
    patient_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Stable patient identifier from the EMR.",
        examples=["P-1042"],
    )

    # Free-text symptom list. Each symptom is short; whole list is bounded.
    symptoms: list[str] = Field(
        ...,
        min_length=1,
        max_length=12,
        description="Symptoms reported by the patient or caller.",
        examples=[["chest pain", "shortness of breath"]],
    )

    age: int = Field(
        ...,
        ge=0,
        le=120,
        description="Patient age in years.",
        examples=[58],
    )

    sex: Sex = Field(
        ...,
        description="M / F / OTHER",
        examples=["M"],
    )

    # Vitals - all optional, but constrained when present. None means
    # "not measured", which the model must treat as missing data, not zero.
    heart_rate: Optional[int] = Field(default=None, ge=0, le=300)
    systolic_bp: Optional[int] = Field(default=None, ge=0, le=300)
    spo2: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    temperature_c: Optional[float] = Field(default=None, ge=25.0, le=45.0)

    # Idempotency hint (Thursday Lesson 5). Same key, same response.
    request_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("symptoms")
    @classmethod
    def _strip_and_drop_empty(cls, v: list[str]) -> list[str]:
        cleaned = [s.strip() for s in v if s and s.strip()]
        if not cleaned:
            raise ValueError("symptoms must contain at least one non-empty entry")
        return cleaned

    @field_validator("patient_id")
    @classmethod
    def _no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("patient_id must not be whitespace-only")
        return v.strip()


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class TriageResponse(BaseModel):
    """Stable response contract. Append-only - see module docstring."""

    request_id: str = Field(..., description="Echoed back; same id = same answer.")
    patient_id: str
    acuity: Acuity
    disposition: Disposition
    red_flags: list[str] = Field(
        default_factory=list,
        description="Symptoms that drove the acuity decision.",
    )
    rationale: str = Field(
        ...,
        description="One-sentence clinician-facing explanation.",
    )
    next_step: str = Field(
        default="",
        description="Operational next step (added in v1.1.0).",
    )
    model_card: str = Field(
        ...,
        description="Which model answered (stub name or real model id).",
    )
    served_at: datetime
    trace_id: str = Field(..., description="Same id appears in API and tool logs.")


class HealthResponse(BaseModel):
    service: str
    version: str
    status: str = "ok"
    model_card: str
    build_sha: str = "dev"
    uptime_seconds: float = 0.0
