"""Week 1 checkpoint (SPEC §6): a sample Detect archive can be run locally,
judged locally with the pinned prompt, and packaged into a valid submission
record with matching score output and transcript hash."""

import hashlib
import json

from conftest import UPSTREAM_DIR, upstream_required
from openevmbench import constants
from openevmbench.dataset import load_detect_dataset
from openevmbench.hashing import sha256_file
from openevmbench.judge import build_user_message
from openevmbench.package import AgentInfo, JudgeInfo, OperatorInfo, RunMeta, deterministic_archive
from openevmbench.runner import run_detect
from openevmbench.signing import generate_keypair, sign_record, verify_record
from openevmbench.validation import validate_lifecycle, validate_phase1_detect


def _marker(text: str) -> str:
    return "MARKER-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class MarkerJudge:
    """Detected iff the audit content contains the marker of the vuln text."""

    def complete(self, system, user):
        assert system.startswith("You are an expert smart contract auditor")
        audit, vuln = user.split("\n\nVulnerability description:\n", 1)
        detected = _marker(vuln) in audit
        return json.dumps({"detected": detected, "reasoning": "marker" if detected else "no marker"})


@upstream_required
def test_week1_checkpoint(tmp_path):
    ds = load_detect_dataset(UPSTREAM_DIR)

    # Fake agent outputs: "solve" every vulnerability of the first two audits.
    solved_audits = ds.audits[:2]
    expected_solved = sum(len(a.vulnerabilities) for a in solved_audits)
    outputs = tmp_path / "agent_outputs"
    for audit in solved_audits:
        report = "\n".join(_marker(v.text_content()) for v in audit.vulnerabilities)
        path = outputs / audit.audit_id / "audit.md"
        path.parent.mkdir(parents=True)
        path.write_text("# Audit findings\n" + report + "\n", encoding="utf-8")

    result = run_detect(
        dataset=ds,
        agent_outputs_dir=outputs,
        harness_dir="harness",
        judge_client=MarkerJudge(),
        judge_info=JudgeInfo(model="marker-judge", params={"deterministic": True}),
        operator=OperatorInfo(github_username="alice", github_id=12345678),
        agent=AgentInfo(
            model="test-model",
            scaffold_name="marker-scaffold",
            scaffold_hash="sha256:" + "b" * 64,
            harness_kind="single-shot",
        ),
        run_meta=RunMeta(
            tokens_total=1000, tokens_prompt=800, tokens_completion=200,
            tokens_per_task=[25] * constants.DETECT_AUDIT_COUNT,
            wall_clock_ms=0,
        ),
        submissions_root=tmp_path / "submissions",
    )

    record = result.package.record
    pkg = result.package.package_dir

    # Score: exactly the seeded audits' vulnerabilities are solved.
    assert result.solved_count == expected_solved
    assert record["score"]["max_score"] == constants.DETECT_VULN_COUNT
    assert len(record["score"]["per_vulnerability"]) == constants.DETECT_VULN_COUNT

    # Phase 1 board validation passes on the packaged record.
    assert validate_phase1_detect(record).ok

    # Package layout (SPEC §4).
    assert (pkg / "record.json").is_file()
    assert (pkg / "judge_transcript.jsonl").is_file()
    assert (pkg / "agent_artifacts" / solved_audits[0].audit_id / "audit.md").is_file()
    assert pkg.parent.name == "alice" and pkg.parent.parent.name == "phase1"

    # Transcript hash matches the file exactly as written.
    assert record["judge"]["transcript_hash"] == sha256_file(pkg / "judge_transcript.jsonl")

    # Transcript lines carry ts/role/content; verdicts match per_vulnerability.
    lines = [json.loads(l) for l in (pkg / "judge_transcript.jsonl").read_text().splitlines()]
    assert all({"ts", "role", "content"} <= set(l) for l in lines)
    verdict_by_vuln = {
        l["vulnerability_id"]: json.loads(l["content"])["detected"]
        for l in lines if l["role"] == "assistant"
    }
    for entry in record["score"]["per_vulnerability"]:
        assert verdict_by_vuln[entry["vulnerability_id"]] == entry["passed"]

    # Pinned prompt hash recorded; system line is the pinned prompt.
    assert record["judge"]["prompt_hash"] == f"sha256:{constants.JUDGE_PROMPT_SHA256}"
    assert hashlib.sha256(lines[0]["content"].encode()).hexdigest() == constants.JUDGE_PROMPT_SHA256

    # Archive hash reproduces from the deterministic recipe.
    rebuilt = deterministic_archive(pkg / "agent_artifacts")
    assert record["submission"]["archive_hash"] == "sha256:" + hashlib.sha256(rebuilt).hexdigest()
    assert record["submission"]["archive_size_bytes"] == len(rebuilt)

    # Acceptance signing path: accept, sign, verify (PR-pipeline preview).
    private_pem, public_pem = generate_keypair()
    accepted = dict(record)
    accepted["state"] = "accepted"
    accepted["state_reason"] = None
    accepted["score"] = dict(record["score"], official_score=record["score"]["claimed_score"])
    accepted["prize_review_status"] = None
    accepted["prize_review_reason"] = None
    signed = sign_record(accepted, private_pem, public_pem)
    verify_record(signed, public_pem)
    assert validate_lifecycle(signed).ok, validate_lifecycle(signed).errors


@upstream_required
def test_missing_agent_outputs_score_zero(tmp_path):
    ds = load_detect_dataset(UPSTREAM_DIR)
    outputs = tmp_path / "agent_outputs"
    outputs.mkdir()

    class ExplodingJudge:
        def complete(self, system, user):
            raise AssertionError("no judge calls expected when all reports are missing")

    result = run_detect(
        dataset=ds,
        agent_outputs_dir=outputs,
        harness_dir="harness",
        judge_client=ExplodingJudge(),
        judge_info=JudgeInfo(model="marker-judge", params={}),
        operator=OperatorInfo(github_username="bob", github_id=2),
        agent=AgentInfo(model="m", scaffold_name="s", scaffold_hash="sha256:" + "0" * 64, harness_kind="single-shot"),
        run_meta=RunMeta(tokens_total=0, tokens_prompt=0, tokens_completion=0, tokens_per_task=[], wall_clock_ms=0),
        submissions_root=tmp_path / "submissions",
    )
    assert result.solved_count == 0
    assert validate_phase1_detect(result.package.record).ok
