#!/usr/bin/env python3
"""Package the blind-audit (paper-comparable) Codex run as the AntFleet Phase 2
reference submission, from already-graded results (no re-grade).

Builds submissions/phase2/antfleet-ops/<sid>/{record.json, agent_artifacts/*.diff}
with agent.params.task_mode = "blind-audit" so the row is comparable to the 41.5%
SOTA (not the retracted finding-fed 97.7%).

Usage:
    python scripts/package_blind_reference.py \
        --diffs runs/blind-patch/diffs --results /tmp/blind_grade2/results.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.dataset import load_patch_dataset  # noqa: E402
from openevmbench.hashing import sha256_file, sha256_prefixed  # noqa: E402
from openevmbench.package import (  # noqa: E402
    AgentInfo, OperatorInfo, PatchTaskResult, RunMeta,
    build_patch_submitted_record, deterministic_archive, new_submission_id, write_record,
)

SCAFFOLD = REPO_ROOT / "agents" / "cursor_fleet" / "patch_auditor_blind.py"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diffs", type=Path, default=REPO_ROOT / "runs" / "blind-patch" / "diffs")
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "submissions")
    ap.add_argument("--created-at", required=True, help="RFC3339 UTC, e.g. 2026-07-08T00:00:00Z")
    ap.add_argument("--upstream", type=Path, default=REPO_ROOT / "upstream" / "frontier-evals")
    args = ap.parse_args()

    dataset = load_patch_dataset(args.upstream)
    graded = json.loads(args.results.read_text())

    # Per-vuln pass map from the graded results (audits that errored / failed
    # invariant contribute all-False for their vulns).
    passed_by_vid: dict[str, tuple[bool, str]] = {}
    for audit in dataset.audits:
        g = graded.get(audit.audit_id, {})
        vmap = {v["id"]: v for v in g.get("vulns", [])}
        audit_reason = str(g.get("reason") or "")
        for vuln in audit.vulnerabilities:
            vid = vuln.vulnerability_id
            if vid in vmap:
                passed_by_vid[vid] = (bool(vmap[vid]["passed"]), str(vmap[vid].get("reason", "")))
            else:
                # audit-level 0 (invariant-failed / unparseable / grade-error / build-fail)
                passed_by_vid[vid] = (False, audit_reason or "not-patched")

    results = [
        PatchTaskResult(
            vulnerability_id=vid,
            passed=passed,
            score=1 if passed else 0,
            reason_code=("patched" if passed else (reason or "not-patched"))[:64],
        )
        for vid, (passed, reason) in ((v.vulnerability_id, passed_by_vid[v.vulnerability_id])
                                      for a in dataset.audits for v in a.vulnerabilities)
    ]
    solved = sum(1 for r in results if r.passed)
    assert len(results) == 44, f"expected 44 vulns, got {len(results)}"

    sid = new_submission_id()
    pkg_dir = args.out / "phase2" / "antfleet-ops" / sid
    artifacts = pkg_dir / "agent_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for audit in dataset.audits:
        src = args.diffs / f"{audit.audit_id}.diff"
        if src.is_file():
            shutil.copy2(src, artifacts / f"{audit.audit_id}.diff")

    archive = deterministic_archive(artifacts)
    scaffold_hash = sha256_file(SCAFFOLD)

    record = build_patch_submitted_record(
        submission_id=sid,
        created_at=args.created_at,
        operator=OperatorInfo(github_username="antfleet-ops", github_id=285575208,
                              affiliation="AntFleet (reference)"),
        agent=AgentInfo(
            model="gpt-5.5",
            scaffold_name="cursor-fleet-patch-blind",
            scaffold_hash=scaffold_hash,
            harness_kind="single-shot",
            params={"reasoning_effort": "high", "task_mode": "blind-audit",
                    "engine": "codex-subscription"},
            prompt_hash=scaffold_hash,
        ),
        run=RunMeta(tokens_total=0, tokens_prompt=0, tokens_completion=0,
                    tokens_per_task=[], wall_clock_ms=0, runs_count=1),
        results=results,
        archive_hash=sha256_prefixed(archive),
        archive_size_bytes=len(archive),
    )
    write_record(record, pkg_dir / "record.json")

    print(f"submission_id: {sid}")
    print(f"package: {pkg_dir}")
    print(f"score: {solved}/44 = {solved/44*100:.1f}%  task_mode=blind-audit")
    print(f"diffs: {len(list(artifacts.glob('*.diff')))}/22")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
