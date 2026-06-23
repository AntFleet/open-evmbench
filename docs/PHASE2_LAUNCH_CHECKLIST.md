# Phase 2 (Patch) Launch Checklist

Tracked gates for opening the public Patch leaderboard. Binding contracts live in
[SPEC §9](SPEC.md). Phase 1 Detect must be stable before Phase 2 opens
([README](../README.md): "Phase 1 stabilizes → Phase 2 opens").

**Dataset pin (verified):** `openai/frontier-evals@51052ce` — 22 audits in
`splits/patch-tasks.txt`, **44** patch vulnerabilities (`patch_path_mapping`).
See [UPSTREAM_PIN.md](UPSTREAM_PIN.md).

**SOTA reference target:** GPT-5.3-Codex **41.5%** Patch (OpenAI EVMbench paper,
Table 9). Reputation-only — no prize ([PRIZE.md](PRIZE.md)).

---

## How to use this doc

- `[ ]` = not started · `[~]` = in progress · `[x]` = done
- Update status inline as work lands; link PRs/commits in the Notes column where helpful.
- Do **not** flip README / announce Phase 2 open until every **Launch blocker**
  row is `[x]`.

---

## Phase 0 — Phase 1 stability gate

Phase 2 SPEC prerequisite: *"Phase 1 submission schema stable in production."*
Operational gate: pipeline proven beyond AntFleet-internal runs.

| Status | Gate | Notes |
|--------|------|-------|
| `[x]` | Phase 1 live (Detect board, signing, render) | 17 promoted rows (local tree) |
| `[x]` | Record schema + fixtures stable (`phase`/`mode`/`judge` rules) | `record.schema.json`, validation tests |
| `[x]` | Launch pin immutable (`detect-v1.0.0+frontier-evals.51052ce`) | [constants.py](../openevmbench/constants.py) |
| `[x]` | **External submitter smoke** — one non-AntFleet operator completes cold [SUBMITTING.md](SUBMITTING.md) path end-to-end | `@Augustas11` — [external_detect_smoke_report.json](external_detect_smoke_report.json) 2026-06-21 |
| `[x]` | Explicit Phase 1 stability sign-off (owner + date) | Phase 2 launch 2026-06-21 — Detect board stable, external smoke pass |

### Why external smoke if there are already 17 submissions?

All 17 promoted Detect rows in the current tree are **`antfleet-ops`** — internal
reference / fleet runs through AntFleet tooling (`scripts/run_consensus_subscriptions.py`,
fleet runners, preflight). They prove the **signing + board pipeline** works, not that
a stranger can follow the public docs with only `pip install -e .` and a GitHub token.

External smoke catches doc drift, CLI UX gaps, credential binding surprises, and
`check-pr` failures that internal runners paper over (custom env vars, `gh auth token`,
pre-built `audit_sources/`, etc.). SPEC §7 lists it as a launch gate for Phase 1; Phase 2
inherits the same risk if skipped.

---

## Phase 1 — Spec & package design

| Status | Gate | Owner / link |
|--------|------|--------------|
| `[x]` | Patch submission package layout documented (SPEC §4 extension or `SUBMITTING_PATCH.md`) | [SUBMITTING_PATCH.md](SUBMITTING_PATCH.md) |
| `[x]` | `harness_version` string pinned (e.g. `patch-v1.0.0+frontier-evals.51052ce`) | [constants.py](../openevmbench/constants.py) |
| `[x]` | Canonical 44 vulnerability ID list checked into repo | [harness/patch_tasks_v1.json](../harness/patch_tasks_v1.json) |
| `[ ]` | Patch-specific `score.per_vulnerability[]` fields specified (invariant, changed_files, reason codes) | SPEC §9 |
| `[ ]` | Schema + fixtures updated for Phase 2 submitted profile | |
| `[ ]` | Rejection reason codes for patch path added to [RULES.md](RULES.md) | |

**Draft package layout:**

```text
submissions/phase2/<github_handle>/<submission_id>/
  record.json
  agent_artifacts/
    <audit-id>.diff              # unified diff vs base_commit (upstream: submission/agent.diff)
  grade_evidence/                # optional locally; CI may regenerate
    <audit-id>/invariant.json
    <audit-id>/<vuln-id>.json
```

---

## Phase 2 — Patch worker (critical path)

Upstream grading reference: `upstream/.../evmbench/nano/grade/patch.py` (`PatchGrader`).
Requires per-audit Docker images + **pinned Foundry nightly** (see spike notes).

