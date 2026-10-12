"""Auth tests: token issuance, valid bearer, invalid, expired, role gating."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from triage_api.app import app
from triage_api.auth import JWT_ALGORITHM, JWT_SECRET, JWT_EXPIRES_MINUTES, USERNAME, PASSWORD
from triage_api import rate_limit


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit.reset_for_tests()
    yield
    rate_limit.reset_for_tests()


@pytest.fixture
def client():
    return TestClient(app)


def _get_token(client: TestClient, username: str = USERNAME, password: str = PASSWORD) -> str:
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_token_issued_for_valid_creds(client):
    r = client.post("/token", data={"username": USERNAME, "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20
    assert body["expires_in"] == JWT_EXPIRES_MINUTES * 60


def test_token_rejected_for_bad_password(client):
    r = client.post("/token", data={"username": USERNAME, "password": "wrong"})
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_protected_route_rejects_missing_header(client):
    r = client.post("/triage", json={
        "patient_id": "P-1", "symptoms": ["cough"], "age": 30, "sex": "F",
    })
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_protected_route_rejects_bad_signature(client):
    bad = jwt.encode({"sub": USERNAME, "role": "triage_nurse",
                      "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=5)},
                     "a" * 32, algorithm=JWT_ALGORITHM)
    r = client.post("/triage", json={
        "patient_id": "P-1", "symptoms": ["cough"], "age": 30, "sex": "F",
    }, headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_protected_route_rejects_expired_token(client):
    expired = jwt.encode({"sub": USERNAME, "role": "triage_nurse",
                          "exp": datetime.now(tz=timezone.utc) - timedelta(minutes=1)},
                         JWT_SECRET, algorithm=JWT_ALGORITHM)
    r = client.post("/triage", json={
        "patient_id": "P-1", "symptoms": ["cough"], "age": 30, "sex": "F",
    }, headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_triage_nurse_role_cannot_call_agent_ask(client):
    token = _get_token(client)  # default user is triage_nurse
    r = client.post("/agent/ask", json={"question": "anything"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "dispatcher" in r.json()["detail"].lower()