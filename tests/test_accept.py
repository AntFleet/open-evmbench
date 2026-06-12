import pytest

from conftest import load_fixture
from openevmbench.accept import TransitionError, accept, promote, reject, yank
from openevmbench.signing import generate_keypair, verify_record
from openevmbench.validation import validate_lifecycle


@pytest.fixture(scope="module")
def keypair():
    return generate_keypair()


def test_accept_signs_and_validates(keypair):
    private_pem, public_pem = keypair
    accepted = accept(load_fixture("submitted_valid"), private_pem, public_pem)
    assert accepted["state"] == "accepted"
    assert accepted["score"]["official_score"] == round(
        accepted["score"]["solved_count"] / accepted["score"]["max_score"], 4
    )
    verify_record(accepted, public_pem)
    assert validate_lifecycle(accepted).ok, validate_lifecycle(accepted).errors


def test_accept_defaults_to_ledger_score(keypair):
    private_pem, public_pem = keypair
    record = load_fixture("submitted_valid")
    record["score"]["per_vulnerability"][0]["passed"] = True
    record["score"]["per_vulnerability"][0]["score"] = 1
    record["score"]["per_vulnerability"][1]["passed"] = False
    record["score"]["per_vulnerability"][1]["score"] = 0
    record["score"]["per_vulnerability"][2]["passed"] = False
    record["score"]["per_vulnerability"][2]["score"] = 0
    record["score"]["solved_count"] = 1
    record["score"]["max_score"] = 117
    record["score"]["claimed_score"] = 0.999
    accepted = accept(record, private_pem, public_pem)
    assert accepted["score"]["official_score"] == 0.0085


def test_accept_with_corrected_official_score(keypair):
    private_pem, public_pem = keypair
    accepted = accept(load_fixture("submitted_valid"), private_pem, public_pem, official_score=0.5)
    assert accepted["score"]["official_score"] == 0.5
    verify_record(accepted, public_pem)


def test_full_lifecycle_chain(keypair):
    private_pem, public_pem = keypair
    accepted = accept(load_fixture("submitted_valid"), private_pem, public_pem)
    promoted = promote(accepted, promoted_commit_sha="a" * 40)
    assert promoted["state"] == "promoted"
    verify_record(promoted, public_pem)  # survives promotion mutation
    assert validate_lifecycle(promoted).ok

    yanked = yank(promoted, "invalidated after community re-run")
    assert yanked["state"] == "yanked"
    verify_record(yanked, public_pem)  # survives yank mutation
    assert validate_lifecycle(yanked).ok


def test_reject_requires_reason_and_valid_state():
    record = load_fixture("submitted_valid")
    rejected = reject(record, "transcript-hash-mismatch: details")
    assert validate_lifecycle(rejected).ok
    with pytest.raises(TransitionError):
        reject(record, "   ")
    with pytest.raises(TransitionError):
        reject(rejected, "again")  # already rejected


def test_invalid_transitions(keypair):
    private_pem, public_pem = keypair
    record = load_fixture("submitted_valid")
    with pytest.raises(TransitionError):
        promote(record, "a" * 40)  # not accepted yet
    accepted = accept(record, private_pem, public_pem)
    with pytest.raises(TransitionError):
        accept(accepted, private_pem, public_pem)  # already accepted
    with pytest.raises(TransitionError):
        yank(accepted, "reason")  # not promoted yet
