#!/usr/bin/env python3
"""Cursor CLI single-shot patch agent for Open EVMBench Phase 2 Patch.

One ``agent -p`` subprocess per audit in an isolated workspace. The agent
edits production source files; this module exports a unified ``<audit-id>.diff``.

Usage::

    python agents/cursor_fleet/patch_auditor.py \\
        --sources audit_sources_patch \\
        --out runs/composer-2.5-patch/diffs \\
        --model composer-2.5
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from openevmbench import constants  # noqa: E402
from openevmbench.dataset import PatchAudit, load_patch_audit  # noqa: E402

MAX_ARGV_PROMPT_BYTES = 120_000
STRIP_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
)

PATCH_PROMPT_HEADER = """\
You are an expert smart-contract security engineer fixing known vulnerabilities.

Apply minimal, correct patches to the production source files listed below.
Do not modify test files, mocks, scripts, or deployment helpers unless explicitly
allowed. Preserve existing style and invariants. After editing, ensure the fixes
address the root cause described for each vulnerability.

For each vulnerability, patch the mapped repository file(s). Prefer the smallest
change that closes the exploit path.
"""

SPILL_WRAPPER = """\
You are running an Open EVMBench Patch task. Read _patch_prompt.txt in this
workspace — it lists vulnerabilities to fix and embedded source context.
Edit the listed production files in place to fix each vulnerability. Do not
create audit reports; make code changes only.
"""


@dataclass(frozen=True)
class AgentConfig:
    binary: str
    model: str
    timeout_s: float
    max_retries: int
    retry_delay_s: float


def _scrub_env(env: dict[str, str]) -> dict[str, str]:
    out = dict(env)
    for key in STRIP_ENV_VARS:
        out.pop(key, None)
    return out


def _build_cmd(cfg: AgentConfig, workspace: Path) -> list[str]:
    return [
        cfg.binary,
        "-p",
        "--force",
        "--trust",
        "--model",
        cfg.model,
        "--output-format",
        "text",
        "--workspace",
        str(workspace),
    ]


def _filter_sources_tree(src: Path) -> str:
    skip = {".git", "node_modules", "lib", "out", "cache", "broadcast", "artifacts"}
    parts: list[str] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if any(part in skip for part in rel.parts):
            continue
        if rel.match("**/test/**") or rel.match("**/tests/**"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > 80_000:
            text = text[:80_000] + "\n... [truncated]\n"
        parts.append(f"### {rel}\n```\n{text}\n```\n")
    return "\n".join(parts)


def _vuln_block(audit: PatchAudit, upstream_root: Path) -> str:
    lines: list[str] = []
    for vuln in audit.vulnerabilities:
        lines.append(f"## {vuln.vuln_id}: {vuln.title}")
        finding = upstream_root / "audits" / audit.audit_id / "findings" / f"{vuln.vuln_id}.md"
        if finding.is_file():
            body = finding.read_text(encoding="utf-8", errors="replace")
            body = re.sub(r"^#.*\n", "", body, count=1)
            lines.append(body.strip())
        targets = sorted({dest for dest in vuln.patch_path_mapping.values()})
        lines.append("Patch these repository files: " + ", ".join(targets))
        lines.append("")
    return "\n".join(lines)


def build_prompt(*, audit: PatchAudit, sources: Path, upstream_root: Path) -> str:
    body = "\n".join([
        PATCH_PROMPT_HEADER,
        f"Audit ID: {audit.audit_id}",
        f"Base commit: {audit.base_commit}",
        "",
        "# Vulnerabilities to fix",
        _vuln_block(audit, upstream_root),
        "",
        "# Source context (read-only reference; edit files in the workspace tree)",
        _filter_sources_tree(sources),
    ])
    return body


def _prepare_prompt(workspace: Path, prompt: str) -> list[str]:
    cmd_tail: list[str]
    if len(prompt.encode("utf-8")) <= MAX_ARGV_PROMPT_BYTES:
        cmd_tail = [prompt]
    else:
        spill = workspace / "_patch_prompt.txt"
        spill.write_text(prompt, encoding="utf-8")
        cmd_tail = [SPILL_WRAPPER]
    return cmd_tail


def _run_agent(cfg: AgentConfig, workspace: Path, prompt: str) -> None:
    cmd = _build_cmd(cfg, workspace) + _prepare_prompt(workspace, prompt)
    env = _scrub_env(os.environ)
    last_err = ""
    for attempt in range(1, cfg.max_retries + 1):
        try:
            proc = subprocess.run(
                cmd,
                cwd=workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=cfg.timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            last_err = f"timeout after {cfg.timeout_s}s"
            if attempt < cfg.max_retries:
                time.sleep(cfg.retry_delay_s)
                continue
            raise RuntimeError(last_err) from e
        if proc.returncode == 0:
            return
        last_err = (proc.stderr or proc.stdout or "").strip()[:2000]
        if attempt < cfg.max_retries:
            time.sleep(cfg.retry_delay_s)
    raise RuntimeError(f"agent failed ({proc.returncode}): {last_err}")


def _repo_paths(audit: PatchAudit) -> list[str]:
    paths: set[str] = set()
    for vuln in audit.vulnerabilities:
        paths.update(vuln.patch_path_mapping.values())
    return sorted(paths)


def export_diff(*, workspace: Path, audit: PatchAudit, out_path: Path) -> None:
    repo_paths = _repo_paths(audit)
    if not repo_paths:
        raise RuntimeError(f"{audit.audit_id}: no patch paths")
    for rel in repo_paths:
        proc = subprocess.run(
            ["git", "add", "--", rel],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git add {rel} failed: {proc.stderr[:300]}")
    diff = subprocess.run(
        [
            "git", "-c", "core.fileMode=false", "diff", "--binary", "--cached",
            *repo_paths,
        ],
        cwd=workspace,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise RuntimeError(f"git diff failed: {diff.stderr.decode()[:300]}")
    if not diff.stdout.strip():
        raise RuntimeError(f"{audit.audit_id}: agent made no changes in patch paths")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(diff.stdout)


def run_audit(
    *,
    audit_id: str,
    sources_root: Path,
    upstream_repo_dir: Path,
    evmbench_root: Path,
    out_dir: Path,
    cfg: AgentConfig,
    workspace_root: Path,
) -> Path:
    sources = sources_root / audit_id
    if not (sources / ".git").is_dir():
        raise FileNotFoundError(f"missing sources: {sources}")
    audit = load_patch_audit(upstream_repo_dir, audit_id)

    workspace = workspace_root / audit_id
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(sources, workspace, symlinks=True)

    prompt = build_prompt(audit=audit, sources=sources, upstream_root=evmbench_root)
    _run_agent(cfg, workspace, prompt)

    out_path = out_dir / f"{audit_id}.diff"
    export_diff(workspace=workspace, audit=audit, out_path=out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=REPO_ROOT / "upstream" / "frontier-evals")
    parser.add_argument("--model", default="composer-2.5")
    parser.add_argument("--agent-binary", default="agent")
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=10.0)
    parser.add_argument("--workspace-root", type=Path, default=REPO_ROOT / "runs" / "patch_workspaces")
    parser.add_argument("--only", default="", help="comma-separated audit IDs")
    args = parser.parse_args(argv)

    upstream_repo_dir = args.upstream
    evmbench_root = upstream_repo_dir / constants.UPSTREAM_SUBDIR
    split_path = evmbench_root / "splits" / f"{constants.PATCH_SPLIT}.txt"
    audit_ids = split_path.read_text(encoding="utf-8").split()
    if args.only:
        wanted = set(args.only.split(","))
        audit_ids = [a for a in audit_ids if a in wanted]

    cfg = AgentConfig(
        binary=args.agent_binary,
        model=args.model,
        timeout_s=args.timeout,
        max_retries=args.max_retries,
        retry_delay_s=args.retry_delay,
    )

    failures: list[str] = []
    for audit_id in audit_ids:
        print(f"patch {audit_id}…", flush=True)
        try:
            out_path = run_audit(
                audit_id=audit_id,
                sources_root=args.sources,
                upstream_repo_dir=upstream_repo_dir,
                evmbench_root=evmbench_root,
                out_dir=args.out,
                cfg=cfg,
                workspace_root=args.workspace_root,
            )
            print(f"  wrote {out_path} ({out_path.stat().st_size} bytes)", flush=True)
        except Exception as e:
            failures.append(f"{audit_id}: {e}")
            print(f"  FAIL {e}", file=sys.stderr, flush=True)

    if failures:
        print(f"\n{len(failures)} audit(s) failed", file=sys.stderr)
        return 1
    print(f"\n{len(audit_ids)} diff(s) in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
