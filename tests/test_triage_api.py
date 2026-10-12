"""Triage API tests: 200, 422, 429, /health, idempotency."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from triage_api.app import app
from triage_api.auth import PASSWORD, USERNAME
from triage_api import rate_limit


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
    r = client.post("/token", data={"username": USERNAME, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]
    assert body["model_card"]


def test_triage_200_happy_path(client, auth_header):
    r = client.post("/triage", headers=auth_header, json={
        "patient_id": "P-1042",
        "symptoms": ["chest pain", "shortness of breath"],
        "age": 58, "sex": "M",
        "spo2": 91.0,
        "request_id": "req-abc-001",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["acuity"] in ("ESI-1", "ESI-2", "ESI-3", "ESI-4", "ESI-5")
    assert body["disposition"]
    assert "chest pain" in body["red_flags"] or "shortness of breath" in body["red_flags"]
    assert body["request_id"] == "req-abc-001"
    assert body["model_card"]
    assert body["trace_id"]


def test_triage_422_on_bad_age(client, auth_header):
    r = client.post("/triage", headers=auth_header, json={
        "patient_id": "P-1", "symptoms": ["cough"], "age": 999, "sex": "F",
    })
    assert r.status_code == 422


def test_triage_422_on_empty_symptoms(client, auth_header):
    r = client.post("/triage", headers=auth_header, json={
        "patient_id": "P-1", "symptoms": ["", "  "], "age": 30, "sex": "F",
    })
    assert r.status_code == 422


def test_triage_422_on_bad_spo2(client, auth_header):
    r = client.post("/triage", headers=auth_header, json={
        "patient_id": "P-1", "symptoms": ["cough"], "age": 30, "sex": "F", "spo2": 150,
    })
    assert r.status_code == 422


def test_triage_429_after_rate_limit(client, auth_header):
    payload = {"patient_id": "P-1", "symptoms": ["cough"], "age": 30, "sex": "F"}
    statuses = []
    for _ in range(6):  # limit is 5
        r = client.post("/triage", headers=auth_header, json=payload)
        statuses.append(r.status_code)
    assert 429 in statuses
    # last response should be 429 with Retry-After
    last = client.post("/triage", headers=auth_header, json=payload)
    assert last.status_code == 429
    assert "retry-after" in {k.lower() for k in last.headers.keys()}


def test_idempotency_same_request_id_same_answer(client, auth_header):
    payload = {
        "patient_id": "P-9",
        "symptoms": ["cough"],
        "age": 30, "sex": "F",
        "request_id": "req-fixed-001",
    }
    r1 = client.post("/triage", headers=auth_header, json=payload)
    rate_limit.reset_for_tests()  # bypass the rate limiter for the second call
    r2 = client.post("/triage", headers=auth_header, json=payload)
    assert r1.status_code == r2.status_code == 200
    for k in ("acuity", "disposition", "red_flags", "rationale", "model_card", "patient_id", "request_id"):
        assert r1.json()[k] == r2.json()[k]