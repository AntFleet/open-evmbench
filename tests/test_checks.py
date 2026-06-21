import json
import shutil

import pytest

from conftest import UPSTREAM_DIR, upstream_required
from openevmbench import checks
from openevmbench.checks import check_package, find_submission_dir

SID = "018f7f64-2c2e-7b70-8f4d-000000000001"
GOOD = f"submissions/phase1/alice/{SID}/record.json"


class TestFindSubmissionDir:
    def test_single_valid_dir(self):
        rel, report = find_submission_dir([GOOD, GOOD.replace("record.json", "judge_transcript.jsonl")])
        assert report.ok
        assert rel == f"submissions/phase1/alice/{SID}/"

    def test_outside_path_rejected(self):
        _, report = find_submission_dir([GOOD, "harness/judge_prompt_v1.md"])
        assert any(f.code == checks.PATH_VIOLATION for f in report.failures)

    def test_multiple_dirs_rejected(self):
        other = GOOD.replace("alice", "bob")
        _, report = find_submission_dir([GOOD, other])
        assert any("multiple submission dirs" in f.message for f in report.failures)

    def test_non_uuid7_dir_rejected(self):
        bad = GOOD.replace(SID, "9f1c1c8e-3d2a-4b5c-8d6e-7f8a9b0c1d2e")  # v4
        _, report = find_submission_dir([bad])
        assert any(f.code == checks.PATH_VIOLATION for f in report.failures)

    def test_phase2_path_accepted(self):
        sid = "018f7f64-2c2e-7b70-8f4d-000000000001"
        good = f"submissions/phase2/alice/{sid}/record.json"
        rel, report = find_submission_dir([good])
        assert report.ok
        assert rel == f"submissions/phase2/alice/{sid}/"

        _, report = find_submission_dir([])
        assert not report.ok

    def test_dotdot_path_rejected(self):
        bad = f"submissions/phase1/alice/{SID}/../../../etc/passwd"
        _, report = find_submission_dir([bad])
        assert any(f.code == checks.PATH_VIOLATION for f in report.failures)


@pytest.fixture(scope="module")
def built_package(tmp_path_factory):
    """One real package built via the runner (shared, copied per test)."""
    pytest.importorskip("yaml")
    if not (UPSTREAM_DIR / "project" / "evmbench").is_dir():
        pytest.skip("upstream cache not fetched")

    import hashlib

    from openevmbench.dataset import load_detect_dataset
    from openevmbench.package import AgentInfo, JudgeInfo, OperatorInfo, RunMeta
    from openevmbench.runner import run_detect

    tmp = tmp_path_factory.mktemp("pkg")
    ds = load_detect_dataset(UPSTREAM_DIR)

    def marker(text):
        return "MARKER-" + hashlib.sha256(text.encode()).hexdigest()[:16]

    class MarkerJudge:
        def complete(self, system, user):
            audit, vuln = user.split("\n\nVulnerability description:\n", 1)
            detected = marker(vuln) in audit
            return json.dumps({"detected": detected, "reasoning": "m"})

    outputs = tmp / "agent_outputs"
    audit = ds.audits[0]
    path = outputs / audit.audit_id / "audit.md"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(marker(v.text_content()) for v in audit.vulnerabilities))

    result = run_detect(
        dataset=ds,
        agent_outputs_dir=outputs,
        harness_dir="harness",
        judge_client=MarkerJudge(),
        judge_info=JudgeInfo(model="marker-judge", params={}),
        operator=OperatorInfo(github_username="alice", github_id=1),
        agent=AgentInfo(model="m", scaffold_name="s", scaffold_hash="sha256:" + "0" * 64, harness_kind="single-shot"),
        run_meta=RunMeta(tokens_total=10, tokens_prompt=8, tokens_completion=2, tokens_per_task=[], wall_clock_ms=1),
        submissions_root=tmp / "repo" / "submissions",
    )
    return tmp / "repo", result.package


@pytest.fixture
def package_copy(built_package, tmp_path):
    repo, package = built_package
    dst_repo = tmp_path / "repo"
    shutil.copytree(repo, dst_repo)
    rel = package.package_dir.relative_to(repo).as_posix()
    return dst_repo, rel


@pytest.fixture(scope="module")
def detect_dataset():
    pytest.importorskip("yaml")
    if not (UPSTREAM_DIR / "project" / "evmbench").is_dir():
        pytest.skip("upstream cache not fetched")
    from openevmbench.dataset import load_detect_dataset

    return load_detect_dataset(UPSTREAM_DIR)


