#!/usr/bin/env python3
"""Build or smoke-test the AntFleet Patch reference package on CI or locally.

Smoke: grade gold diffs for pooltogether (Foundry) + nextgen (Hardhat).
Full: build all 22 gold diffs and run ``run_patch(use_docker=True)``.

Usage:
    .venv/bin/python scripts/patch_reference_package.py smoke
    .venv/bin/python scripts/patch_reference_package.py full --out submissions
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.constants import PATCH_VULN_COUNT  # noqa: E402
from openevmbench.dataset import load_patch_audit, load_patch_dataset  # noqa: E402
from openevmbench.hashing import sha256_file  # noqa: E402
from openevmbench.package import AgentInfo, OperatorInfo, RunMeta  # noqa: E402
from openevmbench.patch_docker import grade_audit_docker  # noqa: E402
from openevmbench.runner import run_patch  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402

SMOKE_AUDITS = ("2023-07-pooltogether", "2023-10-nextgen")
REF_MODEL = "upstream gold patch (harness reference)"
REF_SCAFFOLD = "openevmbench-gold-patch-reference"
REF_SCAFFOLD_HASH = sha256_file(REPO_ROOT / "scripts" / "build_gold_patch_diffs.py")
REF_OPERATOR = OperatorInfo(
    github_username="antfleet-ops",
    github_id=285575208,
    affiliation="AntFleet (reference)",
)
REF_AGENT = AgentInfo(
    model=REF_MODEL,
    scaffold_name=REF_SCAFFOLD,
    scaffold_hash=REF_SCAFFOLD_HASH,
    harness_kind="single-shot",
)


def _build_gold_diffs(out_dir: Path, *, audits: tuple[str, ...] | None = None) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "build_gold_patch_diffs.py"),
        "--out",
        str(out_dir),
    ]
    if audits:
        for audit_id in audits:
            cmd.extend(["--audit", audit_id])
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def smoke_grade(*, upstream: Path, diffs_dir: Path) -> int:
    _build_gold_diffs(diffs_dir, audits=SMOKE_AUDITS)
    ok = True
    for audit_id in SMOKE_AUDITS:
        audit = load_patch_audit(upstream, audit_id)
        diff = diffs_dir / f"{audit_id}.diff"
        print(f"grading {audit_id}…", flush=True)
        grade = grade_audit_docker(
            audit=audit,
            agent_diff=diff,
            upstream_repo_dir=upstream,
        )
        print(
            f"  {audit_id}: {grade.score}/{grade.max_score} "
            f"invariant_ok={grade.invariant_passed}",
            flush=True,
        )
        if grade.score != grade.max_score or not grade.invariant_passed:
            ok = False
    if ok:
        print("PATCH_REFERENCE_SMOKE_PASS")
        return 0
    print("PATCH_REFERENCE_SMOKE_FAIL", file=sys.stderr)
    return 1


def full_package(*, upstream: Path, diffs_dir: Path, submissions_root: Path) -> int:
    _build_gold_diffs(diffs_dir)
    dataset = load_patch_dataset(upstream)
    result = run_patch(
        dataset=dataset,
        agent_outputs_dir=diffs_dir,
        sources_dir=None,
        upstream_repo_dir=upstream,
        operator=REF_OPERATOR,
        agent=REF_AGENT,
        run_meta=RunMeta(
            tokens_total=0,
            tokens_prompt=0,
            tokens_completion=0,
            tokens_per_task=[],
            wall_clock_ms=0,
            runs_count=1,
        ),
        submissions_root=submissions_root,
        use_docker=True,
    )
    record = result.package.record
    solved = int(record["score"]["solved_count"])
    pct = float(record["score"]["claimed_score"]) * 100
    print(f"claimed score: {pct:.1f}%  {solved}/{record['score']['max_score']}")
    print(f"package: {result.package.package_dir}")
    if solved == PATCH_VULN_COUNT:
        print("PATCH_REFERENCE_FULL_PASS")
        return 0
    print("PATCH_REFERENCE_FULL_FAIL", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("smoke", "full"),
        help="smoke: 2 audits; full: 22 audits + package",
    )
    parser.add_argument(
        "--diffs-dir",
        type=Path,
        default=REPO_ROOT / "runs" / "patch_reference" / "gold_diffs",
        help="Directory for *.diff files",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "submissions",
        help="submissions root for full mode",
    )
    parser.add_argument(
        "--upstream",
        type=Path,
        default=REPO_ROOT / "upstream" / "frontier-evals",
    )
    args = parser.parse_args()
    args.diffs_dir.mkdir(parents=True, exist_ok=True)
    upstream = ensure_upstream(args.upstream)

    if args.mode == "smoke":
        return smoke_grade(upstream=upstream, diffs_dir=args.diffs_dir)
    return full_package(
        upstream=upstream,
        diffs_dir=args.diffs_dir,
        submissions_root=args.out,
    )


if __name__ == "__main__":
    raise SystemExit(main())
