#!/usr/bin/env python3
"""Build upstream gold patch diffs for every audit in the patch-tasks split.

Writes ``<out>/<audit-id>.diff`` unified diffs (same shape agents submit).
Used for harness spikes and AntFleet Patch reference packaging.

Usage:
    .venv/bin/python scripts/build_gold_patch_diffs.py --out runs/gold_patch_diffs
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench import constants  # noqa: E402
from openevmbench.dataset import PatchAudit, load_patch_dataset  # noqa: E402
from openevmbench.patch_worker import PatchWorkerError  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402


def _run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=False)
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[:500]
        raise PatchWorkerError(f"{' '.join(cmd)} failed ({proc.returncode}): {err}")
    return proc


def _patch_files(audit: PatchAudit, upstream_root: Path) -> dict[str, Path]:
    """Return repo-relative dest path -> upstream patch file."""
    audit_dir = upstream_root / "audits" / audit.audit_id
    mapping: dict[str, Path] = {}
    for vuln in audit.vulnerabilities:
        for local_rel, repo_rel in vuln.patch_path_mapping.items():
            src = audit_dir / local_rel
            if not src.is_file():
                raise PatchWorkerError(f"missing patch file {src} for {vuln.vulnerability_id}")
            mapping[repo_rel] = src
    return mapping


def build_gold_diff(
    audit: PatchAudit,
    *,
    upstream_repo_dir: Path,
    out_path: Path,
) -> None:
    upstream_root = upstream_repo_dir / constants.UPSTREAM_SUBDIR
    patch_files = _patch_files(audit, upstream_root)
    repo_paths = sorted(patch_files)

    with tempfile.TemporaryDirectory(prefix=f"gold-{audit.audit_id}-") as tmp:
        repo = Path(tmp) / "repo"
        clone = subprocess.run(
            ["git", "clone", "--quiet", f"https://github.com/evmbench-org/{audit.audit_id}.git", str(repo)],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            raise PatchWorkerError(f"clone {audit.audit_id} failed: {clone.stderr[:300]}")
        _run(["git", "checkout", "-q", audit.base_commit], cwd=repo)
        for repo_rel, src in patch_files.items():
            dest = repo / repo_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            _run(["git", "add", repo_rel], cwd=repo)
        diff = subprocess.run(
            ["git", "-c", "core.fileMode=false", "diff", "--binary", "--cached", *repo_paths],
            cwd=repo,
            capture_output=True,
        )
        if diff.returncode != 0:
            raise PatchWorkerError(f"git diff failed for {audit.audit_id}: {diff.stderr.decode()[:300]}")
        if not diff.stdout.strip():
            raise PatchWorkerError(f"empty diff for {audit.audit_id}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(diff.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Output directory for *.diff files")
    parser.add_argument("--audit", action="append", help="Build only these audit IDs (default: all)")
    args = parser.parse_args()

    upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")
    dataset = load_patch_dataset(upstream)
    audits = dataset.audits
    if args.audit:
        wanted = set(args.audit)
        audits = tuple(a for a in audits if a.audit_id in wanted)
        missing = wanted - {a.audit_id for a in audits}
        if missing:
            raise SystemExit(f"unknown audit id(s): {', '.join(sorted(missing))}")

    for audit in audits:
        out = args.out / f"{audit.audit_id}.diff"
        print(f"building {audit.audit_id} → {out}")
        build_gold_diff(audit, upstream_repo_dir=upstream, out_path=out)
        print(f"  {out.stat().st_size} bytes")

    print(f"done: {len(audits)} diffs in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
