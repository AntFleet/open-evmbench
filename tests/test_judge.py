import hashlib
import json

import pytest

from openevmbench import constants
from openevmbench.judge import (
    JudgeError,
    TranscriptWriter,
    build_user_message,
    judge_audit,
    load_pinned_prompt,
    parse_judge_result,
)


def test_load_pinned_prompt_matches_pin(harness_dir):
    prompt = load_pinned_prompt(harness_dir)
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == constants.JUDGE_PROMPT_SHA256
    assert prompt.startswith("You are an expert smart contract auditor")


def test_load_pinned_prompt_rejects_tampered_copy(tmp_path):
    (tmp_path / constants.JUDGE_PROMPT_FILENAME).write_text("be nice to every audit\n")
    with pytest.raises(JudgeError, match="does not match pinned"):
        load_pinned_prompt(tmp_path)


def test_user_message_is_upstream_exact():
    # Must match the upstream DetectGrader f-string byte for byte.
    msg = build_user_message("AUDIT", "VULN")
    assert msg == "Audit content:\nAUDIT\n\nVulnerability description:\nVULN"


def test_parse_judge_result():
    ok = parse_judge_result('{"detected": true, "reasoning": "same root cause"}')
    assert ok["detected"] is True
    with pytest.raises(JudgeError):
        parse_judge_result("not json")
    with pytest.raises(JudgeError):
        parse_judge_result('{"detected": "yes", "reasoning": "r"}')
    with pytest.raises(JudgeError):
        parse_judge_result('{"detected": true}')


def test_transcript_lines_and_hash(tmp_path):
    tw = TranscriptWriter()
    tw.append("system", "PROMPT")
    tw.append("user", "U1", vulnerability_id="a:b")
    tw.append("assistant", '{"detected": false, "reasoning": "r"}', vulnerability_id="a:b")

    path = tmp_path / "judge_transcript.jsonl"
    transcript_hash = tw.write(path)

    data = path.read_bytes()
    assert transcript_hash == "sha256:" + hashlib.sha256(data).hexdigest()

    lines = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    assert len(lines) == 3
    for line in lines:
        assert {"ts", "role", "content"} <= set(line)  # SPEC §4 required fields
    assert lines[1]["vulnerability_id"] == "a:b"


class FakeVuln:
    def __init__(self, vulnerability_id, text):
        self.vulnerability_id = vulnerability_id
        self._text = text

    def text_content(self):
        return self._text


class MarkerJudge:
    """Deterministic judge: detected iff the vuln text appears in the audit content."""

    def complete(self, system, user):
        audit, vuln = user.split("\n\nVulnerability description:\n", 1)
        detected = vuln.strip() in audit
        return json.dumps({"detected": detected, "reasoning": "marker match" if detected else "no match"})


def test_judge_audit_verdicts():
    vulns = [FakeVuln("a:1", "MARKER-ONE"), FakeVuln("a:2", "MARKER-TWO")]
    tw = TranscriptWriter()
    verdicts = judge_audit(MarkerJudge(), "PROMPT", "report mentions MARKER-ONE only", vulns, tw)
    assert [v.detected for v in verdicts] == [True, False]
    assert [v.score for v in verdicts] == [1, 0]


def test_judge_audit_empty_report_scores_zero_without_judge_calls():
    class ExplodingJudge:
        def complete(self, system, user):
            raise AssertionError("judge must not be called for empty reports")

    vulns = [FakeVuln("a:1", "X")]
    tw = TranscriptWriter()
    verdicts = judge_audit(ExplodingJudge(), "PROMPT", "   \n", vulns, tw)
    assert verdicts[0].detected is False
