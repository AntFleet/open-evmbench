"""Regenerate the record fixtures under tests/fixtures/.

Run from the repo root:  .venv/bin/python tests/fixtures/generate_fixtures.py

Fixtures are deterministic (fixed timestamps, fixed submission IDs) except
the signature fields, which are produced with the TEST-ONLY keypair in
tests/fixtures/keys/ (generated on first run, then reused). Ed25519 is
deterministic, so re-running with the same keys is byte-stable.

These fixtures exercise the record PROFILES (submitted/checking/accepted/
rejected/promoted/yanked) with a small 3-vulnerability score block; they are
not full Phase 1 boards (that path is covered by the end-to-end runner test,
which produces a real 117-entry record).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent
REPO_ROOT = FIXTURES_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.signing import generate_keypair, sign_record  # noqa: E402
from openevmbench.constants import JUDGE_PROMPT_SHA256  # noqa: E402

KEYS_DIR = FIXTURES_DIR / "keys"
RECORDS_DIR = FIXTURES_DIR / "records"
PRIVATE_PEM = KEYS_DIR / "TEST_ONLY_private.pem"
PUBLIC_PEM = KEYS_DIR / "TEST_ONLY_public.pem"

T0 = "2026-06-09T00:00:00Z"
T1 = "2026-06-09T01:00:00Z"
T2 = "2026-06-09T02:00:00Z"

BASE = {
    "submission_id": "018f7f64-2c2e-7b70-8f4d-000000000001",
    "phase": 1,
    "mode": "detect",
    "created_at": T0,
    "operator": {
        "github_username": "alice",
        "github_id": 12345678,
        "affiliation": "Example Lab",
    },
    "submission": {
        "archive_hash": "sha256:" + "a" * 64,
        "archive_size_bytes": 1048576,
    },
    "benchmark": {
        "upstream_repo": "openai/frontier-evals",
        "upstream_commit": "51052ce",
        "harness_version": "detect-v1.0.0+frontier-evals.51052ce",
    },
    "agent": {
        "model": "gpt-5.3-codex",
        "scaffold_name": "example-scaffold",
        "scaffold_hash": "sha256:" + "b" * 64,
        "harness_kind": "agentic-scaffold",
    },
    "judge": {
        "model": "gpt-5",
        "params": {"reasoning_effort": "high", "temperature": 0},
        "prompt_hash": f"sha256:{JUDGE_PROMPT_SHA256}",
        "transcript_hash": "sha256:" + "c" * 64,
        "transcript_contents_or_url": "submissions/phase1/alice/018f7f64-2c2e-7b70-8f4d-000000000001/judge_transcript.jsonl",
    },
    "run": {
        "tokens_total": 1234567,
        "tokens_prompt": 1000000,
        "tokens_completion": 234567,
        "tokens_per_task": [400000, 400000, 434567],
        "wall_clock_ms": 3600000,
        "runs_count": 1,
    },
    "score": {
        "claimed_score": 0.6667,
        "solved_count": 2,
        "max_score": 3,
        "per_vulnerability": [
            {"vulnerability_id": "2023-07-pooltogether:vuln-a", "passed": True, "score": 1, "reason_code": "detected"},
            {"vulnerability_id": "2023-07-pooltogether:vuln-b", "passed": False, "score": 0, "reason_code": "not-detected"},
            {"vulnerability_id": "2023-10-nextgen:vuln-a", "passed": True, "score": 1, "reason_code": "detected"},
        ],
    },
}


def main() -> None:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    if PRIVATE_PEM.exists():
        private_pem = PRIVATE_PEM.read_bytes()
        public_pem = PUBLIC_PEM.read_bytes()
    else:
        private_pem, public_pem = generate_keypair()
        PRIVATE_PEM.write_bytes(private_pem)
        PUBLIC_PEM.write_bytes(public_pem)

    out: dict[str, dict] = {}

    out["submitted_valid"] = copy.deepcopy(BASE)

    checking = copy.deepcopy(BASE)
    checking["state"] = "checking"
    checking["state_reason"] = None
    out["checking_valid"] = checking

    accepted_base = copy.deepcopy(BASE)
    accepted_base["state"] = "accepted"
    accepted_base["state_reason"] = None
    accepted_base["score"]["official_score"] = 0.6667
    accepted_base["prize_review_status"] = None
    accepted_base["prize_review_reason"] = None
    accepted = sign_record(accepted_base, private_pem, public_pem, signed_at=T1)
    out["accepted_valid"] = accepted

    rejected = copy.deepcopy(BASE)
    rejected["state"] = "rejected"
    rejected["state_reason"] = "transcript-hash-mismatch: judge_transcript.jsonl does not match judge.transcript_hash"
    out["rejected_valid"] = rejected

    promoted = copy.deepcopy(accepted)
    promoted["state"] = "promoted"
    promoted["promoted_at"] = T2
    promoted["promoted_commit_sha"] = "abc123abc123abc123abc123abc123abc123abc1"
    out["promoted_valid"] = promoted

    yanked = copy.deepcopy(promoted)
    yanked["state"] = "yanked"
    yanked["state_reason"] = "judge transcript shown to be inconsistent with per-vulnerability results after community re-run"
    out["yanked_valid"] = yanked

    # --- negative fixtures ---

    neg = copy.deepcopy(BASE)
    del neg["judge"]
    out["neg_detect_missing_judge"] = neg

    neg = copy.deepcopy(BASE)
    neg["submission"]["archive_hash"] = "md5:abcdef"
    out["neg_bad_archive_hash"] = neg

    neg = copy.deepcopy(BASE)
    neg["submission_id"] = "9f1c1c8e-3d2a-4b5c-8d6e-7f8a9b0c1d2e"  # UUIDv4
    out["neg_bad_submission_id_version"] = neg

    neg = copy.deepcopy(BASE)
    neg["score"]["solved_count"] = 3  # only 2 passed entries
    out["neg_solved_count_mismatch"] = neg

    neg = copy.deepcopy(BASE)
    neg["score"]["per_vulnerability"][1]["vulnerability_id"] = neg["score"]["per_vulnerability"][0]["vulnerability_id"]
    out["neg_duplicate_vulnerability_id"] = neg

    neg = copy.deepcopy(BASE)
    neg["state"] = "rejected"  # missing state_reason
    out["neg_rejected_without_reason"] = neg

    neg = copy.deepcopy(accepted)
    neg["state"] = "promoted"  # missing promoted_at / promoted_commit_sha
    out["neg_promoted_missing_promotion_fields"] = neg

    neg = copy.deepcopy(accepted)  # submitted profile must not carry acceptance
    del neg["state"]
    out["neg_submitted_with_acceptance"] = neg

    neg = copy.deepcopy(BASE)
    neg["agent"]["harness_kind"] = "fully-automatic"
    out["neg_bad_harness_kind"] = neg

    neg = copy.deepcopy(BASE)
    neg["score"]["per_vulnerability"][0]["vulnerability_id"] = "no-colon-here"
    out["neg_bad_vulnerability_id_format"] = neg

    for name, record in out.items():
        path = RECORDS_DIR / f"{name}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
