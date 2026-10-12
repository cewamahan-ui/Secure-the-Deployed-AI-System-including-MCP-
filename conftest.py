"""Test-session secrets.

triage_api.auth now fails closed: importing it without JWT_SECRET in the
environment raises RuntimeError. That is the production behaviour we
want. The test suite injects an ephemeral per-session secret here -
the same way a deploy injects it, one step before the process starts -
so tests exercise the real fail-closed code path with a throwaway key.

This file is imported by pytest before any test module, which is why the
env var is set at import time.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-session-only-not-a-production-key")
