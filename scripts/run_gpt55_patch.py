#!/usr/bin/env python3
"""End-to-end GPT-5.5 Phase 2 Patch run.

Fetches the pinned Patch sources, runs one ``codex exec`` patch attempt per
audit, exports ``<audit-id>.diff`` files, then packages them through the normal
Docker-backed Phase 2 submission path.

Usage:
    python scripts/run_gpt55_patch.py --smoke --skip-grade
    python scripts/run_gpt55_patch.py --full
    python scripts/run_gpt55_patch.py --full --skip-agent --diffs runs/gpt-5.5-patch/diffs
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.cursor_fleet.patch_auditor import build_prompt, export_diff  # noqa: E402
from openevmbench.config import load_credentials  # noqa: E402
from openevmbench.constants import PATCH_SPLIT, UPSTREAM_SUBDIR  # noqa: E402
from openevmbench.dataset import load_patch_audit, load_patch_dataset  # noqa: E402
from openevmbench.hashing import sha256_file  # noqa: E402
from openevmbench.package import AgentInfo, OperatorInfo, RunMeta  # noqa: E402
from openevmbench.runner import run_patch  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402


SMOKE_AUDITS = ("2023-07-pooltogether", "2023-10-nextgen")
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_REASONING_EFFORT = "high"
SCAFFOLD_NAME = "codex-gpt55-patch-single-shot"
SCAFFOLD = Path("scripts/run_gpt55_patch.py")
MAX_CODEX_STDIN_CHARS = 900_000

SPILL_PROMPT = """\
You are running an Open EVMBench Phase 2 Patch task.

