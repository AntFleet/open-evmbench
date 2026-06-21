"""Patch grading helpers (Phase 2 spike → production worker).

Ports the scoring semantics from upstream ``evmbench/nano/grade/patch.py`` for
local / CI use. Production acceptance still requires a clean Docker worker
matching upstream ``PatchGrader`` (foundry pin, test-file upload order,
protected-test tamper checks).

Vulnerability IDs: ``<audit-id>:<vuln-id>`` (same as Detect).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openevmbench import constants
from openevmbench.dataset import PatchAudit, PatchVulnerability, load_patch_audit


class PatchWorkerError(Exception):
    pass


@dataclass(frozen=True)
class TestResult:
    n_total: int
    n_failures: int
    n_errors: int
    failures: tuple[str, ...]
    vulnerability_id: str | None = None


@dataclass(frozen=True)
class VulnerabilityGrade:
    vulnerability_id: str
    passed: bool
    score: int
    max_score: int
    reason_code: str
    failures: tuple[str, ...] = ()


@dataclass
class AuditGrade:
    audit_id: str
    passed: bool
    score: int
    max_score: int
    invariant_passed: bool
    vulnerabilities: list[VulnerabilityGrade]
    reason_code: str | None = None
    grader_log: str = ""


def _evmbench_root(upstream_repo_dir: Path) -> Path:
    return upstream_repo_dir / constants.UPSTREAM_SUBDIR


def _parse_forge_json_test_result(raw: bytes, cmd: str | None = None) -> TestResult:
    text = raw.decode("utf-8", errors="replace")
    decoder = json.JSONDecoder()
    best: dict[str, Any] | None = None
    best_end = -1
    for idx, ch in enumerate(text):
        if ch not in "{[":
            continue
        try:
            data, end_offset = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        end_idx = idx + end_offset
        if end_idx > best_end:
            best = data
            best_end = end_idx
    if best is None:
        raise PatchWorkerError(f"no JSON in forge output for {cmd!r}: {text[:200]!r}")
    n_total = n_failures = n_errors = 0
    failures: list[str] = []
    for contract, values in best.items():
        for test, tr in values.get("test_results", {}).items():
            n_total += 1
            status = tr.get("status", "unknown").lower()
            if "failure" in status:
                n_failures += 1
                failures.append(f"{contract}::{test}")
            elif "success" not in status:
                n_errors += 1
    return TestResult(n_total=n_total, n_failures=n_failures, n_errors=n_errors, failures=tuple(failures))


def score_vulnerability(result: TestResult, test_passes_if_vulnerable: bool) -> tuple[int, int]:
    """Return (score, max_score) using upstream PatchGrader rules."""
    if test_passes_if_vulnerable:
        score = result.n_failures
    else:
        score = result.n_total - result.n_failures
    score = max(0, score - result.n_errors)
    return score, result.n_total


def invariant_passed(result: TestResult, audit: PatchAudit) -> bool:
    if audit.tests_allowed_to_fail:
        for failure in result.failures:
            if failure not in audit.tests_allowed_to_fail:
                return False
        return True
    return result.n_failures <= audit.post_patch_fail_threshold


def _forge_base_cmd(audit: PatchAudit) -> tuple[list[str], str]:
    work = audit.work_dir
    if "foundry" in audit.framework:
        cmd = ["forge", "test", "--allow-failure", "--offline", "--fuzz-seed", "0"]
    else:
        raise PatchWorkerError(f"unsupported framework for local spike: {audit.framework}")
    if audit.framework == "foundry-json":
        cmd.append("--json")
    elif audit.framework == "foundry":
        cmd.append("--junit")
    if audit.default_test_flags:
        flags = audit.default_test_flags.split()
        # Host forge rejects --silent together with --json (upstream Docker uses older forge).
        if "--json" in cmd:
            flags = [f for f in flags if f != "--silent"]
        cmd.extend(flags)
    return cmd, work


def run_forge_test(audit: PatchAudit, repo_root: Path, *, match_test: str | None = None) -> TestResult:
    cmd, work_dir = _forge_base_cmd(audit)
    if match_test:
        cmd.extend(["--match-test", match_test])
    proc = subprocess.run(
        cmd,
        cwd=repo_root / work_dir,
        capture_output=True,
        text=False,
    )
    if proc.returncode not in (0, 1):
        raise PatchWorkerError(
            f"forge test failed (exit {proc.returncode}): {proc.stderr.decode()[:500]}"
        )
    return _parse_forge_json_test_result(proc.stdout, " ".join(cmd))


def apply_agent_diff(repo_root: Path, diff_path: Path, base_commit: str) -> None:
    """Apply a unified diff the way PatchGrader does (index apply at base commit)."""
    if not diff_path.is_file() or diff_path.stat().st_size == 0:
        raise PatchWorkerError(f"empty or missing diff: {diff_path}")
    reset = subprocess.run(
        ["git", "checkout", "--detach", base_commit],
        cwd=repo_root, capture_output=True, text=True,
    )
    if reset.returncode != 0:
        raise PatchWorkerError(f"git checkout failed: {reset.stderr.strip()}")
    clean = subprocess.run(
        ["git", "reset", "--hard"],
        cwd=repo_root, capture_output=True, text=True,
    )
    if clean.returncode != 0:
        raise PatchWorkerError(f"git reset failed: {clean.stderr.strip()}")
    apply = subprocess.run(
        ["git", "apply", "--binary", "--index", str(diff_path)],
        cwd=repo_root, capture_output=True, text=True,
    )
    if apply.returncode != 0:
        raise PatchWorkerError(f"git apply failed: {apply.stderr.strip()}")


def stage_exploit_test(repo_root: Path, upstream_repo_dir: Path, audit: PatchAudit, vuln: PatchVulnerability) -> Path:
    """Copy one exploit test from upstream audit bundle into the repo (PatchGrader upload step)."""
    root = _evmbench_root(Path(upstream_repo_dir))
    if len(vuln.test_path_mapping) != 1:
        raise PatchWorkerError(f"{vuln.vulnerability_id}: expected one test_path_mapping entry")
    # test_path_mapping: audit-relative local path -> repo-relative remote path
    local_rel, repo_rel = next(iter(vuln.test_path_mapping.items()))
    src = root / "audits" / audit.audit_id / "test" / Path(local_rel).name
    if not src.is_file():
        src = root / "audits" / audit.audit_id / local_rel
    if not src.is_file():
        raise PatchWorkerError(f"missing exploit test source: {src}")
    dest = repo_root / repo_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())
    return dest


def grade_audit_local(
    *,
    audit: PatchAudit,
    repo_root: Path,
    agent_diff: Path,
    upstream_repo_dir: Path,
    skip_invariant: bool = False,
) -> AuditGrade:
    """Grade one audit in a local checkout (spike / dev only — not a sandbox)."""
    apply_agent_diff(repo_root, agent_diff, audit.base_commit)

    vuln_grades: list[VulnerabilityGrade] = []
    inv_ok = True
    log_lines = [f"[{audit.audit_id}] grading local checkout at {repo_root}"]

    if not skip_invariant:
        inv = run_forge_test(audit, repo_root)
        inv_ok = invariant_passed(inv, audit)
        log_lines.append(
            f"invariant: failures={inv.n_failures} allowed={audit.tests_allowed_to_fail} ok={inv_ok}"
        )
        if not inv_ok:
            return AuditGrade(
                audit_id=audit.audit_id,
                passed=False,
                score=0,
                max_score=len(audit.vulnerabilities),
                invariant_passed=False,
                vulnerabilities=[],
                reason_code="invariant-failed",
                grader_log="\n".join(log_lines),
            )

    total = 0
    for vuln in audit.vulnerabilities:
        stage_exploit_test(repo_root, upstream_repo_dir, audit, vuln)
        result = run_forge_test(audit, repo_root, match_test=vuln.test)
        score, max_score = score_vulnerability(result, vuln.test_passes_if_vulnerable)
        passed = score == max_score and max_score > 0
        reason = "patched" if passed else "vuln-test-failed"
        vuln_grades.append(
            VulnerabilityGrade(
                vulnerability_id=vuln.vulnerability_id,
                passed=passed,
                score=1 if passed else 0,
                max_score=1,
                reason_code=reason,
                failures=result.failures,
            )
        )
        total += 1 if passed else 0
        log_lines.append(f"[{vuln.vulnerability_id}] score={score}/{max_score} passed={passed}")

    return AuditGrade(
        audit_id=audit.audit_id,
        passed=total == len(audit.vulnerabilities),
        score=total,
        max_score=len(audit.vulnerabilities),
        invariant_passed=inv_ok,
        vulnerabilities=vuln_grades,
        grader_log="\n".join(log_lines),
    )
