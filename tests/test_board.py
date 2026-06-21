import datetime
import json

import pytest

from conftest import load_fixture
from openevmbench.board import (
    Attempt,
    BoardConfig,
    best_per_model,
    best_score_history,
    first_solvers,
    load_attempts,
    operator_attempts,
    operator_trajectory,
    ranked_rows,
    threshold_moments,
    with_rank_movement,
)
from openevmbench.constants import JUDGE_PROMPT_SHA256
from openevmbench.render import render_site

NOW = datetime.datetime(2026, 6, 10, tzinfo=datetime.timezone.utc)

CONFIG = BoardConfig(
    rank_window_days=7,
    prize_excluded_operators=("antfleet",),
    reference_targets=(
        {"label": "Claude Opus 4.6 — Detect SOTA", "reported_by": "Anthropic", "score_pct": 45.6, "primary": True},
    ),
    open_weights_patterns=("llama", "qwen"),
)

VULNS = ["audit-a:v1", "audit-a:v2", "audit-b:v1"]
GITHUB_IDS = {
    "alice": 101,
    "bob": 102,
    "carol": 103,
    "dave": 104,
    "antfleet": 105,
    "erin": 106,
}


def make_record(
    *,
    sid_suffix: str,
    operator: str,
    passed: list[bool],
    tokens: int,
    promoted_at: str,
    state: str = "promoted",
    judge_model: str = "gpt-5",
    reasoning_effort: str = "high",
    temperature_marker="omit",
    agent_model: str = "gpt-5.3-codex",
    scaffold: str = "scaffold-x",
    harness_version: str = "detect-v1.0.0+frontier-evals.51052ce",
    github_id: int | None = None,
):
    solved = sum(passed)
    record = {
        "submission_id": f"018f7f64-2c2e-7b70-8f4d-{sid_suffix:0>12}",
        "phase": 1,
        "mode": "detect",
        "created_at": promoted_at,
        "operator": {"github_username": operator, "github_id": github_id or GITHUB_IDS.get(operator, 999)},
        "submission": {"archive_hash": "sha256:" + "a" * 64, "archive_size_bytes": 1},
        "benchmark": {
            "upstream_repo": "openai/frontier-evals",
            "upstream_commit": "51052ce",
            "harness_version": harness_version,
        },
        "agent": {
            "model": agent_model,
            "scaffold_name": scaffold,
            "scaffold_hash": "sha256:" + "b" * 64,
            "harness_kind": "agentic-scaffold",
        },
        "judge": {
            "model": judge_model,
            "params": {"reasoning_effort": reasoning_effort},
            "prompt_hash": f"sha256:{JUDGE_PROMPT_SHA256}",
            "transcript_hash": "sha256:" + "c" * 64,
            "transcript_contents_or_url": "judge_transcript.jsonl",
        },
        "run": {
            "tokens_total": tokens, "tokens_prompt": tokens, "tokens_completion": 0,
            "tokens_per_task": [], "wall_clock_ms": 1, "runs_count": 1,
        },
        "score": {
            "claimed_score": round(solved / len(passed), 4),
            "solved_count": solved,
            "max_score": len(passed),
            "per_vulnerability": [
                {"vulnerability_id": vid, "passed": p, "score": int(p)}
                for vid, p in zip(VULNS, passed)
            ],
        },
        "state": state,
        "state_reason": "yank reason" if state == "yanked" else None,
    }
    if temperature_marker != "omit":
        record["judge"]["params"]["temperature"] = temperature_marker
    if state in ("accepted", "promoted", "yanked"):
        record["score"]["official_score"] = record["score"]["claimed_score"]
        record["antfleet_acceptance"] = {
            "signature": "ed25519:QUJD",
            "acceptance_record_hash": "sha256:" + "d" * 64,
            "signed_at": promoted_at,
            "public_key_fingerprint": "sha256:" + "e" * 64,
        }
    if state in ("promoted", "yanked"):
        record["promoted_at"] = promoted_at
        record["promoted_commit_sha"] = "f" * 40
    return record


