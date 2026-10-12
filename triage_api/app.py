"""FastAPI service for the AfyaPlus triage platform.

Endpoints:
  GET  /health      unprotected - for liveness/readiness probes
  POST /token       username/password -> JWT (OAuth2PasswordRequestForm)
  POST /triage      protected, rate-limited, Pydantic-validated
  POST /agent/ask   protected, role=dispatcher - delegates to the agent

The trace-id middleware sets a single id for the request that appears in
the response header `x-trace-id`, in the response body, and in any log
line the downstream agent or MCP tool emits.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from injection_guard import InjectionBlocked, detect, require_safe
from redact_then_hash import audit
from . import __version__, trace, rate_limit
from .auth import (
    TokenForm,
    authenticate,
    create_access_token,
    get_current_user,
    require_role,
)
from .model import MODEL_CARD, classify
from .models import HealthResponse, TriageRequest, TriageResponse

log = logging.getLogger("afyaplus.triage")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s trace_id=%(trace_id)s %(message)s',
)


class _TraceIdFilter(logging.Filter):
    """Default trace_id so the %-format never KeyErrors on third-party lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = trace.get_trace_id()
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(_TraceIdFilter())

SERVICE_NAME = os.getenv("SERVICE_NAME", "afyaplus-triage")
RATE_LIMIT_CALLS = int(os.getenv("RATE_LIMIT_CALLS", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
CORS_ALLOW_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()
]

app = FastAPI(
    title="AfyaPlus Triage",
    version=__version__,
    description="Secure FastAPI service wrapping a triage model (stub or LLM).",
)

# Injected at build time via env; "dev" is the local default.
BUILD_SHA = os.getenv("BUILD_SHA", "dev")

# Set at import time so /health can report uptime.
import time as _time
_APP_STARTED_AT = _time.monotonic()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# trace-id middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    incoming = request.headers.get("x-trace-id")
    tid = incoming or trace.new_trace_id()
    trace.set_trace_id(tid)
    response = await call_next(request)
    response.headers["x-trace-id"] = tid
    log.info("api_call", extra={"trace_id": tid})
    return response


# ---------------------------------------------------------------------------
# /health - unprotected on purpose, so probes do not need a token
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        service=SERVICE_NAME,
        version=__version__,
        model_card=MODEL_CARD,
        build_sha=BUILD_SHA,
        uptime_seconds=round(_time.monotonic() - _APP_STARTED_AT, 2),
    )


# ---------------------------------------------------------------------------
# /token - OAuth2 password flow
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@app.post("/token", response_model=TokenResponse)
def issue_token(form: TokenForm = Depends()):
    principal = authenticate(form.username, form.password)
    if principal is None:
        # 401 on bad creds, with WWW-Authenticate per RFC 6750.
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "invalid credentials"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(principal["sub"], principal["role"])
    from .auth import JWT_EXPIRES_MINUTES
    return TokenResponse(access_token=token, expires_in=JWT_EXPIRES_MINUTES * 60)


# ---------------------------------------------------------------------------
# /triage - protected, rate-limited
# ---------------------------------------------------------------------------

@app.post("/triage", response_model=TriageResponse)
def triage(req: TriageRequest, user: dict = Depends(get_current_user)):
    rate_limit.check(
        subject=user["sub"],
        max_calls=RATE_LIMIT_CALLS,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    )
    # Week 9: the injection guard runs BEFORE the model is called and
    # returns 400 without touching classify(). Authentication is still
    # the Week 6 JWT dependency above - authorisation was added, never
    # swapped in for authentication.
    try:
        require_safe(" ".join(req.symptoms))
    except InjectionBlocked as exc:
        audit(
            actor=user["sub"],
            action="triage",
            resource="/triage",
            outcome="denied",
            trace_id=trace.get_trace_id(),
            payload={"symptoms": req.symptoms, "patient_id": req.patient_id},
            guard="injection_guard:" + ",".join(sorted(set(detect(" ".join(req.symptoms))))),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    log.info("triage_call", extra={"trace_id": trace.get_trace_id()})
    response = classify(req)
    audit(
        actor=user["sub"],
        action="triage",
        resource="/triage",
        outcome="ok",
        trace_id=trace.get_trace_id(),
        payload={
            "patient_id": req.patient_id,
            "symptoms": req.symptoms,
            "acuity": response.acuity.value,
            "disposition": response.disposition.value,
        },
    )
    return response


# ---------------------------------------------------------------------------
# /agent/ask - protected, dispatcher role only
# Imported lazily to avoid pulling langchain when only the triage API runs.
# ---------------------------------------------------------------------------

class AgentAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    recursion_limit: int = Field(default=6, ge=1, le=12)


class AgentAskResponse(BaseModel):
    answer: str
    tool_calls: list[dict] = Field(default_factory=list)
    trace_id: str


@app.post("/agent/ask", response_model=AgentAskResponse)
def agent_ask(
    body: AgentAskRequest,
    user: dict = Depends(require_role("dispatcher")),
):
    # Imported here so importing this module never fails when MCP/LLM
    # dependencies are missing.
    from agent.api import ask
    result = ask(
        question=body.question,
        trace_id=trace.get_trace_id(),
        recursion_limit=body.recursion_limit,
    )
    return AgentAskResponse(
        answer=result["answer"],
        tool_calls=result["tool_calls"],
        trace_id=trace.get_trace_id(),
    )