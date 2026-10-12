"""Trace id propagation.

One id links API, agent, and MCP logs for a single request.
Generated in the API middleware, stored in a ContextVar so any downstream
code can read it without threading it through every signature, and echoed
back in the response header `x-trace-id`.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# Set by the API middleware on every request. Read by the agent and by
# tool wrappers so the same id appears in every log line.
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="-")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(trace_id: str) -> None:
    current_trace_id.set(trace_id)


def get_trace_id() -> str:
    return current_trace_id.get()