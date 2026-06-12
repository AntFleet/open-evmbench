"""Fetch the audited contract source trees for agent runs (reference dry-run).

The upstream benchmark builds each audit's Docker image by cloning a frozen
mirror at github.com/evmbench-org/<audit-id> (verified for all 40 Detect
audits at the pinned upstream commit). 23 of 40 audit configs also carry a
`base_commit`; when present we check it out, otherwise mirror HEAD is the
snapshot (matching the upstream Dockerfiles, which clone HEAD).

Writes <out>/<audit-id>/ source trees plus <out>/sources_manifest.json
recording the exact commit fetched per audit, so an agent run's inputs are
reproducible and citable in the submission.

Usage:
    .venv/bin/python scripts/fetch_audit_sources.py --out audit_sources \
        [--upstream upstream/frontier-evals] [--audits id1,id2]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench import constants  # noqa: E402

CLONE_RE = re.compile(r"git clone\s+(?:--[\w-]+\s+)*(https://\S+?)(?:\.git)?\s")


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def fetch_audit(audit_id: str, evmbench_root: Path, out_root: Path) -> dict:
    audit_dir = evmbench_root / "audits" / audit_id
    dockerfile = (audit_dir / "Dockerfile").read_text(encoding="utf-8")
    m = CLONE_RE.search(dockerfile + " ")
    if not m:
        raise RuntimeError(f"{audit_id}: no git clone found in Dockerfile")
    url = m.group(1)
    if not url.endswith(".git"):
        url += ".git"

    base_commit = None
    for line in (audit_dir / "config.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("base_commit:"):
            base_commit = line.split(":", 1)[1].strip().strip("'\"")
            break

    dest = out_root / audit_id
    if not (dest / ".git").exists():
        # No --recurse-submodules: agents/antfleet_reference filters out lib/,
        # node_modules/, test/, mocks/ before sending sources to the auditor, so
        # transitive Foundry/OpenZeppelin deps would only bloat disk and prompts.
        # If a future agent needs them, --recurse-submodules can be added behind
        # a flag (and the agent's filter loosened to match).
        proc = _run(["git", "clone", "-q", url, str(dest)])
        if proc.returncode != 0:
            raise RuntimeError(f"{audit_id}: clone failed: {proc.stderr.strip()[:300]}")

    checked_out = "HEAD"
    if base_commit:
        proc = _run(["git", "checkout", "-q", base_commit], cwd=dest)
        if proc.returncode == 0:
            checked_out = base_commit
        else:
            print(f"warning: {audit_id}: base_commit {base_commit[:12]} not in mirror, using HEAD",
                  file=sys.stderr)

    head = _run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
    return {
        "audit_id": audit_id,
        "mirror": url,
        "base_commit_config": base_commit,
        "checked_out": checked_out,
        "head": head,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="audit_sources")
    parser.add_argument("--upstream", default="upstream/frontier-evals")
    parser.add_argument("--audits", default=None, help="comma-separated subset of audit IDs")
    args = parser.parse_args(argv)

    evmbench_root = Path(args.upstream) / constants.UPSTREAM_SUBDIR
    split = (evmbench_root / "splits" / f"{constants.DETECT_SPLIT}.txt").read_text().split()
    if args.audits:
        wanted = set(args.audits.split(","))
        unknown = wanted - set(split)
        if unknown:
            print(f"error: unknown audit IDs: {sorted(unknown)}", file=sys.stderr)
            return 1
        split = [a for a in split if a in wanted]

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    manifest = []
    failures = []
    for audit_id in split:
        try:
            entry = fetch_audit(audit_id, evmbench_root, out_root)
            manifest.append(entry)
            print(f"{audit_id}: {entry['head'][:12]} ({'pinned' if entry['checked_out'] != 'HEAD' else 'mirror HEAD'})")
        except RuntimeError as e:
            failures.append(str(e))
            print(f"FAIL {e}", file=sys.stderr)

    (out_root / "sources_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n{len(manifest)}/{len(split)} audits fetched; manifest at {out_root}/sources_manifest.json")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
