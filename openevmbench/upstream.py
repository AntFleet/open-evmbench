"""Fetch the pinned upstream benchmark source (docs/UPSTREAM_PIN.md recipe).

The upstream repo uses Git LFS for paperbench data only; the evmbench tree
needs no LFS objects, so the clone disables the LFS filter and works without
git-lfs installed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from openevmbench import constants


class UpstreamError(Exception):
    pass


def _git(args: list[str], cwd: Path) -> None:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise UpstreamError(f"git {' '.join(args[:2])} failed: {proc.stderr.strip()[:500]}")


def ensure_upstream(dest: Path | str = "upstream/frontier-evals") -> Path:
    """Clone or verify the pinned upstream commit at `dest`. Idempotent."""
    dest = Path(dest)
    if (dest / ".git").exists():
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=dest, capture_output=True, text=True
        )
        if proc.returncode == 0 and proc.stdout.strip() == constants.UPSTREAM_COMMIT:
            return dest
        raise UpstreamError(
            f"{dest} exists but is not at the launch pin {constants.UPSTREAM_COMMIT_SHORT}; "
            "remove it and re-run clone"
        )

    dest.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], dest)
    _git(["remote", "add", "origin", f"https://github.com/{constants.UPSTREAM_REPO}.git"], dest)
    _git(["fetch", "--depth", "1", "origin", constants.UPSTREAM_COMMIT], dest)
    _git(
        [
            "-c", "filter.lfs.smudge=cat",
            "-c", "filter.lfs.process=",
            "-c", "filter.lfs.required=false",
            "checkout", "-qf", "FETCH_HEAD",
        ],
        dest,
    )
    return dest