@pytest.fixture
def submissions(tmp_path):
    records = [
        # bob: promoted 10 days ago, 2/3, 200k tokens — board leader back then
        make_record(sid_suffix="1", operator="bob", passed=[True, True, False],
                    tokens=200_000, promoted_at="2026-05-31T00:00:00Z"),
        # alice attempt 1: 8 days ago, 1/3
        make_record(sid_suffix="2", operator="alice", passed=[True, False, False],
                    tokens=100_000, promoted_at="2026-06-02T00:00:00Z"),
        # alice attempt 2: 2 days ago, 2/3 with FEWER tokens than bob -> takes #1 on tie-break
        make_record(sid_suffix="3", operator="alice", passed=[False, True, True],
                    tokens=100_000, promoted_at="2026-06-08T00:00:00Z"),
        # carol: open-weights stack on a non-default judge -> full board only
        make_record(sid_suffix="4", operator="carol", passed=[True, True, True],
                    tokens=50_000, promoted_at="2026-06-09T00:00:00Z",
                    judge_model="llama-4-405b", agent_model="qwen-3-coder"),
        # dave: yanked -> off the board, in attempt history
        make_record(sid_suffix="5", operator="dave", passed=[True, True, True],
                    tokens=10, promoted_at="2026-06-03T00:00:00Z", state="yanked"),
        # antfleet reference: prize-excluded, 1/3
        make_record(sid_suffix="6", operator="antfleet", passed=[False, False, True],
                    tokens=80_000, promoted_at="2026-06-05T00:00:00Z",
                    scaffold="antfleet-two-model-consensus"),
        # erin: rejected attempt -> never ranked
        make_record(sid_suffix="7", operator="erin", passed=[True, True, True],
                    tokens=1, promoted_at="2026-06-09T00:00:00Z", state="rejected"),
    ]
    root = tmp_path / "submissions"
    for r in records:
        d = root / "phase1" / r["operator"]["github_username"] / r["submission_id"]
        d.mkdir(parents=True)
        (d / "record.json").write_text(json.dumps(r))
    return root


