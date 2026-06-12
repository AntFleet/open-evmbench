import base64
import copy
import hashlib

import pytest

from conftest import load_fixture
from openevmbench.jcs import canonicalize
from openevmbench.signing import (
    SignatureError,
    acceptance_payload_bytes,
    generate_keypair,
    sign_record,
    verify_record,
)


@pytest.fixture
def keypair():
    return generate_keypair()


def test_sign_and_verify_roundtrip(keypair):
    private_pem, public_pem = keypair
    record = load_fixture("submitted_valid")
    record["state"] = "accepted"
    record["score"]["official_score"] = 0.6667

    signed = sign_record(record, private_pem, public_pem)
    verify_record(signed, public_pem)  # must not raise

    acc = signed["antfleet_acceptance"]
    assert acc["signature"].startswith("ed25519:")
    assert acc["acceptance_record_hash"].startswith("sha256:")
    assert acc["public_key_fingerprint"] == "sha256:" + hashlib.sha256(public_pem).hexdigest()


def test_signed_payload_omits_acceptance_object(keypair):
    private_pem, public_pem = keypair
    record = load_fixture("submitted_valid")
    signed = sign_record(record, private_pem, public_pem, signed_at="2026-06-09T01:00:00Z")
    # signed_at / fingerprint live inside antfleet_acceptance, which is omitted:
    assert acceptance_payload_bytes(signed) == acceptance_payload_bytes(record)
    # Ed25519 is deterministic: re-signing a signed record yields the same signature.
    resigned = sign_record(signed, private_pem, public_pem, signed_at="2099-01-01T00:00:00Z")
    assert resigned["antfleet_acceptance"]["signature"] == signed["antfleet_acceptance"]["signature"]


def test_tampered_record_fails_hash_check(keypair):
    private_pem, public_pem = keypair
    signed = sign_record(load_fixture("submitted_valid"), private_pem, public_pem)
    tampered = copy.deepcopy(signed)
    tampered["score"]["solved_count"] = 117
    with pytest.raises(SignatureError, match="acceptance_record_hash mismatch"):
        verify_record(tampered, public_pem)


def test_tampered_signature_fails(keypair):
    private_pem, public_pem = keypair
    signed = sign_record(load_fixture("submitted_valid"), private_pem, public_pem)
    sig = signed["antfleet_acceptance"]["signature"]
    raw = bytearray(base64.b64decode(sig[len("ed25519:"):]))
    raw[0] ^= 0xFF
    signed["antfleet_acceptance"]["signature"] = "ed25519:" + base64.b64encode(bytes(raw)).decode()
    with pytest.raises(SignatureError, match="verification failed"):
        verify_record(signed, public_pem)


def test_wrong_public_key_fails(keypair):
    private_pem, public_pem = keypair
    _, other_public = generate_keypair()
    signed = sign_record(load_fixture("submitted_valid"), private_pem, public_pem)
    with pytest.raises(SignatureError, match="verification failed"):
        verify_record(signed, other_public)


def test_third_party_verification_recipe(test_public_pem):
    """SPEC §4 recipe, step by step, against the committed accepted fixture."""
    record = load_fixture("accepted_valid")
    acceptance = record.pop("antfleet_acceptance")
    canonical = canonicalize(record)
    assert "sha256:" + hashlib.sha256(canonical).hexdigest() == acceptance["acceptance_record_hash"]

    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    public_key = load_pem_public_key(test_public_pem)
    signature = base64.b64decode(acceptance["signature"][len("ed25519:"):])
    public_key.verify(signature, canonical)  # must not raise


def test_fixture_signatures_verify(test_public_pem):
    # promoted and yanked records verify via acceptance-time normalization:
    # promotion/yank fields are post-signing mutations and are stripped/reset.
    for name in ("accepted_valid", "promoted_valid", "yanked_valid"):
        verify_record(load_fixture(name), test_public_pem)


def test_promotion_normalization_covers_official_score(test_public_pem):
    # The signature must still attest the official score on a promoted record.
    record = load_fixture("promoted_valid")
    record["score"]["official_score"] = 0.99
    with pytest.raises(SignatureError, match="acceptance_record_hash mismatch"):
        verify_record(record, test_public_pem)
