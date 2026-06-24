from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script():
    path = Path("scripts/run_gpt55_patch.py")
    spec = importlib.util.spec_from_file_location("run_gpt55_patch", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_codex_cmd_uses_gpt55_workspace_write():
    mod = _load_script()
    cfg = mod.CodexPatchConfig(
        binary="codex",
        model="gpt-5.5",
        reasoning_effort="high",
        timeout_s=1,
        max_retries=1,
        retry_delay_s=0,
    )

    cmd = mod._codex_cmd(cfg, Path("/tmp/work"))

    assert cmd[:4] == ["codex", "exec", "--model", "gpt-5.5"]
    assert ["--sandbox", "workspace-write"] == cmd[4:6]
    assert "-C" in cmd
    assert "/tmp/work" in cmd
    assert "model_reasoning_effort=high" in cmd
    assert cmd[-1] == "-"


def test_scrub_codex_env_removes_api_keys():
    mod = _load_script()
    env = {
        "OPENAI_API_KEY": "secret",
        "OPENAI_BASE_URL": "https://api.example",
        "AZURE_OPENAI_API_KEY": "secret",
        "PATH": "/bin",
    }

    scrubbed = mod._scrub_codex_env(env)

    assert scrubbed == {"PATH": "/bin"}


def test_prepare_codex_prompt_spills_large_prompt(tmp_path):
    mod = _load_script()
    prompt = "x" * (mod.MAX_CODEX_STDIN_CHARS + 1)

    prepared = mod._prepare_codex_prompt(tmp_path, prompt)

    assert prepared == mod.SPILL_PROMPT
    assert (tmp_path / "_patch_prompt.txt").read_text(encoding="utf-8") == prompt
