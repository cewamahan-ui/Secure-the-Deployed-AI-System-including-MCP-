# GDPR Trigger Note (Week 9, Deliverable 4)

**Why a Kenyan project reads GDPR at all:** the Kenya DPA 2019 is
structurally close to GDPR — definitions, data subject rights, breach
notification, and the extra-territorial reach article. AfyaPlus has no
EU presence and no EU data subjects today, so GDPR is **not** the
applicable law; this note exists so nobody has to guess which regime
applies later.

## What would trigger GDPR here

1. **Establishment in the EU/EEA** — a BenkiYetu entity incorporated or
   with an EU branch processing this data.
2. **Targeting behaviour** — offering triage to people in the EU
   (EU-language marketing, EU payment rails).
3. **Monitoring behaviour of EU data subjects** — an app analytics
   layer tracking EU users' triage requests.

None of these apply to the current deployment (Kenya-only, synthetic
data, no analytics). Triggers recorded so the next reviewer checks the
list rather than the vibes.

## Where GDPR is stricter or broader than Kenya DPA (teaching comparison)

| Topic | Kenya DPA 2019 | GDPR | Note |
|-------|----------------|------|------|
| Sensitive data | Health data treated as sensitive (s.2) | Art. 9 special categories | Both cover our triage messages |
| Breach notification | To Commissioner, 72 hours (s.43) | To supervisory authority, 72 hours (Art. 33) | Same clock, different regulator |
| Extra-territoriality | Section 26 | Art. 3 | Both reach outside their borders in defined cases |
| Data protection officer | Required for certain processing | Art. 37 duties | Our DPO role is unfilled — flagged, not faked |

*Teaching comparison — verify against the current statutes before
relying on it. Legal review pending.*
