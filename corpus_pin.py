"""Corpus pinning (Week 9 - model/corpus poisoning control).

The Week 4.7 lesson: if your retrieval corpus or fixture data can be
edited without anyone noticing, an attacker can poison what the model
sees. The fix is a pin: hash every corpus file at review time, store
the hashes, and verify them before serving. A changed file fails the
check loudly instead of quietly steering answers.

Pins live in knowledge/pin.json with a human `last_reviewed` date.
Re-pin deliberately (python corpus_pin.py --write) after a reviewed
change; never re-pin to make a red check go green.

    python corpus_pin.py            # verify; exit 1 on drift
    python corpus_pin.py --write    # re-pin after a reviewed change
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
PIN_PATH = ROOT / "knowledge" / "pin.json"

# The corpus files the model/agent path may read. Extend deliberately.
CORPUS_FILES = [
    "mcp_server/data/clinics.json",
    "mcp_server/data/stock.json",
    "mcp_server/clinics_allowlist.json",
    "fixtures/triage_store.json",
    "fixtures/rights_subject.json",
    "data_inventory.json",
    "retention.json",
]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> tuple[bool, list[str]]:
    """Compare disk against the pin. Returns (ok, drift_lines)."""
    if not PIN_PATH.exists():
        return False, [f"pin file missing: {PIN_PATH.relative_to(ROOT)}"]
    pins = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    drift: list[str] = []
    for rel in CORPUS_FILES:
        actual = sha256_of(ROOT / rel)
        expected = pins.get("files", {}).get(rel, {}).get("sha256")
        if expected is None:
            drift.append(f"unpinned corpus file: {rel}")
        elif actual != expected:
            drift.append(
                f"DRIFT {rel}: pinned {expected[:16]}..., disk {actual[:16]}..."
            )
    for rel in pins.get("files", {}):
        if rel not in CORPUS_FILES:
            drift.append(f"stale pin entry (file no longer in corpus scope): {rel}")
    return not drift, drift


def write_pin() -> Path:
    payload = {
        "_comment": (
            "Corpus pin (model/corpus poisoning control). Verify with "
            "corpus_pin.py; re-pin only after a reviewed change."
        ),
        "algorithm": "sha256",
        "last_reviewed": date.today().isoformat(),
        "reviewed_by": "ml-eng (course project)",
        "files": {
            rel: {"sha256": sha256_of(ROOT / rel)} for rel in CORPUS_FILES
        },
    }
    PIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIN_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return PIN_PATH


def main() -> int:
    if "--write" in sys.argv:
        path = write_pin()
        print(f"pinned {len(CORPUS_FILES)} corpus files -> {path.relative_to(ROOT)}")
        return 0
    ok, drift = verify()
    for line in drift:
        print(line)
    if ok:
        print(f"pin OK: {len(CORPUS_FILES)} corpus files match knowledge/pin.json")
        return 0
    print("pin FAILED: corpus changed since last review. Inspect the drift; "
          "re-pin (--write) only if the change was reviewed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
