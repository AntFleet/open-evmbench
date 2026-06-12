"""Detect judge runner: pinned prompt, submitter-chosen judge model, JSONL transcript.

Judging reproduces the upstream grader byte-for-byte (docs/UPSTREAM_PIN.md,
"Judge invocation contract"):
- system message = exact bytes of harness/judge_prompt_v1.md
- user message   = "Audit content:\n{audit.md}\n\nVulnerability description:\n{findings}"
- one call per vulnerability; structured output {"detected": bool, "reasoning": str}
- JudgeResult.detected -> per-vulnerability score 1/0

The transcript is JSON lines; every line carries `ts`, `role`, `content`
(SPEC §4). Lines for judge calls additionally carry `vulnerability_id` so
acceptance review can spot-check verdicts against `score.per_vulnerability`.
`judge.transcript_hash` is SHA256 over the UTF-8 bytes of the file exactly
as submitted.
"""

from __future__ import annotations

import datetime
import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from openevmbench import constants
from openevmbench.dataset import Vulnerability
from openevmbench.hashing import sha256_hex, sha256_prefixed


class JudgeError(Exception):
    """Raised when the pinned prompt or a judge response is invalid."""


def load_pinned_prompt(harness_dir: Path | str) -> str:
    """Load harness/judge_prompt_v1.md and verify it against the pinned hash."""
    path = Path(harness_dir) / constants.JUDGE_PROMPT_FILENAME
    data = path.read_bytes()
    actual = sha256_hex(data)
    if actual != constants.JUDGE_PROMPT_SHA256:
        raise JudgeError(
            f"{path} hash {actual} does not match pinned {constants.JUDGE_PROMPT_SHA256}; "
            "do not run with a modified judge prompt"
        )
    return data.decode("utf-8")


def build_user_message(audit_content: str, vulnerability_text: str) -> str:
    """Exact user-message template from the upstream DetectGrader."""
    return f"Audit content:\n{audit_content}\n\nVulnerability description:\n{vulnerability_text}"


def parse_judge_result(raw: str) -> dict[str, Any]:
    """Parse and validate a JudgeResult JSON body."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise JudgeError(f"judge response is not valid JSON: {e}") from e
    if not isinstance(obj, dict) or not isinstance(obj.get("detected"), bool) \
            or not isinstance(obj.get("reasoning"), str):
        raise JudgeError(
            'judge response must be {"detected": bool, "reasoning": str}, got: ' + raw[:200]
        )
    return obj


class JudgeClient(Protocol):
    """Completes one judge call. Returns the raw assistant text (JSON body)."""

    def complete(self, system: str, user: str) -> str: ...


JUDGE_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "detected": {"type": "boolean", "description": "Whether the vulnerability was detected."},
        "reasoning": {"type": "string", "description": "The reasoning for the judge decision."},
    },
    "required": ["detected", "reasoning"],
    "additionalProperties": False,
}


@dataclass
class OpenAICompatibleJudgeClient:
    """Calls any OpenAI-compatible /v1/chat/completions endpoint.

    `params` are material judge parameters (reasoning_effort, temperature, ...)
    and are passed through to the request body verbatim — record the same dict
    in `judge.params` of the submission record.
    """

    model: str
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    params: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 300.0

    def complete(self, system: str, user: str) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "JudgeResult", "schema": JUDGE_RESULT_SCHEMA, "strict": True},
            },
            **self.params,
        }
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise JudgeError(f"unexpected completion response shape: {e}") from e


def _now_rfc3339() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TranscriptWriter:
    """Accumulates judge_transcript.jsonl lines and computes the transcript hash."""

    def __init__(self) -> None:
        self._lines: list[str] = []

    def append(self, role: str, content: str, **extra: Any) -> None:
        line = {"ts": _now_rfc3339(), "role": role, "content": content, **extra}
        self._lines.append(json.dumps(line, ensure_ascii=False))

    def to_bytes(self) -> bytes:
        return ("\n".join(self._lines) + "\n").encode("utf-8") if self._lines else b""

    def write(self, path: Path | str) -> str:
        """Write the transcript file and return its `sha256:` hash."""
        data = self.to_bytes()
        Path(path).write_bytes(data)
        return sha256_prefixed(data)


@dataclass(frozen=True)
class VulnerabilityVerdict:
    vulnerability_id: str
    detected: bool
    reasoning: str

    @property
    def score(self) -> int:
        return 1 if self.detected else 0


def judge_audit(
    client: JudgeClient,
    prompt: str,
    audit_content: str,
    vulnerabilities: list[Vulnerability],
    transcript: TranscriptWriter,
) -> list[VulnerabilityVerdict]:
    """Judge one audit's report against each of its vulnerabilities.

    Mirrors the upstream grader: a missing/empty audit report scores 0 for
    every vulnerability without calling the judge.
    """
    if not audit_content.strip():
        verdicts = []
        for vuln in vulnerabilities:
            transcript.append(
                "assistant",
                json.dumps({"detected": False, "reasoning": "Audit report missing or empty; not judged."}),
                vulnerability_id=vuln.vulnerability_id,
                skipped=True,
            )
            verdicts.append(
                VulnerabilityVerdict(vuln.vulnerability_id, False, "Audit report missing or empty; not judged.")
            )
        return verdicts

    verdicts = []
    for vuln in vulnerabilities:
        user = build_user_message(audit_content, vuln.text_content())
        transcript.append("user", user, vulnerability_id=vuln.vulnerability_id)
        raw = client.complete(prompt, user)
        transcript.append("assistant", raw, vulnerability_id=vuln.vulnerability_id)
        result = parse_judge_result(raw)
        verdicts.append(
            VulnerabilityVerdict(vuln.vulnerability_id, result["detected"], result["reasoning"])
        )
    return verdicts
