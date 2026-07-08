"""Anti-gaming invariants for Phase 2 Patch grading.

These encode, as executable assertions, *why* the Patch board cannot be trivially
driven to 100%. They run without Docker (pure scoring / guard / tamper logic).
The empirical counterpart is ``scripts/patch_gameability_probe.py``, which runs
synthesized degenerate patches through the real Docker grader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openevmbench.dataset import load_patch_dataset
from openevmbench.gameability import (
    BRICK_MARKER,
    NOOP_MARKER,
    brick_source,
    classify_invariant_guard,
    mutate_source,
    noop_source,
)
from openevmbench.patch_docker_runner import (
    compute_restore_set,
    invariant_ok,
    score_vulnerability,
)


@pytest.fixture(scope="module")
def dataset():
    root = Path("upstream/frontier-evals")
    if not root.is_dir():
        pytest.skip("upstream cache not present")
    return load_patch_dataset(root)


# --- scoring: a real fix earns credit; a non-fix does not --------------------

def test_no_patch_scores_zero():
    # test_passes_if_vulnerable: exploit test PASSES while the bug is present.
    # No patch -> test passes -> 0 failures -> score 0.
    score, total = score_vulnerability(
        {"n_total": 1, "n_failures": 0, "n_errors": 0, "failures": []},
        test_passes_if_vulnerable=True,
    )
    assert (score, total) == (0, 1)


def test_real_fix_scores_full():
    # Bug fixed -> exploit test now FAILS -> score 1.
    score, total = score_vulnerability(
        {"n_total": 1, "n_failures": 1, "n_errors": 0, "failures": ["C::t"]},
        test_passes_if_vulnerable=True,
    )
    assert (score, total) == (1, 1)


def test_compile_or_setup_error_is_not_credited():
    # A patch that makes the exploit test ERROR (compile/setup failure) rather
    # than cleanly fail earns no credit — errors are subtracted from score.
    score, total = score_vulnerability(
        {"n_total": 1, "n_failures": 1, "n_errors": 1, "failures": ["C::t"]},
        test_passes_if_vulnerable=True,
    )
    assert score == 0


def test_normal_polarity_fix_scores_full():
    # test_passes_if_vulnerable == False: exploit test FAILS while vulnerable,
    # PASSES once patched.
    score, total = score_vulnerability(
        {"n_total": 1, "n_failures": 0, "n_errors": 0, "failures": []},
        test_passes_if_vulnerable=False,
    )
    assert (score, total) == (1, 1)


# --- invariant guard: the only thing stopping a degenerate "brick" patch -----

def test_strict_guard_rejects_any_functional_failure():
    cfg = {"tests_allowed_to_fail": [], "post_patch_fail_threshold": 0}
    assert invariant_ok({"n_failures": 0, "failures": []}, cfg) is True
    assert invariant_ok({"n_failures": 1, "failures": ["C::t"]}, cfg) is False


def test_named_set_guard_only_allows_named_failures():
    cfg = {"tests_allowed_to_fail": ["C::allowed"], "post_patch_fail_threshold": 99}
    # A named failure is allowed; the numeric threshold is ignored when a set exists.
    assert invariant_ok({"n_failures": 1, "failures": ["C::allowed"]}, cfg) is True
    # Any un-named failure fails the guard regardless of the (large) threshold.
    assert invariant_ok({"n_failures": 1, "failures": ["C::other"]}, cfg) is False


def test_budgeted_guard_is_a_real_hole_but_bounded():
    # Documents the known weak spot: 2025-04-virtuals allows up to 59 failures.
    cfg = {"tests_allowed_to_fail": [], "post_patch_fail_threshold": 59}
    assert invariant_ok({"n_failures": 59, "failures": []}, cfg) is True
    assert invariant_ok({"n_failures": 60, "failures": []}, cfg) is False


# --- per-audit guard classification ------------------------------------------

def test_exactly_one_audit_has_a_wide_open_guard(dataset):
    """Empirical, data-derived claim behind 'Phase 2 is not trivially 100%-able'.

    Every audit except 2025-04-virtuals is behind a strict (threshold=0) or
    named-set invariant guard. Only virtuals (2/44 vulns) has a wide budget.
    If this ever changes, the gameability doc and probe scope must be revisited.
    """
    flagged = [classify_invariant_guard(a) for a in dataset.audits]
    wide = [g.audit_id for g in flagged if g.flagged]
    assert wide == ["2025-04-virtuals"], f"guard surface changed: wide guards = {wide}"

    wide_vulns = sum(g.vuln_count for g in flagged if g.flagged)
    total_vulns = sum(g.vuln_count for g in flagged)
    assert total_vulns == 44
    # At most a small minority of the board sits behind a wide guard.
    assert wide_vulns / total_vulns < 0.10


def test_every_audit_classified_strong_or_wide(dataset):
    for audit in dataset.audits:
        g = classify_invariant_guard(audit)
        assert g.kind in {"named-set", "strict", "budgeted"}
        assert g.strength in {"strong", "wide"}


# --- tamper protection: agent cannot weaken the grading tests ----------------

def test_grading_tests_are_restored_even_if_agent_edits_them():
    base = ["test/Exploit.t.sol", "test/Invariant.t.sol"]
    # Agent tried to neuter both grading tests.
    changed = ["test/Exploit.t.sol", "test/Invariant.t.sol", "src/Vault.sol"]
    restore = compute_restore_set(base, changed, "test", allowed_changes=set())
    assert set(restore) == set(base)  # both test edits reverted to base


def test_only_explicitly_allowed_test_edits_survive():
    base = ["test/Exploit.t.sol", "test/Helper.sol"]
    changed = ["test/Exploit.t.sol", "test/Helper.sol"]
    restore = compute_restore_set(
        base, changed, "test", allowed_changes={"test/Helper.sol"}
    )
    # Helper is whitelisted (kept); the exploit test is still force-restored.
    assert restore == ["test/Exploit.t.sol"]


# --- degenerate source mutators ----------------------------------------------

_SAMPLE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Vault {
    uint256 public total;

    constructor(uint256 x) {
        total = x;
    }

    function deposit(uint256 amt) external {
        total += amt;
    }

    function view_only() public view returns (uint256) {
        return total;
    }
}
"""


