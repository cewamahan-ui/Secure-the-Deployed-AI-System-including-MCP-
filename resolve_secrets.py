"""Secret resolution that fails closed (Week 9, Deliverable 1).

Contract:

  * resolve("JWT_SECRET") reads the environment - the same place the
    Key Vault / KMS sidecars would inject from in production.
  * Boot refuses to proceed when a required secret is missing. There is
    no "dev-only" fallback string in this file any more: Week 6 shipped
    a default JWT_SECRET, and Week 9 exists because that was wrong.
  * Nothing here ever prints a secret value. Only the key NAME appears
    in any message this module raises or logs.

Run directly to prove the boot gate:

    python resolve_secrets.py                 # exits 0 if all present
    JWT_SECRET= python resolve_secrets.py     # exits 1, name only, no value

The captured failing run lives in evidence/resolve_secrets_fail.txt.
"""

from __future__ import annotations

import os
import sys

# Names the services in deploy/docker-compose.yml require at boot.
# JWT_SECRET: HS256 signing key for the /token -> /triage flow (Week 6 auth).
REQUIRED_SECRETS = ("JWT_SECRET",)

# Anything the operator must inject but that is not needed to boot -
# resolved the same way, tracked here so the README stays honest.
OPTIONAL_SECRETS = ("AZURE_KEY_VAULT_URI", "AWS_KMS_KEY_ID")


def resolve(name: str, *, required: bool = True) -> str | None:
    """Read `name` from the environment.

    Returns the value when set and non-empty. When `required` and the
    value is missing or empty, raises RuntimeError naming the KEY, never
    the value. There is deliberately no default fallback.
    """
    value = os.getenv(name)
    if value is None or value == "":
        if required:
            raise RuntimeError(
                f"missing required secret '{name}' - inject it via the "
                "environment (Key Vault / KMS sidecar in production). "
                "Boot refuses to continue without it."
            )
        return None
    return value


def resolve_all(names: tuple[str, ...] = REQUIRED_SECRETS) -> dict[str, str]:
    """Resolve every required secret, or raise on the first missing one."""
    return {name: resolve(name, required=True) for name in names}


def main() -> int:
    missing: list[str] = []
    for name in REQUIRED_SECRETS:
        try:
            resolve(name, required=True)
            print(f"OK      {name} present (value not shown)")
        except RuntimeError as exc:
            missing.append(name)
            print(f"MISSING {name} - {exc}")
    for name in OPTIONAL_SECRETS:
        state = "present" if resolve(name, required=False) else "absent (fallback path)"
        print(f"info    {name} {state}")

    if missing:
        print(f"\nFAIL CLOSED: {len(missing)} required secret(s) missing: {', '.join(missing)}")
        return 1
    print("\nAll required secrets present. Boot may proceed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
