# AntFleet Reference Agent

Two-model consensus scaffold (SPEC §5 "AntFleet reference agent"). This is
the agent behind AntFleet's reference submission. It is:

- a real harness run, submitted through the same CLI → PR → signing →
  public-log path as every participant submission,
- marked `prize-excluded` on the board (see `prize_excluded_operators` in
  `leaderboard/board_config.json`),
- never eligible for any Open EVMBench prize.

## How it works

1. Each of two models independently audits the contract sources with the
   same auditor prompt (`AUDITOR_PROMPT`).
2. A consensus pass merges the two reports: findings both models surfaced
   rank first, single-reviewer findings follow, labeled.
3. The merged report is written as `<audit-id>/audit.md`, the artifact
   EVMbench Detect grades.

## Running

```bash
python agents/antfleet_reference/consensus_agent.py \
  --sources /path/to/audit-sources \
  --out /tmp/antfleet_outputs \
  --model-a <model-a> --base-url-a <openai-compatible-url> --key-env-a KEY_A \
  --model-b <model-b> --base-url-b <openai-compatible-url> --key-env-b KEY_B

openevmbench run --agent-outputs /tmp/antfleet_outputs \
  --model "<model-a>+<model-b> consensus" \
  --scaffold-name antfleet-two-model-consensus \
  --scaffold-hash "$(python -c "from openevmbench.hashing import sha256_file; print(sha256_file('agents/antfleet_reference/consensus_agent.py'))")" \
  --harness-kind single-shot \
  --judge-model gpt-5 --judge-param reasoning_effort=high
```

## Sourcing the audit contract trees

The benchmark's contract sources are not vendored in this repo: each upstream
audit pins a `base_commit` of the audited project and builds a Docker image
from it. Before the Week 4 dry-run, populate `--sources` with one directory
per audit ID containing the audited Solidity tree (extract from the upstream
audit Docker context or check out each project at its pinned `base_commit`).
A `scripts/fetch_audit_sources.py` helper is planned for the dry-run
(tracked as Week 4 work in the ship plan).

## Dry-run gate (SPEC §7)

The internal dry-run of this agent on Phase 1 Detect is a non-negotiable
launch gate: ≥30% → normal positioning; <30% → the row launches labeled
"current AntFleet baseline (work-in-progress)" and positioning copy is
revised. The result is published either way.
