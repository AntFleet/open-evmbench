# Open EVMBench SPEC v1.1

Date: 2026-06-12

Open EVMBench is AntFleet's open public leaderboard for AI smart-contract vulnerability work. Phase 1 ships Detect, Phase 2 adds Patch, and Phase 3 adds Exploit with the public "Beat OpenAI at Phase 3" prize run.

The v1 operating model is intentionally simple: GitHub identity, self-verifying local submissions, AntFleet-signed acceptance records, and a public Git log of accepted submissions. Submitters run the agent, harness, and any Detect judge locally, then submit a reproducible record by pull request or by a CLI that opens the pull request. AntFleet reviews the record, signs acceptance, and merges it into the public log; reproducibility, not a central scoring service, is the trust anchor.

This SPEC is written for a from-zero, open-source build in `github.com/AntFleet/open-evmbench`. It does not claim reuse or porting from any prior project.

Primary sources for v1:

- Open EVMBench repo README, current public framing of record: `README.md`.
- EVMbench public source, Apache 2.0, `openai/frontier-evals` commit `51052ce`, `project/evmbench`.
- EVMbench paper Table 9 for per-mode public reference scores: Detect 45.6% SOTA by Claude Opus 4.6, Patch 41.5% SOTA by GPT-5.3-Codex, and Exploit 72.2% SOTA by GPT-5.3-Codex.
- EVMbench maintained-home note in source README: as of 2026-04-08, `paradigmxyz/evmbench` is the maintained home. Phase 1 launch remains pinned to the verified `openai/frontier-evals` commit; future source migrations create new versioned boards rather than rewriting old rankings.

## 1. Project Definition

### What Open EVMBench is

Open EVMBench is AntFleet's open public leaderboard for AI smart-contract vulnerability work, beginning with EVMbench Detect mode.

It is a public reference surface for answering:

- Which operators can produce reproducible AI vulnerability-detection results on the public EVMbench task set?
- Which model and scaffold combinations solve which vulnerabilities under disclosed token usage?
- Which claims are backed by public submissions, reproducible artifacts, judge metadata, AntFleet acceptance signatures, and a public Git log rather than closed benchmark announcements?

The project matches AntFleet's positioning: AI-assisted code review with verifiable, reproducible results.

### What Open EVMBench is not

Open EVMBench is not:

- A new benchmark dataset.
- A replacement for EVMbench.
- A closed evaluation service.
- A contest where unverified screenshots, private transcripts, or unverifiable vendor claims rank beside self-verifying submissions.
- A claim that AI agents can replace audits.
- A Phase 2 or Phase 3 implementation in the Phase 1 launch. Those phases are roadmapped here.

### Phase 1 success criteria

Phase 1 is successful when:

- The Detect leaderboard runs against the full public EVMbench Detect task set: 40 audits and 117 runnable vulnerabilities.
- Each ranked submission has GitHub identity, declared model and scaffold metadata, token metadata, artifact hashes, and per-vulnerability grading output.
- The default leaderboard view is `Phase 1 Detect - Ranked operators`.
- The published Detect SOTA, Claude Opus 4.6 at 45.6%, appears as the Phase 1 reference target, not a ranked participant.
- OpenAI's published GPT-5.3-Codex Detect result, 39.2%, appears as a secondary reference target where useful for context.
- AntFleet's own reference submission appears as a real run but is marked `prize-excluded`.
- Phase 1 is reputation-only: operators compete to beat the Detect SOTA on a validated public board, with no Phase 1 prize.
- A third party can inspect the public Git log, artifacts, metadata, judge transcript when applicable, accepted score, and AntFleet acceptance signature.

### Three-phase vision

Open EVMBench launches as three related public leaderboards:

```text
Phase   Leaderboard   Task                                  Security workflow
-----   -----------   ------------------------------------  ------------------------------
1       Detect        Identify vulnerabilities              Catch bugs before they ship
2       Patch         Produce fixes for found issues        Suggest the right fix
3       Exploit       Write transactions that drain funds   Verify the bug is real
```

Each phase targets the highest published score in that mode. The "Beat OpenAI" headline lands at Phase 3 because GPT-5.3-Codex's 72.2% Exploit result is the SOTA there; Phase 1 and Phase 2 are reputation-building leaderboards without prizes.

All three phases share:

- Participant-driven leaderboard identity.
- GitHub handle as the primary public identity.
- GitHub OAuth plus API token submission UX.
- One submission record schema with submitted, accepted, and promoted profiles.
- One best row per GitHub identity per phase on the default ranked board.
- Attempt history behind each operator row.
- Per-task credit and per-vulnerability result surfaces.
- Reference target rows for published claims that were not submitted through Open EVMBench.
- AntFleet reference submissions that are visible, reproducible through the same self-verifying path, and prize-excluded.
- Public Git log of accepted submissions as a public audit trail maintained by AntFleet for external inspection.
- AntFleet Ed25519 acceptance signatures as proof that AntFleet accepted a submitted record at a specific timestamp.

## 2. Phase 1 Bench Parameters

### Dataset

Phase 1 uses EVMbench Detect mode from `openai/frontier-evals` commit `51052ce`, `project/evmbench`.

Verified source facts:

```text
Source path                                                     Fact
--------------------------------------------------------------  -----------------------------------------
project/evmbench/splits/all.txt                                40 audit IDs for the Detect task set
project/evmbench/evmbench/nano/eval.py                         Public eval split name is `detect-tasks`
project/evmbench/evmbench/audit.py                             Audit.vulnerabilities drives task count
detect task audit configs/findings, excluding template scaffolds 117 runnable vulnerabilities across Detect audits
project/evmbench/README.md                                     Apache 2.0 public EVMbench project
```

Phase 1 benchmark parameters:

```text
Mode:             detect
Audit split:      detect-tasks
Audit count:      40
Runnable vulnerability count: 117
Task granularity: per vulnerability
Scoring unit:     binary per vulnerability
Submission artifact graded by EVMbench: submission/audit.md
```

### Judge

EVMbench Detect mode uses an LLM judge.

Verified source facts from `project/evmbench/evmbench/nano/runtime.py` and `project/evmbench/evmbench/nano/grade/detect.py` at commit `51052ce`:

- Default judge model is `gpt-5`.
- Default judge `reasoning_effort` is `high`.
- The judge is invoked through `OpenAICompletionsTurnCompleter`.
- The judge uses structured output shaped as `JudgeResult`.
- Detect grading calls the judge once per vulnerability per audit run.
- Each `JudgeResult.detected` boolean becomes a per-vulnerability score of `1` or `0`.

Open EVMBench vendors the official EVMbench Detect judge prompt as `harness/judge_prompt_v1.md` and pins its SHA256 hash in every Detect submission. The submitter chooses the LLM model and parameters used to run that prompt locally. Valid judge choices include hosted frontier models, other commercial models, and local open-weights models.

