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
from openevmbench.patch_docker import _audit_grade_config, grade_audit_docker
from openevmbench.patch_docker_runner import parse_test_output, score_vulnerability


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
