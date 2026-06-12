"""Lifecycle transitions: accept, reject, promote, yank (SPEC §4).

Acceptance is the only transition that signs. Promotion and yanking are
post-signing mutations recorded in follow-up commits; signature verification
normalizes them away (see openevmbench.signing).

`promoted_commit_sha` is the public Git commit that merged the accepted
record; the promotion-metadata commit that sets these fields immediately
follows it and references it.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any

from openevmbench.signing import sign_record


class TransitionError(Exception):
    """Raised on an invalid lifecycle transition."""


def _now_rfc3339() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def accept(
    record: dict[str, Any],
    private_pem: bytes,
    public_pem: bytes,
    official_score: float | None = None,
    signed_at: str | None = None,
) -> dict[str, Any]:
    """Produce a signed accepted_record from a submitted record.

    `official_score` defaults to the Detect ledger-derived score
    (`solved_count / max_score`, rounded to 4 decimals).
    """
    state = record.get("state")
    if state not in (None, "checking"):
        raise TransitionError(f"cannot accept a record in state {state!r}")

    rec = copy.deepcopy(record)
    rec["state"] = "accepted"
    rec["state_reason"] = None
    rec["score"]["official_score"] = official_score if official_score is not None else round(
        rec["score"]["solved_count"] / rec["score"]["max_score"], 4
    )
    rec["prize_review_status"] = None
    rec["prize_review_reason"] = None
    return sign_record(rec, private_pem, public_pem, signed_at=signed_at)


def reject(record: dict[str, Any], reason: str) -> dict[str, Any]:
    """Produce a rejected record with a public reason code/message."""
    if not reason.strip():
        raise TransitionError("rejection requires a non-empty state_reason")
    state = record.get("state")
    if state not in (None, "checking"):
        raise TransitionError(f"cannot reject a record in state {state!r}")
    rec = copy.deepcopy(record)
    rec["state"] = "rejected"
    rec["state_reason"] = reason
    return rec


def promote(
    record: dict[str, Any],
    promoted_commit_sha: str,
    promoted_at: str | None = None,
) -> dict[str, Any]:
    """Mark an accepted record as promoted into the public Git log."""
    if record.get("state") != "accepted":
        raise TransitionError(f"only accepted records can be promoted, state is {record.get('state')!r}")
    rec = copy.deepcopy(record)
    rec["state"] = "promoted"
    rec["promoted_at"] = promoted_at or _now_rfc3339()
    rec["promoted_commit_sha"] = promoted_commit_sha
    return rec


def yank(record: dict[str, Any], reason: str) -> dict[str, Any]:
    """Invalidate a previously promoted record (follow-up commit, SPEC §5)."""
    if record.get("state") != "promoted":
        raise TransitionError(f"only promoted records can be yanked, state is {record.get('state')!r}")
    if not reason.strip():
        raise TransitionError("yank requires a non-empty state_reason")
    rec = copy.deepcopy(record)
    rec["state"] = "yanked"
    rec["state_reason"] = reason
    return rec
