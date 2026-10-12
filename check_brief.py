"""Machine-check the manager brief (Week 9, Deliverable 5).

The self-assessment's "insufficient" row is a brief that overclaims.
This script turns the four requirements into exit codes:

  1. the four headings exist (Risks, Mitigations, Kenya DPA alignment,
     What we will not claim),
  2. every mitigation cites a real file from this repo,
  3. the word "unhackable" (and other banned overclaims) does not appear,
  4. the finance line recommends rather than decides.

    python check_brief.py        # exit 1 on any finding
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
BRIEF = ROOT / "manager_brief.md"

REQUIRED_HEADINGS = [
    "## Risks",
    "## Mitigations",
    "## Kenya DPA alignment",
    "## What we will not claim",
]

# Banned anywhere in the brief, case-insensitive. The README's own
# instruction is that the word 'unhackable' does not appear in the
# brief at all - not even quoted as something we refuse to say. Refuse
# it structurally: describe the refusal without printing the term.
BANNED_CLAIMS = [
    "unhackable",
    "un-hackable",
    "100% secure",
    "100 percent secure",
    "fully secure",
    "cannot be hacked",
    "can't be hacked",
    "immune to attack",
    "tamper-proof",
    "tamper proof",
]

# Files the brief is allowed/expected to cite (mitigation evidence).
EVIDENCE_FILES = [
    "transit_policy.py",
    "resolve_secrets.py",
    "check_gitignore.py",
    "secret_refs.yaml",
    "injection_guard.py",
    "rbac.py",
    "test_rbac.py",
    "redact_then_hash.py",
    "retention_sweep.py",
    "deletion_records.jsonl",
    "data_inventory.json",
    "retention.json",
    "rights_lookup.py",
    "mcp_server/clinics_allowlist.json",
]

# A citation counts only if the cited path actually exists in the repo.
CITED_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|json|jsonl|yaml|yml|md|txt))`")

FINANCE_LINE_OK = [
    "recommend, not decide",
    "recommend rather than decide",
]


def main() -> int:
    if not BRIEF.exists():
        print("FATAL manager_brief.md not found")
        return 1
    text = BRIEF.read_text(encoding="utf-8")
    findings: list[str] = []

    print("== check 1: four required headings ==")
    for h in REQUIRED_HEADINGS:
        present = h in text
        print(f"{'OK  ' if present else 'FAIL'} {h}")
        if not present:
            findings.append(f"missing heading: {h}")

    print("\n== check 2: cited files exist and cover the deliverables ==")
    cited = set(CITED_PATH.findall(text))
    for f in sorted(cited):
        exists = (ROOT / f).exists()
        print(f"{'OK  ' if exists else 'FAIL'} cited: {f}")
        if not exists:
            findings.append(f"brief cites missing file: {f}")
    missing_evidence = [f for f in EVIDENCE_FILES if f not in cited]
    for f in missing_evidence:
        findings.append(f"deliverable evidence not cited in brief: {f}")
    print(f"evidence files cited: {len(EVIDENCE_FILES) - len(missing_evidence)}/{len(EVIDENCE_FILES)}")

    print("\n== check 3: no banned overclaims ==")
    lowered = text.lower()
    for claim in BANNED_CLAIMS:
        hit = claim in lowered
        print(f"{'OK  ' if not hit else 'FAIL'} banned term absent: {claim!r}")
        if hit:
            findings.append(f"banned overclaim present: {claim!r}")

    print("\n== check 4: finance line recommends, does not decide ==")
    para = next((p for p in text.split("\n\n") if "credit" in p.lower()), "")
    ok = para and any(phrase in para.lower() for phrase in FINANCE_LINE_OK)
    print(f"{'OK  ' if ok else 'FAIL'} finance paragraph recommends rather than decides")
    if not ok:
        findings.append("finance paragraph missing or does not say 'recommend, not decide'")

    if findings:
        print(f"\n{len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("\nBrief passes: four headings, real citations, no overclaim, finance humility present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
