#!/usr/bin/env python3
"""Grade a directory of Phase 2 patch diffs through the Docker grader (resumable).

Grades each ``<audit-id>.diff`` in --diffs against the real ``PatchGrader`` Docker
worker, writing incremental per-audit results to --out/results.json so a rerun
skips already-graded audits. Prints a running Phase 2 score.

Usage:
    python scripts/grade_patch_diffs.py --diffs runs/blind-patch/diffs --out runs/blind-patch
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.constants import PATCH_VULN_COUNT  # noqa: E402
from openevmbench.dataset import load_patch_dataset  # noqa: E402
from openevmbench.patch_docker import grade_audit_docker  # noqa: E402
from openevmbench.patch_worker import PatchWorkerError  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diffs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--upstream", type=Path, default=REPO_ROOT / "upstream" / "frontier-evals")
    ap.add_argument("--force", action="store_true", help="re-grade even if a result exists")
    args = ap.parse_args()

    upstream = ensure_upstream(args.upstream)
    dataset = load_patch_dataset(upstream)
    args.out.mkdir(parents=True, exist_ok=True)
    results_path = args.out / "results.json"

    results: dict = json.loads(results_path.read_text()) if results_path.is_file() and not args.force else {}

    for i, audit in enumerate(dataset.audits, 1):
        aid = audit.audit_id
        if aid in results and not args.force:
            print(f"[{i}/22] {aid}: cached ({results[aid]['score']}/{results[aid]['max_score']})", flush=True)
            continue
        diff = args.diffs / f"{aid}.diff"
        started = time.monotonic()
        if not diff.is_file() or diff.stat().st_size == 0:
            results[aid] = {"score": 0, "max_score": len(audit.vulnerabilities),
                            "invariant_passed": False, "reason": "missing-diff", "vulns": []}
            print(f"[{i}/22] {aid}: MISSING DIFF -> 0", flush=True)
            results_path.write_text(json.dumps(results, indent=2))
            continue
        print(f"[{i}/22] {aid}: grading (building image if needed)...", flush=True)
        try:
            g = grade_audit_docker(audit=audit, agent_diff=diff, upstream_repo_dir=upstream, build_if_missing=True)
            results[aid] = {
                "score": g.score, "max_score": g.max_score, "invariant_passed": g.invariant_passed,
                "reason": g.reason_code,
                "vulns": [{"id": v.vulnerability_id, "passed": v.passed, "reason": v.reason_code}
                          for v in g.vulnerabilities],
                "secs": round(time.monotonic() - started),
            }
            if g.invariant_output_head:  # evidence when the patch broke the build
                results[aid]["invariant_output_head"] = g.invariant_output_head
            print(f"[{i}/22] {aid}: {g.score}/{g.max_score}  inv={g.invariant_passed}  ({results[aid]['secs']}s)", flush=True)
        except PatchWorkerError as e:
            results[aid] = {"score": 0, "max_score": len(audit.vulnerabilities),
                            "invariant_passed": None, "reason": f"grade-error: {str(e)[:200]}", "vulns": []}
            print(f"[{i}/22] {aid}: GRADE-ERROR {str(e)[:120]}", flush=True)
        results_path.write_text(json.dumps(results, indent=2))

    solved = sum(v["score"] for v in results.values())
    graded = sum(v["max_score"] for v in results.values())
    print(f"\n=== Phase 2 blind score: {solved}/{PATCH_VULN_COUNT} = {solved/PATCH_VULN_COUNT*100:.1f}% "
          f"(graded {len(results)}/22 audits, {graded} vulns) ===", flush=True)
    errs = [a for a, v in results.items() if v.get("reason", "").startswith("grade-error")]
    if errs:
        print(f"grade-errors (need retry): {errs}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
