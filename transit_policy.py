"""Transit encryption policy for AfyaPlus (Week 9, Deliverable 1).

transit_ok(url) is the single gate every outbound call in this repo is
meant to pass before it sends anything. The rule is deliberately small
so a marker can read it in one sitting:

  1. localhost / 127.0.0.1 over http is ALLOWED, and it is a lab
     exception, not a policy hole: the Week 9 lab runs on a laptop with
     no public DNS and no production data.
  2. Everything else - any hostname at all, including intranet
     hostnames - must be https. No exceptions, no "we'll add TLS later".

Run directly for a transcript a marker can read:

    python transit_policy.py
    # exit 1 if any checked URL fails, exit 0 when all pass

Week 9 self-assessment wants "one captured failing run such as a denied
cleartext host" - this script is that artefact, and
evidence/transit_policy_denied.txt is the capture.
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}


def transit_ok(url: str) -> tuple[bool, str]:
    """Return (allowed, reason) for sending a request to `url`.

    Pure function - no I/O, so tests can call it directly.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if not scheme or not host:
        return False, f"unparseable URL: {url!r} - refusing to send"

    if scheme == "https":
        return True, "https - TLS in transit"

    if scheme == "http" and host in LOCALHOST_HOSTS:
        # Documented lab exception, not a production allowance.
        return True, "http on localhost - documented lab exception (no production data)"

    return False, (
        f"cleartext {scheme} to host '{host}' refused - "
        "partner and production URLs must be https (encryption in transit)"
    )


def main() -> int:
    # The URLs the deployed AfyaPlus path talks to. The production-shaped
    # ones must pass via https; the deliberately-cleartext partner URL is
    # here so the failing run is captured, not hidden.
    urls = [
        "http://localhost:8000/health",        # lab exception, must PASS
        "https://api.benkiyetu.co.ke/triage",  # partner over TLS, must PASS
        "http://partner.benkiyetu.co.ke/triage",  # cleartext partner, must FAIL
    ]
    failures = 0
    for url in urls:
        allowed, reason = transit_ok(url)
        verdict = "ALLOW" if allowed else "DENY "
        print(f"{verdict} {url} -> {reason}")
        if not allowed:
            failures += 1

    if failures:
        print(f"\n{failures} URL(s) denied by transit policy (expected: the cleartext partner URL).")
        return 1
    print("\nAll checked URLs satisfy the transit policy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