| Status | Gate | Owner / link |
|--------|------|--------------|
| `[~]` | **Spike:** grade gold patch for `2023-07-pooltogether` (2 vulns) | `scripts/spike_patch_worker.py` — **SPIKE PASS** per-vuln (`2/2` with `--skip-invariant`) |
| `[x]` | `PatchDataset` loader (`patch-tasks` split, 44 IDs) | [dataset.py](../openevmbench/dataset.py) + tests |
| `[~]` | `openevmbench/patch_worker.py` — apply diff, invariant suite, per-vuln tests, tamper checks | local spike done; tamper checks + Docker pending |
| `[x]` | Docker worker (clean env) matching upstream `PatchGrader` semantics | [patch_docker.py](../openevmbench/patch_docker.py) |
| `[x]` | `validate_phase2_patch()` | [validation.py](../openevmbench/validation.py) + tests |
| `[x]` | `openevmbench run --mode patch --docker` packages record + artifacts | Docker grading path |
| `[x]` | `check_package()` patch path + CI Docker re-grade | `OPENEVMBENCH_SKIP_PATCH_REGRADE` escape hatch |
| `[ ]` | Unit tests: gold pass, bad diff fail, test-tamper fail | |

### Spike findings (`2023-07-pooltogether`, 2026-06-21)

| Finding | Detail |
|---------|--------|
| Gold diff applies | `git apply --binary --index` on combined `patch/Vault.sol` vs `base_commit` ✓ |
| Per-vuln scoring | H-02 + H-04 exploit tests → **2/2** with gold patch (`scripts/spike_patch_worker.py --skip-invariant`) ✓ |
| Exploit test staging | Invariant run must not include exploit test files; upload per vuln only (matches PatchGrader) |
| Invariant suite | **3 failures** on host forge 1.7.1 (`testFail_*` deprecation); Docker uses `nightly-d369d2486…` — production worker must match Docker |
| Docker | Deferred — run `scripts/docker_spike_patch_worker.py --build --grade` overnight (amd64 emulation is CPU-heavy on Apple Silicon) |
| Next spike step | Build `evmbench/audit:2023-07-pooltogether` image; end-to-end grade inside container |

---

## Phase 3 — Pipeline & board

| Status | Gate | Owner / link |
|--------|------|--------------|
| `[~]` | `submission-checks.yml` allowlists `submissions/phase2/...` | phase 1–3 regex |
| `[~]` | `check-pr` routes Detect vs Patch validators by `record.phase` | by path phase |
| `[x]` | `board_config.json` — GPT-5.3-Codex **41.5%** Patch reference target | `patch_reference_targets` |
| `[x]` | Board UI — Phase selector on `index.html` (Detect / Patch) | unified board + `?phase=patch` |
| `[x]` | Moments threshold = 41.5% on Patch board | `threshold_moments(..., phase=2)` |
| `[x]` | [SUBMITTING.md](SUBMITTING.md) or companion Patch guide | [SUBMITTING_PATCH.md](SUBMITTING_PATCH.md) |
| `[x]` | README updated: Phase 2 open | 2026-06-21 |

---

## Phase 4 — Reference submission & public launch

| Status | Gate | Owner / link |
|--------|------|--------------|
| `[ ]` | Patch preflight script (Docker images, 1-audit smoke, 44-vuln ID check) | |
| `[ ]` | AntFleet Patch reference run → `submissions/phase2/antfleet-ops/...` | |
| `[ ]` | `check-pr` + acceptance signing + promote | |
| `[ ]` | Reference row `prize-excluded` (already in board config handles) | |
| `[ ]` | Positioning copy vs 41.5% SOTA | |
| `[ ]` | @AntFleetDev announce | |

---

## Launch blockers (all must be `[x]` for full pipeline parity)

1. `[x]` Phase 1 stability sign-off (external smoke pass 2026-06-21)
2. `[x]` Patch worker grades submitted diffs in clean Docker env (CI re-grade)
3. `[x]` Phase 2 PR pipeline operational (`submissions/phase2/` path + checks)
4. `[x]` Patch board renders with GPT-5.3-Codex 41.5% reference target
5. `[x]` Submitter documentation complete
6. `[ ]` AntFleet Patch reference row promoted (recommended seed)

---

## Suggested timeline

| Window | Work |
|--------|------|
| Week 1 | Phase 0 sign-off + package spec (Phase 1 checklist rows) |
| Weeks 2–4 | Patch worker + Docker infra (Phase 2 checklist) |
| Week 5 | Pipeline + board (Phase 3) |
| Week 6 | Reference run + launch (Phase 4) |

Critical path: **Docker-backed patch worker** (Phase 2 engineering).
