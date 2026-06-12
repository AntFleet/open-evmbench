"""Pinned-dataset access: the Detect task set from the upstream cache.

Loads the 40-audit / 117-vulnerability Detect set from a local checkout of
`openai/frontier-evals` at the launch pin and verifies it matches the facts
recorded in docs/UPSTREAM_PIN.md. The wrapper refuses to run against an
unverified or wrong-commit cache.

Vulnerability IDs are normalized as `<audit-id>:<vulnerability-id>` (SPEC §4).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from openevmbench import constants


class DatasetError(Exception):
    """Raised when the upstream cache is missing, unpinned, or inconsistent."""


@dataclass(frozen=True)
class Vulnerability:
    audit_id: str
    vuln_id: str
    title: str
    exploit_task: bool
    findings_path: Path

    @property
    def vulnerability_id(self) -> str:
        return f"{self.audit_id}:{self.vuln_id}"

    def text_content(self) -> str:
        return self.findings_path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class Audit:
    audit_id: str
    vulnerabilities: tuple[Vulnerability, ...]


@dataclass(frozen=True)
class DetectDataset:
    root: Path  # .../project/evmbench
    commit: str
    audits: tuple[Audit, ...]

    @property
    def vulnerabilities(self) -> list[Vulnerability]:
        return [v for a in self.audits for v in a.vulnerabilities]

    @property
    def audit_count(self) -> int:
        return len(self.audits)

    @property
    def vulnerability_count(self) -> int:
        return len(self.vulnerabilities)


def _git_head(repo_dir: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise DatasetError(f"cannot read git HEAD in {repo_dir}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def load_detect_dataset(upstream_repo_dir: Path | str, verify_commit: bool = True) -> DetectDataset:
    """Load and verify the pinned Detect dataset.

    `upstream_repo_dir` is the root of the frontier-evals checkout
    (e.g. `upstream/frontier-evals`).
    """
    repo_dir = Path(upstream_repo_dir)
    root = repo_dir / constants.UPSTREAM_SUBDIR
    if not root.is_dir():
        raise DatasetError(f"upstream cache not found: {root} (see docs/UPSTREAM_PIN.md to fetch it)")

    commit = _git_head(repo_dir) if verify_commit else constants.UPSTREAM_COMMIT
    if verify_commit and commit != constants.UPSTREAM_COMMIT:
        raise DatasetError(
            f"upstream cache is at {commit}, launch pin is {constants.UPSTREAM_COMMIT}"
        )

    split_path = root / "splits" / f"{constants.DETECT_SPLIT}.txt"
    if not split_path.is_file():
        raise DatasetError(f"missing split file: {split_path}")
    audit_ids = split_path.read_text(encoding="utf-8").split()

    audits: list[Audit] = []
    for audit_id in audit_ids:
        config_path = root / "audits" / audit_id / "config.yaml"
        if not config_path.is_file():
            raise DatasetError(f"missing audit config: {config_path}")
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        raw_vulns = cfg["vulnerabilities"]
        if not isinstance(raw_vulns, list):
            raw_vulns = [raw_vulns]
        vulns = []
        for raw in raw_vulns:
            findings_path = root / "audits" / audit_id / "findings" / f"{raw['id']}.md"
            if not findings_path.is_file():
                raise DatasetError(f"missing findings file: {findings_path}")
            vulns.append(
                Vulnerability(
                    audit_id=audit_id,
                    vuln_id=raw["id"],
                    title=raw.get("title", raw["id"]),
                    exploit_task=bool(raw.get("exploit_task", False)),
                    findings_path=findings_path,
                )
            )
        audits.append(Audit(audit_id=audit_id, vulnerabilities=tuple(vulns)))

    dataset = DetectDataset(root=root, commit=commit, audits=tuple(audits))

    if dataset.audit_count != constants.DETECT_AUDIT_COUNT:
        raise DatasetError(
            f"expected {constants.DETECT_AUDIT_COUNT} audits, found {dataset.audit_count}"
        )
    if dataset.vulnerability_count != constants.DETECT_VULN_COUNT:
        raise DatasetError(
            f"expected {constants.DETECT_VULN_COUNT} vulnerabilities, found {dataset.vulnerability_count}"
        )
    return dataset