Scores are directly comparable within each judge model and parameter group. The default leaderboard view filters to submissions comparable to OpenAI's paper configuration: `gpt-5` with `reasoning_effort="high"` and the pinned judge prompt. Other Detect submissions are valid but must show the judge model and parameters as visible leaderboard columns.

### Scoring

Phase 1 score:

```text
score_raw = count(vulnerability_results where passed == true)
max_score = 117
score_pct = score_raw / 117 * 100
```

The leaderboard displays both percentage and solved count, for example:

```text
72.6%  85/117
```

Per-audit scores are secondary. Ranking is by full-run per-vulnerability score on the declared phase and harness version.

Tie-breakers for the default launch board:

1. Higher official score.
2. Lower `run.tokens_total`.
3. Earlier `promoted_at`.
4. Lower `submission_id` as a final stable fallback.

Rank movement, climb history, first-solver pages, threshold moments, and score-history tabs are Phase 1 launch features. They are derived from the public Git log and do not change the tie-breaker contract.

### Reference target

The Phase 1 Detect reference target is the highest published Detect score from EVMbench paper Table 9:

```text
Reference model claim: Claude Opus 4.6
Reported by:           Anthropic
Paper score:           45.6%
Leaderboard treatment: reference target row, not ranked
Submission treatment:  no Open EVMBench submission
Token budget:          undisclosed
Validation status:     reference claim; no Open EVMBench submission
```

Secondary Detect reference from Table 9:

```text
Reference model claim: GPT-5.3-Codex
Reported by:           OpenAI
Paper score:           39.2%
Leaderboard treatment: optional secondary reference row, not ranked
Submission treatment:  no Open EVMBench submission
```

Phase 1 has no prize threshold. "Clearing the Phase 1 target" means scoring above the published Detect SOTA of 45.6% on the 117-runnable-vulnerability Detect set.

## 3. Fair-Comparison Rule v1

### Rule statement

A ranked Open EVMBench result is comparable when one submission record binds:

- GitHub operator identity.
- Phase and mode.
- Benchmark upstream repo, upstream commit, and Open EVMBench harness version.
- Uploaded archive hash and size.
- Model, scaffold name, scaffold hash, and harness kind.
- Detect judge model, parameters, pinned prompt hash, transcript hash, and transcript contents or URL when mode is `detect`.
- Prompt, completion, total, and per-task token counts.
- Claimed local score.
- Official score accepted by AntFleet after automated checks and acceptance signing.
- Per-vulnerability results.
- Current lifecycle state.

Detect scores are comparable within each judge group. The default Detect board filters to the OpenAI-paper-comparable judge group: `gpt-5` with `reasoning_effort="high"` and the pinned `harness/judge_prompt_v1.md` hash. The full board shows all accepted submissions and makes the judge model a visible column.

Patch and Exploit scores are deterministic harness results and do not require an LLM judge.

The default competitive unit is:

```text
operator.github_id + phase + harness_version
```

The default board shows one best accepted row per immutable GitHub identity per phase for the active launch harness version. The current GitHub handle remains the displayed public label, but ranking, deduplication, and attempt history are keyed by `operator.github_id` so handle renames do not split or collide identity history. Attempts remain inspectable on operator, model, scaffold, and task detail pages.

### Token display only

Open EVMBench does not classify submissions by token budget.

Each row shows:

- Official score.
- Total tokens.
- Prompt tokens.
- Completion tokens.
- Per-task token distribution.
- Harness kind: `single-shot`, `retry-loop`, or `agentic-scaffold`.

Viewers can compare high-score, low-token, low-latency, single-shot, or agentic-scaffold rows according to their own priorities. Prize eligibility is not tied to token-budget classification.

### Identity and prize disclosure

Public ranked rows use GitHub identity as the displayed operator identity. A ranked row must be bound to a verified GitHub account, identified by the displayed handle plus the immutable numeric `github_id` from the GitHub API. Ranking, deduplication, and attempt history are keyed by `github_id`; the handle is display text and PR path text only.

The v1 identity token is a standard GitHub personal access token (no scopes required — only `GET /user` is called to bind identity). The CLI verifies the token against `api.github.com/user`, stores `(github_username, github_id, token)` locally at `~/.config/openevmbench/credentials.json` (mode 0600), and the automated PR checks enforce that the record's `operator.github_id` matches the PR author's id reported by GitHub. A bespoke 30-day-token web service with create/renew/revoke endpoints is deferred to a post-launch upgrade; switching to it does not require a record-schema change, because the schema binds `github_id`, not the token.

Public real-name disclosure is not required for Phase 1 or Phase 2 ranked rows. Phase 3 prize claims require a private operator-of-record suitable for payout, tax, sanctions, and one-account enforcement review. Counted Phase 3 operators are subject to the anti-sybil rule in §10. Whether public real-name disclosure is required for the Phase 3 prize remains open.

### Manual review scope

Open EVMBench v1 has one manual review process: Phase 3 prize claim review.

Phase 1 and Phase 2 accepted rows are published after automated PR checks and AntFleet acceptance signing. Phase 3 accepted rows follow the same path, but any $1000 prize claim receives AntFleet manual review before payout approval.

Manual prize review checks:

- GitHub identity and private operator-of-record.
- Source pin and harness version.
- Archive hash, size, and artifact sanity.
- Official score recomputation or replay evidence.
- Detect judge transcript and prompt-hash evidence when the prize claim depends on Detect-mode judging.
- Model and scaffold declaration.
- Token metadata.
- Phase 3 safety and payout eligibility.
- AntFleet exclusion.

### Publication

Accepted submissions publish immediately. There is no default transcript delay window and no public redaction queue in v1.

Rejected submissions are public by default with a reason code unless AntFleet determines publication would expose secrets, abuse payloads, or harmful content. The normal rejection state is still visible to the submitter and counted in attempt history.

### Acceptance status

`accepted` means the submitted record passed AntFleet's lightweight checks for the declared phase and harness version and was signed by AntFleet's acceptance key.

There are no public reproduction status levels. Submissions are self-verifying: submitters publish the artifacts, score, judge metadata when applicable, and transcript evidence needed for anyone to re-run the result. AntFleet's acceptance signature says that AntFleet accepted the record at a timestamp; the public Git log and reproducibility are the verification surface. Phase 3 prize claims add manual review before payout.

### Reference entry handling

Phase-specific published claims are reference targets, not ranked competitors. For Phase 1, the Detect SOTA target is Claude Opus 4.6:

```text
Rank cell:       Target
Operator cell:   Anthropic published Claude Opus 4.6 Detect SOTA target
Score cell:      45.6% paper
Submission cell: No Open EVMBench submission
Tokens/task:     undisclosed
Prize status:    never eligible
```

OpenAI's published GPT-5.3-Codex Detect result, 39.2%, may render as a secondary Phase 1 reference row. The GPT-5.3-Codex 72.2% paper / 71.0% blog result belongs to Phase 3 Exploit and must not be shown as a Phase 1 target.

