"""Tests for the agent.params + agent.prompt_hash board columns
(Tier 2 of the 2026-06-20 SPEC §3 amendment)."""

from __future__ import annotations

from openevmbench.board import Attempt, BoardConfig


def _base_record(extra_agent: dict | None = None) -> dict:
    agent = {
        "model": "test-model",
        "scaffold_name": "test-scaffold",
        "scaffold_hash": "sha256:" + "0" * 64,
        "harness_kind": "single-shot",
    }
    if extra_agent:
        agent.update(extra_agent)
    return {
        "submission_id": "x",
        "phase": 1,
        "mode": "detect",
        "created_at": "2026-06-20T00:00:00Z",
        "operator": {"github_username": "alice", "github_id": 1},
        "agent": agent,
        "judge": {
            "model": "gpt-5",
            "params": {"reasoning_effort": "high"},
            "prompt_hash": "sha256:judgeprompt",
        },
        "score": {"claimed_score": 0.5, "solved_count": 1, "max_score": 2,
                  "per_vulnerability": []},
        "state": "promoted",
    }


def test_agent_params_when_missing_returns_none() -> None:
    a = Attempt(record=_base_record(), path="x")
    assert a.agent_params is None
    assert a.agent_reasoning_effort is None
    assert a.agent_reasoning_label == "?"
    assert a.agent_prompt_hash is None
    assert a.agent_prompt_label == "?"


def test_agent_params_when_present_returns_value() -> None:
    a = Attempt(record=_base_record({
        "params": {"reasoning_effort": "high", "temperature": 1},
        "prompt_hash": "sha256:abcdef1234567890",
    }), path="x")
    assert a.agent_params == {"reasoning_effort": "high", "temperature": 1}
    assert a.agent_reasoning_effort == "high"
    assert a.agent_reasoning_label == "high"
    assert a.agent_prompt_hash == "sha256:abcdef1234567890"
    # short prefix should be "sha256:" + first 7 hex chars
    assert a.agent_prompt_label == "sha256:abcdef1"


def test_agent_reasoning_label_distinguishes_explicit_off_from_unknown() -> None:
    """Important for the leaderboard story: a row that ran with reasoning
    explicitly turned off (recorded as such) should render 'off', not '?'.
    Records that predate the schema amendment render '?' because we can't
    distinguish off from unknown for them."""
    a_unknown = Attempt(record=_base_record(), path="x")
    a_off = Attempt(record=_base_record({"params": {"reasoning_effort": "off"}}), path="x")
    a_none = Attempt(record=_base_record({"params": {"reasoning_effort": None}}), path="x")
    assert a_unknown.agent_reasoning_label == "?"
    assert a_off.agent_reasoning_label == "off"
    assert a_none.agent_reasoning_label == "off"


def test_strict_comparable_returns_true_without_strict_group() -> None:
    """is_strictly_comparable defaults to is_comparable when board_config
    has no strict_agent_group — keeps the default leaderboard view
    backward-compatible with existing records that lack agent.params."""
    from openevmbench import constants

    # Manually construct the judge hash so this Attempt is is_comparable
    record = _base_record()
    record["judge"]["prompt_hash"] = f"sha256:{constants.JUDGE_PROMPT_SHA256}"
    a = Attempt(record=record, path="x")
    config = BoardConfig()  # no strict_agent_group set
    assert a.is_strictly_comparable(config)


def test_strict_comparable_filters_out_when_strict_group_set() -> None:
    """With strict_agent_group configured, records missing agent.prompt_hash
    should be filtered out."""
    from openevmbench import constants

    record = _base_record()
    record["judge"]["prompt_hash"] = f"sha256:{constants.JUDGE_PROMPT_SHA256}"
    a_no_hash = Attempt(record=record, path="x")
    a_with_hash = Attempt(record=_base_record({
        "prompt_hash": "sha256:expected_hash",
        "params": {"reasoning_effort": "high"},
    }), path="x")
    a_with_hash.record["judge"]["prompt_hash"] = f"sha256:{constants.JUDGE_PROMPT_SHA256}"

    config = BoardConfig(strict_agent_group={
        "require_agent_prompt_hash": True,
        "agent_prompt_hash": "sha256:expected_hash",
        "agent_reasoning_effort": "high",
    })
    assert not a_no_hash.is_strictly_comparable(config)
    assert a_with_hash.is_strictly_comparable(config)


