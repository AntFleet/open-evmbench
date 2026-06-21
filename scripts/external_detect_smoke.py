"""External Detect smoke — cold docs/SUBMITTING.md path for a non-AntFleet operator.

Validates that someone outside AntFleet can follow the public submitter guide
without internal tooling: login → clone → run → PR checks. Uses the single-audit
dry-run artifact in agent_outputs_dryrun/ (2023-07-pooltogether).

Judge mode (SUBMITTING.md step 4):
  - Default: deterministic marker judge (no API spend) — exercises packaging +
    check_package with real GitHub identity binding.
  - Optional --real-judge: gpt-5 reasoning_effort=high on 2 vulns (needs OPENAI_API_KEY).

Operator identity defaults to gh auth for Augustas11 (non-AntFleet). Override with
EXTERNAL_SMOKE_GH_USER if needed.

Usage:
    .venv/bin/python scripts/external_detect_smoke.py
    .venv/bin/python scripts/external_detect_smoke.py --real-judge

Writes docs/external_detect_smoke_report.json on success.
Exit 0 = pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.checks import check_package  # noqa: E402
from openevmbench.dataset import load_detect_dataset  # noqa: E402
from openevmbench.hashing import sha256_file  # noqa: E402
from openevmbench.judge import OpenAICompatibleJudgeClient, load_pinned_prompt  # noqa: E402
from openevmbench.package import AgentInfo, JudgeInfo, OperatorInfo, RunMeta  # noqa: E402
from openevmbench.runner import run_detect  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402

DRYRUN_AUDIT = "2023-07-pooltogether"
DRYRUN_OUTPUTS = REPO_ROOT / "agent_outputs_dryrun"
REPORT_PATH = REPO_ROOT / "docs" / "external_detect_smoke_report.json"
ANTFLEET_HANDLES = frozenset({"antfleet", "antfleetdev", "antfleet-ops"})


@dataclass
class StepResult:
    step: str
    ok: bool
    detail: str


def _marker(text: str) -> str:
    return "MARKER-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class MarkerJudge:
    def complete(self, system: str, user: str) -> str:
        audit, vuln = user.split("\n\nVulnerability description:\n", 1)
        detected = _marker(vuln) in audit
        return json.dumps({"detected": detected, "reasoning": "external-smoke-marker"})


def _gh_user(login: str) -> tuple[str, int, str]:
    token_proc = subprocess.run(
        ["gh", "auth", "token", "-u", login],
        capture_output=True,
        text=True,
        check=False,
    )
    if token_proc.returncode != 0:
        raise RuntimeError(f"gh auth token for {login!r} failed: {token_proc.stderr.strip()}")
    token = token_proc.stdout.strip()
    user_proc = subprocess.run(
        ["gh", "api", "user", "-H", f"Authorization: token {token}"],
        capture_output=True,
        text=True,
        check=True,
    )
    user = json.loads(user_proc.stdout)
    return user["login"], int(user["id"]), token


def _resolve_external_operator(preferred: str | None) -> tuple[str, int, str]:
    login = preferred or os.environ.get("EXTERNAL_SMOKE_GH_USER", "Augustas11")
    handle, gid, token = _gh_user(login)
    if handle.lower() in ANTFLEET_HANDLES:
        raise RuntimeError(
            f"operator @{handle} is AntFleet-internal; external smoke requires a non-AntFleet account"
        )
    return handle, gid, token


def step_login(creds_home: Path, token: str, handle: str, gid: int) -> StepResult:
    creds_home.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "openevmbench.cli", "login", token],
        capture_output=True,
        text=True,
        env={**os.environ, "OPENEVMBENCH_HOME": str(creds_home)},
    )
    if proc.returncode != 0:
        return StepResult("login", False, proc.stderr.strip() or proc.stdout.strip())
    return StepResult("login", True, proc.stdout.strip())


def step_clone() -> StepResult:
    proc = subprocess.run(
        [sys.executable, "-m", "openevmbench.cli", "clone"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        return StepResult("clone", False, proc.stderr.strip() or proc.stdout.strip())
    return StepResult("clone", True, proc.stdout.strip())


def step_run_marker(
    handle: str,
    gid: int,
    submissions_root: Path,
) -> tuple[StepResult, Path | None]:
    if not (DRYRUN_OUTPUTS / DRYRUN_AUDIT / "audit.md").is_file():
        return (
            StepResult(
                "run",
                False,
                f"missing {DRYRUN_OUTPUTS / DRYRUN_AUDIT / 'audit.md'} — fetch dry-run audit output first",
            ),
            None,
        )

    upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")
    ds = load_detect_dataset(upstream)

    # Marker outputs: embed markers for pooltogether vulns only (2 tasks).
    marker_outputs = submissions_root.parent / "agent_outputs_marker"
    audit = next(a for a in ds.audits if a.audit_id == DRYRUN_AUDIT)
    lines = []
    for v in audit.vulnerabilities:
        lines.append(_marker(v.text_content()))
    out_path = marker_outputs / DRYRUN_AUDIT / "audit.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    scaffold_hash = sha256_file(REPO_ROOT / "harness" / "judge_prompt_v1.md")
    result = run_detect(
        dataset=ds,
        agent_outputs_dir=marker_outputs,
        harness_dir=REPO_ROOT / "harness",
        judge_client=MarkerJudge(),
        judge_info=JudgeInfo(model="external-smoke-marker", params={"deterministic": True}),
        operator=OperatorInfo(github_username=handle, github_id=gid),
        agent=AgentInfo(
            model="external-smoke-agent",
            scaffold_name="external-smoke-scaffold",
            scaffold_hash=scaffold_hash,
            harness_kind="single-shot",
        ),
        run_meta=RunMeta(
            tokens_total=100,
            tokens_prompt=80,
            tokens_completion=20,
            tokens_per_task=[],
            wall_clock_ms=1000,
        ),
        submissions_root=submissions_root,
    )
    if result.solved_count != 2:
        return (
            StepResult(
                "run",
                False,
                f"expected 2/117 solved on {DRYRUN_AUDIT}, got {result.solved_count}",
            ),
            None,
        )
    op = result.package.record["operator"]
    if op["github_username"] != handle or op["github_id"] != gid:
        return (
            StepResult(
                "run",
                False,
                f"operator mismatch in record: {op}",
            ),
            None,
        )
    rel = result.package.package_dir.relative_to(submissions_root.parent)
    return (
        StepResult(
            "run",
            True,
            f"package {rel} — {result.solved_count}/117 ({result.package.record['submission_id']})",
        ),
        result.package.package_dir,
    )


def step_run_real_judge(
    handle: str,
    gid: int,
    creds_home: Path,
    submissions_root: Path,
) -> tuple[StepResult, Path | None]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return StepResult("run", False, "OPENAI_API_KEY unset (use default marker mode)"), None
    if not (DRYRUN_OUTPUTS / DRYRUN_AUDIT / "audit.md").is_file():
        return StepResult("run", False, f"missing {DRYRUN_OUTPUTS}"), None

    scaffold_hash = sha256_file(REPO_ROOT / "agents/antfleet_reference/consensus_agent.py")
    out_root = submissions_root.parent
    cmd = [
        sys.executable,
        "-m",
        "openevmbench.cli",
        "run",
        "--agent-outputs",
        str(DRYRUN_OUTPUTS),
        "--judge-model",
        "gpt-5",
        "--judge-param",
        "reasoning_effort=high",
        "--api-key-env",
        "OPENAI_API_KEY",
        "--model",
        "external-smoke-consensus",
        "--scaffold-name",
        "external-smoke-scaffold",
        "--scaffold-hash",
        scaffold_hash,
        "--harness-kind",
        "single-shot",
        "--tokens-total",
        "1000",
        "--tokens-prompt",
        "800",
        "--tokens-completion",
        "200",
        "--out",
        str(out_root),
    ]
    env = {**os.environ, "OPENEVMBENCH_HOME": str(creds_home)}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=REPO_ROOT)
    if proc.returncode != 0:
        return StepResult("run", False, (proc.stderr or proc.stdout)[-500:]), None
    pkg_line = next((l for l in proc.stdout.splitlines() if l.startswith("package:")), "")
    if not pkg_line:
        return StepResult("run", False, "CLI did not print package path"), None
    package_dir = Path(pkg_line.split("package:", 1)[1].strip())
    record = json.loads((package_dir / "record.json").read_text(encoding="utf-8"))
    if record["operator"]["github_username"] != handle:
        return StepResult("run", False, f"operator {record['operator']}"), None
    if record["score"]["solved_count"] != 2:
        return (
            StepResult(
                "run",
                False,
                f"expected 2/117, got {record['score']['solved_count']}",
            ),
            None,
        )
    return StepResult("run", True, f"real judge — {pkg_line}"), package_dir


def step_check_pr(
    repo_root: Path,
    package_dir: Path,
    handle: str,
    gid: int,
) -> StepResult:
    package_rel = package_dir.relative_to(repo_root).as_posix()
    ds = load_detect_dataset(repo_root / "upstream" / "frontier-evals")
    report = check_package(
        repo_root=repo_root,
        package_rel=package_rel,
        pr_author=handle,
        pr_author_id=gid,
        dataset=ds,
    )
    if not report.ok:
        detail = "; ".join(f"{f.code}: {f.detail}" for f in report.failures[:5])
        return StepResult("check-pr", False, detail)
    return StepResult(
        "check-pr",
        True,
        f"all checks pass ({len(report.warnings)} warnings)",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real-judge",
        action="store_true",
        help="use gpt-5 judge on dry-run audit (needs OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--gh-user",
        default=None,
        help="non-AntFleet GitHub login (default: Augustas11)",
    )
    args = parser.parse_args()

    try:
        handle, gid, token = _resolve_external_operator(args.gh_user)
    except Exception as e:
        print(f"EXTERNAL DETECT SMOKE FAILED: operator resolution: {e}", file=sys.stderr)
        return 1

    print(f"external operator: @{handle} (id {gid})")
    steps: list[StepResult] = []
    tmp = Path(tempfile.mkdtemp(prefix="evmb-ext-smoke-"))
    creds_home = tmp / "creds"
    submissions_root = tmp / "submissions"
    submissions_root.mkdir(parents=True)

    try:
        r = step_login(creds_home, token, handle, gid)
        steps.append(r)
        print(f"[login] {'OK' if r.ok else 'FAIL'}: {r.detail}")
        if not r.ok:
            return 1

        r = step_clone()
        steps.append(r)
        print(f"[clone] {'OK' if r.ok else 'FAIL'}: {r.detail}")
        if not r.ok:
            return 1

        if args.real_judge:
            run_step, package_dir = step_run_real_judge(handle, gid, creds_home, submissions_root)
        else:
            run_step, package_dir = step_run_marker(handle, gid, submissions_root)
        steps.append(run_step)
        print(f"[run] {'OK' if run_step.ok else 'FAIL'}: {run_step.detail}")
        if not run_step.ok or package_dir is None:
            return 1

        # check_package expects repo_root layout; copy package under repo-like tree.
        rel = package_dir.relative_to(tmp)
        dest = REPO_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(package_dir, dest)
        try:
            r = step_check_pr(REPO_ROOT, dest, handle, gid)
        finally:
            shutil.rmtree(dest, ignore_errors=True)
            handle_dir = dest.parent
            if handle_dir.is_dir() and not any(handle_dir.iterdir()):
                handle_dir.rmdir()

        steps.append(r)
        print(f"[check-pr] {'OK' if r.ok else 'FAIL'}: {r.detail}")
        if not r.ok:
            return 1

        report = {
            "status": "pass",
            "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "operator": {"github_username": handle, "github_id": gid},
            "judge_mode": "real" if args.real_judge else "marker",
            "dryrun_audit": DRYRUN_AUDIT,
            "expected_score": "2/117",
            "guide": "docs/SUBMITTING.md",
            "steps": [asdict(s) for s in steps],
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"\nEXTERNAL DETECT SMOKE PASSED — report written to {REPORT_PATH.relative_to(REPO_ROOT)}")
        return 0
    except Exception as e:
        print(f"\nEXTERNAL DETECT SMOKE FAILED: {e}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