If Anthropic, OpenAI, their operators, or any other organization submits through Open EVMBench, that submission becomes a normal ranked row under its operator or organization. Earlier paper and blog claims remain reference targets.

AntFleet's own reference submission:

- Is a real harness run.
- Uses AntFleet's two-model consensus reference agent.
- Appears inline on the board.
- Is marked `prize-excluded`.
- Never receives any Open EVMBench prize.

### Prize scope

Phase 1 is reputation-only. Phase 2 is also reputation-only. The $1000 prize lives entirely in Phase 3 Exploit and is specified in §10.

Phase 3 prize qualification requires:

- Full 30-day prize window.
- At least 50 counted Phase 3 operators under the anti-sybil rule in §10.
- At least 17 of 23 runnable Exploit vulnerabilities cleared.
- GitHub operator identity.
- Private operator-of-record and payout review.
- AntFleet manual review of the prize claim.
- AntFleet excluded from prize eligibility.

## 4. Submission Schema v1

### Submission record profiles

Open EVMBench v1 uses one JSON record per submission. The same base shape is used for Detect, Patch, and Exploit, with phase-specific fields allowed inside per-vulnerability entries when needed.

`submission_id` is a UUIDv7 assigned per submission. It is not derived from record content.

Submitters create the `submitted_record` from a local run, including the claimed score and all artifacts required to re-run the result. AntFleet adds acceptance and promotion fields during review and merge. Accepted records are signed, promoted into the public Git log, and rendered on the leaderboard. AntFleet maintains the public repository; external reproducibility plus public history is the verification surface, not a cryptographic append-only guarantee.

#### `submitted_record`

`submitted_record` is the record the submitter packages and opens in a PR. `state` is implicitly `submitted` on PR creation and is not included in the submitted file.

Required submitter-populated fields:

```json
{
  "submission_id": "018f7f64-2c2e-7b70-8f4d-000000000001",
  "phase": 1,
  "mode": "detect",
  "created_at": "2026-06-09T00:00:00Z",
  "operator": {
    "github_username": "alice",
    "github_id": 12345678,
    "affiliation": "Example Lab"
  },
  "submission": {
    "archive_hash": "sha256:...",
    "archive_size_bytes": 1048576,
    "note_hash": "sha256:..."
  },
  "benchmark": {
    "upstream_repo": "openai/frontier-evals",
    "upstream_commit": "51052ce",
    "harness_version": "detect-v1.0.0+frontier-evals.51052ce"
  },
  "agent": {
    "model": "gpt-5.3-codex",
    "scaffold_name": "example-scaffold",
    "scaffold_hash": "sha256:...",
    "harness_kind": "agentic-scaffold"
  },
  "judge": {
    "model": "gpt-5",
    "params": {
      "reasoning_effort": "high",
      "temperature": 0
    },
    "prompt_hash": "sha256:...",
    "transcript_hash": "sha256:...",
    "transcript_contents_or_url": "submissions/phase1/alice/018f7f64-2c2e-7b70-8f4d-000000000001/judge_transcript.jsonl"
  },
  "run": {
    "tokens_total": 1234567,
    "tokens_prompt": 1000000,
    "tokens_completion": 234567,
    "tokens_per_task": [12345],
    "wall_clock_ms": 3600000,
    "runs_count": 1
  },
  "score": {
    "claimed_score": 0.456,
    "solved_count": 53,
    "max_score": 117,
    "per_vulnerability": [
      {
        "vulnerability_id": "audit-id:vulnerability-id",
        "passed": true,
        "score": 1,
        "reason_code": "detected"
      }
    ]
  }
}
```

Submitter field rules:

- `phase` is `1`, `2`, or `3`.
- `mode` is `detect`, `patch`, or `exploit`.
- `operator.github_username` and `operator.github_id` are required; `operator.affiliation` is optional.
- `submission.archive_hash` and `submission.archive_size_bytes` are required; `submission.note_hash` is optional.
- `agent.harness_kind` is one of `single-shot`, `retry-loop`, or `agentic-scaffold`.
- `judge` is required for Detect submissions. Patch and Exploit omit `judge` unless a future phase adds judge-backed scoring.
- `judge.model` records the model used by the submitter to run the pinned Detect judge prompt.
- `judge.params` records material judge parameters such as `reasoning_effort`, temperature, top-p, seed, or provider-specific equivalents.
- `judge.prompt_hash` is the SHA256 hash of the vendored `harness/judge_prompt_v1.md`.
- `judge.transcript_hash` is the SHA256 hash of the judge transcript evidence.
- `judge.transcript_contents_or_url` contains the transcript contents or a stable URL/path to the transcript. Phase 1 PR packages use `judge_transcript.jsonl`.
- `run.tokens_per_task[]` records the token count used for each task or vulnerability unit where available.
- `score.claimed_score` is submitter-reported local score and must match `score.solved_count / score.max_score` for Detect submissions.
- `score.solved_count`, `score.max_score`, and `score.per_vulnerability[]` are required for every submitted record.
- `score.per_vulnerability[]` stores phase-specific result details while preserving `vulnerability_id`, `passed`, and `score`. For Phase 1 Detect, each entry is limited to `vulnerability_id`, `passed`, `score`, and optional `reason_code`; `score` is the binary integer `0` or `1`.

#### `accepted_record`

`accepted_record` is the submitted record plus AntFleet-populated acceptance fields:

```json
{
  "state": "accepted",
  "state_reason": null,
  "score": {
    "official_score": 0.456
  },
  "antfleet_acceptance": {
    "signature": "ed25519:...",
    "acceptance_record_hash": "sha256:...",
    "signed_at": "2026-06-09T01:00:00Z",
    "public_key_fingerprint": "sha256:..."
  },
  "prize_review_status": null,
  "prize_review_reason": null
}
```

Acceptance field rules:

- `state` is `accepted` when AntFleet accepts the submission and `rejected` when checks fail.
- `state_reason` is required when `state` is `rejected` or `yanked`; otherwise it is null.
- `score.official_score` is the score AntFleet accepted after automated checks and signing. For Detect, it is derived from the submitted ledger as `round(score.solved_count / score.max_score, 4)` after exact pinned vulnerability-ID coverage and transcript spot-checks pass. For Patch and Exploit, AntFleet re-runs the deterministic harness before acceptance.
- `antfleet_acceptance.signature` is an Ed25519 signature over the signed payload defined below.
- `antfleet_acceptance.acceptance_record_hash` is the SHA256 hash of the exact signed payload bytes.
- `antfleet_acceptance.signed_at` is an RFC 3339 timestamp added after signing and is not part of the signed payload.
- `antfleet_acceptance.public_key_fingerprint` is the SHA256 fingerprint of `antfleet.public_key.pem`, added after signing and not part of the signed payload.
- `prize_review_status` and `prize_review_reason` are AntFleet-populated Phase 3-only fields used during prize-claim review.

Signed payload:

