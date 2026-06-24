#!/usr/bin/env python3
"""End-to-end Composer 2.5 Phase 2 Patch run: fetch sources → agent diffs → Docker grade.

Usage:
    .venv/bin/python scripts/run_composer_patch.py --smoke
    .venv/bin/python scripts/run_composer_patch.py --full
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.config import load_credentials  # noqa: E402
from openevmbench.constants import PATCH_SPLIT  # noqa: E402
from openevmbench.hashing import sha256_file  # noqa: E402
from openevmbench.package import AgentInfo, OperatorInfo, RunMeta  # noqa: E402
from openevmbench.runner import run_patch  # noqa: E402
from openevmbench.dataset import load_patch_dataset  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402

SMOKE = ("2023-07-pooltogether", "2023-10-nextgen")
SCAFFOLD = Path("agents/cursor_fleet/patch_auditor.py")
MODEL = "composer-2.5"


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true", help="2 audits only")
    group.add_argument("--full", action="store_true", help="all 22 patch audits")
    parser.add_argument("--sources", type=Path, default=REPO_ROOT / "audit_sources_patch")
    parser.add_argument("--diffs", type=Path, default=REPO_ROOT / "runs" / "composer-2.5-patch" / "diffs")
    parser.add_argument("--submissions", type=Path, default=REPO_ROOT / "submissions")
    parser.add_argument("--skip-agent", action="store_true", help="reuse existing diffs")
    parser.add_argument("--skip-grade", action="store_true", help="agent only, no packaging")
    parser.add_argument("--operator-user", default=os.environ.get("OPENEVMBENCH_OPERATOR_USER", ""))
    parser.add_argument("--operator-id", type=int, default=int(os.environ.get("OPENEVMBENCH_OPERATOR_ID", "0") or "0"))
    args = parser.parse_args()

    upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")
    only = ",".join(SMOKE) if args.smoke else ""

    if not args.skip_agent:
        fetch_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "fetch_audit_sources.py"),
            "--out",
            str(args.sources),
            "--split",
            PATCH_SPLIT,
        ]
        if only:
            fetch_cmd.extend(["--audits", only])
        _run(fetch_cmd)

        agent_cmd = [
            sys.executable,
            str(REPO_ROOT / "agents" / "cursor_fleet" / "patch_auditor.py"),
            "--sources",
            str(args.sources),
            "--out",
            str(args.diffs),
            "--model",
            MODEL,
        ]
        if only:
            agent_cmd.extend(["--only", only])
        _run(agent_cmd)

    if args.skip_grade:
        return 0

    creds = load_credentials()
    if creds is None:
        if not args.operator_user or not args.operator_id:
            print(
                "error: run `openevmbench login` or set "
                "--operator-user/--operator-id (or OPENEVMBENCH_OPERATOR_*)",
                file=sys.stderr,
            )
            return 1
        operator = OperatorInfo(
            github_username=args.operator_user,
            github_id=args.operator_id,
        )
    else:
        operator = OperatorInfo(
            github_username=creds.github_username,
            github_id=creds.github_id,
        )
    dataset = load_patch_dataset(upstream)
    started = time.monotonic()
    result = run_patch(
        dataset=dataset,
        agent_outputs_dir=args.diffs,
        sources_dir=None,
        upstream_repo_dir=upstream,
        operator=operator,
        agent=AgentInfo(
            model=MODEL,
            scaffold_name="cursor-fleet-patch-single-shot",
            scaffold_hash=sha256_file(REPO_ROOT / SCAFFOLD),
            harness_kind="single-shot",
            prompt_hash=sha256_file(REPO_ROOT / SCAFFOLD),
        ),
        run_meta=RunMeta(
            tokens_total=0,
            tokens_prompt=0,
            tokens_completion=0,
            tokens_per_task=[],
            wall_clock_ms=int((time.monotonic() - started) * 1000),
            runs_count=1,
        ),
        submissions_root=args.submissions,
        use_docker=True,
    )
    record = result.package.record
    pct = float(record["score"]["claimed_score"]) * 100
    solved = int(record["score"]["solved_count"])
    print(json.dumps({
        "package": str(result.package.package_dir),
        "score_pct": round(pct, 1),
        "solved": solved,
        "max_score": record["score"]["max_score"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
