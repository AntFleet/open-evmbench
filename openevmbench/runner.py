"""Detect run orchestration: agent outputs -> local judge -> packaged submission.

The agent run itself (producing one audit.md per audit) belongs to the
submitter's scaffold. This runner takes a directory of agent outputs shaped

    <agent_outputs_dir>/<audit-id>/audit.md

judges every vulnerability with the pinned prompt and the submitter-chosen
judge client, and writes a complete, validated PR package under

    <submissions_root>/phase1/<github_handle>/<submission_id>/

Missing or empty audit.md files score 0 for that audit's vulnerabilities
without judge calls, mirroring the upstream grader.
"""

from __future__ import annotations

import datetime
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from openevmbench import constants
from openevmbench.dataset import DetectDataset, PatchDataset, load_patch_audit
from openevmbench.hashing import sha256_prefixed
from openevmbench.judge import JudgeClient, TranscriptWriter, judge_audit, load_pinned_prompt
from openevmbench.package import (
    AgentInfo,
    JudgeInfo,
    OperatorInfo,
    PatchTaskResult,
    RunMeta,
    SubmissionPackage,
    build_patch_submitted_record,
    build_submitted_record,
    deterministic_archive,
    new_submission_id,
    write_record,
)
from openevmbench.patch_docker import PatchWorkerError as _DockerPatchError, grade_audit_docker
from openevmbench.patch_worker import PatchWorkerError, grade_audit_local
from openevmbench.validation import ValidationResult, validate_phase1_detect, validate_phase2_patch


class RunError(Exception):
    """Raised when a detect run cannot produce a valid submission package."""


@dataclass
class DetectRunResult:
    package: SubmissionPackage
    validation: ValidationResult

    @property
    def solved_count(self) -> int:
        return self.package.record["score"]["solved_count"]

    @property
    def claimed_score(self) -> float:
        return self.package.record["score"]["claimed_score"]


@dataclass
class PatchRunResult:
    package: SubmissionPackage
    validation: ValidationResult

    @property
    def solved_count(self) -> int:
        return self.package.record["score"]["solved_count"]

    @property
    def claimed_score(self) -> float:
        return self.package.record["score"]["claimed_score"]


def _now_rfc3339() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_detect(
    *,
    dataset: DetectDataset,
    agent_outputs_dir: Path | str,
    harness_dir: Path | str,
    judge_client: JudgeClient,
    judge_info: JudgeInfo,
    operator: OperatorInfo,
    agent: AgentInfo,
    run_meta: RunMeta,
    submissions_root: Path | str,
    submission_id: str | None = None,
) -> DetectRunResult:
    agent_outputs_dir = Path(agent_outputs_dir)
    submission_id = submission_id or new_submission_id()
    started = time.monotonic()

    prompt = load_pinned_prompt(harness_dir)
    prompt_hash = f"sha256:{constants.JUDGE_PROMPT_SHA256}"

    transcript = TranscriptWriter()
    transcript.append("system", prompt)

    verdicts = []
    for audit in dataset.audits:
        audit_md = agent_outputs_dir / audit.audit_id / "audit.md"
        content = audit_md.read_text(encoding="utf-8") if audit_md.is_file() else ""
        verdicts.extend(
            judge_audit(judge_client, prompt, content, list(audit.vulnerabilities), transcript)
        )

    package_dir = (
        Path(submissions_root) / "phase1" / operator.github_username / submission_id
    )
    if package_dir.exists():
        raise RunError(f"package dir already exists: {package_dir}")
    artifacts_dir = package_dir / "agent_artifacts"
    artifacts_dir.mkdir(parents=True)

    for audit in dataset.audits:
        src = agent_outputs_dir / audit.audit_id / "audit.md"
        if src.is_file():
            dst = artifacts_dir / audit.audit_id / "audit.md"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    transcript_rel = f"submissions/phase1/{operator.github_username}/{submission_id}/judge_transcript.jsonl"
    transcript_hash = transcript.write(package_dir / "judge_transcript.jsonl")

    archive = deterministic_archive(artifacts_dir)

    if run_meta.wall_clock_ms == 0:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        run_meta = RunMeta(
            tokens_total=run_meta.tokens_total,
            tokens_prompt=run_meta.tokens_prompt,
            tokens_completion=run_meta.tokens_completion,
            tokens_per_task=run_meta.tokens_per_task,
            wall_clock_ms=elapsed_ms,
            runs_count=run_meta.runs_count,
        )

    record = build_submitted_record(
        submission_id=submission_id,
        created_at=_now_rfc3339(),
        operator=operator,
        agent=agent,
        judge=judge_info,
        run=run_meta,
        verdicts=verdicts,
        archive_hash=sha256_prefixed(archive),
        archive_size_bytes=len(archive),
        prompt_hash=prompt_hash,
        transcript_hash=transcript_hash,
        transcript_path=transcript_rel,
    )
    write_record(record, package_dir / "record.json")

    validation = validate_phase1_detect(record)
    if not validation.ok:
        raise RunError(
            "packaged record failed Phase 1 Detect validation:\n  " + "\n  ".join(validation.errors)
        )
    return DetectRunResult(
        package=SubmissionPackage(submission_id=submission_id, package_dir=package_dir, record=record),
        validation=validation,
    )