def test_strict_comparable_filters_on_reasoning_effort_mismatch() -> None:
    from openevmbench import constants

    base_extra = {
        "prompt_hash": "sha256:expected_hash",
        "params": {"reasoning_effort": "low"},
    }
    record = _base_record(base_extra)
    record["judge"]["prompt_hash"] = f"sha256:{constants.JUDGE_PROMPT_SHA256}"
    a = Attempt(record=record, path="x")

    config = BoardConfig(strict_agent_group={
        "agent_reasoning_effort": "high",
    })
    assert not a.is_strictly_comparable(config)


# --- Backfill via leaderboard/historical_agent_metadata.json -----------------


def test_backfill_used_when_record_lacks_params(monkeypatch) -> None:
    """When the record predates 2026-06-20 schema, the historical
    backfill map provides the values for display."""
    from openevmbench import board as board_mod

    # Monkeypatch the loaded map for this test
    record = _base_record()
    record["submission_id"] = "test-uuid-abc"
    monkeypatch.setattr(board_mod, "_HISTORICAL_AGENT_METADATA", {
        "test-uuid-abc": {
            "params": {"reasoning_effort": "medium"},
            "prompt_hash": "sha256:backfilledprompt",
        }
    })
    a = Attempt(record=record, path="x")
    assert a.agent_reasoning_effort == "medium"
    assert a.agent_reasoning_label == "medium"
    assert a.agent_params_source == "backfill"
    assert a.agent_prompt_hash == "sha256:backfilledprompt"
    assert a.agent_prompt_hash_source == "backfill"


def test_recorded_params_take_precedence_over_backfill(monkeypatch) -> None:
    """If the record itself has agent.params (new schema), use those —
    backfill is for old records only."""
    from openevmbench import board as board_mod

    record = _base_record({
        "params": {"reasoning_effort": "high"},
        "prompt_hash": "sha256:fromrecord",
    })
    record["submission_id"] = "test-uuid-xyz"
    monkeypatch.setattr(board_mod, "_HISTORICAL_AGENT_METADATA", {
        "test-uuid-xyz": {
            "params": {"reasoning_effort": "low"},  # different value
            "prompt_hash": "sha256:fromhistorical",
        }
    })
    a = Attempt(record=record, path="x")
    assert a.agent_reasoning_effort == "high"
    assert a.agent_params_source == "record"
    assert a.agent_prompt_hash == "sha256:fromrecord"
    assert a.agent_prompt_hash_source == "record"


def test_api_default_renders_as_api_def(monkeypatch) -> None:
    """``api-default`` is the marker used for Virtuals/OpenRouter rows
    where no reasoning block was sent and the API picks per-model. It
    renders as ``api-def`` to stay short in the table."""
    from openevmbench import board as board_mod

    record = _base_record()
    record["submission_id"] = "api-default-test"
    monkeypatch.setattr(board_mod, "_HISTORICAL_AGENT_METADATA", {
        "api-default-test": {"params": {"reasoning_effort": "api-default"}},
    })
    a = Attempt(record=record, path="x")
    assert a.agent_reasoning_label == "api-def"


def test_real_historical_backfill_covers_all_promoted_submissions() -> None:
    """Sanity check on the actual leaderboard/historical_agent_metadata.json:
    every submission_id in submissions/ should either have agent.params
    recorded directly OR be covered by the backfill map. No record should
    fall through to '?'."""
    import json as _json
    from pathlib import Path

    backfill_path = Path("leaderboard/historical_agent_metadata.json")
    if not backfill_path.is_file():
        # In the test isolation case, the file isn't present — skip.
        return

    backfilled_ids = set(_json.loads(backfill_path.read_text())["submissions"].keys())
    submissions_root = Path("submissions/phase1/antfleet-ops")
    if not submissions_root.is_dir():
        return
    for record_json in submissions_root.glob("*/record.json"):
        record = _json.loads(record_json.read_text())
        sub_id = record["submission_id"]
        agent = record.get("agent") or {}
        has_recorded = bool(agent.get("params") and agent.get("prompt_hash"))
        has_backfilled = sub_id in backfilled_ids
        assert has_recorded or has_backfilled, (
            f"submission {sub_id} ({agent.get('model')}) has neither "
            f"agent.params recorded nor a historical backfill entry"
        )
