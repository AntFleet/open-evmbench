"""Docker-backed Patch grading (production worker).

Grades agent diffs inside per-audit ``evmbench/audit:<audit-id>`` containers
with upstream-pinned Foundry, matching ``PatchGrader`` semantics from
``evmbench/nano/grade/patch.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from openevmbench import constants
from openevmbench.dataset import PatchAudit, PatchDataset
from openevmbench.patch_worker import AuditGrade, PatchWorkerError, VulnerabilityGrade

# Upstream images target amd64. Required on Apple Silicon hosts.
DOCKER_PLATFORM = "linux/amd64"
UPSTREAM_BASE_IMAGE = "evmbench/base:latest"
PATCH_BASE_IMAGE = "evmbench/patch-base:latest"
PLOIT_BUILDER_IMAGE = "ploit-builder:latest"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PATCH_BASE_DOCKERFILE = _REPO_ROOT / "docker" / "evmbench-patch-base.Dockerfile"
_RUNNER_PATH = Path(__file__).resolve().parent / "patch_docker_runner.py"


def evmbench_root(upstream_repo_dir: Path) -> Path:
    return upstream_repo_dir / constants.UPSTREAM_SUBDIR


def audit_image_tag(audit_id: str) -> str:
    return f"evmbench/audit:{audit_id}"


def docker_available() -> bool:
    if not Path("/var/run/docker.sock").exists() and not _docker_info_ok():
        return False
    return _docker_info_ok()


def _docker_info_ok() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip()
        raise PatchWorkerError(f"{' '.join(cmd)} failed ({proc.returncode}): {msg[:2000]}")
    return proc


def _use_upstream_base() -> bool:
    return os.environ.get("PATCH_USE_UPSTREAM_BASE", "").strip() == "1"


def _patch_base_image() -> str:
    return UPSTREAM_BASE_IMAGE if _use_upstream_base() else PATCH_BASE_IMAGE


def _rewrite_audit_dockerfile(content: str, base_image: str) -> str:
    replaced = False
    for old in (UPSTREAM_BASE_IMAGE, "evmbench/base:latest", "evmbench/base"):
        if old in content:
            content = content.replace(old, base_image, 1)
            replaced = True
            break
    if not replaced:
        raise PatchWorkerError(
            f"audit Dockerfile must FROM {UPSTREAM_BASE_IMAGE} (or evmbench/base); got:\n{content[:500]}"
        )
    # patch-base ships yarn via corepack; global npm install conflicts on /usr/bin/yarn.
    content = content.replace(
        "RUN npm install -g yarn\n",
        "RUN command -v yarn >/dev/null || npm install -g yarn\n",
    )
    return content


def build_base_images(*, upstream_repo_dir: Path, platform: str = DOCKER_PLATFORM) -> None:
    if _use_upstream_base():
        root = evmbench_root(upstream_repo_dir)
        ploit_dockerfile = root / "ploit" / "Dockerfile"
        if not ploit_dockerfile.is_file():
            raise PatchWorkerError(f"missing {ploit_dockerfile} — run openevmbench clone")
        _run([
            "docker", "build", f"--platform={platform}",
            "-f", str(ploit_dockerfile),
            "-t", PLOIT_BUILDER_IMAGE,
            "--target", "ploit-builder",
            str(root),
        ])
        _run(["docker", "build", f"--platform={platform}", "-t", UPSTREAM_BASE_IMAGE, str(root / "evmbench")])
        return

    if not _PATCH_BASE_DOCKERFILE.is_file():
        raise PatchWorkerError(f"missing {_PATCH_BASE_DOCKERFILE}")
    _run([
        "docker", "build", f"--platform={platform}",
        "-f", str(_PATCH_BASE_DOCKERFILE),
        "-t", PATCH_BASE_IMAGE,
        str(_PATCH_BASE_DOCKERFILE.parent),
    ])


def audit_image_exists(audit_id: str) -> bool:
    proc = subprocess.run(
        ["docker", "image", "inspect", audit_image_tag(audit_id)],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def build_audit_image(
    audit_id: str,
    *,
    upstream_repo_dir: Path,
    platform: str = DOCKER_PLATFORM,
    ensure_base: bool = True,
) -> None:
    root = evmbench_root(upstream_repo_dir)
    audit_dir = root / "audits" / audit_id
    if not (audit_dir / "Dockerfile").is_file():
        raise PatchWorkerError(f"missing audit Dockerfile: {audit_dir / 'Dockerfile'}")
    base_image = _patch_base_image()
    if ensure_base:
        base_ok = subprocess.run(["docker", "image", "inspect", base_image], capture_output=True).returncode == 0
        if not base_ok:
            build_base_images(upstream_repo_dir=upstream_repo_dir, platform=platform)
    dockerfile = audit_dir / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    if _use_upstream_base():
        patched = content
    else:
        patched = _rewrite_audit_dockerfile(content, base_image)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".Dockerfile",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(patched)
        tmp_path = Path(tmp.name)
    try:
        _run([
            "docker", "build", f"--platform={platform}",
            "-f", str(tmp_path),
            "-t", audit_image_tag(audit_id),
            str(audit_dir),
        ])
    finally:
        tmp_path.unlink(missing_ok=True)


def ensure_audit_image(
    audit_id: str,
    *,
    upstream_repo_dir: Path,
    platform: str = DOCKER_PLATFORM,
) -> None:
    if audit_image_exists(audit_id):
        return
    build_audit_image(audit_id, upstream_repo_dir=upstream_repo_dir, platform=platform)


def _audit_grade_config(audit: PatchAudit) -> dict[str, Any]:
    return {
        "audit_id": audit.audit_id,
        "base_commit": audit.base_commit,
        "work_dir": audit.work_dir,
        "test_dir": audit.test_dir,
        "framework": audit.framework,
        "default_test_flags": audit.default_test_flags,
        "forge_clean_between_patch_tests": audit.forge_clean_between_patch_tests,
        "post_patch_fail_threshold": audit.post_patch_fail_threshold,
        "tests_allowed_to_fail": list(audit.tests_allowed_to_fail),
        "test_files_allowed_to_change": list(audit.test_files_allowed_to_change),
        "vulnerabilities": [
            {
                "vulnerability_id": v.vulnerability_id,
                "test": v.test,
                "test_flags": v.test_flags,
                "test_passes_if_vulnerable": v.test_passes_if_vulnerable,
                "remote_test_path": next(iter(v.test_path_mapping.values())),
                "test_mappings": [
                    {"local": local, "local_name": Path(local).name, "dest": dest}
                    for local, dest in v.test_path_mapping.items()
                ],
            }
            for v in audit.vulnerabilities
        ],
    }


def _parse_container_grade(raw: dict[str, Any], audit: PatchAudit) -> AuditGrade:
    if raw.get("error"):
        raise PatchWorkerError(raw["error"])
    if not raw.get("invariant_passed", False):
        return AuditGrade(
            audit_id=audit.audit_id,
            passed=False,
            score=0,
            max_score=len(audit.vulnerabilities),
            invariant_passed=False,
            vulnerabilities=[],
            reason_code=raw.get("reason_code", "invariant-failed"),
            grader_log=f"[{audit.audit_id}] docker invariant failed",
        )
    vuln_grades = [
        VulnerabilityGrade(
            vulnerability_id=v["vulnerability_id"],
            passed=bool(v["passed"]),
            score=int(v["score"]),
            max_score=1,
            reason_code=v.get("reason_code", "vuln-test-failed"),
            failures=tuple(v.get("failures") or []),
        )
        for v in raw.get("vulnerabilities") or []
    ]
    score = int(raw.get("score", 0))
    max_score = len(audit.vulnerabilities)
    return AuditGrade(
        audit_id=audit.audit_id,
        passed=score == max_score,
        score=score,
        max_score=max_score,
        invariant_passed=True,
        vulnerabilities=vuln_grades,
        grader_log=f"[{audit.audit_id}] docker grade {score}/{max_score}",
    )


def grade_audit_docker(
    *,
    audit: PatchAudit,
    agent_diff: Path,
    upstream_repo_dir: Path,
    platform: str = DOCKER_PLATFORM,
    build_if_missing: bool = True,
) -> AuditGrade:
    """Grade one audit diff inside ``evmbench/audit:<audit-id>``."""
    if not agent_diff.is_file():
        raise PatchWorkerError(f"missing diff: {agent_diff}")
    if not docker_available():
        raise PatchWorkerError("Docker daemon not available")

    if build_if_missing:
        ensure_audit_image(audit.audit_id, upstream_repo_dir=upstream_repo_dir, platform=platform)

    root = evmbench_root(upstream_repo_dir)
    tests_dir = (root / "audits" / audit.audit_id / "test").resolve()
    if not tests_dir.is_dir():
        raise PatchWorkerError(f"missing exploit test bundle: {tests_dir}")

    if not _RUNNER_PATH.is_file():
        raise PatchWorkerError(f"missing {_RUNNER_PATH}")

    with tempfile.TemporaryDirectory(prefix="patch-docker-grade-") as tmp:
        tmp_path = Path(tmp)
        config_path = (tmp_path / "grade_config.json").resolve()
        config_path.write_text(json.dumps(_audit_grade_config(audit), indent=2), encoding="utf-8")
        diff_copy = (tmp_path / "agent.diff").resolve()
        diff_copy.write_bytes(agent_diff.read_bytes())
        runner = _RUNNER_PATH.resolve()

        proc = subprocess.run(
            [
                "docker", "run", "--rm", f"--platform={platform}",
                "-v", f"{diff_copy}:/mnt/agent.diff:ro",
                "-v", f"{tests_dir}:/mnt/exploit-tests:ro",
                "-v", f"{config_path}:/mnt/grade_config.json:ro",
                "-v", f"{runner}:/mnt/grade_runner.py:ro",
                audit_image_tag(audit.audit_id),
                "python3", "/mnt/grade_runner.py",
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            raise PatchWorkerError(f"docker grade failed: {err[:2000]}")
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            raise PatchWorkerError("docker grade produced no output")
        try:
            raw = json.loads(lines[-1])
        except json.JSONDecodeError as e:
            raise PatchWorkerError(f"invalid grade JSON: {e}; output={proc.stdout[:500]!r}") from e
        return _parse_container_grade(raw, audit)


def regrade_patch_package(
    *,
    package_dir: Path,
    dataset: PatchDataset,
    upstream_repo_dir: Path,
    platform: str = DOCKER_PLATFORM,
    build_if_missing: bool = True,
) -> dict[str, VulnerabilityGrade]:
    """Re-grade all non-empty diffs in a Phase 2 package; return vuln_id → grade."""
    artifacts = package_dir / "agent_artifacts"
    if not artifacts.is_dir():
        raise PatchWorkerError(f"missing agent_artifacts/: {artifacts}")

    results: dict[str, VulnerabilityGrade] = {}
    for audit in dataset.audits:
        diff_path = artifacts / f"{audit.audit_id}.diff"
        if not diff_path.is_file() or diff_path.stat().st_size == 0:
            for vuln in audit.vulnerabilities:
                results[vuln.vulnerability_id] = VulnerabilityGrade(
                    vulnerability_id=vuln.vulnerability_id,
                    passed=False,
                    score=0,
                    max_score=1,
                    reason_code="missing-diff",
                )
            continue
        grade = grade_audit_docker(
            audit=audit,
            agent_diff=diff_path,
            upstream_repo_dir=upstream_repo_dir,
            platform=platform,
            build_if_missing=build_if_missing,
        )
        for vg in grade.vulnerabilities:
            results[vg.vulnerability_id] = vg
    return results
