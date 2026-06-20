"""Submission packaging: portable artifacts manifest, record assembly, PR layout.

PR package layout (SPEC §4):

    submissions/phase1/<github_handle>/<submission_id>/
      record.json
      judge_transcript.jsonl
      agent_artifacts/
        <audit-id>/audit.md      (one report per audit; 40 for a full run)

`submission.archive_hash` is the SHA-256 of a portable, length-prefixed
serialization of the `agent_artifacts/` tree (manifest-v1 scheme, see
`deterministic_archive` below). The previous tar.gz-based scheme produced
different bytes across (OS, Python, zlib) combos, breaking cross-environment
verification; the manifest scheme depends only on file contents + relative
paths and is deterministic everywhere. `submission.archive_size_bytes` is
the length of those serialized manifest bytes. The archive file itself is
NOT committed in the PR — artifacts are present unpacked, and the
deterministic recipe lets anyone rebuild the exact bytes and check the
hash. `note_hash` is omitted in v1 because Detect runs produce one audit.md
per audit, not a single top-level audit.md.
"""

from __future__ import annotations

import json
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


_MANIFEST_SCHEME = b"openevmbench-artifacts-manifest-v1\n"


def deterministic_archive(artifacts_dir: Path | str) -> bytes:
    """Return a portable, deterministic serialization of `artifacts_dir`.

    Scheme `openevmbench-artifacts-manifest-v1`:

        domain_separator || for each (sorted) entry:
            uint32_be(len(rel_path_bytes)) || rel_path_bytes ||
            uint64_be(len(content_bytes)) || content_bytes

    where rel_path_bytes is the file's path relative to artifacts_dir encoded
    as UTF-8 with POSIX separators ("/"), and the entry list is sorted by
    that byte-sequence. Symlinks and directories are skipped; only regular
    files are included.

    This replaces the previous tar.gz-based scheme, which produced different
    bytes across (OS, Python version, zlib build) combinations and broke
    cross-environment verification (Issue #10). The manifest depends only
    on file contents and paths — no archive lib, no compression, no
    platform-dependent metadata — so the SHA-256 is deterministic on any
    Python 3.11+ stdlib.

    The return value is NOT a usable archive file; it's a hashable
    canonical representation. Code that needs an actual archive file can
    tar/zip the agent_artifacts directory on the fly.
    """
    artifacts_dir = Path(artifacts_dir)
    out = bytearray(_MANIFEST_SCHEME)
    entries = sorted(
        (p.relative_to(artifacts_dir).as_posix().encode("utf-8"), p)
        for p in artifacts_dir.rglob("*")
        if p.is_file() and not p.is_symlink()
    )
    for rel_path_bytes, full_path in entries:
        data = full_path.read_bytes()
        out += len(rel_path_bytes).to_bytes(4, "big")
        out += rel_path_bytes
        out += len(data).to_bytes(8, "big")
        out += data
    return bytes(out)


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
    # Optional — added 2026-06-20 (SPEC §3 amendment in flight). Lets
    # operators record the model-side reasoning_effort / temperature /
    # other knobs that control comparability, mirroring how the judge
    # block tracks judge.params.
    params: dict[str, Any] | None = None
    # Optional — sha256 of the AUDITOR_PROMPT (or whatever system prompt
    # the scaffold uses). Mirrors judge.prompt_hash so leaderboard
    # filtering can require BOTH same agent prompt AND same judge prompt
    # for an apples-to-apples comparison group.
    prompt_hash: str | None = None


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


def _agent_block(agent: AgentInfo) -> dict[str, Any]:
    """Serialize the agent block, omitting optional fields when unset.

    Backward compatibility: the four legacy fields (model, scaffold_name,
    scaffold_hash, harness_kind) always appear, identical to the
    pre-2026-06-20 schema. The new fields (``params``, ``prompt_hash``)
    are emitted ONLY if the operator populated them — older records, and
    new records from runners that haven't been updated yet, omit them so
    they don't trip the JSON schema validator.
    """
    block: dict[str, Any] = {
        "model": agent.model,
        "scaffold_name": agent.scaffold_name,
        "scaffold_hash": agent.scaffold_hash,
        "harness_kind": agent.harness_kind,
    }
    if agent.params:
        block["params"] = agent.params
    if agent.prompt_hash:
        block["prompt_hash"] = agent.prompt_hash
    return block


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
        "agent": _agent_block(agent),
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
