"""Leaderboard data model (SPEC §2 Scoring, §3 Fair-Comparison, §5 Leaderboard).

Everything derives from the promoted records in the public submissions tree —
the views are renderings of this one dataset. Time-dependent features (rank
movement, trajectories, threshold moments) replay the promotion timeline
using `promoted_at`, so the board is a pure function of the records and
needs no git archaeology.

Ranking rules:
- Ranked rows come from `state == "promoted"` records only; yanked records
  drop off the board but stay in attempt history (public audit trail).
- One best row per GitHub identity per harness version; tie-breakers are
  higher official score, lower run.tokens_total, earlier promoted_at,
  lower submission_id (SPEC §2).
- The default board filters to the OpenAI-paper-comparable judge group
  (gpt-5, reasoning_effort=high, pinned prompt hash); the full board shows
  every judge group with the judge as a visible column.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openevmbench import constants
from openevmbench.signing import SignatureError, verify_record

logger = logging.getLogger(__name__)


def _load_historical_agent_metadata() -> dict[str, Any]:
    """Load the presentation-layer backfill for agent.params/prompt_hash.

    SPEC §3 amendment 2026-06-20 added optional ``agent.params`` and
    ``agent.prompt_hash`` to record.json. Records that predate the
    amendment lack these fields. Since records are signed (acceptance
    signature), we DO NOT modify them — instead this map provides
    render-time values, and tooltips disclose that the values are
    backfilled rather than recorded.

    File: ``leaderboard/historical_agent_metadata.json`` at the repo
    root. Returns an empty dict if missing, so tests that don't care
    about this map keep working.
    """
    candidates = [
        Path("leaderboard/historical_agent_metadata.json"),
        Path(__file__).resolve().parent.parent / "leaderboard" / "historical_agent_metadata.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.warning("could not parse %s: %s", path, e)
                return {}
            return data.get("submissions", {}) if isinstance(data, dict) else {}
    return {}


_HISTORICAL_AGENT_METADATA: dict[str, Any] = _load_historical_agent_metadata()


@dataclass(frozen=True)
class BoardConfig:
    default_judge_model: str = constants.DEFAULT_JUDGE_MODEL
    default_judge_reasoning_effort: str = constants.DEFAULT_JUDGE_REASONING_EFFORT
    rank_window_days: int = 7
    prize_excluded_operators: tuple[str, ...] = ()
    reference_targets: tuple[dict[str, Any], ...] = ()
    open_weights_patterns: tuple[str, ...] = ()
    # SPEC §3 amendment 2026-06-20: optional stricter group that requires
    # all rows on the default leaderboard to share an agent.prompt_hash
    # and agent.reasoning_effort. When unset (the default), the board
    # filters only on judge-group as before — keeps the existing 11
    # promoted records on the default view.
    strict_agent_group: dict[str, Any] | None = None

    @staticmethod
    def load(path: Path | str) -> "BoardConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        group = data.get("default_judge_group", {})
        return BoardConfig(
            default_judge_model=group.get("model", constants.DEFAULT_JUDGE_MODEL),
            default_judge_reasoning_effort=group.get(
                "reasoning_effort", constants.DEFAULT_JUDGE_REASONING_EFFORT
            ),
            rank_window_days=int(data.get("rank_window_days", 7)),
            prize_excluded_operators=tuple(
                o.lower() for o in data.get("prize_excluded_operators", [])
            ),
            reference_targets=tuple(data.get("reference_targets", [])),
            open_weights_patterns=tuple(
                p.lower() for p in data.get("open_weights_patterns", [])
            ),
            strict_agent_group=data.get("strict_agent_group") or None,
        )


def _parse_ts(value: str) -> datetime.datetime:
    ts = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        return ts.replace(tzinfo=datetime.timezone.utc)
    return ts


@dataclass(frozen=True)
class Attempt:
    """One submission record, any lifecycle state."""

    record: dict[str, Any]
    path: str  # repo-relative record.json path

    @property
    def submission_id(self) -> str:
        return self.record["submission_id"]

    @property
    def operator(self) -> str:
        return self.record["operator"]["github_username"]

    @property
    def github_id(self) -> int:
        return int(self.record["operator"]["github_id"])

    @property
    def state(self) -> str:
        return self.record.get("state", "submitted")

    @property
    def official_score(self) -> float | None:
        return self.record.get("score", {}).get("official_score")

    @property
    def score_pct(self) -> float | None:
        s = self.official_score
        return None if s is None else round(s * 100, 1)

    @property
    def solved_count(self) -> int:
        return self.record["score"]["solved_count"]

    @property
    def max_score(self) -> int:
        return self.record["score"]["max_score"]

    @property
    def tokens_total(self) -> int:
        return self.record["run"]["tokens_total"]

    @property
    def harness_kind(self) -> str:
        return self.record["agent"]["harness_kind"]

    @property
    def agent_model(self) -> str:
        return self.record["agent"]["model"]

    @property
    def scaffold_name(self) -> str:
        return self.record["agent"]["scaffold_name"]

    @property
    def harness_version(self) -> str:
        return self.record["benchmark"]["harness_version"]

    @property
    def created_at(self) -> str:
        return self.record["created_at"]

    @property
    def promoted_at(self) -> datetime.datetime | None:
        value = self.record.get("promoted_at")
        return _parse_ts(value) if value else None

    @property
    def judge_model(self) -> str | None:
        judge = self.record.get("judge")
        return judge.get("model") if isinstance(judge, dict) else None

    @property
    def judge_params(self) -> dict[str, Any]:
        judge = self.record.get("judge")
        return judge.get("params", {}) if isinstance(judge, dict) else {}

    @property
    def judge_label(self) -> str:
        if self.judge_model is None:
            return "—"
        effort = self.judge_params.get("reasoning_effort")
        return f"{self.judge_model}" + (f" ({effort})" if effort else "")

    # --- agent.params / agent.prompt_hash (SPEC §3 amendment 2026-06-20) ---
    # All four properties consult a presentation-layer backfill map first
    # (``leaderboard/historical_agent_metadata.json``), then fall back to
    # values recorded directly in the record. Records that predate the
    # 2026-06-20 amendment can be displayed with accurate values WITHOUT
    # modifying the signed record itself. ``backfilled_*`` properties
    # expose the source so tooltips can disclose it.

    @property
    def agent_params(self) -> dict[str, Any] | None:
        """Effective agent.params: record value if recorded, else
        historical backfill, else None."""
        agent = self.record.get("agent") or {}
        params = agent.get("params")
        if isinstance(params, dict) and params:
            return params
        backfill = _HISTORICAL_AGENT_METADATA.get(self.submission_id)
        if backfill and isinstance(backfill.get("params"), dict):
            return backfill["params"]
        return None

    @property
    def agent_reasoning_effort(self) -> str | None:
        """Just the reasoning_effort value from agent.params, or None."""
        params = self.agent_params
        return params.get("reasoning_effort") if params else None

    @property
    def agent_params_source(self) -> str:
        """Where the rendered agent.params came from. Used by tooltip."""
        agent = self.record.get("agent") or {}
        params = agent.get("params")
        if isinstance(params, dict) and params:
            return "record"
        if self.submission_id in _HISTORICAL_AGENT_METADATA:
            return "backfill"
        return "missing"

    @property
    def agent_reasoning_label(self) -> str:
        """Display string for the Reasoning column.

        Distinguishes:
        - explicit value ("high", "low", "medium") → show it verbatim
        - "off" / null / "none" → show "off"
        - "api-default" → show "api-def" (Virtuals/OpenRouter served the
          model with no reasoning block; the API decides per-model)
        - no recorded params anywhere → "?"
        """
        params = self.agent_params
        if params is None:
            return "?"
        effort = params.get("reasoning_effort")
        if effort in (None, "", "none", "off"):
            return "off"
        if effort == "api-default":
            return "api-def"
        return str(effort)

    @property
    def agent_prompt_hash(self) -> str | None:
        """Effective agent.prompt_hash: record value if recorded, else
        historical backfill, else None."""
        agent = self.record.get("agent") or {}
        h = agent.get("prompt_hash")
        if h:
            return h
        backfill = _HISTORICAL_AGENT_METADATA.get(self.submission_id)
        if backfill and backfill.get("prompt_hash"):
            return backfill["prompt_hash"]
        return None

    @property
    def agent_prompt_hash_source(self) -> str:
        agent = self.record.get("agent") or {}
        if agent.get("prompt_hash"):
            return "record"
        if (
            self.submission_id in _HISTORICAL_AGENT_METADATA
            and _HISTORICAL_AGENT_METADATA[self.submission_id].get("prompt_hash")
        ):
            return "backfill"
        return "missing"

    @property
    def agent_prompt_label(self) -> str:
        h = self.agent_prompt_hash
        if not h:
            return "?"
        # short prefix: "sha256:abc1234"
        return h[: h.index(":") + 8] if ":" in h else h[:7]

    def is_comparable(self, config: BoardConfig) -> bool:
        """In the OpenAI-paper-comparable judge group?"""
        judge = self.record.get("judge")
        if not isinstance(judge, dict):
            return False
        return (
            judge.get("model") == config.default_judge_model
            and judge.get("params", {}).get("reasoning_effort")
            == config.default_judge_reasoning_effort
            and judge.get("params", {}).get("temperature", 1) == 1
            and judge.get("prompt_hash") == f"sha256:{constants.JUDGE_PROMPT_SHA256}"
        )

    def is_strictly_comparable(self, config: BoardConfig) -> bool:
        """Stricter group: same judge AND same agent prompt_hash AND
        same agent reasoning_effort.

        Added 2026-06-20 with the agent.params / agent.prompt_hash SPEC
        amendment. Defaults to ``is_comparable`` semantics when no
        ``strict_agent_group`` constraint is configured (so old boards
        keep working). When `strict_agent_group` IS configured in
        ``board_config.json``, this is the filter used for the default
        leaderboard view — rows without recorded agent.params /
        agent.prompt_hash fall out, which is the right behavior because
        we can no longer prove they're apples-to-apples.
        """
        if not self.is_comparable(config):
            return False
        strict = getattr(config, "strict_agent_group", None)
        if not strict:
            return True
        if strict.get("require_agent_prompt_hash"):
            if not self.agent_prompt_hash:
                return False
            if strict.get("agent_prompt_hash") and self.agent_prompt_hash != strict["agent_prompt_hash"]:
                return False
        expected = strict.get("agent_reasoning_effort")
        if expected is not None:
            actual = self.agent_reasoning_effort
            if actual != expected:
                return False
        return True

    def is_prize_excluded(self, config: BoardConfig) -> bool:
        return self.operator.lower() in config.prize_excluded_operators

    def is_all_open_weights(self, config: BoardConfig) -> bool:
        if not config.open_weights_patterns:
            return False
        names = [self.agent_model.lower()]
        if self.judge_model:
            names.append(self.judge_model.lower())
        return all(any(p in n for p in config.open_weights_patterns) for n in names)

    def passed_vulnerabilities(self) -> set[str]:
        return {
            e["vulnerability_id"]
            for e in self.record["score"]["per_vulnerability"]
            if e["passed"]
        }


def load_attempts(
    submissions_root: Path | str,
    public_key_path: Path | str | None = "antfleet.public_key.pem",
) -> list[Attempt]:
    """Load every record under the submissions tree, any state."""
    root = Path(submissions_root)
    attempts = []
    if not root.is_dir():
        return attempts
    public_pem = Path(public_key_path).read_bytes() if public_key_path is not None else None
    skipped_bad_signature = 0
    for record_path in sorted(root.rglob("record.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if public_pem is not None and record.get("state") in {"accepted", "promoted", "yanked"}:
            try:
                verify_record(record, public_pem)
            except SignatureError as e:
                skipped_bad_signature += 1
                logger.warning("skipping %s: acceptance signature failed: %s", record_path, e)
                continue
        attempts.append(Attempt(record=record, path=str(record_path)))
    if skipped_bad_signature:
        logger.warning("skipped %d lifecycle record(s) with invalid signatures", skipped_bad_signature)
    return attempts


def _rankable(attempts: list[Attempt], config: BoardConfig, comparable_only: bool,
              at: datetime.datetime | None) -> list[Attempt]:
    out = []
    for a in attempts:
        if a.state != "promoted" or a.promoted_at is None:
            continue
        if at is not None and a.promoted_at > at:
            continue
        if comparable_only and not a.is_comparable(config):
            continue
        out.append(a)
    return out


def _rank_key(a: Attempt) -> tuple:
    return (-(a.official_score or 0.0), a.tokens_total, a.promoted_at, a.submission_id)


@dataclass
class RankedRow:
    rank: int
    attempt: Attempt
    movement: int | None = None  # +N climbed, -N dropped, None = new in window


def ranked_rows(
    attempts: list[Attempt],
    config: BoardConfig,
    comparable_only: bool = True,
    at: datetime.datetime | None = None,
) -> list[RankedRow]:
    """One row per accepted submission, ordered by SPEC tie-breakers.

    Each promoted submission is its own ranked row — there is no collapsing
    by operator. An operator with multiple promoted submissions appears
    multiple times, each at the rank earned by that submission.
    """
    pool = _rankable(attempts, config, comparable_only, at)
    ordered = sorted(pool, key=_rank_key)
    return [RankedRow(rank=i + 1, attempt=a) for i, a in enumerate(ordered)]


def with_rank_movement(
    rows: list[RankedRow],
    attempts: list[Attempt],
    config: BoardConfig,
    now: datetime.datetime,
    comparable_only: bool = True,
) -> list[RankedRow]:
    """Annotate rows with rank delta vs `rank_window_days` ago.

    Movement is tracked per submission: a row's delta is the difference
    between its current rank and the rank it held in the window's
    starting snapshot. Submissions promoted within the window have
    ``movement = None`` (new in window).
    """
    then = now - datetime.timedelta(days=config.rank_window_days)
    old = {
        r.attempt.submission_id: r.rank
        for r in ranked_rows(attempts, config, comparable_only=comparable_only, at=then)
    }
    for row in rows:
        prev = old.get(row.attempt.submission_id)
        row.movement = None if prev is None else prev - row.rank
    return rows


@dataclass(frozen=True)
class FirstSolve:
    vulnerability_id: str
    operator: str
    submission_id: str
    promoted_at: datetime.datetime


def first_solvers(attempts: list[Attempt], config: BoardConfig,
                  comparable_only: bool = False) -> dict[str, FirstSolve]:
    """Earliest promoted solve per vulnerability (SPEC: first-solver credit).

    Defaults to ALL judge groups — first-solver credit is per-task credit,
    not a ranking, so it does not filter to the comparable view.
    """
    pool = sorted(
        _rankable(attempts, config, comparable_only, at=None),
        key=lambda a: (a.promoted_at, a.submission_id),
    )
    solves: dict[str, FirstSolve] = {}
    for a in pool:
        for vid in a.passed_vulnerabilities():
            if vid not in solves:
                solves[vid] = FirstSolve(vid, a.operator, a.submission_id, a.promoted_at)
    return solves


@dataclass(frozen=True)
class Moment:
    when: datetime.datetime
    operator: str
    submission_id: str
    title: str


def threshold_moments(attempts: list[Attempt], config: BoardConfig) -> list[Moment]:
    """Milestones from the promotion timeline (SPEC §5: threshold moments)."""
    timeline = sorted(
        _rankable(attempts, config, comparable_only=False, at=None),
        key=lambda a: (a.promoted_at, a.submission_id),
    )
    moments: list[Moment] = []
    seen: set[str] = set()

    def add(key: str, attempt: Attempt, title: str) -> None:
        if key not in seen:
            seen.add(key)
            moments.append(Moment(attempt.promoted_at, attempt.operator, attempt.submission_id, title))

    sota_pct = next(
        (t["score_pct"] for t in config.reference_targets if t.get("primary")), None
    )
    for a in timeline:
        add("first-submission", a, "First promoted Detect submission")
        pct = (a.official_score or 0) * 100
        if sota_pct is not None and pct > sota_pct and a.is_comparable(config):
            add("crossed-sota", a, f"First to clear the published Detect SOTA ({sota_pct}%)")
        if pct >= 50 and a.is_comparable(config):
            add("crossed-50", a, "First to cross 50%")
        if a.is_all_open_weights(config):
            add("first-open-weights", a, "First all-open-weights Detect stack")
    return moments


@dataclass(frozen=True)
class HistoryPoint:
    when: datetime.datetime
    operator: str
    submission_id: str
    score_pct: float


def best_score_history(attempts: list[Attempt], config: BoardConfig,
                       comparable_only: bool = True) -> list[HistoryPoint]:
    """Board-best score over time (Score history: Best score tab)."""
    timeline = sorted(
        _rankable(attempts, config, comparable_only, at=None),
        key=lambda a: (a.promoted_at, a.submission_id),
    )
    points, best = [], -1.0
    for a in timeline:
        pct = (a.official_score or 0) * 100
        if pct > best:
            best = pct
            points.append(HistoryPoint(a.promoted_at, a.operator, a.submission_id, round(pct, 1)))
    return points


def best_per_model(attempts: list[Attempt], config: BoardConfig,
                   comparable_only: bool = True) -> dict[str, Attempt]:
    """Best promoted attempt per agent model (Improvement per model tab)."""
    out: dict[str, Attempt] = {}
    for a in _rankable(attempts, config, comparable_only, at=None):
        key = a.agent_model
        if key not in out or _rank_key(a) < _rank_key(out[key]):
            out[key] = a
    return out


def operator_trajectory(attempts: list[Attempt], config: BoardConfig, operator: str,
                        comparable_only: bool = True) -> list[tuple[datetime.datetime, int, float]]:
    """(when, rank, score_pct) after each of the operator's promotions
    (operator climb history / Trajectory tab)."""
    promos = sorted(
        (a for a in _rankable(attempts, config, comparable_only, at=None)
         if a.operator.lower() == operator.lower()),
        key=lambda a: (a.promoted_at, a.submission_id),
    )
    trajectory = []
    for a in promos:
        rows = ranked_rows(attempts, config, comparable_only=comparable_only, at=a.promoted_at)
        for row in rows:
            if row.attempt.operator.lower() == operator.lower():
                trajectory.append(
                    (a.promoted_at, row.rank, (row.attempt.official_score or 0) * 100)
                )
                break
    return trajectory


def operator_attempts(attempts: list[Attempt], operator: str) -> list[Attempt]:
    """All attempts (any state, any judge) for an operator, newest first."""
    mine = [a for a in attempts if a.operator.lower() == operator.lower()]
    return sorted(mine, key=lambda a: a.created_at, reverse=True)
