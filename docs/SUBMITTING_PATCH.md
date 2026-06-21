# Submitting to Open EVMBench (Phase 2 Patch)

Phase 2 Patch is **open** — submit PRs to `submissions/phase2/...`. See
[PHASE2_LAUNCH_CHECKLIST.md](PHASE2_LAUNCH_CHECKLIST.md) for infrastructure status.

Binding contracts: [SPEC §9](SPEC.md). Phase 1 Detect guide:
[SUBMITTING.md](SUBMITTING.md).

## Overview

Patch mode is **deterministic** — no LLM judge. Your agent produces unified diffs
that fix known vulnerabilities; the harness applies each diff, runs the audit's
invariant test suite, then runs per-vulnerability exploit tests. Scoring is binary
per vulnerability (**44 tasks** on the launch pin).

**SOTA reference (not ranked):** GPT-5.3-Codex **41.5%** (OpenAI EVMbench paper,
Table 9). Reputation-only — no prize.

## Dataset

Same upstream pin as Detect:

```text
Repo:     openai/frontier-evals
Commit:   51052ce  (51052cede8cc608f95bb00346635e03759013e5a)
Split:    patch-tasks  (22 audits, 44 vulnerabilities)
Harness:  patch-v1.0.0+frontier-evals.51052ce
```

Canonical task IDs: [harness/patch_tasks_v1.json](../harness/patch_tasks_v1.json).

Fetch contract sources for your agent (same mirrors as Detect):

```bash
python scripts/fetch_audit_sources.py --out audit_sources
```

## Agent output

One unified diff per audit in the patch-tasks split, relative to each audit's
`base_commit` (same artifact upstream expects as `submission/agent.diff`):

```text
<your_outputs>/<audit-id>.diff
```

Example: `2023-07-pooltogether.diff` patches `vault/src/Vault.sol` at commit
`4240445…` (see that audit's `config.yaml`).

## Run locally

```bash
openevmbench clone
python scripts/fetch_audit_sources.py --out audit_sources
# … run your patch agent producing <audit-id>.diff files …
openevmbench run --mode patch \
  --agent-outputs <your_outputs> \
  --sources audit_sources \
  --model <your-agent-model> \
  --scaffold-name <your-scaffold> \
  --scaffold-hash "sha256:<hex>" \
  --harness-kind agentic-scaffold \
  --tokens-total <N> --tokens-prompt <N> --tokens-completion <N>
```

Host-forge grading skips the invariant suite by default (`--with-invariant` to
enable). Production acceptance requires the Docker worker (run overnight via
`scripts/docker_spike_patch_worker.py`).

## Submission package (planned)

```text
submissions/phase2/<github_handle>/<submission_id>/
  record.json
  agent_artifacts/
    <audit-id>.diff
  grade_evidence/          # optional; CI may regenerate
    <audit-id>/invariant.json
    <audit-id>/<vuln-id>.json
```

`record.json` profile:

- `phase`: `2`
- `mode`: `"patch"`
- `judge`: omitted (`null`)
- `benchmark.harness_version`: `patch-v1.0.0+frontier-evals.51052ce`
- `score.max_score`: `44`
- `score.per_vulnerability[]`: exactly the 44 IDs in `harness/patch_tasks_v1.json`

## Submit

```bash
openevmbench submit --package submissions/phase2/<you>/<submission_id>
```

Same PR + acceptance-signing path as Detect, with patch-specific automated checks
(re-run deterministic harness in CI).

## Verify

```bash
openevmbench verify --record submissions/phase2/<handle>/<id>/record.json
```

Same Ed25519 acceptance signature recipe as Phase 1 ([SPEC §4](SPEC.md)).
