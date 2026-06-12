"""Submission packaging: deterministic archive, record assembly, PR layout.

PR package layout (SPEC §4):

    submissions/phase1/<github_handle>/<submission_id>/
      record.json
      judge_transcript.jsonl
      agent_artifacts/
        <audit-id>/audit.md      (one report per audit; 40 for a full run)

Note on `submission.archive_hash`: the archive is a deterministic tar.gz of
the `agent_artifacts/` tree (sorted entries, zeroed timestamps/owners, gzip
mtime 0). The archive file itself is NOT committed in the PR — the artifacts
are present unpacked, and the deterministic recipe lets anyone rebuild the
exact bytes and check the hash. `note_hash` is omitted in v1 because Detect
runs produce one audit.md per audit, not a single top-level audit.md.
"""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openevmbench import constants
from openevmbench.hashing import sha256_prefixed
from openevmbench.judge import VulnerabilityVerdict


def new_submission_id() -> str:
    """UUIDv7 per submission (SPEC §8 A2)."""
    if hasattr(uuid, "uuid7"):
        return str(uuid.uuid7())
    # Fallback for Python < 3.14: RFC 9562 UUIDv7 (ms timestamp + random).
    import os
    import time

    ts_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    value = (ts_ms & 0xFFFFFFFFFFFF) << 80        # unix_ts_ms: bits 80..127
    value |= 0x7 << 76                            # version 7:  bits 76..79
    value |= (rand >> 68 & 0xFFF) << 64           # rand_a:     bits 64..75
    value |= 0x2 << 62                            # variant 10: bits 62..63
    value |= rand & 0x3FFFFFFFFFFFFFFF            # rand_b:     bits 0..61
    return str(uuid.UUID(int=value))


def deterministic_archive(artifacts_dir: Path | str) -> bytes:
    """tar.gz of `artifacts_dir` with all nondeterminism stripped."""
    artifacts_dir = Path(artifacts_dir)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(
            p for p in artifacts_dir.rglob("*") if not p.is_symlink() and p.is_file()
        ):
            info = tarfile.TarInfo(name=str(path.relative_to(artifacts_dir)))
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return gzip.compress(buf.getvalue(), compresslevel=9, mtime=0)


@dataclass(frozen=True)
class OperatorInfo:
    github_username: str
    github_id: int
    affiliation: str | None = None


@dataclass(frozen=True)
class AgentInfo:
    model: str
    scaffold_name: str
    scaffold_hash: str  # sha256:<hex of the scaffold definition bytes>
    harness_kind: str   # single-shot | retry-loop | agentic-scaffold


@dataclass(frozen=True)
class JudgeInfo:
    model: str
    params: dict[str, Any]


@dataclass(frozen=True)
class RunMeta:
    tokens_total: int
    tokens_prompt: int
    tokens_completion: int
    tokens_per_task: list[int | None]
    wall_clock_ms: int
    runs_count: int = 1


@dataclass
class SubmissionPackage:
    submission_id: str
    package_dir: Path
    record: dict[str, Any]

    @property
    def record_path(self) -> Path:
        return self.package_dir / "record.json"


def per_vulnerability_entries(verdicts: list[VulnerabilityVerdict]) -> list[dict[str, Any]]:
    return [
        {
            "vulnerability_id": v.vulnerability_id,
            "passed": v.detected,
            "score": v.score,
            "reason_code": "detected" if v.detected else "not-detected",
        }
        for v in verdicts
    ]


def build_submitted_record(
    *,
    submission_id: str,
    created_at: str,
    operator: OperatorInfo,
    agent: AgentInfo,
    judge: JudgeInfo,
    run: RunMeta,
    verdicts: list[VulnerabilityVerdict],
    archive_hash: str,
    archive_size_bytes: int,
    prompt_hash: str,
    transcript_hash: str,
    transcript_path: str,
) -> dict[str, Any]:
    per_vuln = per_vulnerability_entries(verdicts)
    solved = sum(1 for v in verdicts if v.detected)
    max_score = len(verdicts)

    operator_obj: dict[str, Any] = {
        "github_username": operator.github_username,
        "github_id": operator.github_id,
    }
    if operator.affiliation:
        operator_obj["affiliation"] = operator.affiliation

    return {
        "submission_id": submission_id,
        "phase": constants.PHASE_DETECT,
        "mode": constants.MODE_DETECT,
        "created_at": created_at,
        "operator": operator_obj,
        "submission": {
            "archive_hash": archive_hash,
            "archive_size_bytes": archive_size_bytes,
        },
        "benchmark": {
            "upstream_repo": constants.UPSTREAM_REPO,
            "upstream_commit": constants.UPSTREAM_COMMIT_SHORT,
            "harness_version": constants.HARNESS_VERSION,
        },
        "agent": {
            "model": agent.model,
            "scaffold_name": agent.scaffold_name,
            "scaffold_hash": agent.scaffold_hash,
            "harness_kind": agent.harness_kind,
        },
        "judge": {
            "model": judge.model,
            "params": judge.params,
            "prompt_hash": prompt_hash,
            "transcript_hash": transcript_hash,
            "transcript_contents_or_url": transcript_path,
        },
        "run": {
            "tokens_total": run.tokens_total,
            "tokens_prompt": run.tokens_prompt,
            "tokens_completion": run.tokens_completion,
            "tokens_per_task": run.tokens_per_task,
            "wall_clock_ms": run.wall_clock_ms,
            "runs_count": run.runs_count,
        },
        "score": {
            "claimed_score": round(solved / max_score, 4) if max_score else 0.0,
            "solved_count": solved,
            "max_score": max_score,
            "per_vulnerability": per_vuln,
        },
    }


def write_record(record: dict[str, Any], path: Path | str) -> None:
    Path(path).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