- Start from the submission record AntFleet is accepting.
- Omit the entire `antfleet_acceptance` object.
- If verifying a later `promoted` or `yanked` record, normalize it back to acceptance-time form before canonicalization: set `state` to `accepted`, set `state_reason` to null, and remove `promoted_at` and `promoted_commit_sha`.
- JCS-canonicalize the omitted-record object.
- `antfleet_acceptance.acceptance_record_hash` is SHA256 over those canonical bytes.
- `antfleet_acceptance.signature` is the Ed25519 signature over those same canonical bytes, using the published AntFleet acceptance keypair.

Signature scope note: `promoted_at`, `promoted_commit_sha`, and a yanked record's post-acceptance `state_reason` are not covered by the acceptance signature. They are public Git-log lifecycle metadata. The signature attests to AntFleet's acceptance-time record, not to later promotion or yank metadata.

Third-party verification recipe:

1. Read the accepted, promoted, or yanked `record.json`.
2. Remove the entire `antfleet_acceptance` object.
3. If `state` is `promoted` or `yanked`, normalize the payload to acceptance-time form: set `state` to `accepted`, set `state_reason` to null, and remove `promoted_at` and `promoted_commit_sha`.
4. JCS-canonicalize the remaining JSON object to bytes.
5. Compute SHA256 over those bytes and compare it to `antfleet_acceptance.acceptance_record_hash`.
6. Load the published `antfleet.public_key.pem`.
7. Verify `antfleet_acceptance.signature` as an Ed25519 signature over the same canonical bytes.

#### `promoted_record`

`promoted_record` is the accepted record after AntFleet merges it into the public Git log. AntFleet adds:

```json
{
  "state": "promoted",
  "promoted_at": "2026-06-09T01:00:00Z",
  "promoted_commit_sha": "abc123..."
}
```

Promotion field rules:

- `promoted_at` is the RFC 3339 timestamp when AntFleet promotes the accepted submission into the public Git log.
- `promoted_commit_sha` is the public Git commit that contains the promoted record.

### Phase 1 submission package

Phase 1 submitters open a PR with exactly one submission directory:

```text
submissions/phase1/<github_handle>/<submission_id>/
  record.json
  judge_transcript.jsonl
  agent_artifacts/
    audit.md
    (optional supporting files)
```

`record.json` is the `submitted_record` profile. Detect submissions include `judge`; Patch and Exploit do not use this Phase 1 package.

`judge_transcript.jsonl` is a JSON-lines transcript of the Detect judge run, one JSON object per line. Each line must contain `ts`, `role`, and `content`. `judge.transcript_hash` is SHA256 over the UTF-8 bytes of the entire `judge_transcript.jsonl` file, exactly as submitted.

Hash inputs:

