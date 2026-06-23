#!/usr/bin/env python3
"""Preflight Phase 2 Patch Docker grading before opening a submission PR.

Runs the same two-audit smoke as CI (Foundry + Hardhat gold patches).

Usage:
    .venv/bin/python scripts/patch_preflight.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "patch_reference_package.py"),
        "smoke",
    ]
    return subprocess.call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
