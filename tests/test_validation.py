import copy

import pytest

from conftest import load_fixture
from openevmbench.validation import validate_lifecycle, validate_phase1_detect, validate_phase2_patch, validate_submitted

POSITIVE_SUBMITTED = ["submitted_valid"]
POSITIVE_LIFECYCLE = ["checking_valid", "accepted_valid", "rejected_valid", "promoted_valid", "yanked_valid"]

NEGATIVE_SUBMITTED = {
    "neg_detect_missing_judge": "judge",
    "neg_bad_archive_hash": "archive_hash",
    "neg_bad_submission_id_version": "submission_id",
    "neg_solved_count_mismatch": "solved_count",
    "neg_duplicate_vulnerability_id": "duplicate",
    "neg_submitted_with_acceptance": "AntFleet-populated",
    "neg_bad_harness_kind": "harness_kind",
    "neg_bad_vulnerability_id_format": "vulnerability_id",
}
NEGATIVE_LIFECYCLE = {
    "neg_rejected_without_reason": "state_reason",
    "neg_promoted_missing_promotion_fields": "promoted",
}


@pytest.mark.parametrize("name", POSITIVE_SUBMITTED)
def test_positive_submitted(name):
    result = validate_submitted(load_fixture(name))
    assert result.ok, result.errors


@pytest.mark.parametrize("name", POSITIVE_LIFECYCLE)
def test_positive_lifecycle(name):
    result = validate_lifecycle(load_fixture(name))
    assert result.ok, result.errors


@pytest.mark.parametrize("name,needle", NEGATIVE_SUBMITTED.items())
def test_negative_submitted(name, needle):
    result = validate_submitted(load_fixture(name))
    assert not result.ok
    assert any(needle in e for e in result.errors), (needle, result.errors)


@pytest.mark.parametrize("name,needle", NEGATIVE_LIFECYCLE.items())
def test_negative_lifecycle(name, needle):
    result = validate_lifecycle(load_fixture(name))
    assert not result.ok
    assert any(needle in e for e in result.errors), (needle, result.errors)


def test_phase1_detect_requires_full_board():
    # The profile fixtures are 3-vulnerability minis; the Phase 1 board
    # requires the full 117-entry run and the pinned benchmark facts.
    record = load_fixture("submitted_valid")
    result = validate_phase1_detect(record)
    assert any("117" in e for e in result.errors)


def test_phase1_detect_rejects_wrong_prompt_hash():
    record = load_fixture("submitted_valid")
    record["judge"]["prompt_hash"] = "sha256:" + "0" * 64
    result = validate_phase1_detect(record)
    assert any("pinned prompt hash" in e for e in result.errors)


def test_phase1_detect_rejects_wrong_pin():
    record = load_fixture("submitted_valid")
    record["benchmark"]["upstream_commit"] = "deadbeef"
    result = validate_phase1_detect(record)
    assert any("launch pin" in e for e in result.errors)


def test_claimed_score_mismatch_is_error():
    record = load_fixture("submitted_valid")
    record["score"]["claimed_score"] = 0.456  # far from 2/3
    result = validate_submitted(record)
    assert not result.ok
    assert any("claimed_score" in e for e in result.errors)


def test_patch_mode_allows_null_judge():
    record = load_fixture("submitted_valid")
    record["mode"] = "patch"
    record["phase"] = 2
    record["judge"] = None
    result = validate_submitted(record)
    assert result.ok, result.errors


def test_phase2_patch_requires_full_task_set():
    record = load_fixture("submitted_valid")
    record["phase"] = 2
    record["mode"] = "patch"
    record["judge"] = None
    record["benchmark"]["harness_version"] = "patch-v1.0.0+frontier-evals.51052ce"
    record["score"]["max_score"] = 44
    result = validate_phase2_patch(record)
    assert any("44" in e for e in result.errors)


def test_phase2_patch_rejects_judge():
    record = load_fixture("submitted_valid")
    record["phase"] = 2
    record["mode"] = "patch"
    record["benchmark"]["harness_version"] = "patch-v1.0.0+frontier-evals.51052ce"
    result = validate_phase2_patch(record)
    assert any("omit judge" in e for e in result.errors)


def test_passed_true_score_zero_rejected():
    record = load_fixture("submitted_valid")
    record["score"]["per_vulnerability"][0]["score"] = 0
    result = validate_submitted(record)
    assert any("passed is true but score is 0" in e for e in result.errors)


def test_per_vulnerability_score_must_be_binary_integer():
    record = load_fixture("submitted_valid")
    record["score"]["per_vulnerability"][0]["score"] = 5
    result = validate_submitted(record)
    assert any("score" in e for e in result.errors)

    record = load_fixture("submitted_valid")
    record["score"]["per_vulnerability"][1]["score"] = 0.5
    result = validate_submitted(record)
    assert any("score" in e for e in result.errors)


def test_per_vulnerability_extra_keys_rejected():
    record = load_fixture("submitted_valid")
    record["score"]["per_vulnerability"][0]["extra"] = "nope"
    result = validate_submitted(record)
    assert any("Additional properties" in e for e in result.errors)


def test_lifecycle_official_score_must_match_ledger():
    record = load_fixture("accepted_valid")
    record["score"]["official_score"] = 0.999
    result = validate_lifecycle(record)
    assert any("official_score" in e for e in result.errors)
