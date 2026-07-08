"""Paper-comparability guarantees for the blind ("detect+patch") patch scaffold.

The blind scaffold must reveal NO findings / vulnerability titles / target files
(otherwise it is not comparable to the 41.5% detect+patch SOTA), and its diff
export must capture production changes anywhere the agent chose to patch — not
just the known gold target files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agents.cursor_fleet import patch_auditor, patch_auditor_blind
from openevmbench.dataset import load_patch_audit


@pytest.fixture(scope="module")
def upstream():
    root = Path("upstream/frontier-evals")
    if not root.is_dir():
        pytest.skip("upstream cache not present")
    return root


def _sample_sources(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    (src / "src").mkdir(parents=True)
    (src / "src" / "Vault.sol").write_text(
        "// SPDX-License-Identifier: MIT\ncontract Vault { function mintYieldFee(uint256 s, address r) external {} }\n",
        encoding="utf-8",
    )
    return src


def test_blind_prompt_reveals_no_findings_titles_or_targets(upstream, tmp_path):
    audit = load_patch_audit(upstream, "2023-07-pooltogether")
    prompt = patch_auditor_blind.build_prompt(audit=audit, sources=_sample_sources(tmp_path))

    # PATCH.md-style detect+patch framing is present.
    assert "audit these smart contracts and fix vulnerabilities you find" in prompt.lower()

    # No vulnerability ids, titles, target paths, or recommended-fix text leak.
    for vuln in audit.vulnerabilities:
        assert vuln.vuln_id not in prompt          # e.g. "H-04"
        assert vuln.title not in prompt            # e.g. "mintYieldFee ... any recipient"
        for target in vuln.patch_path_mapping.values():
            assert target not in prompt            # e.g. "vault/src/Vault.sol"
    # No finding-file body leaks (the recommended fix lives there).
    assert "recommended" not in prompt.lower()
    assert "Vulnerabilities to fix" not in prompt  # finding-fed section header


def test_finding_fed_prompt_DOES_leak_targets_and_findings(upstream, tmp_path):
    """Contrast: the finding-fed scaffold hands over the answer key (why it scores ~98%)."""
    audit = load_patch_audit(upstream, "2023-07-pooltogether")
    prompt = patch_auditor.build_prompt(
        audit=audit, sources=_sample_sources(tmp_path), upstream_root=upstream / "project" / "evmbench"
    )
    # It embeds the vuln title, a target path, and the recommended remediation.
    assert any(v.title in prompt for v in audit.vulnerabilities)
    assert any(t in prompt for v in audit.vulnerabilities for t in v.patch_path_mapping.values())
    assert "recommended" in prompt.lower()


def test_blind_export_captures_changes_outside_gold_target(upstream, tmp_path):
    """A blind agent may patch a file the finding-fed scaffold would never diff."""
    audit = load_patch_audit(upstream, "2023-07-pooltogether")
    ws = tmp_path / "ws"
    (ws / "vault" / "src").mkdir(parents=True)
    (ws / "vault" / "test").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=ws, check=True)
    # Base files.
    gold = ws / "vault" / "src" / "Vault.sol"
    other = ws / "vault" / "src" / "Helper.sol"      # NOT a gold target path
    test = ws / "vault" / "test" / "Exploit.t.sol"
    gold.write_text("contract Vault {}\n", encoding="utf-8")
    other.write_text("contract Helper {}\n", encoding="utf-8")
    test.write_text("contract T {}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=ws, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=ws, check=True)

    # Agent patched a non-gold-target source file and (illegally) touched a test.
    other.write_text("contract Helper { uint256 fixed_; }\n", encoding="utf-8")
    test.write_text("contract T { uint256 tampered_; }\n", encoding="utf-8")

    out = tmp_path / "out.diff"
    patch_auditor_blind.export_diff(workspace=ws, audit=audit, out_path=out)
    diff = out.read_text(encoding="utf-8")
    assert "vault/src/Helper.sol" in diff          # captured, even though not a gold target
    assert "vault/test/Exploit.t.sol" not in diff  # test edits excluded (grader restores them)


# --- Codex subscription-CLI: the run must NOT bill the OpenAI API -------------

def test_codex_cmd_excludes_api_via_ignore_user_config():
    cmd = patch_auditor_blind.build_codex_cmd("gpt-5.5", "high")
    # Primary guard: config.toml (and any `env_key` API-key redirection) is skipped.
    assert "--ignore-user-config" in cmd
    assert cmd[:2] == ["codex", "exec"]
    assert "workspace-write" in cmd            # can edit source in cwd
    assert "model_reasoning_effort=high" in cmd
    assert cmd[-1] == "-"                        # prompt on stdin
    # Never a raw API key / base-url override on the command line.
    joined = " ".join(cmd).lower()
    assert "api_key" not in joined and "api-key" not in joined


def test_codex_env_scrub_removes_all_api_keys(monkeypatch):
    # The config env_key on the reference machine + generic *_API_KEY must be gone.
    monkeypatch.setenv("ANTSEED_API_KEY", "sk-should-be-removed")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-be-removed")
    monkeypatch.setenv("SOME_OTHER_API_KEY", "sk-should-be-removed")
    monkeypatch.setenv("PATH", "/usr/bin")  # sanity: non-key vars survive
    env = patch_auditor_blind._scrub_codex_env()
    assert "ANTSEED_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "SOME_OTHER_API_KEY" not in env
    assert not any(k.endswith("_API_KEY") for k in env)
    assert env.get("PATH") == "/usr/bin"
