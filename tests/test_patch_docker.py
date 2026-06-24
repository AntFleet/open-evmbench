"""Tests for Docker-backed patch grading."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from openevmbench.checks import GRADER_UNAVAILABLE, check_package
from openevmbench.dataset import load_patch_dataset
from openevmbench.hashing import sha256_prefixed
from openevmbench.package import deterministic_archive
from openevmbench.patch_docker import (
    _audit_grade_config,
    _rewrite_audit_dockerfile,
    grade_audit_docker,
    regrade_patch_package,
)
from openevmbench.patch_worker import AuditGrade, PatchWorkerError, VulnerabilityGrade
from openevmbench.patch_docker_runner import (
    build_test_shell,
    hardhat_test_path,
    parse_test_output,
    score_vulnerability,
)


@pytest.fixture
def upstream():
    root = Path("upstream/frontier-evals")
    if not root.is_dir():
        pytest.skip("upstream cache not present")
    return root


def test_audit_grade_config_pooltogether(upstream):
    ds = load_patch_dataset(upstream)
    audit = next(a for a in ds.audits if a.audit_id == "2023-07-pooltogether")
    cfg = _audit_grade_config(audit)
    assert cfg["audit_id"] == "2023-07-pooltogether"
    assert len(cfg["vulnerabilities"]) == 2
    assert cfg["vulnerabilities"][0]["test_mappings"]


def test_audit_grade_config_hardhat_includes_remote_test_path(upstream):
    ds = load_patch_dataset(upstream)
    audit = next(a for a in ds.audits if a.audit_id == "2023-10-nextgen")
    cfg = _audit_grade_config(audit)
    assert cfg["framework"] == "hardhat"
    assert cfg["vulnerabilities"][0]["remote_test_path"] == "hardhat/test/h01-reentrancy.test.js"


def test_build_test_shell_hardhat_uses_audit_absolute_test_path(upstream):
    ds = load_patch_dataset(upstream)
    audit = next(a for a in ds.audits if a.audit_id == "2023-10-nextgen")
    cfg = _audit_grade_config(audit)
    audit_dir = Path("/home/agent/audit")
    vuln = cfg["vulnerabilities"][0]
    cmd = build_test_shell(cfg, audit_dir, vuln=vuln, out_path=Path("/tmp/vuln.out"))
    expected = hardhat_test_path(audit_dir, vuln["remote_test_path"])
    assert expected in cmd
    assert "hardhat/hardhat/test" not in cmd
    assert "> /tmp/vuln.out 2>&1" in cmd
    assert "|| true" not in cmd

    inv_cmd = build_test_shell(cfg, audit_dir, out_path=Path("/tmp/invariant.out"))
    assert "|| true" in inv_cmd


def test_rewrite_audit_dockerfile_skips_yarn_when_corepack_present():
    content = "\n".join([
        "FROM evmbench/base:latest",
        "",
        "RUN npm install -g yarn",
        "RUN yarn",
    ]) + "\n"
    patched = _rewrite_audit_dockerfile(content, "evmbench/patch-base:latest")
    assert "FROM evmbench/patch-base:latest" in patched
    assert "command -v yarn" in patched
    assert patched.count("npm install -g yarn") == 1


def test_audit_grade_config_size_h03_includes_via_ir(upstream):
    ds = load_patch_dataset(upstream)
    audit = next(a for a in ds.audits if a.audit_id == "2024-06-size")
    cfg = _audit_grade_config(audit)
    h03 = next(v for v in cfg["vulnerabilities"] if v["vulnerability_id"].endswith(":H-03"))
    assert h03["test_flags"] == "--via-ir"
    cmd = build_test_shell(
        cfg,
        Path("/home/agent/audit"),
        vuln=h03,
        out_path=Path("/tmp/vuln.out"),
    )
    assert "--via-ir" in cmd
    assert "--match-test test_liquidate_protocol_profit" in cmd


def test_parse_hardhat_json_stats():
    raw = json.dumps({
        "stats": {"tests": 2, "passes": 1, "pending": 0, "failures": 1},
        "failures": [{"fullTitle": "H-01 reentrancy mints full supply"}],
    }).encode()
    result = parse_test_output("hardhat", raw)
    score, max_score = score_vulnerability(result, test_passes_if_vulnerable=True)
    assert result["n_total"] == 2
    assert result["n_failures"] == 1
    assert score == 1
    assert max_score == 2


def test_grade_audit_docker_parses_container_json(upstream, tmp_path, monkeypatch):
    ds = load_patch_dataset(upstream)
    audit = next(a for a in ds.audits if a.audit_id == "2023-07-pooltogether")
    diff = tmp_path / "agent.diff"
    diff.write_text("diff stub\n", encoding="utf-8")

    payload = {
        "audit_id": audit.audit_id,
        "invariant_passed": True,
        "score": 2,
        "max_score": 2,
        "vulnerabilities": [
            {
                "vulnerability_id": "2023-07-pooltogether:H-02",
                "passed": True,
                "score": 1,
                "reason_code": "patched",
                "failures": [],
            },
            {
                "vulnerability_id": "2023-07-pooltogether:H-04",
                "passed": True,
                "score": 1,
                "reason_code": "patched",
                "failures": [],
            },
        ],
    }

    monkeypatch.setattr("openevmbench.patch_docker.docker_available", lambda: True)
    monkeypatch.setattr("openevmbench.patch_docker.ensure_audit_image", lambda *a, **k: None)
    monkeypatch.setattr(
        "openevmbench.patch_docker.subprocess.run",
        lambda *a, **k: mock.Mock(returncode=0, stdout=json.dumps(payload) + "\n", stderr=""),
    )

    grade = grade_audit_docker(
        audit=audit,
        agent_diff=diff,
        upstream_repo_dir=upstream,
        build_if_missing=False,
    )
    assert grade.score == 2
    assert grade.invariant_passed
    assert all(v.passed for v in grade.vulnerabilities)


def _patch_package(tmp_path, ds, submission_id: str, operator: str = "alice", gid: int = 1):
    package_dir = tmp_path / "submissions" / "phase2" / operator / submission_id
    artifacts = package_dir / "agent_artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "2023-07-pooltogether.diff").write_text("x\n", encoding="utf-8")
    archive = deterministic_archive(artifacts)
    per_vuln = [
        {
            "vulnerability_id": vid,
            "passed": False,
            "score": 0,
            "reason_code": "missing-diff",
        }
        for vid in ds.vulnerability_ids
    ]
    record = {
        "submission_id": submission_id,
        "phase": 2,
        "mode": "patch",
        "created_at": "2026-06-21T00:00:00Z",
        "operator": {"github_username": operator, "github_id": gid},
        "submission": {
            "archive_hash": sha256_prefixed(archive),
            "archive_size_bytes": len(archive),
        },
        "benchmark": {
            "upstream_repo": "openai/frontier-evals",
            "upstream_commit": "51052ce",
            "harness_version": "patch-v1.0.0+frontier-evals.51052ce",
        },
        "agent": {
            "model": "test",
            "scaffold_name": "test",
            "scaffold_hash": "sha256:" + "0" * 64,
            "harness_kind": "single-shot",
        },
        "run": {
            "tokens_total": 0,
            "tokens_prompt": 0,
            "tokens_completion": 0,
            "tokens_per_task": [],
            "wall_clock_ms": 0,
            "runs_count": 1,
        },
        "score": {
            "claimed_score": 0.0,
            "solved_count": 0,
            "max_score": 44,
            "per_vulnerability": per_vuln,
        },
    }
    (package_dir / "record.json").write_text(json.dumps(record), encoding="utf-8")
    upstream_src = Path("upstream/frontier-evals")
    upstream_dst = tmp_path / "upstream" / "frontier-evals"
    if upstream_src.is_dir() and not upstream_dst.exists():
        upstream_dst.parent.mkdir(parents=True, exist_ok=True)
        upstream_dst.symlink_to(upstream_src.resolve())
    return package_dir


def test_check_package_skips_docker_regrade_when_env_set(upstream, tmp_path, monkeypatch):
    ds = load_patch_dataset(upstream)
    sid = "019f0000-0000-7000-8000-000000000001"
    package_dir = _patch_package(tmp_path, ds, sid)
    monkeypatch.setenv("OPENEVMBENCH_SKIP_PATCH_REGRADE", "1")

    rel = package_dir.relative_to(tmp_path).as_posix()
    report = check_package(tmp_path, rel, pr_author="alice", pr_author_id=1, dataset=ds)
    assert report.ok
    assert any("skipped" in w.lower() for w in report.warnings)


def test_regrade_patch_package_records_grade_error_per_audit(upstream, tmp_path, monkeypatch):
    ds = load_patch_dataset(upstream)
    sid = "019f0000-0000-7000-8000-000000000010"
    package_dir = _patch_package(tmp_path, ds, sid)
    artifacts = package_dir / "agent_artifacts"
    for audit in ds.audits:
        p = artifacts / f"{audit.audit_id}.diff"
        if not p.is_file():
            p.write_text("diff\n", encoding="utf-8")

    def fake_grade(*, audit, **kwargs):
        if audit.audit_id == "2023-07-pooltogether":
            raise PatchWorkerError("docker grade failed")
        return AuditGrade(
            audit_id=audit.audit_id,
            passed=True,
            score=len(audit.vulnerabilities),
            max_score=len(audit.vulnerabilities),
            invariant_passed=True,
            vulnerabilities=[
                VulnerabilityGrade(
                    vulnerability_id=v.vulnerability_id,
                    passed=True,
                    score=1,
                    max_score=1,
                    reason_code="patched",
                )
                for v in audit.vulnerabilities
            ],
        )

    monkeypatch.setattr("openevmbench.patch_docker.grade_audit_docker", fake_grade)
    upstream_root = tmp_path / "upstream" / "frontier-evals"
    if not upstream_root.is_dir():
        upstream_root.parent.mkdir(parents=True, exist_ok=True)
        upstream_root.symlink_to(upstream.resolve())

    results = regrade_patch_package(
        package_dir=package_dir,
        dataset=ds,
        upstream_repo_dir=upstream_root,
        build_if_missing=False,
    )

    pool = next(a for a in ds.audits if a.audit_id == "2023-07-pooltogether")
    for vuln in pool.vulnerabilities:
        entry = results[vuln.vulnerability_id]
        assert entry.reason_code == "grade-error"
        assert not entry.passed

    assert sum(1 for v in results.values() if v.passed) == 44 - len(pool.vulnerabilities)


def test_check_package_fails_without_docker(upstream, tmp_path, monkeypatch):
    ds = load_patch_dataset(upstream)
    sid = "019f0000-0000-7000-8000-000000000002"
    package_dir = _patch_package(tmp_path, ds, sid)
    monkeypatch.delenv("OPENEVMBENCH_SKIP_PATCH_REGRADE", raising=False)
    monkeypatch.setattr("openevmbench.patch_docker.docker_available", lambda: False)

    rel = package_dir.relative_to(tmp_path).as_posix()
    report = check_package(tmp_path, rel, pr_author="alice", pr_author_id=1, dataset=ds)
    assert not report.ok
    assert any(f.code == GRADER_UNAVAILABLE for f in report.failures)