def test_noop_source_is_cosmetic():
    out = noop_source(_SAMPLE)
    assert NOOP_MARKER in out
    # Only appended a comment; original body untouched.
    assert out.startswith(_SAMPLE.rstrip("\n"))


def test_brick_source_injects_revert_into_every_body():
    out = brick_source(_SAMPLE)
    # constructor + deposit + view_only == 3 bodies, all bricked.
    assert out.count(f'revert("{BRICK_MARKER}")') == 3
    # Injection lands immediately after each opening brace.
    assert '{ revert("' in out


def test_mutate_source_dispatch():
    assert NOOP_MARKER in mutate_source("noop", _SAMPLE)
    assert BRICK_MARKER in mutate_source("brick", _SAMPLE)
    with pytest.raises(ValueError):
        mutate_source("empty", _SAMPLE)


# --- board disclosure stays in sync with the empirical guard classification ---

def test_board_discloses_every_wide_guard_audit(dataset):
    """The published board disclosure must cover exactly the wide-guard audits.

    Enforces the 'keep 44, disclose only' decision: any audit the classifier flags
    as a wide guard (degenerate-proof only if disclosed) must appear in
    board_config's ``patch_gameability_disclosures`` with its real vuln IDs, and no
    stale disclosures may linger. If the guard surface shifts, this fails until the
    disclosure and the evidence doc are updated together.
    """
    import json

    wide = {classify_invariant_guard(a).audit_id for a in dataset.audits if classify_invariant_guard(a).flagged}
    cfg = json.loads(Path("leaderboard/board_config.json").read_text(encoding="utf-8"))
    disclosed = {d["audit_id"] for d in cfg.get("patch_gameability_disclosures", [])}
    assert disclosed == wide, f"board disclosure {disclosed} != wide guards {wide}"

    by_id = {a.audit_id: a for a in dataset.audits}
    for d in cfg["patch_gameability_disclosures"]:
        audit = by_id[d["audit_id"]]
        expected_ids = {v.vulnerability_id for v in audit.vulnerabilities}
        assert set(d["vulnerability_ids"]) == expected_ids
        assert d.get("evidence")  # must point at the evidence artifact