- `judge.prompt_hash`: SHA256 over the UTF-8 bytes of the pinned `harness/judge_prompt_v1.md` file.
- `judge.transcript_hash`: SHA256 over the UTF-8 bytes of `judge_transcript.jsonl`.
- `submission.archive_hash`: SHA256 over the portable artifacts-manifest serialization of `agent_artifacts/` (scheme `openevmbench-artifacts-manifest-v1`: domain-separator header, then for each regular file sorted by relative POSIX path, `uint32_be(len(rel_path)) || rel_path || uint64_be(len(content)) || content`). Recipe in `openevmbench/package.py:deterministic_archive`. The scheme was changed from a tar.gz hash in v1.2 because the tar.gz bytes varied across (OS, Python, zlib) combos, breaking cross-environment verification (Issue #10).
- `submission.note_hash`: SHA256 over `agent_artifacts/audit.md` when present.
- Any supporting artifact hash is SHA256 over the exact bytes of that artifact.

The submitter opens a PR against the public `antfleet/open-evmbench` repo adding only files under their submission directory. AntFleet PR review confirms the layout, `record.json` schema, hashes, transcript, and declared judge model and parameters.

`openevmbench submit` performs local validation before opening the PR. It checks the schema, required hashes, Detect `judge` field presence, `judge.prompt_hash` against pinned `harness/judge_prompt_v1.md`, `judge.transcript_hash` against `judge_transcript.jsonl`, artifact hashes against file bytes, and PR path containment under the submitter's submission directory.

Minimal Phase 1 `record.json` shape:

```json
{
  "submission_id": "018f7f64-2c2e-7b70-8f4d-000000000001",
  "phase": 1,
  "mode": "detect",
  "created_at": "2026-06-09T00:00:00Z",
  "operator": {
    "github_username": "alice",
    "github_id": 12345678
  },
  "submission": {
    "archive_hash": "sha256:PLACEHOLDER_ARCHIVE_HASH",
    "archive_size_bytes": 1048576,
    "note_hash": "sha256:PLACEHOLDER_AUDIT_MD_HASH"
  },
  "benchmark": {
    "upstream_repo": "openai/frontier-evals",
    "upstream_commit": "51052ce",
    "harness_version": "detect-v1.0.0+frontier-evals.51052ce"
  },
  "agent": {
    "model": "gpt-5.3-codex",
    "scaffold_name": "example-scaffold",
    "scaffold_hash": "sha256:PLACEHOLDER_SCAFFOLD_HASH",
    "harness_kind": "agentic-scaffold"
  },
  "judge": {
    "model": "gpt-5",
    "params": {
      "reasoning_effort": "high",
      "temperature": 0
    },
    "prompt_hash": "sha256:PLACEHOLDER_PROMPT_HASH",
    "transcript_hash": "sha256:PLACEHOLDER_TRANSCRIPT_HASH",
    "transcript_contents_or_url": "submissions/phase1/alice/018f7f64-2c2e-7b70-8f4d-000000000001/judge_transcript.jsonl"
  },
  "run": {
    "tokens_total": 1234567,
    "tokens_prompt": 1000000,
    "tokens_completion": 234567,
    "tokens_per_task": [12345],
    "wall_clock_ms": 3600000,
    "runs_count": 1
  },
  "score": {
    "claimed_score": 0.456,
    "solved_count": 53,
    "max_score": 117,
    "per_vulnerability": [
      {
        "vulnerability_id": "audit-id:vulnerability-id",
        "passed": true,
        "score": 1,
        "reason_code": "detected"
      }
    ]
  }
}
```

State values:

```text
submitted  Submission PR or CLI-created package received.
checking   Automated PR checks or acceptance review are running.
accepted   Submission checks passed and AntFleet acceptance signature was produced.
rejected   Automated checks failed, acceptance review failed, or the submission is invalid.
promoted   Accepted submission has been committed to the public Git log.
yanked     Previously promoted submission was later invalidated.
```

Normal lifecycle:

```text
submitted -> checking -> accepted -> promoted
submitted -> checking -> rejected
promoted -> yanked
```

There is no formal transition matrix. AntFleet updates state as needed and records a human-readable `state_reason` for rejected or yanked submissions.

### Claimed score vs official score

`score.claimed_score` records what the submitter reported from the local run. `score.official_score` records what AntFleet accepted after checking the submitted evidence and signing the record.

The leaderboard ranks by official score. The UI may show claimed-vs-official deltas to explain deterministic re-run differences, Detect transcript corrections, or yanks.

## 5. Substrate Components To Build From Zero (Phase 1 Only)

### Harness wrapper around EVMbench Detect mode

Purpose: run the public EVMbench Detect task set locally and extract stable artifacts for submission packaging, acceptance checks, and leaderboard rendering.

Responsibilities:

- Pin upstream EVMbench source to `openai/frontier-evals` commit `51052ce` for launch board `detect-v1.0.0+frontier-evals.51052ce`.
- Verify the Detect split has 40 audits and 117 runnable vulnerabilities.
- Run Detect mode against a submitted `submission/audit.md`.
- Extract per-vulnerability results.
- Normalize task IDs, audit IDs, and vulnerability IDs for stable leaderboard display.
- Record archive hash, archive size, token counts, wall-clock time, run count, and harness version.
- Vendor the pinned Detect judge prompt as `harness/judge_prompt_v1.md`.
- Run the pinned judge prompt locally with the submitter's chosen judge model and parameters.
- Package judge metadata, prompt hash, transcript hash, transcript contents or URL, score, and per-vulnerability results.
- Support submitter local runs and AntFleet acceptance checks with the same wrapper.

### Judge integration

Purpose: make Detect judging self-verifying while preserving an OpenAI-paper-comparable default view.

Decision:

- Open EVMBench pins the Detect judge prompt; submitters choose the judge model and parameters.
- The pinned prompt hash is part of the submission record and must match the vendored prompt.
- `gpt-5` with `reasoning_effort="high"` is the default comparable-to-OpenAI-paper judge group.
- Other judges are valid but must be visibly labeled and compared within their judge group.
- AntFleet does not host the Detect judge for general submissions.

Implementation notes:

- Capture judge model, material parameters, call count, prompt hash, transcript hash, transcript contents or URL, and result schema in submission metadata.
- Reject Detect submissions whose prompt hash does not match `harness/judge_prompt_v1.md`.
- Spot-check the submitted judge transcript during AntFleet acceptance review: the verdicts must match the transcript evidence.
- Let the community re-run any accepted agent plus judge using the public artifacts.

### PR review pipeline

Purpose: receive submission PRs, run lightweight checks, and keep the public Git log reproducible.

Review stages:

1. Confirm API token and GitHub identity, including immutable `operator.github_id` against the PR author's numeric GitHub ID.
2. Enforce that the PR touches exactly one `submissions/phase1/<handle>/<submission_id>/` directory and no code, workflow, script, harness, or other repository files.
3. Check record/transcript size caps before reading attacker-controlled files.
4. Check archive size and archive hash, and reject symlinks under `agent_artifacts/`.
5. Unpack in a clean worker when automated checks require it.
6. Check required files for the declared phase and mode.
7. Check benchmark upstream repo, upstream commit, and harness version.
8. For Detect, validate the pinned prompt hash, require the exact pinned Detect vulnerability ID set with no missing or fabricated IDs, and spot-check judge transcript consistency.
9. For Patch and Exploit, re-run the deterministic harness and compare the result to the claimed score.
10. Write or confirm `score.official_score`, `score.solved_count`, `score.max_score`, and `score.per_vulnerability[]`.
11. Set state to `accepted` or `rejected`.
12. Send accepted records to the signing step.

Queue policy:

- PR checks are FIFO by default.
- Abuse throttles may delay or reject submissions from a GitHub identity or API token.
- There is no formal response-time target in v1.

### Acceptance signing service

Purpose: produce a verifiable AntFleet acceptance attestation for every accepted record.

Responsibilities:

- Generate one AntFleet Ed25519 keypair before launch.
- Publish the public key as `antfleet.public_key.pem` in the repo.
- Sign the JCS-canonicalized submission record with the entire `antfleet_acceptance` object omitted.
- Normalize promoted/yanked records back to the acceptance-time payload before third-party signature verification.
- Store the signature, acceptance record hash, signed timestamp, and public key fingerprint in `antfleet_acceptance` after signing.
- Keep key rotation documented so a compromised key can be retired without rewriting old accepted records.

### Submission CLI

Purpose: a small, predictable submitter flow — login, run, submit.

Commands:

```text
openevmbench login <token>
openevmbench clone
openevmbench run
openevmbench submit
```

CLI responsibilities:

- Accept a GitHub personal access token and verify it against `api.github.com/user` to bind `(github_username, github_id)` to the local credentials.
- Store credentials at `~/.config/openevmbench/credentials.json` (mode 0600). When the 30-day-token web service ships post-launch, accept its tokens through the same `login` command and the same storage shape.
- Clone or verify the pinned benchmark harness.
- Run the agent and harness locally.
- Run the pinned Detect judge prompt locally with the submitter's chosen judge model when mode is Detect.
- Package the archive.
- Compute archive hash and size.
- Collect model, scaffold, harness kind, token, wall-clock, and run-count metadata.
- Collect judge metadata and transcript evidence when mode is Detect.
- Create the submission record and open a PR to the public submissions repository, or emit the PR-ready package.
- Display claimed score, accepted score when available, and public row URL after promotion.

### Leaderboard rendering

Purpose: render a public, static-first board backed by submission records and the public Git log.

Default Phase 1 columns:

```text
Rank
Rank movement
Operator
Official score
Solved count
Judge
Tokens total
Harness kind
Model
Scaffold
Created
Promoted
Submission
```

Required views:

- Phase selector: Detect, Patch, Exploit.
- Ranked operators: one best row per GitHub identity.
- Attempt history per operator.
- Rank movement column with up/down arrows and rank delta over the last N days.
- Operator profile page with rank trajectory / climb history.
- Model and scaffold detail pages.
- Per-vulnerability result pages.
- Per-vulnerability first-solver credit pages for all 117 Detect tasks.
- Threshold moments page for milestones such as crossing 45.6%, crossing 50%, and first Detect submission with an all-open-weights stack.
- Score history tabs: Best score, Improvement per model, and Trajectory.
- Reference target rows.
- AntFleet reference row, marked `prize-excluded`.
- Full view with all judges and default comparable-to-OpenAI-paper view filtered to `gpt-5` with `reasoning_effort="high"`.

### AntFleet reference agent

Purpose: provide an internal reference submission that exercises the whole pipeline before public launch.

Requirements:

- Uses AntFleet's two-model consensus reference agent.
- Runs through the same CLI, PR, acceptance signing, and public Git log path as participant submissions.
- Is marked `prize-excluded`.
- Is visible on the leaderboard.
- Does not define the public SOTA target unless it actually exceeds the published reference target.
- Must be internally dry-run on Phase 1 Detect before public Phase 1 launch.

### Public Git log

Purpose: publish accepted submission records through a public repository history.

AntFleet maintains the public submissions repository. The verification surface is public history for inspection plus independently reproducible artifacts and signatures, not cryptographic append-only enforcement.

Responsibilities:

- Keep a canonical public submissions repo with public read access.
- Merge accepted submission PRs after automated checks and AntFleet acceptance signing.
- Add or update the promoted submission record.
- Include `submission_id` in the file path or file name.
- Write `promoted_at` and `promoted_commit_sha`.
- Store `antfleet_acceptance` with the accepted record.
- Keep accepted submissions inspectable through normal Git history.
- Record yanks as follow-up commits with `state = "yanked"` and `state_reason`.
- Use AntFleet-controlled signed commits for accepted records.

### Submission flow

```text
GitHub OAuth + API token
  -> CLI local run
  -> local judge run for Detect
  -> CLI package and PR creation
  -> AntFleet automated checks
  -> AntFleet acceptance signing
  -> accepted or rejected state
  -> public Git commit on accept
  -> leaderboard render
```

## 6. Phase 1 Build Plan

The simplified Phase 1 build target is 3 to 4 weeks instead of 6 weeks.

### Week 1: Harness wrapper, submission schema, dataset cache, vendored judge prompt

Deliverables:

- Detect wrapper pinned to `openai/frontier-evals@51052ce`.
- Verified dataset cache for 40 audits and 117 runnable vulnerabilities.
- Submission record profiles implemented in code and fixture JSON.
- Vendored pinned Detect judge prompt at `harness/judge_prompt_v1.md`.
- Prompt hash computation wired into Detect submission packaging.
- Positive and negative fixtures for submitted, checking, accepted, rejected, promoted, and yanked states.

Checkpoint:

- A sample Detect archive can be run locally, judged locally with the pinned prompt, and packaged into a valid submission record with matching score output and transcript hash.

### Week 2: Submission CLI, GitHub OAuth, PR creation, AntFleet acceptance signing

Deliverables:

- `openevmbench login <token>`, `clone`, `run`, and `submit` commands.
- GitHub OAuth login.
- 30-day renewable API token creation, storage, renewal, and web revocation.
- Local agent run, local Detect judge run, submission packaging, and PR creation.
- AntFleet Ed25519 acceptance keypair generation.
- `antfleet.public_key.pem` committed to the repo.
- Acceptance signing service that signs JCS-canonicalized accepted records with the entire `antfleet_acceptance` object omitted.
- Automated PR checks for schema, prompt hash, transcript hash, archive hash, and mode-specific required artifacts.
- Claimed-vs-accepted score display.

Checkpoint:

- An external test GitHub identity can run the CLI, open a Detect submission PR, pass automated checks, receive an AntFleet acceptance signature, and see the accepted record merged to the public Git log.

### Week 3: Leaderboard renderer, public Git log, AntFleet reference agent, climb-history features

Deliverables:

- Static leaderboard renderer with default Detect ranked operators view.
- Solver-grouped rows with attempt history.
- Rank movement column with up/down arrows and rank delta over the last N days.
- Operator climb-history pages with rank trajectory.
- Per-vulnerability first-solver pages for all 117 Detect tasks.
- Threshold moments page for crossing 45.6%, crossing 50%, first all-open-weights Detect stack, and similar milestones.
- Score history tabs: Best score, Improvement per model, and Trajectory.
- Reference target row for Claude Opus 4.6 at 45.6%, plus optional GPT-5.3-Codex Detect row at 39.2%.
- AntFleet reference agent submission, accepted through PR review and signing, and marked `prize-excluded`.
- Public Git log writer for accepted submissions.

Checkpoint:

- Accepted submissions are promoted into a public Git commit and render on the board from the committed record.

### Week 4: Polish, AntFleet reference dry-run, external submitter test, launch buffer

Deliverables:

- Documentation for `openevmbench login <token>`, `clone`, `run`, `submit`, and leaderboard interpretation.
- Public rejection reason codes.
- AntFleet reference submission internally dry-run on Phase 1 Detect before public launch.
- AntFleet reference positioning copy finalized based on the dry-run result.
- External submitter smoke test.
- Launch readiness checklist completed.

Checkpoint:

- A clean checkout can render the public board, verify AntFleet's acceptance signature, inspect at least one accepted submission record from the public Git log, and reproduce the submitted Detect judge evidence.

## 7. Phase 1 Launch Readiness Gates

Go live only when all gates pass:

```text
Gate                           Required state
-----------------------------  ------------------------------------------------------------
Source pin                     Detect v1 launch pin immutable: openai/frontier-evals@51052ce plus Open EVMBench harness version
Dataset                        40 audits / 117 runnable vulnerabilities verified in wrapper metadata
Judge strategy                 Pinned Detect judge prompt vendored as harness/judge_prompt_v1.md; prompt hash fixture-tested
Submission schema              Submitted, accepted, and promoted record profiles implemented, documented, and fixture-tested
Submission validation          PR accept/reject pipeline tested with positive and negative fixtures
Submission flow                GitHub PAT verified at api.github.com/user -> CLI local run -> local judge -> PR creation operational; record.operator.github_id enforced against PR author id
Acceptance key                 AntFleet Ed25519 keypair generated; antfleet.public_key.pem published in repo
Acceptance signing            Accepted records signed over JCS-canonicalized payload with the entire `antfleet_acceptance` object omitted
Public Git log                 Accepted submissions promoted through public Git commits with AntFleet acceptance records
Leaderboard                    Default Detect ranked-operators board renders required columns, judge column, and reference rows
Climb-history features         Rank movement, operator trajectory, first-solver pages, threshold moments, and score-history tabs functional
Reference target               Claude Opus 4.6 45.6% Detect SOTA row rendered as Target with no Open EVMBench submission
AntFleet reference             Prize-excluded AntFleet run accepted through same PR/signing pipeline
Reference dry-run              AntFleet reference submission internally dry-run on Phase 1 Detect before public launch; result published
Operator identity              GitHub identity required for ranked rows
Hosting/infra                  Static board plus lightweight PR checks and acceptance signing service
Prize rollover                 Phase 3 rollover policy documented and $1000 escrow commitment in place
Docs                           login <token>, clone, run, submit, and rules docs complete
CI                             Schema, lint/type/test, fixture validation, and static render checks pass
```

The AntFleet reference dry-run gate is non-negotiable. If the reference submission scores at least 30% on Phase 1 Detect, the reference row launches with normal positioning. If it scores below 30%, the reference row launches with an explicit "current AntFleet baseline (work-in-progress)" label and AntFleet's positioning copy must be revised before launch. Public Phase 1 launch is blocked until this dry-run and positioning decision are complete.

Phase 3 prize launch gates, in addition to phase-specific Exploit engineering gates in §10:

- 30-day prize window tracking implemented.
- At least 50 counted Phase 3 operators under the anti-sybil rule in §10.
- Threshold detection for `score.solved_count >= 17` out of 23.
- Private operator-of-record and payout/tax/sanctions review path implemented for prize claims.
- AntFleet manual prize review implemented.
- AntFleet prize exclusion implemented.
- Prize rollover path and escrow commitment implemented: the $1000 never returns to AntFleet's account if Phase 3 conditions fail.
- Source pin and harness-version lineage policy applied to Exploit exactly as for Detect.

Remaining Phase 1 launch blockers are implementation blockers only: if any gate above is not implemented, tested, and documented, launch waits.

## 8. Open Decisions

### Final state of prior A-series decisions

A1 serialization profile: removed. No content-derived serialization profile exists in v1.

A2 public submission ID scheme: resolved. `submission_id` is a UUIDv7 per submission.

A4 operator credential requirement: removed. GitHub OAuth identity and API tokens are the submission auth path.

A5 operator credential event schema: removed. There is no separate credential-event schema.

A6 source pin policy: partly resolved, partly open. The launch pin is immutable per phase. Phase 1 Detect launches on `openai/frontier-evals@51052ce` plus an Open EVMBench harness version. The exact policy for future upstream migrations remains open, but old rankings must not be rewritten in place.

### Final state of prior B-series decisions

B1 LLM judge strategy: resolved. Open EVMBench vendors and pins the Detect judge prompt; submitters run it locally with their chosen judge model. The default comparable-to-OpenAI-paper view filters to `gpt-5` with `reasoning_effort="high"`.

B2 token budget classification: removed. Rows show token counts and harness kind; no token classification is assigned.

B3 real-name disclosure for Phase 3 prize: open. Private operator-of-record is required for payout review. Public real-name disclosure remains a legal/tax question and should move to legal review before Phase 3 terms are finalized.

B4 manual review scope: simplified. The only manual review process is Phase 3 prize claim review.

B5 transcript publication: resolved. Accepted submissions publish immediately; no default delay window.

B6 reproduction confirmation ladder: removed. `accepted` means AntFleet signed the record after checks; the public Git log and reproducible artifacts carry the verification load.

B7 scaffold overfitting: resolved. There is no automated public flag system in v1. Phase 3 prize claim review may reject a prize claim if the submission is not eligible under the prize terms.

B8 formal response targets: removed. Operations are best-effort in v1.

B9 hosting and infra: resolved. PR checks, acceptance signing, promotion, and board rendering all run as GitHub Actions on the public submissions repo, with the Ed25519 private key held as an environment-protected secret. The static board publishes through GitHub Pages. There is no standing web service in v1.

B10 identity token: resolved for v1. v1 accepts GitHub personal access tokens at `openevmbench login` (verified against `api.github.com/user`); ranking identity is the immutable `github_id`, not the renameable handle. The OAuth-backed 30-day-token web service from earlier drafts is deferred to a post-launch upgrade and does not require a record-schema change.

### Operational blockers after simplification

API token policy: simplified. Tokens last 30 days, are renewable, and are revocable through the web UI.

Archival storage: resolved. Accepted submissions are archived through the public Git log.

Rejected/failed visibility: resolved. Rejected attempts are public by default with reason codes unless publication would expose secrets, abuse payloads, or harmful content.

Transcript publication: resolved. Detect submissions include judge transcript contents or a stable transcript URL/path. There is no default delay window.

Scaffold overfit flag weights: removed. There is no automated public flag system in v1.

Ops rota, escalation, and staffing model: removed. Operations are best-effort.

Credential-event sub-questions: removed. There are no credential events in v1.

## 9. Phase 2 (Patch) Roadmap

Phase 2 adds the Patch leaderboard after Phase 1 stabilizes. Phase 2 is reputation-only and carries no prize.

### What changes from Phase 1

```text
Mode:             patch
Task:             produce a patch that fixes a known vulnerability
Known SOTA:       GPT-5.3-Codex at 41.5%
Task count:       44 tasks
Prize:            none
Primary artifact: code patch / diff
Scoring:          binary per task
```

Patch grading is deterministic and does not need an LLM judge. The submitter runs the Patch harness locally, packages the diff, test results, score, and metadata, then submits the record by PR or CLI-created PR. AntFleet re-runs the deterministic harness during automated PR checks before acceptance signing.

### What stays the same

- GitHub OAuth identity.
- API-token CLI submission.
- Submitted, accepted, and promoted record profiles.
- Claimed score vs official score.
- Self-verifying submission package plus AntFleet acceptance signing.
- Public Git log of accepted submissions.
- Solver-grouped leaderboard rows.
- Attempt history behind each operator row.
- Reference target row for GPT-5.3-Codex 41.5% Patch SOTA.

### New engineering work

Phase 2 needs:

- Patch archive format.
- Clean patch-apply worker.
- Protected-test tamper checks.
- Changed-file inventory.
- Invariant and vulnerability test result capture.
- Patch-specific per-task result fields inside `score.per_vulnerability[]`.

### Phase 2 launch prerequisites

- Phase 1 submission schema stable in production.
- Patch worker can apply and grade a submitted patch in a clean environment.
- GPT-5.3-Codex 41.5% Patch SOTA row is documented and rendered as a reference target.
- AntFleet Patch reference submission, if produced, is marked `prize-excluded`.

## 10. Phase 3 (Exploit) Roadmap

Phase 3 adds the Exploit leaderboard and the $1000 "Beat OpenAI at Phase 3" prize.

### What changes from Phase 1

```text
Mode:             exploit
Task:             write transactions that drain vulnerable contracts
Known SOTA:       GPT-5.3-Codex at 72.2%
Runnable set:     23 vulnerabilities
Prize:            $1000
Primary artifact: exploit transaction / script bundle
Scoring:          binary per runnable vulnerability
```

Exploit grading is per-vulnerability script replay. It does not need a Detect-style LLM judge.
The submitter runs the Exploit harness locally, packages exploit transactions or scripts, chain-state results, score, and metadata, then submits the record by PR or CLI-created PR. AntFleet re-runs the deterministic harness during automated PR checks before acceptance signing.

### Reference target

The Phase 3 reference target is GPT-5.3-Codex's published Exploit SOTA:

```text
Reference model claim: GPT-5.3-Codex
Reported by:           OpenAI
Paper score:           72.2%
Blog score:            71.0%
Leaderboard treatment: reference target row, not ranked
Submission treatment:  no Open EVMBench submission
Token budget:          undisclosed
Prize status:          never eligible
```

### Phase 3 prize

The prize headline is:

```text
$1000 for the highest-scoring eligible Open EVMBench Phase 3 submission that beats OpenAI at Phase 3.
```

Prize qualification requires:

- 30-day prize window.
- At least 50 counted Phase 3 operators under the anti-sybil rule below.
- At least 17 of 23 runnable Exploit vulnerabilities cleared.
- AntFleet excluded from prize eligibility.
- AntFleet manual review of the prize claim.

Why `17/23`: 16/23 is 69.6%, below the 72.2% reference; 17/23 is 73.9%, the first integer score that clears 72.2%.

Winner is the highest-scoring eligible Phase 3 submission at the end of the 30-day window, after AntFleet manual review.

Counted Phase 3 operator anti-sybil rule:

A Phase 3 operator counts toward the 50-operator gate only if all of the following hold:

1. The GitHub account was created at least 90 days before the Phase 3 launch date.
2. The account has at least one accepted Phase 3 submission with `score.solved_count >= 1` out of 23.
3. The account has a distinct operator-of-record; shared identity across counted accounts is not allowed, and AntFleet may request lightweight attestation if accounts look clearly linked.
4. AntFleet org members and employees are excluded from the count.
5. AntFleet may exclude clearly coordinated sybil clusters from the count, with the decision and reason logged in the public Git log.

Rollover rule: if fewer than 50 counted Phase 3 operators submit accepted Phase 3 records, or if no eligible submission reaches at least 17/23 during the 30-day window, the $1000 rolls over instead of returning to AntFleet.

Rollover options:

- Roll over to Phase 4, a future Open EVMBench prize round using the same prize model.
- Roll over to a partial-credit pool distributed pro-rata to top-N submitters who attempted Phase 3 but did not clear 17/23.

AntFleet commits that the $1000 never returns to AntFleet's account after the Phase 3 prize window opens. It is escrowed for submitter payout under the winner, rollover, or partial-credit path.

Prize eligibility is computed from Phase 3 submission records only. Phase 1 and Phase 2 activity contributes reputation and operator history, not the Phase 3 counted-operator gate.

### Manual prize review

AntFleet reviews the prize claim before payout. The submission record uses:

```text
prize_review_status = pending | approved | rejected
prize_review_reason = human-readable reason when rejected
```

The review confirms identity, payout eligibility, source pin, replay result, score threshold, AntFleet exclusion, and artifact safety. AntFleet must re-verify any prize-claim submission by re-running the deterministic Exploit harness. If a future prize claim depends on Detect-mode judging, AntFleet may need to pay for one judge re-run when the submission used a paid model. This is the only formal manual review path in v1.

### New engineering work

Phase 3 needs:

- Exploit archive format.
- Per-vulnerability replay worker.
- Chain-state identity and block-number capture.
- Deploy and grade script hash capture.
- Broadcast or deploy artifact hash capture.
- Replay result detail.
- Artifact safety handling for public publication.
- Prize-window tracking.
- Counted Phase 3 operator tracking under the anti-sybil rule.
- Prize claim review UI and public status fields.

### Phase 3 launch prerequisites

- Phase 1 submission schema stable in production.
- Exploit worker can replay submitted artifacts in a clean environment.
- GPT-5.3-Codex 72.2% paper / 71.0% blog Exploit SOTA row is documented and rendered as a reference target.
- Phase 3 prize mechanism is implemented, including 30-day window tracking, accepted Phase 3 submission counting, counted-operator anti-sybil checks, `solved_count >= 17` threshold detection, AntFleet prize exclusion, end-window winner selection, manual prize review, and rollover handling.
- API-token policy, public Git log, PR checks, acceptance signing, rejected-attempt visibility, and best-effort ops posture are reflected in Phase 3 terms.

## 11. Cross-Phase Considerations

### Simultaneous leaderboard surfaces

The public leaderboard supports phase filters:

```text
Phase tabs: Detect | Patch | Exploit | All
```

No token-budget grouping tabs exist in v1. The row itself shows official score, total tokens, and harness kind.

Example table:

```text
Detect / Ranked operators

| Phase   | Rank | Operator | Score       | Tokens | Harness kind      | Model           | Submission |
| ------- | ---- | -------- | ----------- | ------ | ----------------- | --------------- | ---------- |
| Detect  | #1   | @alice   | 75.2% 88/117| 1.2M   | agentic-scaffold  | claude-opus-4.6 | View       |
| Patch   | #1   | @bob     | 68.2% 30/44 | 350k   | retry-loop        | gpt-5.3-codex   | View       |
| Exploit | #1   | @carol   | 52.2% 12/23 | 900k   | single-shot       | gpt-5.3-codex   | View       |
```

### Operator identity across phases

Submission identity is the GitHub handle across all phases.

The same GitHub identity can appear in Detect, Patch, and Exploit. Default views show one best row per GitHub identity per phase and harness version, with attempt history behind the row.

Phase 3 prize eligibility is computed at Phase 3 close from accepted Phase 3 submission records only. Detect and Patch submissions do not count toward the 50-operator Phase 3 prize gate. Counted Phase 3 operators must satisfy the anti-sybil rule in §10.

### One schema across all phases

One submission schema with submitted, accepted, and promoted profiles applies uniformly across Detect, Patch, and Exploit.

Mode-aware differences live in:

- `phase`
- `mode`
- `benchmark.harness_version`
- phase-specific archive contents
- phase-specific result details inside `score.per_vulnerability[]`
- `judge` for Detect only; Patch and Exploit are deterministic and set it to null unless a future phase changes that contract

### Public Git log across all phases

Accepted submissions in every phase are promoted into the public Git log. The log is the shared public audit trail for accepted records, AntFleet acceptance signatures, yanks, and state reasons.

Judge prompts are pinned per phase only when a phase needs judge-backed scoring. Detect v1 uses `harness/judge_prompt_v1.md`; Patch and Exploit are deterministic and do not use an LLM judge.

## 12. Risk Register

```text
Risk                                                     Mitigation
-------------------------------------------------------  ------------------------------------------------------------
Judge model variance in Detect                           Make judge model and params visible, compare within same-judge groups, default to the OpenAI-paper-comparable gpt-5 high filter, and rely on community re-verification
Judge transcript falsification                           Require transcript hash plus transcript contents or URL, spot-check verdicts during AntFleet acceptance, and keep artifacts public for community re-runs
Sybil flood around Phase 3 prize                         Apply counted-operator anti-sybil rule, exclude AntFleet members and employees, and log any sybil-cluster exclusion reason publicly
AntFleet reference embarrassment                         Mark AntFleet reference as prize-excluded and treat it as a pipeline test, not a guaranteed target-beater
Competitive obsolescence before Phase 3 launch           Keep Phase 1/2 as reputation-building, keep Phase 3 headline tied to current 72.2% reference until a new source pin is adopted
Phase 3 prize fizzles                                    Publish 30-day window, 50-operator gate, 17/23 threshold, rollover rule, and escrow commitment before submissions open
Codex CLI version drift changes scaffold behavior         Record model, scaffold name, scaffold hash, harness kind, run count, token counts, and harness version in every submission
Rejected-attempt publication exposes sensitive content    Public by default with reason codes, with narrow withholding for secrets, abuse payloads, or harmful content
AntFleet acceptance keypair compromise                    Use standard key management, publish the public key fingerprint, document rotation, and preserve old signed records in public Git history
AntFleet remains a listing trust point                    Limit AntFleet's role to acceptance signing and public-log merge; make artifacts reproducible so accepted records can be independently re-run
Source migration invalidates old comparisons              Immutable launch pin per phase; future migrations create new versioned boards instead of rewriting old rankings
```
