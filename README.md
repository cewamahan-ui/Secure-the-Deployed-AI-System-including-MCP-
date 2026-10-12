# Week 9: AI Security and Compliance

## Overview

This capstone locks the deployed AfyaPlus path from Weeks 6–8 — the
FastAPI triage API **and** the logistics MCP server — behind encryption,
access control, structured logging and Kenya Data Protection Act
alignment, then summarises it for a non-technical manager. The Act we
aligned to is the **Kenya Data Protection Act 2019** (with a GDPR
comparison note); the manager brief lives at
[`manager_brief.md`](manager_brief.md). Nothing was retrained and no
exploit tooling was built; the model is still the Week 6/7 deterministic
stub, so the whole capstone runs at **$0 API spend**.

**What was locked (ties to Weeks 6–8):**
- **Week 6 triage API** (`triage_api/`): JWT auth kept, plus the Week 9
  injection guard (400 pre-model) and the redact-then-hash audit trail.
- **Week 6 MCP server** (`mcp_server/server.py`): hardened with a clinic
  allowlist, smallest-useful-dict responses and a new `check_stock`
  tool scoped to one allowlisted clinic at a time.
- **Week 8 versioned MCP**: the version banner/manifest concern belongs
  to Week 8; Week 9 reuses that server's tool surface and adds the
  security layer on top.

## Encryption

- **transit_ok / TLS evidence:** [`transit_policy.py`](transit_policy.py)
  — denies cleartext to any non-localhost host. Captured failing run
  (a denied cleartext partner URL): [`evidence/transit_policy_denied.txt`](evidence/transit_policy_denied.txt)
  (`exit=1`).
- **gitignore / resolve_secrets:** [`.gitignore`](.gitignore) covers every
  secret-shaped path; [`check_gitignore.py`](check_gitignore.py) proves it
  via `git check-ignore` + a tracked-file scan
  ([`evidence/check_gitignore.txt`](evidence/check_gitignore.txt)).
  [`resolve_secrets.py`](resolve_secrets.py) fails closed on a missing
  `JWT_SECRET` — failing run:
  [`evidence/resolve_secrets_fail.txt`](evidence/resolve_secrets_fail.txt),
  passing run:
  [`evidence/resolve_secrets_pass.txt`](evidence/resolve_secrets_pass.txt).
  Compose ([`deploy/docker-compose.yml`](deploy/docker-compose.yml))
  references `${JWT_SECRET}` with **no default**, so the deploy layer
  refuses to boot unset.
- **Key Vault / KMS, or the fallback twin JSON:** no cloud console in
  this lab, so the declared fallback path:
  [`secret_refs.yaml`](secret_refs.yaml) (references only, no values) +
  [`kms_twin.json`](kms_twin.json) + a runnable envelope-encryption
  demonstration, [`encrypt_at_rest.py`](encrypt_at_rest.py)
  ([`evidence/encrypt_at_rest.txt`](evidence/encrypt_at_rest.txt)).

## Access control (including MCP)

- **rbac.py roles:** [`rbac.py`](rbac.py) — partner tools
  (`find_clinic_by_county`, `check_stock`) vs operations tools
  (`plan_delivery_route`, `clinics_catalog`, `agent_ask`); unknown
  roles and unknown tools are denied by the fall-through, not by a list.
  Matrix printout: [`evidence/rbac_matrix.txt`](evidence/rbac_matrix.txt).
- **injection_guard:** [`injection_guard.py`](injection_guard.py) —
  override-style input returns **HTTP 400 before any model or tool call**
  (wired into [`triage_api/app.py`](triage_api/app.py)). JWT
  authentication on `/triage` is unchanged from Week 6: security adds
  authorisation, it does not remove authentication.
- **clinic allowlist:** [`mcp_server/clinics_allowlist.json`](mcp_server/clinics_allowlist.json) —
  one list narrows every tool and the `clinics://catalog` resource;
  missing/empty allowlist fails closed to "deny all". `check_stock`
  answers `{clinic_id, item, units}` for one clinic and cannot dump a
  county, a country, or the environment. Fixed response samples (happy
  path, off-allowlist denial, county-as-id attack):
  [`evidence/mcp_response_sample.txt`](evidence/mcp_response_sample.txt).

## Logging

- **path to the jsonl:** [`logs/audit.jsonl`](logs/audit.jsonl)
  (gitignored; created on first audit call). Sample line shown in
  [`evidence/redact_sample.txt`](evidence/redact_sample.txt) and in the
  script's own transcript.
