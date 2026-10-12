"""Deterministic triage stub.

The brief permits a stub when no LLM key is available: the FastAPI
agreement is unchanged, the response shape is unchanged, only the
`model_card` field reveals which backend answered. To swap in a real
model later, replace `classify` with a function that takes a
TriageRequest and returns a TriageResponse with the same field set.

Rule set below is the AfyaPlus teaching example, not a clinical device.
It exists so the API can be exercised end-to-end without burning budget.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import Acuity, Disposition, TriageRequest, TriageResponse
from . import trace as _trace

MODEL_CARD = "afyaplus-triage-stub-v1"

# Red flags driving ESI-1/2 decisions. Case-insensitive substring match.
_RED_FLAGS_HIGH = (
    "chest pain", "shortness of breath", "unconscious", "unresponsive",
    "severe bleeding", "stroke", "seizure", "anaphylaxis",
)
_RED_FLAGS_MID = (
    "high fever", "persistent vomiting", "severe pain", "dehydration",
    "abdominal pain", "pregnant", "labour", "labor",
)


def _lower(req: TriageRequest) -> list[str]:
    return [s.lower() for s in req.symptoms]


def classify(req: TriageRequest) -> TriageResponse:
    """Return a TriageResponse for the given request.

    Pure function of the request - deterministic, no I/O, no time dependency
    except `served_at` which is when the API received the call.
    """
    syms = _lower(req)
    red_flags = [s for s in syms if any(rf in s for rf in _RED_FLAGS_HIGH)]

    # ESI-1: unconscious / unresponsive / anaphylaxis -> immediate ED.
    if any(any(critical in s for s in syms)
           for critical in ("unconscious", "unresponsive", "anaphylaxis")):
        acuity, disp, rationale = (
            Acuity.ESI_1, Disposition.ED,
            "Critical red flag - immediate resuscitation pathway.",
        )
    # ESI-2: high-acuity red flag, esp. with age > 50 or low SpO2.
    elif red_flags and (req.age >= 50 or (req.spo2 is not None and req.spo2 < 94)):
        acuity, disp, rationale = (
            Acuity.ESI_2, Disposition.ED,
            "High-acuity red flag with risk modifiers (age/SpO2) - ED now.",
        )
    elif red_flags:
        acuity, disp, rationale = (
            Acuity.ESI_3, Disposition.URGENT_CLINIC,
            "Red flag without immediate risk modifiers - urgent clinic within hours.",
        )
    elif any(any(mid in s for s in syms) for mid in _RED_FLAGS_MID):
        acuity, disp, rationale = (
            Acuity.ESI_3, Disposition.URGENT_CLINIC,
            "Moderate symptoms - urgent clinic review.",
        )
    else:
        acuity, disp, rationale = (
            Acuity.ESI_4, Disposition.PRIMARY_CAT,
            "Low-acuity presentation - primary care or self-care.",
        )

    return TriageResponse(
        request_id=req.request_id or "",
        patient_id=req.patient_id,
        acuity=acuity,
        disposition=disp,
        red_flags=red_flags,
        rationale=rationale,
        next_step=_next_step(disp, req),
        model_card=MODEL_CARD,
        served_at=datetime.now(tz=timezone.utc),
        trace_id=_trace.get_trace_id(),
    )


def _next_step(disp, req) -> str:
    """Operational follow-up action. Added in v1.1.0."""
    pid = req.patient_id
    if disp == Disposition.ED:
        return f"Dispatch ambulance for patient {pid} within 15 minutes."
    if disp == Disposition.URGENT_CLINIC:
        return f"Refer patient {pid} to nearest urgent clinic."
    if disp == Disposition.PRIMARY_CAT:
        return f"Schedule primary-care follow-up for patient {pid} within 48 hours."
    if disp == Disposition.SELF_CAT:
        return "Provide self-care advice; advise return if symptoms worsen."
    return ""