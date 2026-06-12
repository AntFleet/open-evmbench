"""Automated PR checks (SPEC §5 review stages 1-9, Detect path).

Used three ways with the same code:
- `openevmbench submit` runs them locally before opening a PR,
- the submission-checks GitHub Action runs them on every submission PR,
- the acceptance-signing step re-runs them before signing.

Failures carry public reason codes (SPEC §3 Publication): the code is the
machine-readable rejection reason, the message is the human-readable detail.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from openevmbench.dataset import DetectDataset
from openevmbench.hashing import sha256_file, sha256_prefixed
from openevmbench.package import deterministic_archive
from openevmbench.validation import validate_phase1_detect

# Public rejection reason codes.
PATH_VIOLATION = "path-violation"
MISSING_FILE = "missing-file"
RECORD_INVALID = "record-invalid"
IDENTITY_MISMATCH = "identity-mismatch"
SUBMISSION_ID_MISMATCH = "submission-id-mismatch"
TRANSCRIPT_HASH_MISMATCH = "transcript-hash-mismatch"
TRANSCRIPT_INCONSISTENT = "transcript-inconsistent"
TRANSCRIPT_PATH_MISMATCH = "transcript-path-mismatch"
ARCHIVE_MISMATCH = "archive-mismatch"
VULNERABILITY_ID_MISMATCH = "vulnerability-id-mismatch"
ARCHIVE_SYMLINK = "archive-symlink"
FILE_TOO_LARGE = "file-too-large"

MAX_TRANSCRIPT_BYTES = 50 * 1024 * 1024
MAX_RECORD_BYTES = 1 * 1024 * 1024

_SUBMISSION_PATH_RE = re.compile(
    r"^submissions/phase1/(?P<handle>[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})/"
    r"(?P<sid>[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
)


@dataclass(frozen=True)
class CheckFailure:
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


@dataclass
class CheckReport:
    failures: list[CheckFailure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def fail(self, code: str, message: str) -> None:
        self.failures.append(CheckFailure(code, message))

    def summary(self) -> str:
        if self.ok:
            return "all checks passed" + (f" ({len(self.warnings)} warning(s))" if self.warnings else "")
        return "\n".join(str(f) for f in self.failures)


def find_submission_dir(changed_paths: list[str]) -> tuple[str | None, CheckReport]:
    """Stage: PR path containment. Exactly one submission dir, nothing outside it."""
    report = CheckReport()
    dirs: set[str] = set()
    for path in changed_paths:
        normalized = _safe_relative_posix_path(path)
        if normalized is None:
            report.fail(
                PATH_VIOLATION,
                f"{path!r} is outside submissions/phase1/<github_handle>/<submission_id>/",
            )
            continue
        m = re.fullmatch(f"{_SUBMISSION_PATH_RE.pattern}/.+", normalized)
        if not m:
            report.fail(
                PATH_VIOLATION,
                f"{path!r} is outside submissions/phase1/<github_handle>/<submission_id>/",
            )
            continue
        dirs.add(f"submissions/phase1/{m.group('handle')}/{m.group('sid')}/")
    if len(dirs) > 1:
        report.fail(PATH_VIOLATION, f"PR touches multiple submission dirs: {sorted(dirs)}")
    if not dirs and not report.failures:
        report.fail(PATH_VIOLATION, "PR contains no submission files")
    return (next(iter(dirs)) if len(dirs) == 1 and report.ok else None), report


def _safe_relative_posix_path(path: str) -> str | None:
    if "\\" in path:
        return None
    pure = PurePosixPath(path)
    if pure.is_absolute():
        return None
    parts = pure.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        return None
    normalized = pure.as_posix()
    if normalized != path.rstrip("/"):
        return None
    return normalized


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _reject_large_file(path: Path, limit: int, report: CheckReport) -> bool:
    size = _file_size(path)
    if size > limit:
        report.fail(FILE_TOO_LARGE, f"{path.name} is {size} bytes, exceeds limit {limit}")
        return True
    return False


def _check_transcript_consistency(
    transcript_path: Path, record: dict, report: CheckReport
) -> None:
    """Stage: judge transcript spot-check — every verdict in the transcript must
    match score.per_vulnerability, and every vulnerability must be covered."""
    verdicts: dict[str, bool] = {}
    with transcript_path.open("r", encoding="utf-8") as f:
        lines = enumerate(f, 1)
        for n, line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                report.fail(TRANSCRIPT_INCONSISTENT, f"transcript line {n} is not valid JSON")
                return
            if not {"ts", "role", "content"} <= set(obj):
                report.fail(TRANSCRIPT_INCONSISTENT, f"transcript line {n} lacks ts/role/content")
                return
            if obj["role"] == "assistant" and "vulnerability_id" in obj:
                try:
                    verdict = json.loads(obj["content"])
                    detected = verdict["detected"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    report.fail(
                        TRANSCRIPT_INCONSISTENT,
                        f"transcript line {n}: assistant content is not a JudgeResult",
                    )
                    return
                vid = obj["vulnerability_id"]
                if vid in verdicts and verdicts[vid] != detected:
                    report.fail(TRANSCRIPT_INCONSISTENT, f"conflicting verdicts for {vid}")
                    return
                verdicts[vid] = detected

    for entry in record["score"]["per_vulnerability"]:
        vid = entry["vulnerability_id"]
        if vid not in verdicts:
            report.fail(TRANSCRIPT_INCONSISTENT, f"no transcript verdict for {vid}")
        elif verdicts[vid] != entry["passed"]:
            report.fail(
                TRANSCRIPT_INCONSISTENT,
                f"{vid}: transcript says detected={verdicts[vid]}, record says passed={entry['passed']}",
            )


def _check_vulnerability_ids(record: dict, dataset: DetectDataset, report: CheckReport) -> None:
    expected = {v.vulnerability_id for v in dataset.vulnerabilities}
    actual = {
        entry.get("vulnerability_id")
        for entry in record.get("score", {}).get("per_vulnerability", [])
        if isinstance(entry, dict)
    }
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing {len(missing)} pinned id(s): {', '.join(missing[:5])}")
        if extra:
            details.append(f"unexpected {len(extra)} id(s): {', '.join(extra[:5])}")
        report.fail(VULNERABILITY_ID_MISMATCH, "; ".join(details) or "vulnerability IDs differ")


def _check_archive_symlinks(artifacts_dir: Path, repo_root: Path, report: CheckReport) -> None:
    for path in artifacts_dir.rglob("*"):
        if path.is_symlink():
            report.fail(
                ARCHIVE_SYMLINK,
                f"agent_artifacts contains symlink {path.relative_to(repo_root)}",
            )
            return


def check_package(
    repo_root: Path | str,
    package_rel: str,
    pr_author: str | None = None,
    pr_author_id: int | str | None = None,
    dataset: DetectDataset | None = None,
) -> CheckReport:
    """Run all automated checks on one submission package directory.

    `package_rel` is the path relative to the repo root, e.g.
    `submissions/phase1/alice/<submission_id>` (trailing slash optional).
    """
    report = CheckReport()
    repo_root = Path(repo_root)
    package_rel = package_rel.rstrip("/")
    package_dir = repo_root / package_rel

    normalized = _safe_relative_posix_path(package_rel)
    m = re.fullmatch(_SUBMISSION_PATH_RE.pattern, normalized or "")
    if not m:
        report.fail(PATH_VIOLATION, f"{package_rel!r} is not a valid submission directory path")
        return report
    package_rel = normalized or package_rel
    path_handle, path_sid = m.group("handle"), m.group("sid")

    record_path = package_dir / "record.json"
    transcript_path = package_dir / "judge_transcript.jsonl"
    artifacts_dir = package_dir / "agent_artifacts"
    for required, code in (
        (record_path, MISSING_FILE),
        (transcript_path, MISSING_FILE),
        (artifacts_dir, MISSING_FILE),
    ):
        if not required.exists():
            report.fail(code, f"missing required {required.relative_to(repo_root)}")
    if report.failures:
        return report

    if _reject_large_file(record_path, MAX_RECORD_BYTES, report):
        return report
    if _reject_large_file(transcript_path, MAX_TRANSCRIPT_BYTES, report):
        return report

    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        report.fail(RECORD_INVALID, f"record.json is not valid JSON: {e}")
        return report

    validation = validate_phase1_detect(record)
    for err in validation.errors:
        report.fail(RECORD_INVALID, err)
    report.warnings.extend(validation.warnings)
    if report.failures:
        return report

    if dataset is not None:
        _check_vulnerability_ids(record, dataset, report)

    # Stage: identity binding.
    operator = record["operator"]["github_username"]
    if operator.casefold() != path_handle.casefold():
        report.fail(
            IDENTITY_MISMATCH,
            f"record operator {operator!r} does not match path handle {path_handle!r}",
        )
    if pr_author is not None and operator.lower() != pr_author.lower():
        report.fail(
            IDENTITY_MISMATCH,
            f"record operator {operator!r} does not match PR author {pr_author!r}",
        )
    if pr_author_id is not None:
        try:
            ids_match = int(record["operator"]["github_id"]) == int(pr_author_id)
        except (TypeError, ValueError):
            ids_match = False
        if not ids_match:
            report.fail(
                IDENTITY_MISMATCH,
                f"record operator github_id {record['operator']['github_id']} does not match PR author id {pr_author_id}",
            )
    if record["submission_id"] != path_sid:
        report.fail(
            SUBMISSION_ID_MISMATCH,
            f"record submission_id {record['submission_id']} does not match path {path_sid}",
        )

    # Stage: transcript hash + declared path.
    actual_transcript_hash = sha256_file(transcript_path)
    if record["judge"]["transcript_hash"] != actual_transcript_hash:
        report.fail(
            TRANSCRIPT_HASH_MISMATCH,
            f"judge.transcript_hash {record['judge']['transcript_hash']} != file {actual_transcript_hash}",
        )
    expected_rel = f"{package_rel}/judge_transcript.jsonl"
    if record["judge"]["transcript_contents_or_url"] != expected_rel:
        report.fail(
            TRANSCRIPT_PATH_MISMATCH,
            f"judge.transcript_contents_or_url is {record['judge']['transcript_contents_or_url']!r}, expected {expected_rel!r}",
        )

    # Stage: transcript verdict consistency.
    if not any(f.code == TRANSCRIPT_HASH_MISMATCH for f in report.failures):
        _check_transcript_consistency(transcript_path, record, report)

    # Stage: archive symlink guard.
    _check_archive_symlinks(artifacts_dir, repo_root, report)
    if report.failures:
        return report

    # Stage: archive hash + size reproduce from the deterministic recipe.
    rebuilt = deterministic_archive(artifacts_dir)
    if record["submission"]["archive_hash"] != sha256_prefixed(rebuilt):
        report.fail(
            ARCHIVE_MISMATCH,
            f"submission.archive_hash does not reproduce from agent_artifacts/ "
            f"(recorded {record['submission']['archive_hash']}, rebuilt {sha256_prefixed(rebuilt)})",
        )
    elif record["submission"]["archive_size_bytes"] != len(rebuilt):
        report.fail(
            ARCHIVE_MISMATCH,
            f"submission.archive_size_bytes {record['submission']['archive_size_bytes']} != rebuilt {len(rebuilt)}",
        )

    return report
