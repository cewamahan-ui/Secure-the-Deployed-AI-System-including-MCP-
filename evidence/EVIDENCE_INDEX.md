# Evidence Index (Week 9)

Every capture shows the command, its output, and its exit code. Failing
runs are captured on purpose — a control you cannot see fail is a
control you cannot trust.

| File | Command | Expected result |
|------|---------|-----------------|
| `transit_policy_denied.txt` | `python transit_policy.py` | **exit 1** — localhost http ALLOW (lab exception), https ALLOW, cleartext partner host **DENY** |
| `resolve_secrets_fail.txt` | `JWT_SECRET= python resolve_secrets.py` | **exit 1** — "FAIL CLOSED", key named, no value echoed |
| `resolve_secrets_pass.txt` | `JWT_SECRET=lab-key python resolve_secrets.py` | exit 0 — boot may proceed |
| `check_gitignore.txt` | `python check_gitignore.py` | exit 0 — every secret-shaped path ignored; no secret-shaped tracked file |
| `check_brief.txt` | `python check_brief.py` | exit 0 — four headings, all cited files exist, banned overclaim terms absent, finance line recommends not decides |
| `encrypt_at_rest.txt` | `python encrypt_at_rest.py` | exit 0 — ciphertext blob contains no plaintext identifiers |
| `redact_sample.txt` | `python redact_then_hash.py` | exit 0 — sample audit line carries no raw token, phone or patient id |
| `injection_guard_selftest.txt` | `python injection_guard.py` | exit 0 — clean input passes, override input blocked |
| `retention_sweep.txt` | `python retention_sweep.py` | exit 0 — aged records deleted, legal hold kept, deletion record appended (the log itself never swept) |
| `rights_lookup.txt` | `python rights_lookup.py --subject P-1042` | exit 0 — what is held + the named human owner |
| `corpus_pin.txt` | `python corpus_pin.py` | exit 0 — 7 corpus files match `knowledge/pin.json` |
| `rbac_matrix.txt` | `python rbac.py` | exit 0 — printed role matrix + fail-closed self-check |
| `mcp_response_sample.txt` | inline Python calling the MCP tool functions | fixed samples: allowlisted happy path, off-allowlist denial without enumeration, county-as-clinic_id attack yields error not a dump |
| `pytest_full.log` | `python -m pytest tests test_rbac.py -q` | exit 0 — the whole suite |

Regenerate any capture with the command printed on its first line.
