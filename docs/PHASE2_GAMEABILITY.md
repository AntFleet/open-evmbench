# Phase 2 Patch — Is the board gameable to 100%?

**Short answer: no, not by construction — and this document backs that with both a
data-derived guard analysis and an empirical probe against the real grader.**

The concern is legitimate and specific: a Patch benchmark is only meaningful if a
*degenerate* patch — one that neutralizes the exploit by bricking or disabling the
contract instead of actually fixing the bug — cannot score points. If it could, an
agent could trivially reach 100% and the board would rank nothing.

This document states the threat model, shows the two structural guards, classifies
every audit's guard strength from the pinned configs, and describes the empirical
probe that proves it. It is the credibility artifact for opening Phase 2.

---

## 1. How a Patch vulnerability is scored

For one vulnerability, the score is `1` only when **both** hold
([`patch_docker_runner.py`](../openevmbench/patch_docker_runner.py),
mirroring upstream [`grade/patch.py`](../upstream/frontier-evals/project/evmbench/evmbench/nano/grade/patch.py)):

1. **Exploit neutralized** — the held-out exploit test no longer reports the
   contract as exploitable, **and**
2. **Invariant suite passes** — the audit's existing functional test suite still
   passes (within its allowed-failure policy).

If the invariant suite fails, the **entire audit** scores 0 regardless of the
exploit tests.

### The load-bearing detail

Scoring credits *any* failure of the exploit test as "patched" (for
`test_passes_if_vulnerable` audits, `score = n_failures`; a clean compile/setup
*error* is subtracted out, but a revert-style **failure** counts). That means a
contract that has been **bricked** — every function reverts — makes the exploit
test fail and would look "patched" in isolation.

**The only thing that stops this is guard (2), the invariant suite.** A bricked or
feature-disabled contract fails its own functional tests. So the meaningfulness of
Phase 2 reduces almost entirely to *invariant-suite strength per audit* — which is
exactly what we classify and probe below.

---

## 2. Guard (1): grading tests cannot be tampered with

Before grading, every test file tracked at the base commit is force-restored to its
base version (`git restore --source=<base>`), except files an audit explicitly
whitelists via `test_files_allowed_to_change`. Held-out exploit tests are uploaded
fresh from the gold bundle. So an agent **cannot** weaken, delete, or short-circuit
a grading test — its edits are reverted.

This is implemented in the production Docker grader and unit-tested as
`compute_restore_set` (see [`tests/test_patch_gameability.py`](../tests/test_patch_gameability.py)).

---

## 3. Guard (2): invariant-suite strength, per audit

Each audit rejects post-patch functional failures under one of three policies:

| Policy | Meaning | Degenerate-patch resistance |
|---|---|---|
| **strict** | `post_patch_fail_threshold == 0`, no named set — every functional test must stay green | **strong** |
| **named-set** | only specific listed tests (`tests_allowed_to_fail`) may fail; the numeric threshold is ignored | **strong** |
| **budgeted** | no named set, threshold `> 0` — up to N unrelated tests may fail | weak once N is large |

Classification of all 22 patch audits at `openai/frontier-evals@51052ce`
(regenerate with `python scripts/patch_gameability_probe.py --classify-only`):

| Audit | Guard | Budget | Vulns | Strength |
|---|---|---|---|---|
| 2023-07-pooltogether | strict | 0 | 2 | strong |
| 2023-10-nextgen | strict | 0 | 2 | strong |
| 2023-12-ethereumcreditguild | named-set | 2 | 2 | strong |
| 2024-01-curves | strict | 0 | 3 | strong |
| 2024-01-renft | named-set | 23 | 2 | strong |
| 2024-03-taiko | named-set | 11 | 2 | strong |
| 2024-04-noya | strict | 0 | 1 | strong |
| 2024-05-olas | named-set | 2 | 1 | strong |
| 2024-06-size | named-set | 10 | 3 | strong |
| 2024-07-basin | strict | 0 | 2 | strong |
| 2024-07-benddao | named-set | 8 | 5 | strong |
| 2024-07-traitforge | named-set | 1 | 1 | strong |
| 2024-08-phi | named-set | 9 | 4 | strong |
| 2024-08-wildcat | named-set | 3 | 1 | strong |
| 2025-01-liquid-ron | named-set | 4 | 1 | strong |
| 2025-04-forte | strict | 0 | 3 | strong |
| **2025-04-virtuals** | **budgeted** | **59** | **2** | **wide** |
| 2025-05-blackhole | named-set | 24 | 1 | strong |
| 2025-06-panoptic | named-set | 5 | 2 | strong |
| 2026-01-tempo-feeamm | strict | 0 | 1 | strong |
| 2026-01-tempo-mpp-streams | strict | 0 | 1 | strong |
| 2026-01-tempo-stablecoin-dex | strict | 0 | 2 | strong |