@upstream_required
class TestCheckPackage:
    def test_clean_package_passes(self, package_copy, detect_dataset):
        repo, rel = package_copy
        report = check_package(repo, rel, pr_author="alice", pr_author_id=1, dataset=detect_dataset)
        assert report.ok, report.summary()

    def test_pr_author_mismatch(self, package_copy):
        repo, rel = package_copy
        report = check_package(repo, rel, pr_author="mallory")
        assert any(f.code == checks.IDENTITY_MISMATCH for f in report.failures)

    def test_pr_author_id_mismatch(self, package_copy):
        repo, rel = package_copy
        report = check_package(repo, rel, pr_author="alice", pr_author_id=2)
        assert any(f.code == checks.IDENTITY_MISMATCH for f in report.failures)

    def test_fabricated_vulnerability_ids_rejected(self, package_copy, detect_dataset):
        repo, rel = package_copy
        record_path = repo / rel / "record.json"
        record = json.loads(record_path.read_text())
        for idx, entry in enumerate(record["score"]["per_vulnerability"]):
            entry["vulnerability_id"] = f"fake-audit:fake-{idx}"
        record_path.write_text(json.dumps(record))
        report = check_package(repo, rel, pr_author="alice", dataset=detect_dataset)
        assert any(f.code == checks.VULNERABILITY_ID_MISMATCH for f in report.failures)

    def test_missing_real_id_plus_fake_rejected(self, package_copy, detect_dataset):
        repo, rel = package_copy
        record_path = repo / rel / "record.json"
        record = json.loads(record_path.read_text())
        record["score"]["per_vulnerability"][0]["vulnerability_id"] = "fake-audit:fake-one"
        record_path.write_text(json.dumps(record))
        report = check_package(repo, rel, pr_author="alice", dataset=detect_dataset)
        assert any(f.code == checks.VULNERABILITY_ID_MISMATCH for f in report.failures)

    def test_tampered_transcript(self, package_copy):
        repo, rel = package_copy
        transcript = repo / rel / "judge_transcript.jsonl"
        transcript.write_bytes(transcript.read_bytes() + b'{"ts":"t","role":"note","content":"x"}\n')
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.TRANSCRIPT_HASH_MISMATCH for f in report.failures)

    def test_oversized_transcript_rejected_before_read(self, package_copy):
        repo, rel = package_copy
        transcript = repo / rel / "judge_transcript.jsonl"
        with transcript.open("wb") as f:
            f.seek(checks.MAX_TRANSCRIPT_BYTES)
            f.write(b"x")
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.FILE_TOO_LARGE for f in report.failures)

    def test_inflated_score_caught_by_transcript(self, package_copy):
        """Submitter edits record.json to claim an extra solve: solved_count is
        kept consistent within the record but contradicts the judge transcript."""
        repo, rel = package_copy
        record_path = repo / rel / "record.json"
        record = json.loads(record_path.read_text())
        flipped = next(e for e in record["score"]["per_vulnerability"] if not e["passed"])
        flipped["passed"] = True
        flipped["score"] = 1
        record["score"]["solved_count"] += 1
        record["score"]["claimed_score"] = round(
            record["score"]["solved_count"] / record["score"]["max_score"], 4
        )
        record_path.write_text(json.dumps(record))
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.TRANSCRIPT_INCONSISTENT for f in report.failures)

    def test_tampered_artifacts(self, package_copy):
        repo, rel = package_copy
        artifacts = repo / rel / "agent_artifacts"
        next(artifacts.rglob("audit.md")).write_text("post-hoc edited report")
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.ARCHIVE_MISMATCH for f in report.failures)

    def test_artifact_symlink_rejected(self, package_copy):
        repo, rel = package_copy
        link = repo / rel / "agent_artifacts" / "leak"
        link.symlink_to("/etc/passwd")
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.ARCHIVE_SYMLINK for f in report.failures)

    def test_missing_transcript(self, package_copy):
        repo, rel = package_copy
        (repo / rel / "judge_transcript.jsonl").unlink()
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.MISSING_FILE for f in report.failures)

    def test_wrong_prompt_hash_rejected(self, package_copy):
        repo, rel = package_copy
        record_path = repo / rel / "record.json"
        record = json.loads(record_path.read_text())
        record["judge"]["prompt_hash"] = "sha256:" + "0" * 64
        record_path.write_text(json.dumps(record))
        report = check_package(repo, rel, pr_author="alice")
        assert any(f.code == checks.RECORD_INVALID and "pinned prompt hash" in f.message
                   for f in report.failures)
