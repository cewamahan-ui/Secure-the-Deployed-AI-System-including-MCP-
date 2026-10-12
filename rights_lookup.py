"""Data subject rights path stub (Week 9, Deliverable 4).

The Kenya DPA gives data subjects rights of access and erasure among
others. This stub is the PROCESS NOTE made runnable: given a subject id
it (1) looks the subject up in a static fixture, (2) reports what is
held and where, and (3) names the human owner who executes the request.
It does not delete anything itself - erasure in the real system is a
ticket to the owner below, and a stub that silently deleted records
would be a worse lie than no stub at all.

Owners (from manager_brief.md and data_inventory.json):
  - access requests:  engineering lead (data protection officer role
                      unfilled - legal review pending)
  - erasure requests: platform-security (executes store deletions)
                      + retention_sweep.py for aged records

    python rights_lookup.py --subject P-1042
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SUBJECT_FIXTURE = ROOT / "fixtures" / "rights_subject.json"

# Who to hand a request to. Named humans are roles, not invented names.
RIGHTS_OWNERS = {
    "access": {
        "owner_role": "engineering lead (acting data protection officer)",
        "sla_teaching_label": "TEACHING LABEL - 7 days is the GDPR-style working period; Kenya DPA timelines differ, legal review pending",
        "steps": [
            "verify the requester's identity against the EMR record",
            "export triage_messages for the subject from the upstream store",
            "export the hashed audit trail rows (actor/subject hashes only)",
            "hand the pack to the requester, recording the disclosure",
        ],
    },
    "erasure": {
        "owner_role": "platform-security",
        "sla_teaching_label": "TEACHING LABEL - 30 days teaching figure; legal review pending",
        "steps": [
            "check for a legal hold (retention_sweep.py honours legal_hold)",
            "delete triage_messages rows for the subject in the upstream store",
            "append a row to deletion_records.jsonl - the record survives the sweep",
            "confirm to the requester; keep the confirmation, not the data",
        ],
        "note": "Erasure does NOT delete the deletion record or the hashed "
                "audit rows - those are the evidence that erasure happened.",
    },
}


def lookup(subject_id: str, fixture: Path | None = None) -> dict:
    """Static-fixture lookup. Returns a report dict; raises nothing."""
    path = fixture or SUBJECT_FIXTURE
    if not path.exists():
        return {"error": f"rights fixture missing at {path.name}", "held": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    record = data.get("subjects", {}).get(subject_id)
    if record is None:
        return {"subject_id": subject_id, "found": False, "held": []}
    return {
        "subject_id": subject_id,
        "found": True,
        "held": record["held"],
        "stores": record["stores"],
        "lawful_basis_note": "TEACHING LABEL - see data_inventory.json; legal review pending",
    }


def main() -> int:
    subject = sys.argv[sys.argv.index("--subject") + 1] if "--subject" in sys.argv else "P-1042"
    report = lookup(subject)
    print(json.dumps(report, indent=2))
    print("\nNext step: open a ticket with the owner in RIGHTS_OWNERS "
          f"(access -> {RIGHTS_OWNERS['access']['owner_role']}; "
          f"erasure -> {RIGHTS_OWNERS['erasure']['owner_role']}).")
    return 0 if report.get("found") else 1


if __name__ == "__main__":
    sys.exit(main())