- **redact and hash approach:** [`redact_then_hash.py`](redact_then_hash.py)
  — **redact first** (Bearer tokens, phone numbers, NIN-shaped numbers),
  **then** salted-truncate-hash identifiers (`patient_id`, `actor`) to
  12 hex chars. Ordering matters: a hashed Bearer token is still
  replayable, so raw values never reach disk. Structured fields: actor,
  action, resource, outcome, trace_id.

## Kenya DPA

- **inventory path:** [`data_inventory.json`](data_inventory.json) —
  four datasets: triage messages, patient/staff identifiers, MCP
  logistics queries, audit logs. Every `lawful_basis` is marked as a
  **teaching label**; no regulator approval numbers are invented.
- **retention:** [`retention.json`](retention.json) (30 days for
  triage messages) + [`retention_sweep.py`](retention_sweep.py) stub with
  a legal-hold check. Deletions are recorded in
  [`deletion_records.jsonl`](deletion_records.jsonl), which the sweep is
  **forbidden to delete** (enforced in code, demonstrated in
  [`evidence/retention_sweep.txt`](evidence/retention_sweep.txt)).
- **rights stub / owner:** [`rights_lookup.py`](rights_lookup.py) —
  static-fixture access/erasure lookup naming the human owner
  (engineering lead as acting DPO; platform-security executes erasure).
  GDPR comparison: [`gdpr_trigger_note.md`](gdpr_trigger_note.md);
  DPIA: [`dpia_stub.md`](dpia_stub.md) with "legal review pending".

## Manager brief

[`manager_brief.md`](manager_brief.md) with the four headings —
**Risks, Mitigations, Kenya DPA alignment, What we will not claim**.
Every mitigation cites a file from this week; the finance paragraph
states our systems **recommend, not decide** credit. Machine-checked by
[`check_brief.py`](check_brief.py)
([`evidence/check_brief.txt`](evidence/check_brief.txt), exit 0). The
word the brief must not contain does not appear — the checker greps for
it and its synonyms.

## Fallbacks declared

- [x] **no Azure Key Vault** — `secret_refs.yaml` + `resolve_secrets.py`
  env injection + `kms_twin.json` (this is the path taken)
- [x] **no AWS account** — same twin card; the AWS column is not skipped
- [x] **local MCP stub** — the Week 6 MCP server hardened in place
  (`mcp_server/server.py`), no live network transport needed for tests
- [x] **legal review pending on lawful_basis** — every label marked
  teaching-only in `data_inventory.json`, `dpia_stub.md`,
  `gdpr_trigger_note.md` and `manager_brief.md`

**Cost path taken:** stubbed model calls and authored vault/KMS material
as configuration → **0 API calls, $0**.

## Checklist

- [x] **Secrets not in git** — `.gitignore` + `check_gitignore.py`
  transcript; nothing secret-shaped is tracked; rotation note: the
  Week 6 default `JWT_SECRET` was removed from code entirely
  (`resolve_secrets.py` fails closed without it), which *is* the
  rotation away from the leaked-by-design dev default.
- [x] **MCP cannot dump the environment or every clinic** —
  `check_stock` is one-clinic-one-item; the catalog and lookup tools
  are allowlist-scoped; `tests/test_mcp_server.py::test_no_tool_returns_environment`
  asserts it structurally.
- [x] **The brief is readable by a non-engineer** — `check_brief.py`
  verifies headings, real citations, and no overclaim language.

## Evidence

Transcripts of every control (pass **and** deliberate fail) live in
[`evidence/`](evidence/) with an
[`evidence/EVIDENCE_INDEX.md`](evidence/EVIDENCE_INDEX.md) describing
each capture.

## Tests

```bash
python -m pytest tests test_rbac.py -q   # 91 passed
```

Covers the transit policy, the injection guard (unit + API 400), the
role matrix, the redactor (including the doubled-bearer residue
regression), the retention sweep, the corpus pins and the fail-closed
secret boot.

## Corpus poisoning defence

[`corpus_pin.py`](corpus_pin.py) + [`knowledge/pin.json`](knowledge/pin.json)
— SHA-256 pins over every corpus/fixture file the model or agent path
reads. `python corpus_pin.py` exits 1 on unreviewed drift; re-pin with
`--write` only after a reviewed change (evidence:
[`evidence/corpus_pin.txt`](evidence/corpus_pin.txt)).
