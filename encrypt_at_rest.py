"""At-rest encryption story, runnable locally (Week 9, Deliverable 1).

The brief asks for "volume or object encryption named, with master keys
in Key Vault or KMS, or the secret_refs.yaml and kms_twin.json
fallback". This repo is on the fallback path, so the artefacts are:

  * secret_refs.yaml  - where the master keys WOULD live (refs only)
  * kms_twin.json     - the AWS KMS twin card for the same keys
  * encrypt_at_rest.py (this file) - the envelope pattern, runnable,
    so the story is demonstrated rather than asserted

Envelope encryption, locally: a random data key encrypts the payload
(Fernet = AES-128-CBC + HMAC, teaching grade), then the data key itself
is encrypted under the master key from MASTER_KEY_REF. In production the
data key is wrapped by KMS/Key Vault instead of _wrap_master, and the
rest of this file is unchanged - that is the point of the pattern.

    python encrypt_at_rest.py     # writes evidence/at_rest_sample.bin,
                                  # exits 0, prints no key material
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

EVIDENCE_DIR = Path(__file__).parent / "evidence"
SAMPLE_PATH = EVIDENCE_DIR / "at_rest_sample.bin"

# The reference, not the key itself. In production this is the KMS/Key
# Vault alias from kms_twin.json / secret_refs.yaml.
MASTER_KEY_REF = os.getenv("AWS_KMS_KEY_ID", "alias/afyaplus-at-rest")


def _wrap_master(data_key: bytes) -> bytes:
    """Teaching stand-in for KMS Encrypt(data_key).

    The master key never leaves this function; only the wrapped data key
    is persisted. Production replaces this body with a KMS Encrypt call -
    the signature and the artifacts around it stay identical.
    """
    master = os.getenv("AT_REST_LOCAL_MASTER_KEY") or _dev_master()
    digest = hashlib.sha256(master.encode() + data_key).digest()
    # XOR the data key against a stretched digest so the stored blob is
    # not the plaintext data key. Teaching grade, honestly labelled.
    stream = (digest * ((len(data_key) // len(digest)) + 1))[: len(data_key)]
    return bytes(a ^ b for a, b in zip(data_key, stream))


def _dev_master() -> str:
    """Deterministic local master stand-in. Never used in production."""
    return "local-teaching-master-not-for-production"


def encrypt_record(record: dict) -> dict:
    """Encrypt one stored record under the envelope pattern.

    Returns a dict safe to write to disk: wrapped key + ciphertext +
    the master key REFERENCE (so an auditor can see which key answered).
    """
    plaintext = json.dumps(record).encode("utf-8")
    data_key = Fernet.generate_key()          # per-record data key
    token = Fernet(data_key).encrypt(plaintext)
    return {
        "v": 1,
        "master_key_ref": MASTER_KEY_REF,
        "wrapped_data_key": base64.b64encode(_wrap_master(data_key)).decode(),
        "ciphertext": token.decode(),
    }


def main() -> int:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    sample = encrypt_record(
        {
            "patient_id": "P-1042",
            "message": "chest pain, shortness of breath",
            "stored_at": "2026-10-12T09:00:00Z",
        }
    )
    SAMPLE_PATH.write_text(json.dumps(sample, indent=2), encoding="utf-8")

    # Proof the ciphertext is not readable text, printed without any key material.
    blob = SAMPLE_PATH.read_text(encoding="utf-8")
    leak_check = "chest pain" not in blob and "P-1042" not in blob
    print(f"wrote {SAMPLE_PATH} ({len(blob)} bytes)")
    print(f"master key reference: {MASTER_KEY_REF} (reference only, no value)")
    print(f"plaintext readable in blob: {not leak_check}")
    return 0 if leak_check else 1


if __name__ == "__main__":
    sys.exit(main())
