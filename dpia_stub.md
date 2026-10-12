# DPIA Stub — AfyaPlus Triage + Logistics MCP (Week 9)

**Status: teaching stub. Legal review pending — no regulator has seen or
approved this document, and the brief says so out loud.**

The Kenya Data Protection Act expects a Data Protection Impact
Assessment before high-risk processing. This stub marks the sections a
real DPIA needs, fills in what the course can honestly fill, and leaves
the rest labelled rather than invented. Carried into
`manager_brief.md` under "Kenya DPA alignment".

## 1. Processing described

Automated triage of symptom messages (POST /triage) plus logistics
lookups over MCP (clinics, routes, stock). Inventory:
`data_inventory.json` (DS-1..DS-4).

## 2. Necessity and proportionality

- Data minimisation: the API collects only the fields the triage stub
  reads; logs store hashed identifiers only (`redact_then_hash.py`).
- The model is a deterministic stub — no training on patient data, so
  no corpus-poisoning surface and no model-data retention question
  beyond the messages themselves.
- Logistics tools carry no personal data; clinic phone numbers were
  removed from partner-visible responses in Week 9.

## 3. Risks (teaching assessment)

| # | Risk | Sev | Mitigation (file) | Residual |
|---|------|-----|-------------------|----------|
| R1 | Cleartext transit of health data | High | `transit_policy.py` refuses non-HTTPS partner hosts | Low on the graded path; requires TLS termination in any real deploy |
| R2 | Secret leakage (JWT signing key) | High | `resolve_secrets.py` fail-closed boot; `.gitignore` + `check_gitignore.py`; compose `${JWT_SECRET}` | Low; rotation still manual |
| R3 | Prompt injection steering triage | High | `injection_guard.py` returns 400 pre-model; JWT unchanged | **Medium — pattern lists are not complete; see residual_risk.txt** |
| R4 | MCP over-scoping (dumping clinics/stock) | Medium | `mcp_server/clinics_allowlist.json`, smallest-useful-dict responses, `rbac.py` | Low |
| R5 | Indefinite retention of health messages | Medium | `retention.json` 30d rule, `retention_sweep.py`, deletion records | Low; sweeper is a stub until cron-ed |
| R6 | Log-borne re-identification | Medium | Redact-then-hash order in `redact_then_hash.py` | Low; 12-hex truncation is a deliberate trade-off, documented |

## 4. Consultation

**Not performed.** No data protection officer has been consulted — the
role is unfilled in this scenario. `manager_brief.md` names the owner
and states "legal review pending". Fabricating a consultation record
would be the exact overclaim Deliverable 5 fails.

## 5. Outcome

Processing may continue as a **course project** on synthetic data with
the mitigations above. Before any real patient data: fill the DPO role,
run a real DPIA consultation, replace the sweeper stub with a scheduled
job, and re-review R3 (injection guard completeness).
