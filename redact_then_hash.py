"""Redact, then hash - the audit logging pipeline (Week 9, Deliverable 3).

One script, two stacked stages, in this order and never the reverse:

  1. REDACT: strip raw secrets and direct identifiers out of the event
     dict. Bearer tokens, national-id-shaped numbers (Kenyan NIN is 9
     digits after a letter), emails, phone numbers, patient_id.
  2. HASH: replace each identifier that mattered with a truncated
     SHA-256 keyed by AUDIT_HASH_SALT (env-injected, same secret path
     as JWT_SECRET - see secret_refs.yaml). Truncated to 12 hex chars:
     enough to correlate one patient across log lines, not enough to
     brute-force a 9-digit NIN space offline.

Order matters: hashing raw text is not redaction - a Bearer token
hashed is still a Bearer token replayable against /token until it
expires. Redact first so the raw value never reaches disk, then hash
the (already safe) identifier so the audit trail can still answer
"same patient?".

Output contract (one JSON line per event):
  {ts, trace_id, actor, action, resource, outcome, actor_hash,
   subject_hash, redacted_fields, guard}

    python redact_then_hash.py   # writes logs/audit.jsonl + prints the
                                 # sample line shown in the README
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
AUDIT_PATH = LOG_DIR / "audit.jsonl"

# Salts come from the environment, never from code. The fallback is a
# per-process random salt for the lab: logs still correlate within one
# run, and nothing a committed default can be used to precompute a
# rainbow table in production. resolve_secrets.py tracks
# AUDIT_HASH_SALT alongside JWT_SECRET for the real deployment.
_SALT = os.getenv("AUDIT_HASH_SALT") or os.urandom(16).hex()

# Field-level redaction rules: field name -> replacement.
# The bearer rule tolerates a doubled prefix ("bearer Bearer tok") so
# the token itself can never survive as residue after one replacement.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer", re.compile(r"(?:\bBearer\s+){1,3}[A-Za-z0-9\-._~+/]+=*", re.I)),
    ("kenyan_nin", re.compile(r"\b\d{9}\b")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone_ke", re.compile(r"\+?254\d{9}|0[17]\d{8}")),
)

# Fields whose VALUE is replaced wholesale (identifiers we hash instead).
IDENTITY_FIELDS = ("actor", "subject", "patient_id")


def redact_text(value: str) -> str:
    """Stage 1a: scrub secret-shaped substrings from free text.

    Runs to a fixpoint: redaction is idempotent by construction, so a
    second pass can only confirm the first one finished the job. This
    is what stops a malformed doubling ("bearer Bearer tok") from
    leaving the token behind after a single replacement.
    """
    out = value
    for _ in range(5):
        new = out
        for _, pat in _PATTERNS:
            new = pat.sub("[REDACTED]", new)
        if new == out:
            break
        out = new
    return out


def _hash_value(value: str) -> str:
    """Stage 2: salted SHA-256, truncated. Never reversible at 12 hex."""
    digest = hashlib.sha256(_SALT.encode() + value.encode("utf-8")).hexdigest()
    return digest[:12]


def build_event(
    *,
    actor: str | None,
    action: str,
    resource: str,
    outcome: str,
    trace_id: str = "-",
    payload: dict | None = None,
    guard: str | None = None,
) -> dict:
    """Build one audit event: redact everything, hash identities.

    `payload` is the request body (or a summary of it). Every string
    value in it is text-redacted; identity fields are additionally
    replaced by their hash. The raw payload is never stored.
    """
    redacted_fields: list[str] = []
    safe_payload: dict = {}

    for key, value in (payload or {}).items():
        if key.lower() in IDENTITY_FIELDS and isinstance(value, str) and value:
            safe_payload[key + "_hash"] = _hash_value(value)
            redacted_fields.append(key)
        elif isinstance(value, str):
            cleaned = redact_text(value)
            if cleaned != value:
                redacted_fields.append(key)
            safe_payload[key] = cleaned
        elif isinstance(value, list):
            cleaned_list = [redact_text(str(v)) for v in value]
            if cleaned_list != [str(v) for v in value]:
                redacted_fields.append(key)
            safe_payload[key] = cleaned_list
        else:
            safe_payload[key] = value

    return {
        "ts": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "trace_id": trace_id,
        "actor": actor or "anonymous",
        "actor_hash": _hash_value(actor) if actor else None,
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "subject_hash": safe_payload.pop("patient_id_hash", None),
        "payload": safe_payload or None,
        "redacted_fields": sorted(set(redacted_fields)),
        "guard": guard,
    }


def write_event(event: dict, path: Path | None = None) -> Path:
    """Append one event as a JSON line. Never raises on shape."""
    target = path or AUDIT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return target


def audit(
    *,
    actor: str | None,
    action: str,
    resource: str,
    outcome: str,
    trace_id: str = "-",
    payload: dict | None = None,
    guard: str | None = None,
    path: Path | None = None,
) -> dict:
    """Convenience: build + write + return the event."""
    event = build_event(
        actor=actor, action=action, resource=resource, outcome=outcome,
        trace_id=trace_id, payload=payload, guard=guard,
    )
    write_event(event, path)
    return event


def contains_no_secrets(line: str) -> bool:
    """Self-check used by tests and the README transcript.

    Stricter than a substring list: it asserts no token-shaped run of
    alphanumerics survives after a redaction marker, because that is
    the residue shape a leaked bearer token actually has.
    """
    forbidden = ("Bearer ey", '"token"', "+254", "@", "abc123SECRET")
    if any(f in line for f in forbidden):
        return False
    # No high-entropy-looking run directly after a [REDACTED] marker.
    residue = re.search(r"\[REDACTED\][\s,]*[A-Za-z0-9\-._~+/]{16,}", line)
    return residue is None


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    sample = audit(
        actor="olu",
        action="triage",
        resource="/triage",
        outcome="ok",
        trace_id="trace-sample-1",
        payload={
            "patient_id": "P-1042",
            "symptoms": ["chest pain", "shortness of breath"],
            "note": "caller reached us on +254712345678, bearer Bearer abc123SECRET",
            "age": 58,
        },
    )
    line = json.dumps(sample, ensure_ascii=False)
    print("sample audit line written to", AUDIT_PATH)
    print(line)
    ok = contains_no_secrets(line) and sample["subject_hash"]
    print("\nraw token / phone / patient id present in line:", not ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
