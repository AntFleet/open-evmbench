#!/usr/bin/env python3
"""Docker spike: grade gold patch inside evmbench/audit:2023-07-pooltogether.

Uses the production ``openevmbench.patch_docker`` worker. First run builds
ploit-builder → evmbench/base → audit image (slow on Apple Silicon amd64).

Usage:
    .venv/bin/python scripts/docker_spike_patch_worker.py --check-only
    .venv/bin/python scripts/docker_spike_patch_worker.py --build
    .venv/bin/python scripts/docker_spike_patch_worker.py --build --grade
    .venv/bin/python scripts/docker_spike_patch_worker.py --grade
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

from openevmbench.dataset import load_patch_audit  # noqa: E402
from openevmbench.patch_docker import (  # noqa: E402
    audit_image_exists,
    build_audit_image,
    build_base_images,
    docker_available,
    evmbench_root,
    grade_audit_docker,
)
from openevmbench.upstream import ensure_upstream  # noqa: E402

AUDIT_ID = "2023-07-pooltogether"


def _build_gold_diff(upstream: Path, audit_id: str, diff_path: Path) -> None:
    audit = load_patch_audit(upstream, audit_id)
    evm = evmbench_root(upstream)
    gold = evm / "audits" / audit_id / "patch" / "Vault.sol"
    if not gold.is_file():
        raise RuntimeError(f"missing gold patch: {gold}")

    with tempfile.TemporaryDirectory(prefix="gold-diff-") as tmp:
        repo = Path(tmp) / "repo"
        proc = subprocess.run(
            ["git", "clone", "--quiet", f"https://github.com/evmbench-org/{audit_id}.git", str(repo)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {proc.stderr[:300]}")
        subprocess.run(["git", "checkout", "-q", audit.base_commit], cwd=repo, check=True)
        target = repo / "vault" / "src" / "Vault.sol"
        shutil.copy2(gold, target)
        subprocess.run(["git", "add", "vault/src/Vault.sol"], cwd=repo, check=True)
        out = subprocess.run(
            ["git", "-c", "core.fileMode=false", "diff", "--binary", "--cached", "vault/src/Vault.sol"],
            cwd=repo,
            capture_output=True,
        )
        if out.returncode != 0:
            raise RuntimeError("git diff failed")
        diff_path.write_bytes(out.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Verify Docker daemon only")
    parser.add_argument("--build", action="store_true", help="Build base + audit images")
    parser.add_argument("--grade", action="store_true", help="Grade gold patch in container")
    args = parser.parse_args()

    if not docker_available():
        print("error: Docker daemon not available", file=sys.stderr)
        return 1

    if args.check_only:
        print("docker: ok")
        return 0

    upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")

    if args.build or (args.grade and not audit_image_exists(AUDIT_ID)):
        print(f"building Docker images for {AUDIT_ID}…")
        build_base_images(upstream_repo_dir=upstream)
        build_audit_image(AUDIT_ID, upstream_repo_dir=upstream, ensure_base=False)
        if not args.grade:
            print("build complete")
            return 0

    if args.grade or not (args.check_only or args.build):
        with tempfile.TemporaryDirectory(prefix="docker-patch-spike-") as tmp:
            diff = Path(tmp) / "agent.diff"
            _build_gold_diff(upstream, AUDIT_ID, diff)
            audit = load_patch_audit(upstream, AUDIT_ID)
            grade = grade_audit_docker(
                audit=audit,
                agent_diff=diff,
                upstream_repo_dir=upstream,
                build_if_missing=False,
            )
        print(grade.grader_log)
        for v in grade.vulnerabilities:
            print(f"  {v.vulnerability_id}: passed={v.passed} reason={v.reason_code}")
        if grade.score == grade.max_score and grade.invariant_passed:
            print(f"\nDOCKER_SPIKE_PASS {grade.score}/{grade.max_score}")
            return 0
        print("\nDOCKER_SPIKE_FAIL", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
