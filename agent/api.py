"""Agent API shim - imported lazily by triage_api.app.

Keeps a single import path so the FastAPI module does not have to know
about the agent implementation file layout.
"""

from .agent import ask  # re-export

__all__ = ["ask"]