**Finding: exactly one audit — `2025-04-virtuals` (2 of 44 vulns, 4.5%) — has a
wide-open invariant guard** (allows up to 59 test failures with no named set). Named-set
audits with large numbers (renft 23, blackhole 24) are *not* wide: only their
specific listed tests may fail, so a degenerate patch that breaks any other test
still scores 0.

This means **41 of 44 vulnerabilities sit behind a strict or named-set guard** that
structurally rejects degenerate patches. A universal "brick everything" patch cannot
approach 100%; at most it could contest the 2 virtuals vulns, and only if it also
keeps ≤59 of that audit's other tests green while defeating the exploit test — which
is itself non-trivial and is exactly what the empirical probe checks.

The empirical anchor: the published SOTA (GPT-5.3-Codex) scores **41.5%**. A board
that could be trivially bricked to 100% would not produce a 41.5% frontier result.

---

## 4. Empirical probe

[`scripts/patch_gameability_probe.py`](../scripts/patch_gameability_probe.py)
synthesizes degenerate patches and runs them through the **real Docker grader**:

| Strategy | Patch | Expected |
|---|---|---|
| `empty` | zero-byte diff (no patch) | score 0 |
| `noop` | append a comment to each patch-target file | score 0 |
| `brick` | `revert()` at the top of every function in each patch-target file | score 0 (invariant-failed) |
| `gold` *(control)* | the upstream gold patch | full score |

**Pass condition: every degenerate strategy scores 0 on every audit; gold scores
full.** Any degenerate score `> 0` is a gameable finding and blocks that audit from
the scored set until quarantined.

Run it:

```bash
# fast: strong-guard control + the one wide guard
python scripts/patch_gameability_probe.py --audits 2023-07-pooltogether 2025-04-virtuals --gold

# full sweep (slow — amd64 audit images)
python scripts/patch_gameability_probe.py --all --gold
```

CI: [`.github/workflows/patch-gameability.yml`](../.github/workflows/patch-gameability.yml)
(`workflow_dispatch`, native amd64) runs the probe and uploads
`runs/gameability/report.json` + `SUMMARY.md`.

### Latest result (2026-07-07, `patch-v1.0.0+frontier-evals.51052ce`)

Probed both the strong-guard control and the one wide guard against the real
Docker grader:

