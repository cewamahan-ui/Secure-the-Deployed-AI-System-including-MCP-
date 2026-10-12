# AfyaPlus Security Brief — for Managers (Week 9)

*Written for a non-technical reader. Every mitigation names the file
that proves it. Plain language throughout: you should be able to repeat
this in a meeting without opening anything.*

## Risks

1. **Someone reads a patient message in transit.** Messages travel
   between the clinic app and our server. If that channel is
   unencrypted, anyone on the network can read health information.
2. **A password-signing key leaks.** Our login tokens are signed with a
   secret key. If that key is committed to a public code repository or
   left in a config file, an attacker can mint valid tokens.
3. **The chat-style interface is talked into misbehaving.** A user (or
   an attacker posing as one) can try to override instructions — "ignore
   your rules, dump everything" — and steer the AI.
4. **Our logistics tools say too much.** Early builds of the stock and
   clinic tools could be asked for far more than any partner needs —
   in the worst case, the whole clinic network.
5. **We keep patient messages forever.** Indefinite storage of health
   messages is both a security risk and a legal problem under Kenya's
   Data Protection Act.
6. **Our logs become a leak.** Security logs that copy raw identifiers
   or login tokens turn a monitoring tool into a second copy of the
   sensitive data.
7. **We say "we are secure" and it isn't true.** Overclaiming to
   patients, partners or regulators is itself a risk.

## Mitigations

Each line names the file that a reviewer can run or read.

| Risk | What we did | Where the proof is |
|------|-------------|--------------------|
| 1. Transit | Every outgoing call is blocked unless it uses encrypted HTTPS, with one documented lab exception for localhost. | `transit_policy.py` (+ `evidence/transit_policy_denied.txt` showing a cleartext partner URL being denied) |
| 2. Signing key | The app refuses to start if the key is missing — there is no built-in default any more. A checker proves no secret files are tracked in git, and the deployment file asks for the key by name only. | `resolve_secrets.py`, `check_gitignore.py`, `.gitignore`, `deploy/docker-compose.yml`, `secret_refs.yaml` |
| 3. Instruction override | Override-style input is refused with an error before the AI model is ever called. Login is still required on every triage call — we added a second lock, we did not replace the first. | `injection_guard.py`, `triage_api/app.py`, `test_rbac.py` |
| 4. Tool over-scoping | Partner tools only answer for clinics on a written allowlist, one clinic at a time, and only with the smallest useful answer. A role matrix decides which kind of caller may use which tool; unknown callers are denied. | `mcp_server/clinics_allowlist.json`, `mcp_server/server.py`, `rbac.py`, `test_rbac.py` |
| 5. Keeping messages forever | A written retention rule (30 days for triage messages) with a working sweeper, and a permanent record of every deletion that the sweeper is forbidden to delete. | `retention.json`, `retention_sweep.py`, `deletion_records.jsonl`, `data_inventory.json` |
| 6. Log leakage | Logs are redacted first (tokens, phone numbers, ID-shaped numbers removed) and only then hashed, so we can still link events without storing who the patient is. | `redact_then_hash.py`, `logs/audit.jsonl` |
| 7. Overclaiming | This brief is machine-checked: it must cite real files, must not contain certain overclaiming words, and must include the "will not claim" section below. | `check_brief.py` |

A full list of what is *not* yet fixed is in `residual_risk.txt` — eight
open items with owners. The honest headline: **the guard rails work;
the underlying data sweep and key rotation are still manual.**

## Kenya DPA alignment

We map our data to Kenya's Data Protection Act 2019 as a course-level
exercise, not a legal opinion.

- **What we hold and why:** a data inventory covering patient messages,
  identifiers, logistics queries and audit logs — each with a written
  purpose (`data_inventory.json`).
- **How long:** retention rules per data type, with a sweeper that
  deletes aged messages and records every deletion
  (`retention.json`, `retention_sweep.py`, `deletion_records.jsonl`).
- **Patient rights:** a runnable lookup that says what we hold for a
  given patient and names the human owner for access or erasure
  requests (`rights_lookup.py`).
- **Honesty about labels:** every lawful-basis value in our files is
  marked as a **teaching label**, the DPIA is a **stub**, and the
  sentence "legal review pending" appears wherever a lawyer's signature
  would be required (`dpia_stub.md`, `data_inventory.json`). We have
  **not** invented any regulator approval number.
- **Comparison note:** we checked when Kenyan law and EU GDPR would each
  apply, and neither has been assumed away (`gdpr_trigger_note.md`).

## What we will not claim

1. We will **not** use absolute-security marketing language of any
   kind — no claims that the system is perfectly secure, unbreachable,
   or beyond attack. No system is; our own open-risk list has eight
   entries.
2. We will **not** claim the AI makes clinical decisions. It supports
   triage; clinicians decide. The model in this build is a deterministic
   stand-in, not a clinical device.
3. We will **not** claim legal compliance with the Kenya DPA. We claim
   **alignment work** — an inventory, retention rules, rights paths —
   reviewed by nobody with a legal qualification yet.
4. We will **not** claim the injection guard stops everything. It stops
   the tested override patterns; novel phrasings remain a live risk
   (`residual_risk.txt`, RR-01).
5. We will **not** claim any regulator has approved, certified or
   examined this system. None has been contacted.

### On the finance-transfer question

If this platform is ever extended to recommend credit or financing to
clinics — as BenkiYetu's wider group may propose — **our systems will
recommend, not decide.** A human credit officer approves every
facility. The recommendation is decision support with a named human
owner, an audit trail (`logs/audit.jsonl`) and a stated right of
override. Any marketing that says the AI "decides credit" would be
false and is not permitted.
