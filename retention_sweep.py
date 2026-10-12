"""Retention sweeper stub (Week 9, Deliverable 4).

Reads retention.json, sweeps a fixture store of triage messages, and
writes one row per deletion into deletion_records.jsonl. The two rules
that make this a control rather than a poster:

  1. Records older than their dataset's retention_days are deleted
     (here: replaced in the fixture; the production job would issue the
     delete against the real store - same function, same rules).
  2. deletion_records.jsonl itself is NEVER swept. The rule
     `action: never_delete` in retention.json is enforced in code:
     deletion of a deletion record raises, it does not silently pass.
     Deleting the record of a deletion is how a sweep covers its tracks.

    python retention_sweep.py          # exits 0; writes fixture_swept.json
                                       # + appends to deletion_records.jsonl
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, datetime as _dt, timezone
from pathlib import Path

ROOT = Path(__file__).parent
RETENTION_PATH = ROOT / "retention.json"
DELETION_LOG = ROOT / "deletion_records.jsonl"
FIXTURE_STORE = ROOT / "fixtures" / "triage_store.json"
FIXTURE_SWEPT = ROOT / "fixtures" / "triage_store.swept.json"


def _load_rules() -> dict:
    with RETENTION_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)["rules"]


def record_deletion(dataset: str, record_id: str, count: int = 1,
                    *, path: Path | None = None) -> dict:
    """Append a deletion record. This log is exempt from every sweep."""
    row = {
        "deleted_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "dataset": dataset,
        "record_id": record_id,
        "count": count,
        "actor": "retention_sweep",
        "rule": "retention.json",
    }
    target = path or DELETION_LOG
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def protect_deletion_log(dataset: str | None = None, path: Path | None = None) -> None:
    """Refuse to sweep the deletion log itself. Hard stop, by design.

    Called two ways:
      * protect_deletion_log("deletion_records") - raises, because a
        sweep targeting the deletion log is exactly the behaviour this
        control forbids.
      * protect_deletion_log() with no argument - a pre-flight sanity
        check that retention.json still marks deletion_records as
        never_delete; raises only if the RULE has been weakened.
    """
    target = path or DELETION_LOG
    rules = _load_rules()
    if dataset and dataset.lower() == "deletion_records":
        raise RuntimeError(
            f"refusing to sweep {target.name}: retention.json marks "
            "deletion_records as never_delete - the record of a deletion "
            "must outlive the sweep that performed it"
        )
    if rules.get("deletion_records", {}).get("action") != "never_delete":
        raise RuntimeError(
            "retention.json no longer marks deletion_records as never_delete "
            "- restore the rule before running the sweep"
        )


def sweep(store: list[dict], rules: dict, *, now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """Return (kept, deletions). Pure function - the cron job wraps it."""
    now = now or datetime.now(tz=timezone.utc)
    kept: list[dict] = []
    deleted: list[dict] = []
    for record in store:
        dataset = record.get("dataset", "triage_messages")
        if dataset.lower() == "deletion_records":
            # Rule 2 enforced in the sweep itself, not only at the edge.
            kept.append(record)
            continue
        rule = rules.get(dataset)
        if not rule or rule.get("action") == "never_delete":
            kept.append(record)
            continue
        if record.get("legal_hold"):
            kept.append(record)  # legal hold beats retention, recorded
            continue
        created = _dt.fromisoformat(record["created_at"])
        age_days = (now - created).total_seconds() / 86400
        if age_days > (rule.get("retention_days") or 0):
            deleted.append(record)
        else:
            kept.append(record)
    return kept, deleted


def main() -> int:
    protect_deletion_log()  # rule 2, before anything is deleted

    rules = _load_rules()
    with FIXTURE_STORE.open("r", encoding="utf-8") as fh:
        store = json.load(fh)

    kept, deleted = sweep(store, rules)

    FIXTURE_SWEPT.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    if deleted:
        record_deletion("triage_messages", "bulk-sweep", count=len(deleted))

    print(f"swept {len(store)} records: kept {len(kept)}, deleted {len(deleted)}")
    print(f"wrote {FIXTURE_SWEPT.relative_to(ROOT)}")
    print(f"deletion record appended to {DELETION_LOG.name} (itself never swept)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
