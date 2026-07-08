#!/usr/bin/env python3
"""Empirically prove the Phase 2 Patch board is not gameable to 100%.

Synthesizes *degenerate* patches — ones that neutralize the exploit by bricking
or cosmetically touching the contract instead of actually fixing the bug — and
runs them through the REAL Docker grader (``grade_audit_docker``). A correct,
non-gameable board scores every degenerate patch **0** on every audit: the
invariant (functional) suite must reject a bricked contract.

Also emits the data-derived invariant-guard classification (which audits are
behind a strict / named-set / wide guard) so the evidence artifact ties the
empirical result to the config surface.

Strong-guard control:   2023-07-pooltogether (threshold=0)  -> expect all 0
Wide-guard stress:      2025-04-virtuals (threshold=59)     -> the only real hole
Positive control:       --gold  (upstream gold patch)       -> expect full score

Usage:
    .venv/bin/python scripts/patch_gameability_probe.py --audits 2025-04-virtuals 2023-07-pooltogether
    .venv/bin/python scripts/patch_gameability_probe.py --all              # all 22 (slow; amd64 emulation)
    .venv/bin/python scripts/patch_gameability_probe.py --classify-only    # no Docker; guard table only
    .venv/bin/python scripts/patch_gameability_probe.py --generate-only --audits 2025-04-virtuals   # diffs only
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench import constants  # noqa: E402
from openevmbench.dataset import PatchAudit, load_patch_dataset  # noqa: E402
from openevmbench.gameability import (  # noqa: E402
    DEGENERATE_STRATEGIES,
    classify_invariant_guard,
    mutate_source,
)
from openevmbench.patch_docker import docker_available, grade_audit_docker  # noqa: E402
from openevmbench.patch_worker import AuditGrade, PatchWorkerError  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402

AUDIT_GIT = "https://github.com/evmbench-org/{audit_id}.git"


def _run(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=False)
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")[:500]
        raise PatchWorkerError(f"{' '.join(cmd)} failed ({proc.returncode}): {err}")
    return proc


def _patch_targets(audit: PatchAudit, upstream_root: Path) -> dict[str, Path]:
    """repo-relative dest path -> upstream gold patch file (for the gold control)."""
    audit_dir = upstream_root / "audits" / audit.audit_id
    out: dict[str, Path] = {}
    for vuln in audit.vulnerabilities:
        for local_rel, repo_rel in vuln.patch_path_mapping.items():
            src = audit_dir / local_rel
            if not src.is_file():
                raise PatchWorkerError(f"missing gold patch {src} for {vuln.vulnerability_id}")
            out[repo_rel] = src
    return out


def generate_diffs(
    audit: PatchAudit,
    *,
    upstream_repo_dir: Path,
    strategies: list[str],
    out_dir: Path,
    include_gold: bool,
) -> dict[str, Path]:
    """Clone the audit at base_commit once; write one diff per strategy.

    Returns strategy -> diff path. The ``empty`` strategy is a zero-byte file
    (no patch). ``noop``/``brick`` mutate every patch-target file. ``gold`` (when
    requested) drops in the upstream gold patch as a positive control.
    """
    upstream_root = upstream_repo_dir / constants.UPSTREAM_SUBDIR
    gold_targets = _patch_targets(audit, upstream_root)
    repo_rel_paths = sorted(gold_targets)
    out_dir.mkdir(parents=True, exist_ok=True)
    diffs: dict[str, Path] = {}

    with tempfile.TemporaryDirectory(prefix=f"gameprobe-{audit.audit_id}-") as tmp:
        repo = Path(tmp) / "repo"
        clone = subprocess.run(
            ["git", "clone", "--quiet", AUDIT_GIT.format(audit_id=audit.audit_id), str(repo)],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            raise PatchWorkerError(f"clone {audit.audit_id} failed: {clone.stderr[:300]}")
        _run(["git", "checkout", "-q", audit.base_commit], cwd=repo)

        # Capture the pristine (vulnerable) base content of each target file.
        base_content = {rel: (repo / rel).read_text(encoding="utf-8") for rel in repo_rel_paths}

        def _reset() -> None:
            _run(["git", "checkout", "-q", "--", "."], cwd=repo, check=False)
            _run(["git", "reset", "-q"], cwd=repo, check=False)

        def _diff_current() -> bytes:
            _run(["git", "add", *repo_rel_paths], cwd=repo)
            d = subprocess.run(
                ["git", "-c", "core.fileMode=false", "diff", "--binary", "--cached", *repo_rel_paths],
                cwd=repo,
                capture_output=True,
            )
            if d.returncode != 0:
                raise PatchWorkerError(f"git diff failed for {audit.audit_id}: {d.stderr.decode()[:300]}")
            return d.stdout

        for strat in strategies:
            _reset()
            path = out_dir / f"{audit.audit_id}.{strat}.diff"
            if strat == "empty":
                path.write_bytes(b"")
                diffs[strat] = path
                continue
            for rel in repo_rel_paths:
                (repo / rel).write_text(mutate_source(strat, base_content[rel]), encoding="utf-8")
            path.write_bytes(_diff_current())
            diffs[strat] = path

        if include_gold:
            _reset()
            for rel in repo_rel_paths:
                (repo / rel).write_bytes(gold_targets[rel].read_bytes())
            gold_path = out_dir / f"{audit.audit_id}.gold.diff"
            gold_path.write_bytes(_diff_current())
            diffs["gold"] = gold_path

    return diffs


def _grade(audit: PatchAudit, diff: Path, upstream_repo_dir: Path) -> AuditGrade:
    return grade_audit_docker(
        audit=audit,
        agent_diff=diff,
        upstream_repo_dir=upstream_repo_dir,
        build_if_missing=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--audits", nargs="+", help="audit ids to probe")
    g.add_argument("--all", action="store_true", help="probe all 22 patch audits (slow)")
    ap.add_argument("--classify-only", action="store_true", help="print guard table and exit (no Docker)")
    ap.add_argument("--generate-only", action="store_true", help="write degenerate diffs but do not grade")
    ap.add_argument("--gold", action="store_true", help="also grade the upstream gold patch (positive control)")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "runs" / "gameability")
    args = ap.parse_args()

    upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")
    dataset = load_patch_dataset(upstream)

    # --- guard classification (always) ---
    guards = {a.audit_id: classify_invariant_guard(a) for a in dataset.audits}
    print("Invariant-guard classification (all 22 patch audits):")
    print(f"  {'audit':32s} {'kind':10s} {'strength':8s} {'budget':>6s} vulns")
    for a in dataset.audits:
        gc = guards[a.audit_id]
        flag = "  <-- WIDE GUARD" if gc.flagged else ""
        print(f"  {gc.audit_id:32s} {gc.kind:10s} {gc.strength:8s} {gc.budget:6d} {gc.vuln_count:5d}{flag}")
    wide = [gc.audit_id for gc in guards.values() if gc.flagged]
    print(f"\nWide-guard audits: {wide or 'none'}")

    if args.classify_only:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "guards.json").write_text(
            json.dumps({k: asdict(v) for k, v in guards.items()}, indent=2), encoding="utf-8"
        )
        return 0

    if args.all:
        audit_ids = [a.audit_id for a in dataset.audits]
    elif args.audits:
        audit_ids = args.audits
    else:
        # Default: the strong-guard control + the one wide-guard hole.
        audit_ids = ["2023-07-pooltogether", "2025-04-virtuals"]
    by_id = {a.audit_id: a for a in dataset.audits}
    for aid in audit_ids:
        if aid not in by_id:
            print(f"error: {aid} not in patch-tasks split", file=sys.stderr)
            return 2

    strategies = list(DEGENERATE_STRATEGIES)
    diffs_dir = args.out / "diffs"
    print(f"\nGenerating degenerate diffs ({', '.join(strategies)}"
          + (", gold" if args.gold else "") + f") for: {', '.join(audit_ids)}")

    generated: dict[str, dict[str, Path]] = {}
    for aid in audit_ids:
        try:
            generated[aid] = generate_diffs(
                by_id[aid],
                upstream_repo_dir=upstream,
                strategies=strategies,
                out_dir=diffs_dir,
                include_gold=args.gold,
            )
            sizes = {s: p.stat().st_size for s, p in generated[aid].items()}
            print(f"  [{aid}] diffs: {sizes}")
        except PatchWorkerError as e:
            print(f"  [{aid}] diff generation FAILED: {e}", file=sys.stderr)
            generated[aid] = {}

    if args.generate_only:
        print(f"\nDiffs written to {diffs_dir} (grading skipped).")
        return 0

    if not docker_available():
        print("\nERROR: Docker daemon not available; cannot grade. "
              "Re-run with --generate-only or start Docker.", file=sys.stderr)
        return 3

    # --- grade every diff through the real Docker grader ---
    report: dict[str, dict] = {}
    gameable_hits: list[str] = []
    gold_failures: list[str] = []
    for aid in audit_ids:
        audit = by_id[aid]
        report[aid] = {"guard": asdict(guards[aid]), "strategies": {}}
        for strat, diff in generated.get(aid, {}).items():
            is_degenerate = strat in DEGENERATE_STRATEGIES
            try:
                grade = _grade(audit, diff, upstream)
                entry = {
                    "score": grade.score,
                    "max_score": grade.max_score,
                    "invariant_passed": grade.invariant_passed,
                    "reason_code": grade.reason_code,
                    "invariant_n_failures": grade.invariant_n_failures,
                    "invariant_failures": list(grade.invariant_failures),
                }
            except PatchWorkerError as e:
                entry = {"error": str(e)[:300]}
            report[aid]["strategies"][strat] = entry
            verdict = "?"
            if is_degenerate:
                # A degenerate patch that errors (e.g. bricked contract won't compile)
                # earns no credit — the guard rejected it. Only a positive score is a hit.
                if "error" in entry:
                    verdict = "OK (0 — rejected, grader error, no credit)"
                elif entry["score"] == 0:
                    inv = "" if entry["invariant_passed"] else " [invariant-failed]"
                    verdict = f"OK (0 — not gameable){inv}"
                else:
                    verdict = f"GAMEABLE ({entry['score']}/{entry['max_score']})"
                    gameable_hits.append(f"{aid}:{strat}={entry['score']}/{entry['max_score']}")
            else:  # gold positive control
                if "error" in entry:
                    verdict = f"GOLD-ERROR: {entry['error'][:70]}"
                    gold_failures.append(f"{aid}=error")
                elif entry["score"] == entry["max_score"]:
                    verdict = f"OK (gold {entry['score']}/{entry['max_score']})"
                else:
                    verdict = f"GOLD-REGRESSION ({entry['score']}/{entry['max_score']})"
                    gold_failures.append(f"{aid}={entry['score']}/{entry['max_score']}")
            inv_n = entry.get("invariant_n_failures")
            inv_str = f"  (inv_failures={inv_n})" if inv_n is not None else ""
            print(f"  [{aid}] {strat:6s} -> {verdict}{inv_str}")

    args.out.mkdir(parents=True, exist_ok=True)
    verdict_pass = not gameable_hits
    summary = {
        "harness_version": constants.PATCH_HARNESS_VERSION,
        "upstream_commit": constants.UPSTREAM_COMMIT,
        "audits_probed": audit_ids,
        "strategies": strategies + (["gold"] if args.gold else []),
        "wide_guard_audits": wide,
        "gameable_hits": gameable_hits,
        "gold_regressions": gold_failures,
        "verdict": "NOT-GAMEABLE" if verdict_pass else "GAMEABLE-FINDINGS",
        "report": report,
    }
    (args.out / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_summary_md(args.out / "SUMMARY.md", summary, guards)
    print(f"\nVerdict: {summary['verdict']}")
    if gameable_hits:
        print("  Gameable findings:", gameable_hits)
    if gold_failures:
        print("  Gold regressions:", gold_failures)
    print(f"Report: {args.out / 'report.json'}")
    return 0 if verdict_pass else 1


def _write_summary_md(path: Path, summary: dict, guards: dict) -> None:
    lines = [
        "# Phase 2 Patch — Gameability Probe Result",
        "",
        f"- Harness: `{summary['harness_version']}`",
        f"- Upstream: `{summary['upstream_commit']}`",
        f"- Audits probed: {', '.join(summary['audits_probed'])}",
        f"- Degenerate strategies: {', '.join(summary['strategies'])}",
        f"- **Verdict: {summary['verdict']}**",
        "",
        "A degenerate strategy scoring anything above 0 is a gameable finding: the",
        "board credited a patch that bricked/cosmetically-touched the contract instead",
        "of fixing the bug.",
        "",
        "## Results",
        "",
        "| Audit | Guard | Strategy | Score | Invariant | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for aid, data in summary["report"].items():
        gc = data["guard"]
        for strat, entry in data["strategies"].items():
            if "error" in entry:
                lines.append(f"| {aid} | {gc['kind']} ({gc['budget']}) | {strat} | — | — | ERROR |")
                continue
            degen = strat != "gold"
            if degen:
                verdict = "not gameable" if entry["score"] == 0 else "**GAMEABLE**"
            else:
                verdict = "gold ok" if entry["score"] == entry["max_score"] else "**GOLD REGRESSION**"
            inv = "pass" if entry["invariant_passed"] else "fail"
            lines.append(
                f"| {aid} | {gc['kind']} ({gc['budget']}) | {strat} | "
                f"{entry['score']}/{entry['max_score']} | {inv} | {verdict} |"
            )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
