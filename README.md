# Open EVMBench

*The open public leaderboard for AI smart-contract vulnerability work.*

AI-assisted code review with verifiable, reproducible results — not claims
you have to trust.

## What OpenAI published in February

OpenAI shipped [EVMbench](https://openai.com/index/introducing-evmbench/) —
a benchmark for AI agents on real smart-contract vulnerabilities pulled
from 40 audits. It tests three modes: **Detect** (find the bugs),
**Patch** (fix them), and **Exploit** (write transactions that drain funds).

The headline result: their flagship GPT-5.3-Codex hit **72.2%** on
Exploit (paper) / **71.0%** (blog). That's the number we're ultimately
gunning for.

Closed model, closed eval run, no transcripts. A benchmark designed for
verification, evaluated without any.

Four months later, the leaderboard is still a press release.

We can do better than that. Not just with our model. With everyone's.

## Open EVMBench — three leaderboards, building to the headline

Open EVMBench launches in three phases. Each phase opens a public
leaderboard against the highest-published score in that mode. The
*"Beat OpenAI"* headline lands at Phase 3 — the Exploit endgame.

| Phase | Mode | Dataset | SOTA to beat | Reported by |
|---|---|---|---|---|
| **1** | **Detect** — identify vulnerabilities | 117 vulns | **45.6%** | Anthropic — Claude Opus 4.6 |
| **2** | **Patch** — produce fixes for the identified vulnerabilities | 44 vulns | **41.5%** | OpenAI — GPT-5.3-Codex |
| **3** | **Exploit** — write transactions that drain funds | 23 vulns | **72.2%** | OpenAI — GPT-5.3-Codex |

Phase 1 stabilizes → Phase 2 opens → Phase 3 opens. Each phase carries
its own challenge against the highest published number in that mode.

## Phase 1: Detection

The first leaderboard runs **detect mode** — given a vulnerable
contract, identify the vulnerabilities present. This is the mode that
maps directly to defensive code review: catch bugs before they ship.

- **Anyone can submit.** Claude, Gemini, GPT, your jailbroken DeepSeek,
  your local Llama fine-tune. Bring a model + a prompt scaffold.
- **Everything runs on your machine.** Run the harness locally, and for
  Detect bring any judge model you want. To compare directly with
  the OpenAI EVMbench paper numbers, use `gpt-5` with `reasoning_effort=high`
  against the pinned Open EVMBench judge prompt.
- **Every accepted submission lands in a public log.** Open transcripts.
  Disclosed token budgets. Full artifacts so anyone can re-run the
  submission against the official harness. AntFleet reviews the PR,
  signs acceptance, and merges it to the public Git log.
- **Default board is the OpenAI-paper-comparable view.** `gpt-5` with
  `reasoning_effort=high` judge is the headline rank. Other judge groups have
  labeled views, and the full view shows all accepted submissions side by
  side.

Public log > announcements.

## How to submit (the short version)

1. Create a GitHub personal access token (no scopes needed — used only to bind your identity)
2. `openevmbench login <token>`
3. `openevmbench clone`
4. `openevmbench run`
5. `openevmbench submit`
6. AntFleet reviews the submission PR and signs accepted records
7. Accepted submissions land in a public Git log and on the leaderboard

Everything runs locally: agent, harness, and Detect judge. The submission
package carries your outputs, score, judge model and parameters, pinned
prompt hash, transcript evidence, and artifact hashes; the canonical package
contract is in SPEC §4, "Phase 1 submission package." AntFleet's Ed25519
acceptance signature plus public history is the inspection surface.
Patch and Exploit submissions are deterministic harness runs, so they do
not need an LLM judge.

## Beat OpenAI at Phase 3 — $1000 prize

The headline of this whole project: a public submission that beats OpenAI's
published Exploit result on the open leaderboard. $1000 to the operator
who lands it.

Phases 1 and 2 build the leaderboard — ranks live, public, reproducible —
and Phase 3 is where the prize lands. Phases 1 and 2 don't carry a prize;
the reward at every earlier phase is reputation. The cash is at the
headline.

**Phase 3 prize conditions** (all must hold):

- 30-day window from Phase 3 launch
- ≥50 counted Phase 3 operators under the SPEC anti-sybil rule
- At least one Phase 3 submission clears **OpenAI's 72.2% Exploit**
  reference — solve at least **17 of 23 exploit tasks**
- AntFleet manual review of the prize-claim submission
- AntFleet's own reference submission is excluded from prize eligibility

Winner = highest-scoring eligible Phase 3 submission at end of the 30-day
window, after AntFleet manual review.

If any condition fails (<50 counted operators, or nobody clears 17/23), the $1000
rolls over. It either moves into a future Open EVMBench prize round or
into a partial-credit pool for top submitters who attempted Phase 3. It
does not return to AntFleet.

## What spills back to DeFi builders

We're not running a contest. We're producing a public reference for what
AI can and can't currently do at smart-contract vulnerability work:

- Which model combinations catch which vulnerability classes →
  defensive playbook for protocol teams choosing AI tooling
- Which prompt scaffolds generalize vs overfit → methodology for the
  AI-for-security community
- Which vulnerabilities NO AI can solve at each phase → research targets
  for the next generation of agents
- Public submission log + open harness → a reproducible baseline future
  labs can't undercut by posing with closed benchmarks

The authoritative open reference for AI smart-contract vulnerability work.

## Live now — Phase 1 Detect is open

**Public leaderboard**: [antfleet.github.io/open-evmbench](https://antfleet.github.io/open-evmbench/)

AntFleet's reference submission opens the board at **51/117 = 43.6%**
(`claude-opus-4-8 + gpt-5.5` two-model consensus, single-shot,
`gpt-5 reasoning_effort=high` judge — paper-comparable view), sitting
2 points below the published Claude Opus 4.6 reference target and 4.4
points above GPT-5.3-Codex. The full record, judge transcript, audit
artifacts, and Ed25519 acceptance signature are inspectable in
[`submissions/phase1/antfleet-ops/`](submissions/phase1/antfleet-ops/).

**To submit your own run:** follow [`docs/SUBMITTING.md`](docs/SUBMITTING.md).
Submissions are PRs against this repo; the harness, judge prompt, and
acceptance signing are all verifiable from the public Git log.

**To follow along:** [@AntFleetDev](https://twitter.com/AntFleetDev) for
new submissions and Phase 2/3 progress. Issues and PRs against this repo
are how the community moves the board.

The more models on the board, the harder it is for the closed-eval
pattern to keep going.

## Repo layout

```
open-evmbench/
├── harness/judge_prompt_v1.md   ← pinned Detect judge prompt (hash-bound)
├── openevmbench/                ← harness wrapper, CLI, schema, signing, board
├── agents/antfleet_reference/   ← AntFleet two-model consensus agent (prize-excluded)
├── scripts/                     ← audit-source fetcher, pipeline smoke test
├── submissions/                 ← public log of accepted submissions
├── leaderboard/                 ← board config + static site renderer output
├── docs/                        ← SPEC, submitter guide, rules, keys, prize terms
└── antfleet.public_key.pem      ← AntFleet acceptance public key
```

Start here: [docs/SUBMITTING.md](docs/SUBMITTING.md) (how to run and
submit), [docs/RULES.md](docs/RULES.md) (what ranks, rejection codes),
[docs/SPEC.md](docs/SPEC.md) (binding contracts).

## Status

Phase 1 Detect is live. Submit via `openevmbench` (see
[docs/SUBMITTING.md](docs/SUBMITTING.md)) and the rules in
[docs/RULES.md](docs/RULES.md). The binding contract is
[docs/SPEC.md](docs/SPEC.md).

— [AntFleet](https://antfleet.dev)
