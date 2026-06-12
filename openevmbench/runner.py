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
from openevmbench.dataset import DetectDataset
from openevmbench.hashing import sha256_prefixed
from openevmbench.judge import JudgeClient, TranscriptWriter, judge_audit, load_pinned_prompt
from openevmbench.package import (
    AgentInfo,
    JudgeInfo,
    OperatorInfo,
    RunMeta,
    SubmissionPackage,
    build_submitted_record,
    deterministic_archive,
    new_submission_id,
    write_record,
)
from openevmbench.validation import ValidationResult, validate_phase1_detect


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
