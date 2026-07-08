# Paper-comparable Phase 2 Patch run via the Codex subscription CLI

How to produce the honest, SOTA-comparable Patch number using the **blind-audit**
scaffold ([`patch_auditor_blind.py`](../agents/cursor_fleet/patch_auditor_blind.py))
driven by `codex exec` on the **ChatGPT subscription** — never the OpenAI API.

Why blind: the finding-fed scaffold hands the agent the fix (97.7%, non-comparable);
the blind scaffold makes the agent detect+patch like the 41.5% SOTA. See
[PHASE2_GAMEABILITY.md §4b](PHASE2_GAMEABILITY.md).

## API exclusion — three layers (verified)

The run must bill the subscription. The scaffold enforces three independent guards:

1. **`--ignore-user-config`** (primary) — codex skips `$CODEX_HOME/config.toml`, so
   a `env_key = "<VAR>"` line cannot redirect codex to read an API key from the
   environment. Auth still resolves from `CODEX_HOME/auth.json` (subscription).
   *On this machine `config.toml` had `env_key = "ANTSEED_API_KEY"` and that var was
   set — exactly the bypass this guard closes.*
2. **env-strip** — `_scrub_codex_env()` removes `OPENAI_*`, `ANTSEED_API_KEY`, and
   **every** `*_API_KEY` from the child environment (defense in depth).
3. **probe-verify** — `assert_codex_subscription()` runs `codex login status` under
   the scrubbed env and **aborts the run** unless it reports `ChatGPT` (and never an
   API key). Runs before any audit starts.

Verify by hand any time:

```bash
codex login status          # must print: Logged in using ChatGPT
codex exec --help | grep ignore-user-config
```

## Preflight

```bash
codex login                 # ChatGPT subscription (not `--api-key`)
codex login status          # -> "Logged in using ChatGPT"
python -c "from openevmbench.upstream import ensure_upstream; ensure_upstream()"
python scripts/fetch_audit_sources.py --out audit_sources_patch --split patch-tasks
```

## Run the agent (subscription, blind)

```bash
python agents/cursor_fleet/patch_auditor_blind.py \
    --engine codex --model gpt-5.5 --reasoning-effort high \
    --sources audit_sources_patch \
    --out runs/blind-patch/diffs
    # add --only 2023-07-pooltogether for a single-audit smoke first
```

The scaffold prints `codex auth verified: ChatGPT subscription (API excluded)`
before it starts, then writes one `<audit-id>.diff` per audit (all non-test
production changes — a blind agent chooses where to patch).

## Grade (Docker, canonical amd64 — in CI, not local)

Grading is deterministic and must match upstream `PatchGrader`. Run it the same way
as the reference package, pointing at the blind diffs:

```bash
# CI (native amd64): reuse patch-reference.yml / patch-composer.yml grade path,
# or locally if Docker is available:
python scripts/run_composer_patch.py --full --skip-agent \
    --diffs runs/blind-patch/diffs \
    --operator-user antfleet-ops --operator-id 285575208
```

This packages `submissions/phase2/antfleet-ops/<sid>/` with the graded record.
Then the normal submit → check → sign → promote path.

## Expectations & caveats

- **Score will be far below 97.7%** — detection is back in the task. Expect roughly
  the Detect ballpark (SOTA Patch is 41.5%). That is the point: an honest number.
- Declare `task_mode: blind-audit` on the record; only blind-audit ranks vs 41.5%
  (`leaderboard/board_config.json`).
- `reasoning_effort=high` is the default; `xhigh` has a subscription credit ceiling.
  Record the effort in `agent.params` (reproducibility).
- `codex exec` runs one subprocess per audit in an isolated workspace with
  `--sandbox workspace-write` (edits only that workspace).
- `2025-04-virtuals` (2 vulns) remains a disclosed wide-guard audit (gameability),
  independent of task mode.
