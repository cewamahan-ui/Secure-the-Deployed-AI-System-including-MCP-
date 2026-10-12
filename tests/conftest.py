"""Shared test fixtures for the Week 9 capstone test suite.

The root conftest.py injects the per-session JWT_SECRET (fail-closed
boot needs one present); this file adds the shared FastAPI test client
and the rate-limit reset the API tests rely on.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from triage_api import rate_limit
from triage_api.app import app


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit.reset_for_tests()
    yield
    rate_limit.reset_for_tests()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_header(client):
    r = client.post("/token", data={"username": "olu", "password": "olu-pass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
