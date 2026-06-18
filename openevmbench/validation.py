"""Record validation: JSON Schema plus the cross-field rules the schema can't express.

Profiles (SPEC §4):
- "submitted": the file a submitter packages in a PR. No `state`, no
  AntFleet-populated fields (`score.official_score`, `antfleet_acceptance`,
  `prize_review_*`, `promoted_*`).
- "lifecycle": any record carrying a `state` (checking/accepted/rejected/
  promoted/yanked). State-conditional requirements are in the schema; this
  module adds presence/absence rules per profile.

`validate_*` functions return a ValidationResult; `errors` non-empty means
the record must be rejected. `warnings` are advisory (e.g. claimed_score not
matching solved_count/max_score — claimed_score is submitter-reported and
the official score is what ranks, SPEC §4).
"""

from __future__ import annotations

import importlib.resources
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import jsonschema

from openevmbench import constants

_ANTFLEET_FIELDS = ("state", "state_reason", "antfleet_acceptance",
                    "prize_review_status", "prize_review_reason",
                    "promoted_at", "promoted_commit_sha")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load_schema() -> dict[str, Any]:
    ref = importlib.resources.files("openevmbench.schemas") / "record.schema.json"
    return json.loads(ref.read_text(encoding="utf-8"))


_SCHEMA = _load_schema()
_VALIDATOR = jsonschema.Draft202012Validator(_SCHEMA)


def _schema_errors(record: dict[str, Any]) -> list[str]:
    errors = []
    for err in sorted(_VALIDATOR.iter_errors(record), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"schema: {path}: {err.message}")
    return errors


def _cross_field_checks(record: dict[str, Any], result: ValidationResult) -> None:
    score = record.get("score", {})
    per_vuln = score.get("per_vulnerability", [])
    if not isinstance(per_vuln, list):
        return

    passed_count = sum(1 for v in per_vuln if isinstance(v, dict) and v.get("passed") is True)
    solved_count = score.get("solved_count")
    if isinstance(solved_count, int) and solved_count != passed_count:
        result.errors.append(
            f"score.solved_count is {solved_count} but per_vulnerability has {passed_count} passed entries"
        )

    ids = [v.get("vulnerability_id") for v in per_vuln if isinstance(v, dict)]
    counts = Counter(i for i in ids if i is not None)
    dupes = sorted(i for i, count in counts.items() if count > 1)
    if dupes:
        result.errors.append(f"duplicate vulnerability_id entries: {', '.join(dupes)}")

    for v in per_vuln:
        if isinstance(v, dict) and v.get("passed") is True and v.get("score") == 0:
            result.errors.append(
                f"{v.get('vulnerability_id')}: passed is true but score is 0"
            )

    max_score = score.get("max_score")
    claimed = score.get("claimed_score")
    if isinstance(max_score, int) and max_score > 0 and isinstance(claimed, (int, float)):
        if isinstance(solved_count, int) and abs(claimed - solved_count / max_score) > 0.005:
            result.errors.append(
                f"score.claimed_score {claimed} differs from solved_count/max_score "
                f"({solved_count}/{max_score} = {solved_count / max_score:.4f})"
            )
    official = score.get("official_score")
    if (
        record.get("state") in ("accepted", "promoted", "yanked")
        and isinstance(max_score, int)
        and max_score > 0
        and isinstance(solved_count, int)
        and isinstance(official, (int, float))
    ):
        derived = round(solved_count / max_score, 4)
        if official != derived:
            result.errors.append(
                f"score.official_score {official} must equal solved_count/max_score "
                f"rounded to 4 decimals ({derived})"
            )

    run = record.get("run", {})
    tp, tc, tt = run.get("tokens_prompt"), run.get("tokens_completion"), run.get("tokens_total")
    if all(isinstance(x, int) for x in (tp, tc, tt)) and tp + tc != tt:
        result.warnings.append(
            f"run.tokens_total {tt} != tokens_prompt + tokens_completion ({tp} + {tc})"
        )


def validate_submitted(record: dict[str, Any]) -> ValidationResult:
    """Validate the submitted_record profile (what a PR's record.json must be)."""
    result = ValidationResult()
    result.errors.extend(_schema_errors(record))

    for fld in _ANTFLEET_FIELDS:
        if fld in record:
            result.errors.append(f"submitted record must not contain AntFleet-populated field {fld!r}")
    if isinstance(record.get("score"), dict) and "official_score" in record["score"]:
        result.errors.append("submitted record must not contain score.official_score")

    if not result.errors:
        _cross_field_checks(record, result)
    return result


def validate_lifecycle(record: dict[str, Any]) -> ValidationResult:
    """Validate a record carrying a lifecycle state (checking..yanked)."""
    result = ValidationResult()
    result.errors.extend(_schema_errors(record))
    if "state" not in record:
        result.errors.append("lifecycle record must contain a state field")
    if not result.errors:
        _cross_field_checks(record, result)
    return result


def validate_phase1_detect(record: dict[str, Any]) -> ValidationResult:
    """Phase 1 Detect launch-board rules.

    Records carrying an `antfleet_acceptance` block have already been signed
    by acceptance-signing and are in a lifecycle state (accepted/promoted/
    yanked). For those we validate against the lifecycle profile rather than
    the submitted profile (which forbids the very acceptance fields the
    signing workflow legitimately writes back to the PR branch). Submission
    PRs that have NOT yet been signed are still validated as submitted.
    """
    if "antfleet_acceptance" in record:
        result = validate_lifecycle(record)
    else:
        result = validate_submitted(record)

    if record.get("phase") != constants.PHASE_DETECT:
        result.errors.append(f"phase must be {constants.PHASE_DETECT} for the Phase 1 board")
    if record.get("mode") != constants.MODE_DETECT:
        result.errors.append(f"mode must be {constants.MODE_DETECT!r} for the Phase 1 board")

    benchmark = record.get("benchmark", {})
    if benchmark.get("upstream_repo") != constants.UPSTREAM_REPO:
        result.errors.append(
            f"benchmark.upstream_repo must be {constants.UPSTREAM_REPO!r}, got {benchmark.get('upstream_repo')!r}"
        )
    pinned = (constants.UPSTREAM_COMMIT, constants.UPSTREAM_COMMIT_SHORT)
    if benchmark.get("upstream_commit") not in pinned:
        result.errors.append(
            f"benchmark.upstream_commit must be the launch pin {constants.UPSTREAM_COMMIT_SHORT!r}"
        )
    if benchmark.get("harness_version") != constants.HARNESS_VERSION:
        result.errors.append(
            f"benchmark.harness_version must be {constants.HARNESS_VERSION!r}"
        )

    judge = record.get("judge")
    if isinstance(judge, dict):
        expected = f"sha256:{constants.JUDGE_PROMPT_SHA256}"
        if judge.get("prompt_hash") != expected:
            result.errors.append(
                f"judge.prompt_hash must equal the pinned prompt hash {expected}"
            )

    score = record.get("score", {})
    if score.get("max_score") != constants.DETECT_VULN_COUNT:
        result.errors.append(
            f"score.max_score must be {constants.DETECT_VULN_COUNT} for a full Detect run"
        )
    per_vuln = score.get("per_vulnerability", [])
    if isinstance(per_vuln, list) and len(per_vuln) != constants.DETECT_VULN_COUNT:
        result.errors.append(
            f"score.per_vulnerability must have {constants.DETECT_VULN_COUNT} entries, got {len(per_vuln)}"
        )
    return result
