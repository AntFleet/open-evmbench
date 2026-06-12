"""AntFleet acceptance signing (SPEC §4).

Signed payload contract:
- Start from the record being accepted (the `accepted_record` profile:
  state="accepted", state_reason=null, score.official_score and
  prize_review_* present).
- Omit the ENTIRE `antfleet_acceptance` object.
- JCS-canonicalize the rest.
- `acceptance_record_hash` = SHA256 over those canonical bytes.
- `signature` = Ed25519 over those same canonical bytes.
- `signed_at` and `public_key_fingerprint` are added AFTER signing and are
  not part of the signed payload (they live inside `antfleet_acceptance`,
  which is omitted from the payload entirely).

v1 normative clarification (gap in SPEC §4 as written): promotion and yanking
mutate the record AFTER acceptance signing (`state` becomes "promoted"/"yanked",
`promoted_at`/`promoted_commit_sha` are added, a yank sets `state_reason`).
The signature always covers the ACCEPTANCE-TIME payload, so verification of a
promoted or yanked record first normalizes it back to that form:
remove `promoted_at` and `promoted_commit_sha`, set state="accepted" and
state_reason=null. `acceptance_payload_bytes` implements this for both
signing and verification, making the two paths symmetric.

Signature encoding: `ed25519:<base64>`.
Public key fingerprint: SHA256 over the PEM bytes of the published
`antfleet.public_key.pem`.
"""

from __future__ import annotations

import base64
import copy
import datetime
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from openevmbench.hashing import sha256_prefixed
from openevmbench.jcs import canonicalize

SIGNATURE_PREFIX = "ed25519:"
_PROMOTION_FIELDS = ("promoted_at", "promoted_commit_sha")


class SignatureError(Exception):
    """Raised when acceptance verification fails."""


def acceptance_payload_bytes(record: dict[str, Any]) -> bytes:
    """JCS-canonical bytes of the record normalized to its acceptance-time form."""
    payload = copy.deepcopy(record)
    payload.pop("antfleet_acceptance", None)
    if payload.get("state") in ("promoted", "yanked"):
        payload["state"] = "accepted"
        payload["state_reason"] = None
        for fld in _PROMOTION_FIELDS:
            payload.pop(fld, None)
    return canonicalize(payload)


def generate_keypair() -> tuple[bytes, bytes]:
    """Return (private_pem, public_pem) for a fresh Ed25519 keypair."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def public_key_fingerprint(public_pem: bytes) -> str:
    return sha256_prefixed(public_pem)


def sign_record(
    record: dict[str, Any],
    private_pem: bytes,
    public_pem: bytes,
    signed_at: str | None = None,
) -> dict[str, Any]:
    """Return a copy of `record` with a populated `antfleet_acceptance` object.

    Any existing `antfleet_acceptance` is discarded before signing (it is
    never part of the signed payload).
    """
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise SignatureError("private key is not Ed25519")

    payload = acceptance_payload_bytes(record)
    signature = private_key.sign(payload)

    signed = copy.deepcopy(record)
    signed["antfleet_acceptance"] = {
        "signature": SIGNATURE_PREFIX + base64.b64encode(signature).decode("ascii"),
        "acceptance_record_hash": sha256_prefixed(payload),
        "signed_at": signed_at
        or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "public_key_fingerprint": public_key_fingerprint(public_pem),
    }
    return signed


def verify_record(record: dict[str, Any], public_pem: bytes) -> None:
    """Third-party verification recipe (SPEC §4). Raises SignatureError on failure.

    Works for accepted, promoted, and yanked records: the payload is
    normalized to its acceptance-time form before checking.
    """
    acceptance = record.get("antfleet_acceptance")
    if not isinstance(acceptance, dict):
        raise SignatureError("record has no antfleet_acceptance object")

    payload = acceptance_payload_bytes(record)

    expected_hash = sha256_prefixed(payload)
    if acceptance.get("acceptance_record_hash") != expected_hash:
        raise SignatureError(
            "acceptance_record_hash mismatch: "
            f"recorded {acceptance.get('acceptance_record_hash')!r}, computed {expected_hash!r}"
        )

    sig_value = acceptance.get("signature", "")
    if not sig_value.startswith(SIGNATURE_PREFIX):
        raise SignatureError(f"signature does not start with {SIGNATURE_PREFIX!r}")
    try:
        signature = base64.b64decode(sig_value[len(SIGNATURE_PREFIX):], validate=True)
    except Exception as e:
        raise SignatureError(f"signature is not valid base64: {e}") from e

    public_key = serialization.load_pem_public_key(public_pem)
    if not isinstance(public_key, Ed25519PublicKey):
        raise SignatureError("public key is not Ed25519")
    try:
        public_key.verify(signature, payload)
    except Exception as e:
        raise SignatureError(f"Ed25519 signature verification failed: {e}") from e
