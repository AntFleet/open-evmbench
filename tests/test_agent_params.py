"""Test agent.params + agent.prompt_hash schema amendment (2026-06-20)."""

from __future__ import annotations

from openevmbench.package import AgentInfo, _agent_block


BASE_FIELDS = {
    "model": "test-model",
    "scaffold_name": "test-scaffold",
    "scaffold_hash": "sha256:" + "a" * 64,
    "harness_kind": "single-shot",
}


def test_agent_block_omits_optional_fields_when_unset() -> None:
    """Records without params or prompt_hash should serialize the legacy
    four fields verbatim — no `params: null` or `prompt_hash: null`
    sneaking into the JSON, which would trip strict schema validators
    on older readers."""
    agent = AgentInfo(**BASE_FIELDS)
    block = _agent_block(agent)
    assert set(block.keys()) == set(BASE_FIELDS.keys())
    assert "params" not in block
    assert "prompt_hash" not in block


def test_agent_block_includes_params_when_set() -> None:
    agent = AgentInfo(**BASE_FIELDS, params={"reasoning_effort": "high"})
    block = _agent_block(agent)
    assert block["params"] == {"reasoning_effort": "high"}
    assert "prompt_hash" not in block


def test_agent_block_includes_prompt_hash_when_set() -> None:
    agent = AgentInfo(**BASE_FIELDS, prompt_hash="sha256:" + "b" * 64)
    block = _agent_block(agent)
    assert block["prompt_hash"] == "sha256:" + "b" * 64
    assert "params" not in block


def test_agent_block_includes_both_when_both_set() -> None:
    agent = AgentInfo(
        **BASE_FIELDS,
        params={"reasoning_effort": "high", "temperature": 0.7},
        prompt_hash="sha256:" + "c" * 64,
    )
    block = _agent_block(agent)
    assert block["params"]["reasoning_effort"] == "high"
    assert block["params"]["temperature"] == 0.7
    assert block["prompt_hash"] == "sha256:" + "c" * 64


def test_agent_block_empty_params_dict_treated_as_unset() -> None:
    """An empty params dict shouldn't add the field — same outcome as
    None. Prevents accidental ``"params": {}`` noise in records."""
    agent = AgentInfo(**BASE_FIELDS, params={})
    block = _agent_block(agent)
    assert "params" not in block


def test_agent_block_field_order_stable() -> None:
    """The four legacy fields appear first in deterministic order; the
    optional fields come after. Stable order helps record diffs stay
    readable across schema-version transitions."""
    agent = AgentInfo(
        **BASE_FIELDS,
        params={"reasoning_effort": "high"},
        prompt_hash="sha256:" + "d" * 64,
    )
    block = _agent_block(agent)
    keys = list(block.keys())
    assert keys[:4] == ["model", "scaffold_name", "scaffold_hash", "harness_kind"]
    assert keys[4:] == ["params", "prompt_hash"]
