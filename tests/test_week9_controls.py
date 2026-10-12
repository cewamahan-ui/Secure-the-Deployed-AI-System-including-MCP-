"""Week 9 control tests: transit, redaction/hashing, retention, pins,
fail-closed secrets, manager brief.

These are the pytest evidence named in the submission checklist:
transit policy, guard (tests/test_injection_guard.py), role matrix
(test_rbac.py), redactor (below), pins (below).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


# --------------------------------------------------------------------------
# Transit policy
# --------------------------------------------------------------------------

def test_transit_ok_allows_https_anywhere():
    from transit_policy import transit_ok
    ok, _ = transit_ok("https://api.benkiyetu.co.ke/triage")
    assert ok


def test_transit_ok_allows_localhost_http_as_lab_exception():
    from transit_policy import transit_ok
    ok, reason = transit_ok("http://localhost:8000/health")
    assert ok
    assert "lab exception" in reason


def test_transit_ok_denies_cleartext_partner_host():
    """The captured failing run: cleartext to a partner host is refused."""
    from transit_policy import transit_ok
    ok, reason = transit_ok("http://partner.benkiyetu.co.ke/triage")
    assert not ok
    assert "https" in reason


def test_transit_policy_cli_fails_on_cleartext():
    """The CLI exits 1 because the demo list includes a cleartext URL."""
    proc = subprocess.run(
        [sys.executable, "transit_policy.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 1
    assert "DENY" in proc.stdout


# --------------------------------------------------------------------------
# Redact then hash
# --------------------------------------------------------------------------

def test_redaction_strips_bearer_token_and_phone():
    from redact_then_hash import build_event
    event = build_event(
        actor="olu", action="triage", resource="/triage", outcome="ok",
        payload={"note": "call back on +254712345678, auth Bearer eyJhbGciOi.abc123"},
    )
    line = json.dumps(event)
    assert "eyJhbGciOi" not in line
    assert "254712345678" not in line
    assert "[REDACTED]" in line


def test_doubled_bearer_prefix_leaves_no_token_residue():
    """Regression: 'bearer Bearer <tok>' once redacted the prefix pair
    and left the token itself in the line. Fixpoint redaction must not."""
    from redact_then_hash import build_event, contains_no_secrets
    event = build_event(
        actor="olu", action="triage", resource="/triage", outcome="ok",
        payload={"note": "auth: bearer Bearer abc123SECRET"},
    )
    line = json.dumps(event)
    assert "abc123SECRET" not in line
    assert contains_no_secrets(line)


def test_patient_id_is_hashed_not_stored():
    from redact_then_hash import build_event
    event = build_event(
        actor="olu", action="triage", resource="/triage", outcome="ok",
        payload={"patient_id": "P-1042", "symptoms": ["chest pain"]},
    )
    assert "patient_id" not in event["payload"]
    assert event["subject_hash"] and len(event["subject_hash"]) == 12
    assert "P-1042" not in json.dumps(event)


def test_hash_is_stable_and_salted_shape():
    from redact_then_hash import _hash_value
    a, b = _hash_value("P-1042"), _hash_value("P-1042")
    assert a == b and len(a) == 12 and all(c in "0123456789abcdef" for c in a)


def test_audit_line_written_to_jsonl(tmp_path):
    from redact_then_hash import audit
    target = tmp_path / "audit.jsonl"
    audit(actor="olu", action="triage", resource="/triage", outcome="ok",
          payload={"patient_id": "P-9"}, path=target)
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["action"] == "triage"
    assert row["outcome"] == "ok"


# --------------------------------------------------------------------------
# Retention sweep
# --------------------------------------------------------------------------

def test_sweep_deletes_only_expired_non_hold_records():
    import retention_sweep as rs
    rules = rs._load_rules()
    store = json.loads((ROOT / "fixtures" / "triage_store.json").read_text(encoding="utf-8"))
    kept, deleted = rs.sweep(store, rules, now=datetime(2026, 10, 12, tzinfo=timezone.utc))
    deleted_ids = {r["id"] for r in deleted}
    kept_ids = {r["id"] for r in kept}
    assert deleted_ids == {"TM-001", "TM-002", "MQ-001"}
    assert kept_ids == {"TM-003", "TM-004", "AL-001"}


def test_legal_hold_beats_retention():
    import retention_sweep as rs
    rules = rs._load_rules()
    store = [{"id": "TM-HOLD", "dataset": "triage_messages",
              "created_at": "2020-01-01T00:00:00+00:00", "legal_hold": True}]
    kept, deleted = rs.sweep(store, rules)
    assert kept and not deleted


def test_deletion_log_is_never_swept():
    import retention_sweep as rs
    # Asking to sweep the deletion log itself: hard stop.
    with pytest.raises(RuntimeError, match="never_delete"):
        rs.protect_deletion_log("deletion_records")
    # And a deletion-log record inside a store survives the sweep.
    rules = rs._load_rules()
    store = [{"id": "DL-1", "dataset": "deletion_records",
              "created_at": "2020-01-01T00:00:00+00:00"}]
    kept, deleted = rs.sweep(store, rules)
    assert kept and not deleted


def test_weakened_rule_blocks_sweep(tmp_path):
    import retention_sweep as rs
    import json as _json
    bad = _json.loads(rs.RETENTION_PATH.read_text(encoding="utf-8"))
    bad["rules"]["deletion_records"]["action"] = "delete"
    fake = tmp_path / "retention.json"
    fake.write_text(_json.dumps(bad), encoding="utf-8")
    real = rs.RETENTION_PATH
    rs.RETENTION_PATH = fake
    try:
        with pytest.raises(RuntimeError, match="never_delete"):
            rs.protect_deletion_log()
    finally:
        rs.RETENTION_PATH = real


def test_deletion_record_roundtrip(tmp_path):
    import retention_sweep as rs
    target = tmp_path / "deletion_records.jsonl"
    rs.record_deletion("triage_messages", "TM-X", path=target)
    row = json.loads(target.read_text(encoding="utf-8").strip())
    assert row["dataset"] == "triage_messages"
    assert row["actor"] == "retention_sweep"


# --------------------------------------------------------------------------
# Corpus pin
# --------------------------------------------------------------------------

def test_corpus_pin_verifies_clean():
    import corpus_pin
    ok, drift = corpus_pin.verify()
    assert ok, f"corpus drift: {drift}"


def test_corpus_pin_detects_drift(tmp_path, monkeypatch):
    import corpus_pin
    pinned = json.loads(corpus_pin.PIN_PATH.read_text(encoding="utf-8"))
    # Corrupt one hash to simulate an unreviewed corpus edit.
    first = next(iter(pinned["files"]))
    pinned["files"][first]["sha256"] = "0" * 64
    fake = tmp_path / "pin.json"
    fake.write_text(json.dumps(pinned), encoding="utf-8")
    monkeypatch.setattr(corpus_pin, "PIN_PATH", fake)
    ok, drift = corpus_pin.verify()
    assert not ok
    assert any(first in d for d in drift)


# --------------------------------------------------------------------------
# Secrets fail closed
# --------------------------------------------------------------------------

def test_resolve_secrets_fails_closed_when_missing():
    proc = subprocess.run(
        [sys.executable, "resolve_secrets.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "JWT_SECRET": ""},
    )
    assert proc.returncode == 1
    assert "JWT_SECRET" in proc.stdout
    assert "FAIL CLOSED" in proc.stdout


def test_resolve_secrets_passes_when_present():
    proc = subprocess.run(
        [sys.executable, "resolve_secrets.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
        env={**os.environ, "JWT_SECRET": "unit-test-key"},
    )
    assert proc.returncode == 0


def test_resolve_never_echoes_the_value():
    from resolve_secrets import resolve
    os.environ["JWT_SECRET"] = "super-secret-value-xyz"
    try:
        with pytest.raises(RuntimeError) as excinfo:
            os.environ.pop("JWT_SECRET")
            resolve("JWT_SECRET")
        assert "super-secret-value-xyz" not in str(excinfo.value)
    finally:
        os.environ["JWT_SECRET"] = "unit-test-key"


# --------------------------------------------------------------------------
# At-rest encryption
# --------------------------------------------------------------------------

def test_encrypt_at_rest_hides_plaintext():
    from encrypt_at_rest import encrypt_record
    blob = encrypt_record({"patient_id": "P-1042", "note": "chest pain"})
    flat = json.dumps(blob)
    assert "chest pain" not in flat
    assert "P-1042" not in flat
    assert blob["master_key_ref"] == os.getenv("AWS_KMS_KEY_ID", "alias/afyaplus-at-rest")


# --------------------------------------------------------------------------
# Injection guard CLI self-check
# --------------------------------------------------------------------------

def test_injection_guard_cli_selfcheck():
    proc = subprocess.run(
        [sys.executable, "injection_guard.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0


# --------------------------------------------------------------------------
# Manager brief
# --------------------------------------------------------------------------

def test_check_brief_passes():
    proc = subprocess.run(
        [sys.executable, "check_brief.py"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
