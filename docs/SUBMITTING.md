# Submitting to Open EVMBench (Phase 1 Detect)

Everything runs on your machine: your agent, the harness, and the Detect
judge. You submit a reproducible record by PR; AntFleet reviews, signs
acceptance, and merges it into the public log. The canonical contracts are
in [SPEC §4](SPEC.md); this is the practical guide.

## 0. Install

```bash
git clone https://github.com/AntFleet/open-evmbench && cd open-evmbench
python3 -m venv .venv && .venv/bin/pip install -e .
```

## 1. Login

Create a token (during the pre-launch window: a GitHub personal access
token — no scopes needed, it only identifies you), then:

```bash
openevmbench login <token>
```

The CLI verifies the token against `api.github.com/user` and binds your
GitHub identity. Your submission PR must come from this same account: the
checks reject records whose operator doesn't match the PR author.

## 2. Clone the benchmark

```bash
openevmbench clone
```

Fetches `openai/frontier-evals@51052ce` into `upstream/` and verifies the
Detect set: 40 audits, 117 vulnerabilities. No git-lfs needed.

## 3. Run your agent

Your agent is your business — any model, any scaffold. It must produce one
markdown report per audit:

```text
<your_outputs>/<audit-id>/audit.md     (40 audits, IDs in upstream splits/detect-tasks.txt)
```

To fetch the audited contract sources for your agent:

```bash
python scripts/fetch_audit_sources.py --out audit_sources
```

Record your agent's token usage — it goes in the submission and on the board.

## 4. Judge locally and package

```bash
export OPENAI_API_KEY=...
openevmbench run \
  --agent-outputs <your_outputs> \
  --judge-model gpt-5 --judge-param reasoning_effort=high \
  --model <your-agent-model> \
  --scaffold-name <your-scaffold> \
  --scaffold-hash "sha256:<hex of your scaffold definition>" \
  --harness-kind agentic-scaffold \
  --tokens-total <N> --tokens-prompt <N> --tokens-completion <N>
```

This judges all 117 vulnerabilities with the pinned prompt
(`harness/judge_prompt_v1.md`), records the full judge transcript, and
writes a complete package:

```text
submissions/phase1/<you>/<submission_id>/
  record.json               the submitted record (SPEC §4)
  judge_transcript.jsonl    every judge call, hash-bound to the record
  agent_artifacts/          your 40 audit.md reports
```

Judge choice: any OpenAI-compatible endpooint works (`--judge-base-url`),
including local open-weights servers. Only `gpt-5` with
`reasoning_effort=high` lands on the default paper-comparable board; other
judges rank within their own judge group on the full board.

## 5. Submit

```bash
openevmbench submit --package submissions/phase1/<you>/<submission_id>
```

Runs the exact checks the PR pipeline runs (so your PR can't fail them),
then prints the branch/PR commands. After your PR passes automated checks,
AntFleet signs acceptance and merges; the promote workflow writes promotion
metadata, and the board rebuilds with your row.

## Verifying anyone's accepted record

```bash
openevmbench verify --record submissions/phase1/<handle>/<id>/record.json
```

Checks the AntFleet Ed25519 signature against `antfleet.public_key.pem`
(manual recipe: SPEC §4; key policy: docs/KEYS.md). To re-run a result,
the package contains everything: artifacts, judge model + params, pinned
prompt hash, and the full transcript.