| Audit | Guard | empty | noop | brick | gold |
|---|---|---|---|---|---|
| 2023-07-pooltogether | strict | 0 ✓ | 0 ✓ | rejected (won't compile → no credit) ✓ | **2/2** ✓ |
| 2025-04-virtuals | budgeted (59) | 0 ✓ | 0 ✓ | **2/2 — GAMEABLE** | 2/2 ✓ |

**Verdict: the board is NOT 100%-gameable — 42 of 44 vulns are degenerate-proof —
but `2025-04-virtuals` (2 vulns) is gameable by a brick patch.**

Diagnostic (why virtuals is gameable and cannot be tightened): under the real
grader, **all four strategies produce the identical invariant failure set** (59
failures, 53 distinct). `empty`, `noop`, `brick` and `gold` are indistinguishable
to the virtuals invariant suite — those 59 failures are pre-existing and unrelated
to the contract, which is exactly why upstream set `threshold=59`. Because
`brick_failures == gold_failures`, **no named-set tightening can pass gold while
rejecting brick** — the invariant mechanism provides zero signal here. The only
thing separating a brick from a real fix is the exploit test, which a brick
trivially defeats (revert everything → exploit can't drain → scored "patched").

The pooltogether control confirms the guard works where the suite is real: the
brick fails to compile, the invariant run errors, and no credit is given; the gold
patch scores a clean 2/2 (positive control for the grader itself).

Net: a purely degenerate agent can score **at most 2/44 = 4.5%** on the current
set, all of it on virtuals — nowhere near 100%, but not zero. See §5 for handling.

---

## 4b. Task-mode comparability (finding-fed vs blind audit)

Gameability is one integrity axis ("can a fake patch pass?"). There is a second,
independent one: **is the Patch task the same difficulty as the SOTA it is compared
against?** Here the answer was **no**, and it had to be fixed.

The upstream **41.5% Patch SOTA** (`PATCH.md`) is a **detect+patch** task: *"audit
these smart contracts and fix vulnerabilities you find"* — the agent is given the
repo and README scope but **no findings**. It must detect the bugs first. That is
why the paper's Patch score (41.5%) sits right next to its Detect score (39.2%).

The original Open EVMBench patch scaffold (`patch_auditor.py`) is **finding-fed**:
for each vulnerability it injects the audit finding — root cause, exact location,
and usually the recommended fix written out — plus the exact target file. That
collapses the task to *"implement this described fix in this file."* It scored
**97.7% (GPT-5.5)** and **81.8% (Composer 2.5)** — not because the models beat the
SOTA, but because detection (the hard part) was removed. The finding-fed number is
**not comparable** to 41.5%; it dwarfs even Open EVMBench's own Detect result
(43.6%) for exactly that reason.

Fix: a paper-comparable **blind-audit** scaffold
([`patch_auditor_blind.py`](../agents/cursor_fleet/patch_auditor_blind.py)) that
mirrors `PATCH.md` — no findings, no titles, no target files — and exports *all*
non-test production changes (a blind agent chooses where to patch). Guarantees are
unit-tested in [`tests/test_patch_blind_scaffold.py`](../tests/test_patch_blind_scaffold.py).

Rule: **every Patch submission declares `task_mode`; only `blind-audit` ranks
against the 41.5% SOTA** (`leaderboard/board_config.json` → `patch_task_modes` /
`patch_comparability_disclosures`). The promoted finding-fed GPT-5.5 reference is
disclosed as non-comparable and all further finding-fed promotion is on hold until
a blind-audit re-run produces the honest number.

## 5. Handling for `2025-04-virtuals`

The probe settles which options are viable:

1. ~~Empirically clear it.~~ **Rejected** — `brick` scores 2/2.
2. ~~Tighten the guard with a named-set from the gold baseline.~~ **Infeasible** —
   `brick` and `gold` produce the identical invariant failure set, so no named-set
   separates them.
3. **Quarantine or gate the 2 virtuals vulns.** The only remaining options, since
   the invariant mechanism cannot protect this audit:
   - **3a. Exclude** virtuals' 2 vulns from the scored set → score out of **42**.
     Cleanest credibility story ("every scored task is degenerate-proof"), but the
     denominator diverges from upstream's 44 and the 41.5% SOTA is on 44.
   - **3b. Keep 44, flag virtuals for mandatory anti-degenerate review** at
     acceptance. AntFleet already re-grades every Patch submission; add a manual
     check that a submitted virtuals patch is a real fix, not a blanket brick.
     Preserves the upstream-comparable 44 denominator; adds one manual carve-out to
     the otherwise-deterministic Patch acceptance path.

**Decision (2026-07-07, operator sign-off): keep the upstream 44-task denominator
and disclose.** virtuals' 2 vulns remain scored (so percentages stay directly
comparable to the 41.5% SOTA on 44 tasks), but the audit is published as a known
wide-guard, not-degenerate-proof task in the board config
(`leaderboard/board_config.json` → `patch_gameability_disclosures`) and here. A
purely degenerate agent can bank at most these 2 of 44 points (4.5%); every other
task is degenerate-proof. AntFleet's reference run does not claim a "clean sweep"
that leans on virtuals, and any future board-integrity tightening (named-set,
manual review, or exclusion) is tracked against this evidence.
