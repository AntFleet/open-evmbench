"""Static leaderboard site renderer (SPEC §5 Leaderboard rendering).

Every page derives from the promoted-records dataset in openevmbench.board.
Output is dependency-free static HTML plus a machine-readable
`data/board.json` mirror.

Pages:
    index.html                  default comparable ranked board + reference rows
    all.html                    full board, all judge groups
    operators/<handle>.html     attempt history + rank trajectory
    models/<slug>.html          best rows per agent model
    scaffolds/<slug>.html       rows per scaffold
    vulns/index.html            117-task first-solver index
    vulns/<slug>.html           per-vulnerability results + first-solver credit
    moments.html                threshold moments
    history.html                score-history tabs (best / per-model / trajectory)
"""

from __future__ import annotations

import datetime
import html
import json
import re
from pathlib import Path

from openevmbench import constants
from openevmbench.board import (
    Attempt,
    BoardConfig,
    Moment,
    RankedRow,
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

_CSS = """
body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;margin:2rem auto;max-width:72rem;
padding:0 1rem;color:#1a1a1a;background:#fafaf8;font-size:14px;line-height:1.5}
h1{font-size:1.3rem}h2{font-size:1.1rem;margin-top:2rem}
.table-wrap{overflow-x:auto;margin:1rem 0}
table{border-collapse:collapse;width:100%;margin:0}
th,td{text-align:left;padding:.35rem .6rem;border-bottom:1px solid #ddd;white-space:nowrap}
th{border-bottom:2px solid #999;font-weight:600}
tr.target{background:#fff8e1}tr.excluded{background:#f0f0f0;color:#555}
a{color:#0b57d0;text-decoration:none}a:hover{text-decoration:underline}
.up{color:#0a7d33}.down{color:#c0392b}.new{color:#666}
.tag{font-size:.75rem;border:1px solid #999;border-radius:3px;padding:0 .3rem;margin-left:.4rem}
nav{margin-bottom:1.5rem}nav a{margin-right:1rem}
footer{margin-top:3rem;font-size:.8rem;color:#777}
"""


def _esc(value: object) -> str:
    return html.escape(str(value))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")


def _page(title: str, body: str, depth: int = 0) -> str:
    prefix = "../" * depth
    nav = (
        f'<nav><a href="{prefix}index.html">Ranked</a><a href="{prefix}all.html">All judges</a>'
        f'<a href="{prefix}vulns/index.html">Vulnerabilities</a>'
        f'<a href="{prefix}moments.html">Moments</a><a href="{prefix}history.html">History</a></nav>'
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{_esc(title)}</title>"
        f"<style>{_CSS}</style></head><body>{nav}<h1>{_esc(title)}</h1>{body}"
        f"<footer>Open EVMBench — harness {_esc(constants.HARNESS_VERSION)} — "
        f"records and signatures inspectable in the public Git log.</footer></body></html>"
    )


def _table(headers: list[str], rows: list[str]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    return f"<div class='table-wrap'><table><tr>{head}</tr>{''.join(rows)}</table></div>"


def _movement_cell(movement: int | None) -> str:
    if movement is None:
        return '<span class="new">new</span>'
    if movement > 0:
        return f'<span class="up">▲ {movement}</span>'
    if movement < 0:
        return f'<span class="down">▼ {abs(movement)}</span>'
    return "—"


def _score_cell(attempt: Attempt) -> str:
    return f"{attempt.score_pct}% {attempt.solved_count}/{attempt.max_score}"


def _operator_link(handle: str, depth: int = 0) -> str:
    return f'<a href="{"../" * depth}operators/{_slug(handle)}.html">@{_esc(handle)}</a>'


def _agent_params_tooltip(a: Attempt) -> str:
    """Hover text for the Reasoning cell.

    Three cases:
    - "record": values came from agent.params in the signed record
    - "backfill": values came from leaderboard/historical_agent_metadata.json
                  (record predates the 2026-06-20 SPEC amendment; we still
                  display real values, but disclose the source)
    - "missing": nothing recorded and no backfill — render as "?"
    """
    params = a.agent_params
    source = a.agent_params_source
    if params is None:
        return ("agent.params not recorded and no backfill available "
                "(record predates 2026-06-20 schema amendment)")
    body = "; ".join(f"{k}={v}" for k, v in sorted(params.items()))
    if source == "record":
        return f"{body} (from signed record)"
    if source == "backfill":
        return f"{body} (backfilled from leaderboard/historical_agent_metadata.json; record predates 2026-06-20)"
    return body


def _prompt_hash_tooltip(a: Attempt) -> str:
    h = a.agent_prompt_hash
    source = a.agent_prompt_hash_source
    if not h:
        return ("agent.prompt_hash not recorded and no backfill available "
                "(record predates 2026-06-20 schema amendment)")
    if source == "record":
        return f"{h} (from signed record)"
    if source == "backfill":
        return f"{h} (backfilled from leaderboard/historical_agent_metadata.json; record predates 2026-06-20)"
    return h


def _row_html(row: RankedRow, config: BoardConfig, depth: int = 0) -> str:
    a = row.attempt
    excluded = a.is_prize_excluded(config)
    cls = ' class="excluded"' if excluded else ""
    tag = '<span class="tag">prize-excluded</span>' if excluded else ""
    prefix = "../" * depth
    # Column order (2026-06-20 reorg):
    # Rank, Δ, Operator, Official score, Model, Harness, Scaffold,
    # Reasoning, Prompt, Judge, Created, Promoted, Submission
    # ("Tokens total" removed — token counts weren't being tracked
    # consistently and weren't a useful comparability signal.)
    return (
        f"<tr{cls}><td>#{row.rank}</td><td>{_movement_cell(row.movement)}</td>"
        f"<td>{_operator_link(a.operator, depth)}{tag}</td>"
        f"<td>{_score_cell(a)}</td>"
        f"<td><a href='{prefix}models/{_slug(a.agent_model)}.html'>{_esc(a.agent_model)}</a></td>"
        f"<td>{_esc(a.harness_kind)}</td>"
        f"<td><a href='{prefix}scaffolds/{_slug(a.scaffold_name)}.html'>{_esc(a.scaffold_name)}</a></td>"
        f"<td title='{_esc(_agent_params_tooltip(a))}'>{_esc(a.agent_reasoning_label)}</td>"
        f"<td title='{_esc(_prompt_hash_tooltip(a))}'>{_esc(a.agent_prompt_label)}</td>"
        f"<td>{_esc(a.judge_label)}</td>"
        f"<td>{_esc(a.created_at[:10])}</td>"
        f"<td>{_esc(a.record.get('promoted_at', '—')[:10])}</td>"
        f"<td><a href='{prefix}{_esc(a.path)}'>record</a></td></tr>"
    )


def _reference_rows(config: BoardConfig) -> str:
    rows = []
    for target in config.reference_targets:
        # Columns: Rank, Δ, Operator, Score, Model, Harness, Scaffold,
        # Reasoning, Prompt, Judge, Created, Promoted, Submission
        rows.append(
            f"<tr class='target'><td>Target</td><td>—</td>"
            f"<td>{_esc(target['label'])} <span class='tag'>reference</span></td>"
            f"<td>{target['score_pct']}% paper</td>"
            f"<td>—</td><td>—</td><td>—</td>"  # model, harness, scaffold
            f"<td>—</td><td>—</td>"  # reasoning, prompt
            f"<td>—</td>"  # judge
            f"<td>—</td><td>—</td>"  # created, promoted
            f"<td>no Open EVMBench submission</td></tr>"
        )
    return "".join(rows)


_BOARD_HEADERS = [
    "Rank", "Δ", "Operator", "Official score",
    "Model", "Harness kind", "Scaffold",
    "Reasoning",  # agent.params.reasoning_effort — "?" if not recorded
    "Prompt",     # short prefix of agent.prompt_hash — "?" if not recorded
    "Judge",
    "Created", "Promoted", "Submission",
]


def _board_page(title: str, rows: list[RankedRow], config: BoardConfig, note: str) -> str:
    body = f"<p>{note}</p>" + _table(
        _BOARD_HEADERS,
        [_reference_rows(config)] + [_row_html(r, config) for r in rows],
    )
    if not rows:
        body += "<p><em>No promoted submissions yet.</em></p>"
    return _page(title, body)


def render_site(
    submissions_root: Path | str,
    config_path: Path | str,
    out_dir: Path | str,
    now: datetime.datetime | None = None,
    public_key_path: Path | str | None = "antfleet.public_key.pem",
) -> Path:
    config = BoardConfig.load(config_path)
    attempts = load_attempts(submissions_root, public_key_path=public_key_path)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    comparable = with_rank_movement(
        ranked_rows(attempts, config, comparable_only=True), attempts, config, now
    )
    full = with_rank_movement(
        ranked_rows(attempts, config, comparable_only=False), attempts, config, now,
        comparable_only=False,
    )

    (out / "index.html").write_text(
        _board_page(
            "Phase 1 Detect — Ranked operators",
            comparable,
            config,
            f"Default view: judge group comparable to the OpenAI paper "
            f"({_esc(config.default_judge_model)}, reasoning_effort="
            f"{_esc(config.default_judge_reasoning_effort)}, pinned prompt). "
            f"One row per accepted submission. "
            f"Rank Δ is movement over the last {config.rank_window_days} days.",
        ),
        encoding="utf-8",
    )
    (out / "all.html").write_text(
        _board_page(
            "Phase 1 Detect — All judge groups",
            full,
            config,
            "Full board: every accepted judge group. Detect scores are comparable "
            "within each judge model + parameter group (SPEC §3).",
        ),
        encoding="utf-8",
    )

    # --- operator pages ---
    (out / "operators").mkdir(exist_ok=True)
    for handle in sorted({a.operator for a in attempts}, key=str.lower):
        history = operator_attempts(attempts, handle)
        trajectory = operator_trajectory(attempts, config, handle)
        traj_rows = [
            f"<tr><td>{when.date()}</td><td>#{rank}</td><td>{pct:.1f}%</td></tr>"
            for when, rank, pct in trajectory
        ]
        attempt_rows = [
            f"<tr><td>{_esc(a.created_at[:10])}</td><td>{_esc(a.state)}</td>"
            f"<td>{_score_cell(a) if a.official_score is not None else f'{a.solved_count}/{a.max_score} claimed'}</td>"
            f"<td>{_esc(a.judge_label)}</td><td>{_esc(a.agent_model)}</td>"
            f"<td>{a.tokens_total:,}</td>"
            f"<td>{_esc(a.record.get('state_reason') or '')}</td>"
            f"<td><a href='../{_esc(a.path)}'>record</a></td></tr>"
            for a in history
        ]
        body = (
            "<h2>Rank trajectory (default board)</h2>"
            + (_table(["Promoted", "Rank", "Official score"], traj_rows) if traj_rows
               else "<p><em>No promoted submissions on the default board.</em></p>")
            + "<h2>Attempt history (all states, all judges)</h2>"
            + _table(["Created", "State", "Score", "Judge", "Model", "Tokens", "Reason", "Record"],
                     attempt_rows)
        )
        (out / "operators" / f"{_slug(handle)}.html").write_text(
            _page(f"@{handle} — climb history", body, depth=1), encoding="utf-8"
        )

    # --- model / scaffold pages ---
    for kind, key_fn in (("models", lambda a: a.agent_model), ("scaffolds", lambda a: a.scaffold_name)):
        (out / kind).mkdir(exist_ok=True)
        groups: dict[str, list[Attempt]] = {}
        for a in attempts:
            if a.state == "promoted":
                groups.setdefault(key_fn(a), []).append(a)
        for name, group in groups.items():
            group.sort(key=lambda a: -(a.official_score or 0))
            rows = [
                f"<tr><td>{_operator_link(a.operator, 1)}</td><td>{_score_cell(a)}</td>"
                f"<td>{_esc(a.judge_label)}</td><td>{a.tokens_total:,}</td>"
                f"<td>{_esc(a.harness_kind)}</td><td><a href='../{_esc(a.path)}'>record</a></td></tr>"
                for a in group
            ]
            (out / kind / f"{_slug(name)}.html").write_text(
                _page(f"{name} — promoted rows",
                      _table(["Operator", "Official score", "Judge", "Tokens", "Harness kind", "Record"], rows),
                      depth=1),
                encoding="utf-8",
            )

    # --- per-vulnerability pages (first-solver credit for all 117 tasks) ---
    solves = first_solvers(attempts, config)
    vuln_ids = sorted(
        {e["vulnerability_id"] for a in attempts for e in a.record["score"]["per_vulnerability"]}
    )
    (out / "vulns").mkdir(exist_ok=True)
    index_rows = []
    for vid in vuln_ids:
        solve = solves.get(vid)
        solvers = [
            a for a in attempts
            if a.state == "promoted" and vid in a.passed_vulnerabilities()
        ]
        solver_rows = [
            f"<tr><td>{_operator_link(a.operator, 1)}</td><td>{_esc(a.agent_model)}</td>"
            f"<td>{_esc(a.judge_label)}</td><td>{_esc(a.record.get('promoted_at', '')[:10])}</td>"
            f"<td><a href='../{_esc(a.path)}'>record</a></td></tr>"
            for a in sorted(solvers, key=lambda a: a.promoted_at)
        ]
        first = (
            f"<p>First solver: {_operator_link(solve.operator, 1)} on {solve.promoted_at.date()} "
            f"(submission <code>{_esc(solve.submission_id)}</code>)</p>"
            if solve else "<p><em>Unsolved on the public board.</em></p>"
        )
        body = first + "<h2>Promoted submissions that detected it</h2>" + (
            _table(["Operator", "Model", "Judge", "Promoted", "Record"], solver_rows)
            if solver_rows else "<p><em>None yet.</em></p>"
        )
        (out / "vulns" / f"{_slug(vid)}.html").write_text(
            _page(vid, body, depth=1), encoding="utf-8"
        )
        index_rows.append(
            f"<tr><td><a href='{_slug(vid)}.html'>{_esc(vid)}</a></td>"
            f"<td>{_operator_link(solve.operator, 1) if solve else '—'}</td>"
            f"<td>{solve.promoted_at.date() if solve else '—'}</td>"
            f"<td>{len(solver_rows)}</td></tr>"
        )
    (out / "vulns" / "index.html").write_text(
        _page(
            f"Per-vulnerability first-solver credit ({len(vuln_ids)} tasks)",
            _table(["Vulnerability", "First solver", "Date", "Solved by"], index_rows),
            depth=1,
        ),
        encoding="utf-8",
    )

    # --- threshold moments ---
    moments: list[Moment] = threshold_moments(attempts, config)
    moment_rows = [
        f"<tr><td>{m.when.date()}</td><td>{_esc(m.title)}</td>"
        f"<td>{_operator_link(m.operator)}</td><td><code>{_esc(m.submission_id)}</code></td></tr>"
        for m in moments
    ]
    (out / "moments.html").write_text(
        _page("Threshold moments",
              _table(["When", "Milestone", "Operator", "Submission"], moment_rows)
              if moment_rows else "<p><em>No milestones yet.</em></p>"),
        encoding="utf-8",
    )

    # --- score history tabs ---
    hist = best_score_history(attempts, config)
    hist_rows = [
        f"<tr><td>{p.when.date()}</td><td>{p.score_pct}%</td><td>{_operator_link(p.operator)}</td></tr>"
        for p in hist
    ]
    per_model = best_per_model(attempts, config)
    model_rows = [
        f"<tr><td><a href='models/{_slug(m)}.html'>{_esc(m)}</a></td><td>{_score_cell(a)}</td>"
        f"<td>{_operator_link(a.operator)}</td></tr>"
        for m, a in sorted(per_model.items(), key=lambda kv: -(kv[1].official_score or 0))
    ]
    traj_sections = []
    for row in comparable:
        handle = row.attempt.operator
        traj = operator_trajectory(attempts, config, handle)
        pts = " → ".join(f"{pct:.1f}% (#{rank})" for _, rank, pct in traj)
        traj_sections.append(f"<tr><td>{_operator_link(handle)}</td><td>{pts}</td></tr>")
    body = (
        "<h2>Best score</h2>"
        + (_table(["When", "Board best", "Operator"], hist_rows) if hist_rows else "<p><em>—</em></p>")
        + "<h2>Improvement per model</h2>"
        + (_table(["Model", "Best official score", "Operator"], model_rows) if model_rows else "<p><em>—</em></p>")
        + "<h2>Trajectory</h2>"
        + (_table(["Operator", "Score (rank) after each promotion"], traj_sections)
           if traj_sections else "<p><em>—</em></p>")
    )
    (out / "history.html").write_text(_page("Score history", body), encoding="utf-8")

    # --- machine-readable mirror ---
    (out / "data").mkdir(exist_ok=True)
    (out / "data" / "board.json").write_text(
        json.dumps(
            {
                "harness_version": constants.HARNESS_VERSION,
                "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "reference_targets": list(config.reference_targets),
                "default_board": [
                    {
                        "rank": r.rank,
                        "operator": r.attempt.operator,
                        "official_score": r.attempt.official_score,
                        "solved_count": r.attempt.solved_count,
                        "max_score": r.attempt.max_score,
                        "tokens_total": r.attempt.tokens_total,
                        "judge": r.attempt.judge_label,
                        "model": r.attempt.agent_model,
                        "scaffold": r.attempt.scaffold_name,
                        "harness_kind": r.attempt.harness_kind,
                        "prize_excluded": r.attempt.is_prize_excluded(config),
                        "movement": r.movement,
                        "record": r.attempt.path,
                        "submission_id": r.attempt.submission_id,
                    }
                    for r in comparable
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out