def run_patch(
    *,
    dataset: PatchDataset,
    agent_outputs_dir: Path | str,
    sources_dir: Path | str | None,
    upstream_repo_dir: Path | str,
    operator: OperatorInfo,
    agent: AgentInfo,
    run_meta: RunMeta,
    submissions_root: Path | str,
    submission_id: str | None = None,
    skip_invariant: bool = True,
    use_docker: bool = False,
) -> PatchRunResult:
    """Grade patch diffs and package a Phase 2 submission.

    Expects ``<agent_outputs_dir>/<audit-id>.diff`` for each audit in the
    patch-tasks split. With ``use_docker=True``, grades inside per-audit
    containers (production path). Otherwise uses host forge against
    ``sources_dir`` when provided.
    """
    if use_docker and grade_audit_docker is None:  # pragma: no cover
        raise RunError("Docker patch grading is unavailable in this installation")
    agent_outputs_dir = Path(agent_outputs_dir)
    submission_id = submission_id or new_submission_id()
    started = time.monotonic()
    upstream_repo_dir = Path(upstream_repo_dir)

    results_by_id: dict[str, PatchTaskResult] = {}
    for audit in dataset.audits:
        diff_path = agent_outputs_dir / f"{audit.audit_id}.diff"
        if not diff_path.is_file() or diff_path.stat().st_size == 0:
            for vuln in audit.vulnerabilities:
                results_by_id[vuln.vulnerability_id] = PatchTaskResult(
                    vulnerability_id=vuln.vulnerability_id,
                    passed=False,
                    score=0,
                    reason_code="missing-diff",
                )
            continue

        grade = None
        if use_docker:
            print(f"grading {audit.audit_id}…", flush=True)
            try:
                grade = grade_audit_docker(
                    audit=audit,
                    agent_diff=diff_path,
                    upstream_repo_dir=upstream_repo_dir,
                )
                print(
                    f"  {audit.audit_id}: {grade.score}/{grade.max_score} "
                    f"invariant_ok={grade.invariant_passed}",
                    flush=True,
                )
            except (PatchWorkerError, _DockerPatchError) as e:
                print(f"  {audit.audit_id}: grade-error ({e})", flush=True)
                for vuln in audit.vulnerabilities:
                    results_by_id[vuln.vulnerability_id] = PatchTaskResult(
                        vulnerability_id=vuln.vulnerability_id,
                        passed=False,
                        score=0,
                        reason_code="grade-error",
                    )
                continue
        elif sources_dir is None:
            for vuln in audit.vulnerabilities:
                results_by_id[vuln.vulnerability_id] = PatchTaskResult(
                    vulnerability_id=vuln.vulnerability_id,
                    passed=False,
                    score=0,
                    reason_code="not-graded",
                )
            continue
        else:
            repo_root = Path(sources_dir) / audit.audit_id
            if not (repo_root / ".git").is_dir():
                for vuln in audit.vulnerabilities:
                    results_by_id[vuln.vulnerability_id] = PatchTaskResult(
                        vulnerability_id=vuln.vulnerability_id,
                        passed=False,
                        score=0,
                        reason_code="missing-sources",
                    )
                continue

            try:
                grade = grade_audit_local(
                    audit=audit,
                    repo_root=repo_root,
                    agent_diff=diff_path,
                    upstream_repo_dir=upstream_repo_dir,
                    skip_invariant=skip_invariant,
                )
            except PatchWorkerError:
                for vuln in audit.vulnerabilities:
                    results_by_id[vuln.vulnerability_id] = PatchTaskResult(
                        vulnerability_id=vuln.vulnerability_id,
                        passed=False,
                        score=0,
                        reason_code="grade-error",
                    )
                continue

        if grade is None:
            continue
        if not grade.vulnerabilities:
            reason = grade.reason_code or "grade-error"
            for vuln in audit.vulnerabilities:
                results_by_id[vuln.vulnerability_id] = PatchTaskResult(
                    vulnerability_id=vuln.vulnerability_id,
                    passed=False,
                    score=0,
                    reason_code=reason,
                )
            continue

        for vg in grade.vulnerabilities:
            results_by_id[vg.vulnerability_id] = PatchTaskResult(
                vulnerability_id=vg.vulnerability_id,
                passed=vg.passed,
                score=vg.score,
                reason_code=vg.reason_code,
            )

    ordered_results = [
        results_by_id[vid]
        for vid in dataset.vulnerability_ids
        if vid in results_by_id
    ]
    if len(ordered_results) != constants.PATCH_VULN_COUNT:
        raise RunError(
            f"internal error: expected {constants.PATCH_VULN_COUNT} patch results, got {len(ordered_results)}"
        )

    package_dir = (
        Path(submissions_root) / "phase2" / operator.github_username / submission_id
    )
    if package_dir.exists():
        raise RunError(f"package dir already exists: {package_dir}")
    artifacts_dir = package_dir / "agent_artifacts"
    artifacts_dir.mkdir(parents=True)

    for audit in dataset.audits:
        src = agent_outputs_dir / f"{audit.audit_id}.diff"
        if src.is_file() and src.stat().st_size > 0:
            shutil.copyfile(src, artifacts_dir / f"{audit.audit_id}.diff")

    archive = deterministic_archive(artifacts_dir)

    if run_meta.wall_clock_ms == 0:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        run_meta = RunMeta(
            tokens_total=run_meta.tokens_total,
            tokens_prompt=run_meta.tokens_prompt,
            tokens_completion=run_meta.tokens_completion,
            tokens_per_task=run_meta.tokens_per_task,
            wall_clock_ms=elapsed_ms,
            runs_count=run_meta.runs_count,
        )

    record = build_patch_submitted_record(
        submission_id=submission_id,
        created_at=_now_rfc3339(),
        operator=operator,
        agent=agent,
        run=run_meta,
        results=ordered_results,
        archive_hash=sha256_prefixed(archive),
        archive_size_bytes=len(archive),
    )
    write_record(record, package_dir / "record.json")

    validation = validate_phase2_patch(record)
    if not validation.ok:
        raise RunError(
            "packaged record failed Phase 2 Patch validation:\n  " + "\n  ".join(validation.errors)
        )
    return PatchRunResult(
        package=SubmissionPackage(submission_id=submission_id, package_dir=package_dir, record=record),
        validation=validation,
    )
