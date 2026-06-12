# Rules and Leaderboard Interpretation

Binding contracts live in [SPEC](SPEC.md); this summarizes what ranks, what
gets rejected, and how to read the board.

## What ranks

- Ranked rows are promoted records: accepted by AntFleet's automated checks,
  Ed25519-signed, merged into the public Git log.
- One best row per GitHub identity per phase and harness version. Earlier
  and worse attempts stay public behind the row (operator page).
- Tie-breakers, in order: higher official score → lower total tokens →
  earlier promotion → lower submission_id.
- The **default board** filters to the OpenAI-paper-comparable judge group:
  `gpt-5`, `reasoning_effort=high`, omitted `temperature` (the pinned
  EVMbench runtime does not set it, so the API default applies), and the
  pinned prompt hash. Explicit non-default temperature values are shown in
  the All judges view. The **All judges** view shows every accepted judge
  group; scores compare within a judge group, not across groups.
- **Target rows** (Claude Opus 4.6 45.6%, GPT-5.3-Codex 39.2%) are published
  paper claims, not submissions. They are never ranked and never eligible
  for anything. If their owners submit through Open EVMBench, those become
  normal ranked rows; the paper claims remain reference targets.
- AntFleet's own reference rows are real runs through the same pipeline,
  marked `prize-excluded`, never prize-eligible.

## Acceptance, rejection, yanks

`accepted` means: the record passed AntFleet's automated checks for the
declared phase and harness version, and AntFleet signed it at a timestamp.
It is not a reproduction claim — the package is self-verifying and anyone
can re-run it (SPEC §3 "Acceptance status").

Rejected submissions are public by default with a reason code, and count in
attempt history. Promoted records later shown invalid are yanked in a
follow-up commit (`state: yanked` + reason) and drop off rankings while
remaining inspectable.

### Rejection reason codes

| Code | Meaning |
|---|---|
| `path-violation` | PR touches files outside one `submissions/phase1/<you>/<submission_id>/` dir |
| `missing-file` | `record.json`, `judge_transcript.jsonl`, or `agent_artifacts/` absent |
| `record-invalid` | Schema violation, wrong benchmark pin, wrong pinned prompt hash, score inconsistencies |
| `identity-mismatch` | Record operator ≠ PR author (or ≠ path handle) |
| `submission-id-mismatch` | `submission_id` ≠ directory name |
| `transcript-hash-mismatch` | `judge.transcript_hash` ≠ actual transcript file bytes |
| `transcript-inconsistent` | Judge verdicts in the transcript contradict `score.per_vulnerability` (or coverage gaps) |
| `transcript-path-mismatch` | `judge.transcript_contents_or_url` doesn't point at the packaged transcript |
| `archive-mismatch` | `archive_hash`/size don't reproduce from `agent_artifacts/` via the deterministic recipe |
| `archive-symlink` | `agent_artifacts/` contains a symlink; archives and Pages publishing never follow submitter symlinks |
| `file-too-large` | `record.json` or `judge_transcript.jsonl` exceeds the check-time size cap |
| `vulnerability-id-mismatch` | Detect `per_vulnerability[]` is not the exact pinned 117-ID set |
| `pr-touches-non-submission-files` | Workflow prepare job found PR changes outside one submission directory |

Narrow exception (SPEC §3): a rejection is withheld from publication only if
publishing would expose secrets, abuse payloads, or harmful content.

## Reading the board

- **Δ column**: rank movement over the last 7 days (▲ climbed, ▼ dropped,
  "new" = entered the window).
- **Official score**: what AntFleet accepted; the UI may show
  claimed-vs-official deltas. Ranking always uses official score.
- **Tokens / harness kind**: display only. There are no token-budget
  classes; compare high-score vs low-token rows by your own priorities.
- **Vulnerabilities pages**: per-task first-solver credit across all judge
  groups, plus every promoted submission that detected the task.
- **Moments**: first promoted submission, first to clear the 45.6% SOTA
  (default board), first past 50%, first all-open-weights stack.
- **History tabs**: board-best over time, best per agent model, and each
  operator's rank trajectory.

## Operations

Best-effort (SPEC §8): PR checks are FIFO, no response-time target. Abuse
throttles may delay or reject submissions per identity or token. The only
manual review in v1 is the Phase 3 prize claim (docs/PRIZE.md).
