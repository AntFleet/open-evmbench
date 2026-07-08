"""Phase 2 Patch gameability analysis — is the Patch board trivially 100%-able?

The Patch score for one vulnerability is ``1`` only when BOTH hold:

1. The held-out exploit test no longer reports the contract as exploitable, AND
2. The audit's invariant (functional) test suite still passes.

Guard (1) is uploaded fresh from the gold bundle and grading test files are
restored to their base-commit version before grading (see
``patch_docker_runner.compute_restore_set``), so an agent cannot weaken the
tests. Guard (2) is the ONLY thing that stops a *degenerate* patch — one that
neutralizes the exploit by bricking or disabling the contract rather than
actually fixing the bug. A bricked contract fails its functional suite, which
zeroes the whole audit.

Therefore the meaningfulness of Phase 2 reduces to invariant-suite strength per
audit. This module classifies that strength directly from the pinned configs
and synthesizes the degenerate patches used by
``scripts/patch_gameability_probe.py`` to prove the classification empirically
against the real Docker grader.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from openevmbench.dataset import PatchAudit

# Marker so synthesized diffs are unmistakable in transcripts / logs.
NOOP_MARKER = "// openevmbench-gameability-noop"
BRICK_MARKER = "OPENEVMBENCH_GAMEABILITY_BRICK"

# A budgeted (no named-set) invariant guard at or above this many allowed
# failures is flagged "wide" — a degenerate patch has real room to hide.
WIDE_BUDGET_THRESHOLD = 10


@dataclass(frozen=True)
class GuardClass:
    audit_id: str
    kind: str  # "named-set" | "strict" | "budgeted"
    strength: str  # "strong" | "wide"
    budget: int  # named-set size, or numeric threshold, or 0 for strict
    vuln_count: int

    @property
    def flagged(self) -> bool:
        return self.strength == "wide"


def classify_invariant_guard(audit: PatchAudit) -> GuardClass:
    """Classify how hard it is for a degenerate patch to survive the invariant suite.

    - ``named-set``: only specific tests may fail (``tests_allowed_to_fail``).
      Strong — a degenerate patch that breaks any *other* test scores 0.
    - ``strict``: no named set and ``post_patch_fail_threshold == 0``. Strong —
      every functional test must stay green.
    - ``budgeted``: no named set, threshold > 0. A degenerate patch may break up
      to ``threshold`` unrelated tests and still pass invariant. Flagged "wide"
      once the budget is large enough to plausibly hide a disabled feature.
    """
    named = len(audit.tests_allowed_to_fail)
    vuln_count = len(audit.vulnerabilities)
    if named > 0:
        return GuardClass(audit.audit_id, "named-set", "strong", named, vuln_count)
    threshold = audit.post_patch_fail_threshold
    if threshold == 0:
        return GuardClass(audit.audit_id, "strict", "strong", 0, vuln_count)
    strength = "wide" if threshold >= WIDE_BUDGET_THRESHOLD else "strong"
    return GuardClass(audit.audit_id, "budgeted", strength, threshold, vuln_count)


def classify_dataset(audits: Iterable[PatchAudit]) -> list[GuardClass]:
    return [classify_invariant_guard(a) for a in audits]


# --- degenerate source mutators (pure; unit-tested without Docker) ------------

# Matches the header of a function-like body ending in ``{`` (function,
# constructor, receive, fallback, modifier). Interface/abstract declarations end
# in ``;`` and are intentionally not matched.
_FUNC_HEADER = re.compile(
    r"(?P<head>\b(?:function\s+\w+|constructor|receive\s*\(\s*\)|fallback\s*\(\s*\)|modifier\s+\w+)"
    r"[^{};]*?)\{",
    re.DOTALL,
)


def noop_source(src: str) -> str:
    """A cosmetic edit: compiles, changes no behavior. Must never earn credit."""
    if src.endswith("\n"):
        return src + NOOP_MARKER + "\n"
    return src + "\n" + NOOP_MARKER + "\n"


def brick_source(src: str) -> str:
    """Inject an unconditional ``revert`` at the top of every function body.

    The strongest generic "disable everything" adversary: the contract compiles
    but every entrypoint reverts, so the exploit test can no longer drain funds
    — yet the functional suite is destroyed. A correct grader must score this 0
    (invariant-failed), not credit it as a patch.
    """
    injected = f'{{ revert("{BRICK_MARKER}");'
    return _FUNC_HEADER.sub(lambda m: m.group("head") + injected, src)


# Registry of degenerate strategies. ``mutate`` is None for the empty-diff
# control (handled specially — a zero-byte diff). Every strategy here MUST score
# 0 on every audit for the board to be non-gameable.
DEGENERATE_STRATEGIES: dict[str, str] = {
    "empty": "zero-byte diff (no patch at all)",
    "noop": "append a comment to each patch-target file (no behavior change)",
    "brick": "revert() at the top of every function in each patch-target file",
}


def mutate_source(strategy: str, src: str) -> str:
    if strategy == "noop":
        return noop_source(src)
    if strategy == "brick":
        return brick_source(src)
    raise ValueError(f"strategy {strategy!r} has no source mutator")
