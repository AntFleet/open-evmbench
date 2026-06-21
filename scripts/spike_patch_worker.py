#!/usr/bin/env python3
"""Spike: grade the upstream gold patch for 2023-07-pooltogether locally.

This validates PatchGrader semantics (apply diff → invariant → per-vuln tests)
before investing in Docker-backed CI workers. See docs/PHASE2_LAUNCH_CHECKLIST.md.

Usage:
    .venv/bin/python scripts/spike_patch_worker.py
    .venv/bin/python scripts/spike_patch_worker.py --skip-invariant
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.patch_worker import (  # noqa: E402
    PatchWorkerError,
    grade_audit_local,
)
from openevmbench.dataset import load_patch_audit  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402

AUDIT_ID = "2023-07-pooltogether"
SOURCES = REPO_ROOT / "audit_sources" / AUDIT_ID


def _run(cmd: list[str], *, cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PatchWorkerError(f"{' '.join(cmd)} failed: {proc.stderr.strip()[:400]}")


def _build_gold_diff(upstream: Path, audit_id: str, repo: Path, diff_path: Path) -> Path:
    evm = upstream / "project" / "evmbench"
    cfg = load_patch_audit(upstream, audit_id)
    gold_vault = evm / "audits" / audit_id / "patch" / "Vault.sol"
    if not gold_vault.is_file():
        raise PatchWorkerError(f"missing gold patch file: {gold_vault}")

    _run(["git", "checkout", "-q", cfg.base_commit], cwd=repo)
    target = repo / "vault" / "src" / "Vault.sol"
    shutil.copy2(gold_vault, target)
    _run(["git", "add", "vault/src/Vault.sol"], cwd=repo)
    proc = subprocess.run(
        ["git", "-c", "core.fileMode=false", "diff", "--binary", "--cached", "vault/src/Vault.sol"],
        cwd=repo, capture_output=True,
    )
    if proc.returncode != 0:
        raise PatchWorkerError(f"git diff failed: {proc.stderr.decode()[:300]}")
    diff_path.write_bytes(proc.stdout)
    _run(["git", "checkout", "-q", cfg.base_commit, "--", "vault/src/Vault.sol"], cwd=repo)
    return diff_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-invariant",
        action="store_true",
        help="Skip invariant suite (useful when host forge != Docker foundry pin)",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=SOURCES,
        help=f"Checkout of evmbench-org/{AUDIT_ID} (default: {SOURCES})",
    )
    args = parser.parse_args()

    if not args.sources.is_dir():
        print(f"error: missing {args.sources} — run scripts/fetch_audit_sources.py first", file=sys.stderr)
        return 1

    upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")
    audit = load_patch_audit(upstream, AUDIT_ID)

    with tempfile.TemporaryDirectory(prefix="patch-spike-") as tmp:
        tmp_path = Path(tmp)
        work = tmp_path / "repo"
        shutil.copytree(args.sources, work, symlinks=True)
        # Drop stray exploit tests from prior local runs (not in base commit).
        for name in ("ExploitH02.t.sol", "ExploitH04.t.sol"):
            for p in work.rglob(name):
                if "test" in p.parts:
                    p.unlink(missing_ok=True)

        diff = _build_gold_diff(upstream, AUDIT_ID, work, tmp_path / "agent.diff")
        print(f"gold diff: {diff.stat().st_size} bytes")

        grade = grade_audit_local(
            audit=audit,
            repo_root=work,
            agent_diff=diff,
            upstream_repo_dir=upstream,
            skip_invariant=args.skip_invariant,
        )

    print(grade.grader_log)
    print(f"\nRESULT {grade.audit_id}: {grade.score}/{grade.max_score} invariant_ok={grade.invariant_passed}")
    for v in grade.vulnerabilities:
        print(f"  {v.vulnerability_id}: passed={v.passed} reason={v.reason_code}")

    if grade.passed or (args.skip_invariant and grade.score == grade.max_score):
        print("\nSPIKE PASS")
        return 0
    print("\nSPIKE FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