Read _patch_prompt.txt in this workspace. It lists the vulnerabilities, mapped
production files, and source context. Edit the listed production files in place
to fix the vulnerabilities. Do not create audit reports, do not commit changes,
and do not modify files outside the mapped production patch paths.
"""

CODEX_STRIP_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION",
    "AZURE_OPENAI_API_KEY",
)


@dataclass(frozen=True)
class CodexPatchConfig:
    binary: str
    model: str
    reasoning_effort: str
    timeout_s: float
    max_retries: int
    retry_delay_s: float


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd or REPO_ROOT, check=True)


def _scrub_codex_env(env: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(os.environ if env is None else env)
    for key in CODEX_STRIP_ENV:
        out.pop(key, None)
    return out


def _codex_cmd(cfg: CodexPatchConfig, workspace: Path) -> list[str]:
    cmd = [
        cfg.binary,
        "exec",
        "--model",
        cfg.model,
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--ephemeral",
        "-C",
        str(workspace),
        "-c",
        'developer_instructions=""',
    ]
    if cfg.reasoning_effort:
        cmd.extend(["-c", f"model_reasoning_effort={cfg.reasoning_effort}"])
    cmd.append("-")
    return cmd


def _run_codex(cfg: CodexPatchConfig, workspace: Path, prompt: str, log_path: Path) -> None:
    cmd = _codex_cmd(cfg, workspace)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    last_err = ""
    for attempt in range(1, cfg.max_retries + 1):
        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                cwd=workspace,
                env=_scrub_codex_env(),
                capture_output=True,
                text=True,
                timeout=cfg.timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            last_err = f"timeout after {cfg.timeout_s}s"
            log_path.write_text(
                json.dumps({"attempt": attempt, "error": last_err}) + "\n",
                encoding="utf-8",
            )
            if attempt < cfg.max_retries:
                time.sleep(cfg.retry_delay_s)
                continue
            raise RuntimeError(last_err) from e

        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_path.write_text(
            json.dumps(
                {
                    "attempt": attempt,
                    "returncode": proc.returncode,
                    "elapsed_ms": elapsed_ms,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if proc.returncode == 0:
            return
        last_err = (proc.stderr or proc.stdout or "").strip()[:2000]
        if attempt < cfg.max_retries:
            time.sleep(cfg.retry_delay_s)
    raise RuntimeError(f"codex failed ({proc.returncode}): {last_err}")


def _prepare_codex_prompt(workspace: Path, prompt: str) -> str:
    if len(prompt) <= MAX_CODEX_STDIN_CHARS:
        return prompt
    (workspace / "_patch_prompt.txt").write_text(prompt, encoding="utf-8")
    return SPILL_PROMPT


def _fetch_sources(sources: Path, only: str) -> None:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "fetch_audit_sources.py"),
        "--out",
        str(sources),
        "--split",
        PATCH_SPLIT,
    ]
    if only:
        cmd.extend(["--audits", only])
    _run(cmd)


def _audit_ids(upstream: Path, *, only: str) -> list[str]:
    evmbench_root = upstream / UPSTREAM_SUBDIR
    split_path = evmbench_root / "splits" / f"{PATCH_SPLIT}.txt"
    audit_ids = split_path.read_text(encoding="utf-8").split()
    if only:
        wanted = set(only.split(","))
        audit_ids = [a for a in audit_ids if a in wanted]
    return audit_ids


def _run_audit(
    *,
    audit_id: str,
    sources_root: Path,
    upstream: Path,
    out_dir: Path,
    workspace_root: Path,
    logs_dir: Path,
    cfg: CodexPatchConfig,
) -> Path:
    sources = sources_root / audit_id
    if not (sources / ".git").is_dir():
        raise FileNotFoundError(f"missing sources: {sources}")

    workspace = workspace_root / audit_id
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(sources, workspace, symlinks=True)

    audit = load_patch_audit(upstream, audit_id)
    prompt = build_prompt(
        audit=audit,
        sources=sources,
        upstream_root=upstream / UPSTREAM_SUBDIR,
    )
    prompt += (
        "\n\n# Execution constraints\n"
        "- Edit only the mapped production files in this workspace.\n"
        "- Do not commit changes or create reports.\n"
        "- Finish once the source files are patched.\n"
    )
    _run_codex(
        cfg,
        workspace,
        _prepare_codex_prompt(workspace, prompt),
        logs_dir / f"{audit_id}.jsonl",
    )

    out_path = out_dir / f"{audit_id}.diff"
    export_diff(workspace=workspace, audit=audit, out_path=out_path)
    return out_path


def _operator_from_args(args: argparse.Namespace) -> OperatorInfo | None:
    creds = load_credentials()
    if creds is not None:
        return OperatorInfo(github_username=creds.github_username, github_id=creds.github_id)
    if args.operator_user and args.operator_id:
        return OperatorInfo(github_username=args.operator_user, github_id=args.operator_id)
    return None


def _package(args: argparse.Namespace, upstream: Path, started: float) -> int:
    operator = _operator_from_args(args)
    if operator is None:
        print(
            "error: run `openevmbench login` or set --operator-user/--operator-id "
            "(or OPENEVMBENCH_OPERATOR_*)",
            file=sys.stderr,
        )
        return 1

    dataset = load_patch_dataset(upstream)
    result = run_patch(
        dataset=dataset,
        agent_outputs_dir=args.diffs,
        sources_dir=None,
        upstream_repo_dir=upstream,
        operator=operator,
        agent=AgentInfo(
            model=args.model,
            scaffold_name=SCAFFOLD_NAME,
            scaffold_hash=sha256_file(REPO_ROOT / SCAFFOLD),
            harness_kind="single-shot",
            params={"reasoning_effort": args.reasoning_effort} if args.reasoning_effort else None,
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
    solved = int(record["score"]["solved_count"])
    max_score = int(record["score"]["max_score"])
    pct = float(record["score"]["claimed_score"]) * 100
    print(
        json.dumps(
            {
                "package": str(result.package.package_dir),
                "score_pct": round(pct, 1),
                "solved": solved,
                "max_score": max_score,
                "next": f"openevmbench submit --package {result.package.package_dir}",
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true", help="run 2 audits only")
    group.add_argument("--full", action="store_true", help="run all 22 patch audits")
    parser.add_argument("--only", default="", help="comma-separated audit IDs; overrides --smoke")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--reasoning-effort", default=DEFAULT_REASONING_EFFORT)
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=10.0)
    parser.add_argument("--sources", type=Path, default=REPO_ROOT / "audit_sources_gpt55_patch")
    parser.add_argument("--diffs", type=Path, default=REPO_ROOT / "runs" / "gpt-5.5-patch" / "diffs")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "runs" / "gpt-5.5-patch" / "logs")
    parser.add_argument("--workspace-root", type=Path, default=REPO_ROOT / "runs" / "gpt-5.5-patch" / "workspaces")
    parser.add_argument("--submissions", type=Path, default=REPO_ROOT / "submissions")
    parser.add_argument("--upstream", type=Path, default=REPO_ROOT / "upstream" / "frontier-evals")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument("--skip-agent", action="store_true", help="reuse existing diffs")
    parser.add_argument("--skip-grade", action="store_true", help="generate diffs only; do not package")
    parser.add_argument("--operator-user", default=os.environ.get("OPENEVMBENCH_OPERATOR_USER", ""))
    parser.add_argument(
        "--operator-id",
        type=int,
        default=int(os.environ.get("OPENEVMBENCH_OPERATOR_ID", "0") or "0"),
    )
    args = parser.parse_args()

    started = time.monotonic()
    upstream = ensure_upstream(args.upstream)
    only = args.only or (",".join(SMOKE_AUDITS) if args.smoke else "")

    if not args.skip_agent:
        if not args.skip_fetch:
            _fetch_sources(args.sources, only)
        cfg = CodexPatchConfig(
            binary=args.codex_binary,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_s=args.timeout,
            max_retries=args.max_retries,
            retry_delay_s=args.retry_delay,
        )
        failures: list[str] = []
        for audit_id in _audit_ids(upstream, only=only):
            print(f"patch {audit_id} with {args.model}...", flush=True)
            try:
                out_path = _run_audit(
                    audit_id=audit_id,
                    sources_root=args.sources,
                    upstream=upstream,
                    out_dir=args.diffs,
                    workspace_root=args.workspace_root,
                    logs_dir=args.logs,
                    cfg=cfg,
                )
                print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)", flush=True)
            except Exception as e:
                failures.append(f"{audit_id}: {e}")
                print(f"  FAIL {e}", file=sys.stderr, flush=True)
        if failures:
            print(f"\n{len(failures)} audit(s) failed", file=sys.stderr)
            return 1

    if args.skip_grade:
        print(f"diffs: {args.diffs}")
        print(f"logs: {args.logs}")
        return 0

    return _package(args, upstream, started)


if __name__ == "__main__":
    raise SystemExit(main())