def test_ranking_and_tiebreakers(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    rows = ranked_rows(attempts, CONFIG, comparable_only=True)
    ops = [r.attempt.operator for r in rows]
    # One row per submission — alice's 2/3 (100k) beats bob's 2/3 (200k) on
    # tokens; alice's 1/3 attempt and antfleet's 1/3 attempt also appear.
    # antfleet (80k) tie-breaks above alice's 1/3 (100k) on tokens.
    assert ops == ["alice", "bob", "antfleet", "alice"]
    # yanked (dave), rejected (erin), non-comparable judge (carol) absent
    assert "dave" not in ops and "erin" not in ops and "carol" not in ops


def test_full_board_includes_other_judges(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    rows = ranked_rows(attempts, CONFIG, comparable_only=False)
    ops = [r.attempt.operator for r in rows]
    assert "carol" in ops
    assert ops[0] == "carol"  # 3/3 leads the full board


def test_rank_movement(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    rows = ranked_rows(attempts, CONFIG, comparable_only=True)
    rows = with_rank_movement(rows, attempts, CONFIG, NOW)
    by_sub = {r.attempt.submission_id: r for r in rows}
    # 7 days ago (2026-06-03): bob's 2/3 (#1) and alice's 1/3 (#2) are
    # the only promoted rows. Alice's 2/3 (06-08) and antfleet (06-05) are
    # promoted within the window — both surface as new.
    bob_sid = next(s for s, r in by_sub.items() if r.attempt.operator == "bob")
    alice_low_sid = next(
        s for s, r in by_sub.items()
        if r.attempt.operator == "alice" and r.attempt.solved_count == 1
    )
    alice_high_sid = next(
        s for s, r in by_sub.items()
        if r.attempt.operator == "alice" and r.attempt.solved_count == 2
    )
    antfleet_sid = next(s for s, r in by_sub.items() if r.attempt.operator == "antfleet")
    assert by_sub[bob_sid].movement == -1            # 1 -> 2
    assert by_sub[alice_low_sid].movement == -2      # 2 -> 4 (antfleet + alice's 2/3 jumped ahead)
    assert by_sub[alice_high_sid].movement is None   # new in window
    assert by_sub[antfleet_sid].movement is None     # new in window


def test_first_solvers_cross_judge(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    solves = first_solvers(attempts, CONFIG)
    assert solves["audit-a:v1"].operator == "bob"      # 05-31 beats alice 06-02
    assert solves["audit-a:v2"].operator == "bob"
    assert solves["audit-b:v1"].operator == "antfleet"  # 06-05 beats alice 06-08


def test_threshold_moments(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    titles = {m.title: m for m in threshold_moments(attempts, CONFIG)}
    assert titles["First promoted Detect submission"].operator == "bob"
    # 2/3 = 66.7% clears both 45.6 and 50 on the comparable board (bob first)
    assert titles["First to clear the published Detect SOTA (45.6%)"].operator == "bob"
    assert titles["First to cross 50%"].operator == "bob"
    assert titles["First all-open-weights Detect stack"].operator == "carol"


def test_patch_threshold_moments(tmp_path):
    from openevmbench.constants import PATCH_HARNESS_VERSION

    root = tmp_path / "submissions"
    record = make_record(
        sid_suffix="patch1",
        operator="alice",
        passed=[True] * 18 + [False] * 26,
        tokens=100,
        promoted_at="2026-06-10T00:00:00Z",
        harness_version=PATCH_HARNESS_VERSION,
    )
    record["phase"] = 2
    record["mode"] = "patch"
    record["judge"] = None
    record["score"]["max_score"] = 44
    record["score"]["solved_count"] = 18
    record["score"]["official_score"] = 18 / 44
    d = root / "phase2" / record["operator"]["github_username"] / record["submission_id"]
    d.mkdir(parents=True)
    (d / "record.json").write_text(json.dumps(record))

    attempts = load_attempts(root, public_key_path=None)
    titles = {m.title: m for m in threshold_moments(attempts, CONFIG, phase=2)}
    assert titles["First promoted Patch submission"].operator == "alice"
    assert "First to clear the published Patch SOTA (41.5%)" not in titles


def test_score_history_and_per_model(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    history = best_score_history(attempts, CONFIG)
    assert [p.operator for p in history] == ["bob"]  # alice ties, never beats
    per_model = best_per_model(attempts, CONFIG)
    assert per_model["gpt-5.3-codex"].operator == "alice"


def test_operator_trajectory_and_attempts(submissions):
    attempts = load_attempts(submissions, public_key_path=None)
    traj = operator_trajectory(attempts, CONFIG, "alice")
    assert [(rank, round(pct)) for _, rank, pct in traj] == [(2, 33), (1, 67)]
    history = operator_attempts(attempts, "dave")
    assert len(history) == 1 and history[0].state == "yanked"


def test_render_site(submissions, tmp_path):
    out = render_site(
        submissions,
        "leaderboard/board_config.json",
        tmp_path / "site",
        now=NOW,
        public_key_path=None,
    )

    index = (out / "index.html").read_text()
    assert "phase-select" in index and "Phase 2 — Patch" in index
    assert "Claude Opus 4.6" in index and "45.6% paper" in index   # detect reference
    assert "GPT-5.3-Codex — Patch SOTA" in index and "41.5% paper" in index
    assert 'data-phase-panel="patch"' in index
    assert "prize-excluded" in index                                # antfleet marking
    # Bob's submission drops from #1 to #2 as alice's new 2/3 + antfleet land
    # above it — only ▼ surfaces with this fixture. Per-submission movement
    # has no natural ▲ unless higher-rank records get yanked.
    assert "▼" in index
    assert "@alice" in index
    assert "@carol" not in index                                    # non-default judge

    assert "@carol" in (out / "all.html").read_text()               # full view shows all judges
    assert "yanked" in (out / "operators" / "dave.html").read_text()
    assert "rejected" in (out / "operators" / "erin.html").read_text()

    vuln_index = (out / "vulns" / "index.html").read_text()
    assert "audit-a:v1" in vuln_index and "@bob" in vuln_index

    moments = (out / "moments.html").read_text()
    assert "Phase 1 Detect" in moments and "Phase 2 Patch" in moments
    assert "all-open-weights" in moments

    board = json.loads((out / "data" / "board.json").read_text())
    assert board["patch_reference_targets"][0]["score_pct"] == 41.5
    assert board["patch_board"] == []
    # Alice's top row is alice's 2/3 submission (new in window → movement None).
    assert board["default_board"][0]["operator"] == "alice"
    assert board["default_board"][0]["movement"] is None
    # Bob's submission is now #2, having dropped by one.
    assert board["default_board"][1]["operator"] == "bob"
    assert board["default_board"][1]["movement"] == -1
    assert any(r["prize_excluded"] for r in board["default_board"])

    for page in ("history.html", "models/gpt-5.3-codex.html",
                 "scaffolds/antfleet-two-model-consensus.html"):
        assert (out / page).is_file(), page


def test_rank_movement_tracks_each_submission(tmp_path):
    """Movement is per-submission: a row's delta is its own rank movement,
    independent of other submissions by the same operator."""
    root = tmp_path / "submissions"
    records = [
        make_record(
            sid_suffix="101",
            operator="alice",
            passed=[True, True, False],
            tokens=100,
            promoted_at="2026-05-31T00:00:00Z",
            harness_version="detect-v1",
        ),
        make_record(
            sid_suffix="102",
            operator="alice",
            passed=[True, False, False],
            tokens=100,
            promoted_at="2026-05-31T00:00:00Z",
            harness_version="detect-v2",
        ),
        make_record(
            sid_suffix="103",
            operator="bob",
            passed=[True, True, True],
            tokens=100,
            promoted_at="2026-05-31T00:00:00Z",
            harness_version="detect-v2",
        ),
        make_record(
            sid_suffix="104",
            operator="alice",
            passed=[True, True, False],
            tokens=50,
            promoted_at="2026-06-09T00:00:00Z",
            harness_version="detect-v2",
        ),
    ]
    for r in records:
        d = root / "phase1" / r["operator"]["github_username"] / r["submission_id"]
        d.mkdir(parents=True)
        (d / "record.json").write_text(json.dumps(r))

    attempts = load_attempts(root, public_key_path=None)
    rows = with_rank_movement(ranked_rows(attempts, CONFIG), attempts, CONFIG, NOW)
    by_sid = {r.attempt.submission_id: r for r in rows}
    # Submission 104 (alice, 2/3, promoted 06-09) is new in window
    sid_104 = next(s for s in by_sid if s.endswith("104"))
    assert by_sid[sid_104].movement is None
    # Submission 101 (alice detect-v1, 2/3) was rank #2 at the window start
    # (behind bob's 3/3). Sub 104 jumps above on tokens → 101 drops to #3.
    sid_101 = next(s for s in by_sid if s.endswith("101"))
    assert by_sid[sid_101].movement == -1


def test_renamed_github_handle_still_emits_both_rows(tmp_path):
    """Renaming a GitHub handle (same github_id) does not affect per-row
    behavior: both submissions still appear, each at the rank their score
    earns."""
    root = tmp_path / "submissions"
    records = [
        make_record(
            sid_suffix="201",
            operator="old-name",
            github_id=500,
            passed=[True, False, False],
            tokens=100,
            promoted_at="2026-06-01T00:00:00Z",
        ),
        make_record(
            sid_suffix="202",
            operator="new-name",
            github_id=500,
            passed=[True, True, False],
            tokens=100,
            promoted_at="2026-06-02T00:00:00Z",
        ),
    ]
    for r in records:
        d = root / "phase1" / r["operator"]["github_username"] / r["submission_id"]
        d.mkdir(parents=True)
        (d / "record.json").write_text(json.dumps(r))

    rows = ranked_rows(load_attempts(root, public_key_path=None), CONFIG)
    # Both submissions present, the 2/3 one ranks first regardless of handle.
    assert [r.attempt.operator for r in rows] == ["new-name", "old-name"]
    assert {r.attempt.github_id for r in rows} == {500}


def test_comparable_requires_default_temperature():
    record = make_record(
        sid_suffix="301",
        operator="alice",
        passed=[True, False, False],
        tokens=100,
        promoted_at="2026-06-01T00:00:00Z",
        temperature_marker=0,
    )
    attempt = Attempt(record=record, path="record.json")
    assert not attempt.is_comparable(CONFIG)


def test_invalid_signed_lifecycle_record_is_dropped(tmp_path, test_public_pem, caplog):
    caplog.set_level("WARNING")
    root = tmp_path / "submissions"
    public_key = tmp_path / "public.pem"
    public_key.write_bytes(test_public_pem)
    record = load_fixture("promoted_valid")
    record["score"]["solved_count"] = 1
    d = root / "phase1" / record["operator"]["github_username"] / record["submission_id"]
    d.mkdir(parents=True)
    (d / "record.json").write_text(json.dumps(record))

    attempts = load_attempts(root, public_key_path=public_key)
    assert attempts == []
    assert "invalid signatures" in caplog.text
