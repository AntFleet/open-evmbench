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


@dataclass(frozen=True)
class PatchVulnerability:
    audit_id: str
    vuln_id: str
    title: str
    test: str
    test_flags: str
    test_passes_if_vulnerable: bool
    test_path_mapping: dict[str, str]
    patch_path_mapping: dict[str, str]

    @property
    def vulnerability_id(self) -> str:
        return f"{self.audit_id}:{self.vuln_id}"


@dataclass(frozen=True)
class PatchAudit:
    audit_id: str
    framework: str
    run_cmd_dir: str
    test_dir: str
    default_test_flags: str
    base_commit: str
    run_tests_individually: bool
    forge_clean_between_patch_tests: bool
    post_patch_fail_threshold: int
    tests_allowed_to_fail: tuple[str, ...]
    test_files_allowed_to_change: tuple[str, ...]
    vulnerabilities: tuple[PatchVulnerability, ...]

    @property
    def work_dir(self) -> str:
        return self.run_cmd_dir or "."


@dataclass(frozen=True)
class PatchDataset:
    root: Path
    commit: str
    audits: tuple[PatchAudit, ...]

    @property
    def vulnerabilities(self) -> list[PatchVulnerability]:
        return [v for a in self.audits for v in a.vulnerabilities]

    @property
    def audit_count(self) -> int:
        return len(self.audits)

    @property
    def vulnerability_count(self) -> int:
        return len(self.vulnerabilities)

    @property
    def vulnerability_ids(self) -> tuple[str, ...]:
        return tuple(v.vulnerability_id for v in self.vulnerabilities)


def _load_patch_audit_config(root: Path, audit_id: str) -> PatchAudit:
    config_path = root / "audits" / audit_id / "config.yaml"
    if not config_path.is_file():
        raise DatasetError(f"missing audit config: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    vulns_raw = raw.get("vulnerabilities") or []
    if not isinstance(vulns_raw, list):
        vulns_raw = [vulns_raw]
    vulns: list[PatchVulnerability] = []
    for v in vulns_raw:
        if not v.get("patch_path_mapping"):
            continue
        vulns.append(
            PatchVulnerability(
                audit_id=audit_id,
                vuln_id=v["id"],
                title=v.get("title", v["id"]),
                test=v["test"],
                test_flags=v.get("test_flags") or "",
                test_passes_if_vulnerable=bool(v.get("test_passes_if_vulnerable", True)),
                test_path_mapping=dict(v.get("test_path_mapping") or {}),
                patch_path_mapping=dict(v.get("patch_path_mapping") or {}),
            )
        )
    if not vulns:
        raise DatasetError(f"{audit_id}: no patch vulnerabilities in config")
    return PatchAudit(
        audit_id=audit_id,
        framework=raw.get("framework", "foundry-json"),
        run_cmd_dir=raw.get("run_cmd_dir") or "",
        test_dir=raw.get("test_dir", "test"),
        default_test_flags=raw.get("default_test_flags") or "",
        base_commit=raw["base_commit"],
        run_tests_individually=bool(raw.get("run_tests_individually", True)),
        forge_clean_between_patch_tests=bool(raw.get("forge_clean_between_patch_tests", False)),
        post_patch_fail_threshold=int(raw.get("post_patch_fail_threshold", 0)),
        tests_allowed_to_fail=tuple(raw.get("tests_allowed_to_fail") or []),
        test_files_allowed_to_change=tuple(raw.get("test_files_allowed_to_change") or []),
        vulnerabilities=tuple(vulns),
    )


def load_patch_dataset(upstream_repo_dir: Path | str, verify_commit: bool = True) -> PatchDataset:
    """Load and verify the pinned Patch task set (22 audits / 44 vulns)."""
    repo_dir = Path(upstream_repo_dir)
    root = repo_dir / constants.UPSTREAM_SUBDIR
    if not root.is_dir():
        raise DatasetError(f"upstream cache not found: {root} (see docs/UPSTREAM_PIN.md to fetch it)")

    commit = _git_head(repo_dir) if verify_commit else constants.UPSTREAM_COMMIT
    if verify_commit and commit != constants.UPSTREAM_COMMIT:
        raise DatasetError(
            f"upstream cache is at {commit}, launch pin is {constants.UPSTREAM_COMMIT}"
        )

    split_path = root / "splits" / f"{constants.PATCH_SPLIT}.txt"
    if not split_path.is_file():
        raise DatasetError(f"missing split file: {split_path}")
    audit_ids = split_path.read_text(encoding="utf-8").split()

    audits = tuple(_load_patch_audit_config(root, audit_id) for audit_id in audit_ids)
    dataset = PatchDataset(root=root, commit=commit, audits=audits)

    if dataset.audit_count != constants.PATCH_AUDIT_COUNT:
        raise DatasetError(
            f"expected {constants.PATCH_AUDIT_COUNT} patch audits, found {dataset.audit_count}"
        )
    if dataset.vulnerability_count != constants.PATCH_VULN_COUNT:
        raise DatasetError(
            f"expected {constants.PATCH_VULN_COUNT} patch vulnerabilities, found {dataset.vulnerability_count}"
        )
    return dataset


def load_patch_audit(upstream_repo_dir: Path | str, audit_id: str) -> PatchAudit:
    """Load one audit from the patch-tasks split."""
    dataset = load_patch_dataset(upstream_repo_dir)
    for audit in dataset.audits:
        if audit.audit_id == audit_id:
            return audit
    raise DatasetError(f"{audit_id} is not in the {constants.PATCH_SPLIT} split")
