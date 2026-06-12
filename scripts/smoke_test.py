"""End-to-end pipeline smoke test (launch checklist rehearsal).

Exercises the full submitter→AntFleet path with no API keys or network
(beyond the upstream clone if not already cached): deterministic marker
judge stands in for the LLM judge.

    run → package → PR checks → accept+sign → verify → promote → verify → board

Usage:  .venv/bin/python scripts/smoke_test.py
Exit 0 = every stage passed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench.accept import accept, promote  # noqa: E402
from openevmbench.checks import check_package, find_submission_dir  # noqa: E402
from openevmbench.dataset import load_detect_dataset  # noqa: E402
from openevmbench.package import AgentInfo, JudgeInfo, OperatorInfo, RunMeta  # noqa: E402
from openevmbench.render import render_site  # noqa: E402
from openevmbench.runner import run_detect  # noqa: E402
from openevmbench.signing import generate_keypair, verify_record  # noqa: E402
from openevmbench.upstream import ensure_upstream  # noqa: E402


def _marker(text: str) -> str:
    return "MARKER-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class MarkerJudge:
    def complete(self, system: str, user: str) -> str:
        audit, vuln = user.split("\n\nVulnerability description:\n", 1)
        detected = _marker(vuln) in audit
        return json.dumps({"detected": detected, "reasoning": "marker"})


def main() -> int:
    stage = "upstream"
    tmp = Path(tempfile.mkdtemp(prefix="evmb-smoke-"))
    try:
        upstream = ensure_upstream(REPO_ROOT / "upstream" / "frontier-evals")
        ds = load_detect_dataset(upstream)
        print(f"[1/8] upstream OK: {ds.audit_count} audits / {ds.vulnerability_count} vulns")

        stage = "agent outputs"
        outputs = tmp / "agent_outputs"
        solved_audits = ds.audits[:3]
        for audit in solved_audits:
            p = outputs / audit.audit_id / "audit.md"
            p.parent.mkdir(parents=True)
            p.write_text("\n".join(_marker(v.text_content()) for v in audit.vulnerabilities))
        expected = sum(len(a.vulnerabilities) for a in solved_audits)
        print(f"[2/8] fake agent outputs for {len(solved_audits)} audits ({expected} solvable)")

        stage = "run"
        result = run_detect(
            dataset=ds,
            agent_outputs_dir=outputs,
            harness_dir=REPO_ROOT / "harness",
            judge_client=MarkerJudge(),
            judge_info=JudgeInfo(model="marker-judge", params={"deterministic": True}),
            operator=OperatorInfo(github_username="smoketest", github_id=1),
            agent=AgentInfo(model="smoke-model", scaffold_name="smoke",
                            scaffold_hash="sha256:" + "0" * 64, harness_kind="single-shot"),
            run_meta=RunMeta(tokens_total=1, tokens_prompt=1, tokens_completion=0,
                             tokens_per_task=[], wall_clock_ms=0),
            submissions_root=tmp / "submissions",
        )
        assert result.solved_count == expected, (result.solved_count, expected)
        print(f"[3/8] run + package OK: {result.solved_count}/117")

        stage = "checks"
        rel = result.package.package_dir.relative_to(tmp).as_posix()
        changed = [f"{rel}/{p.relative_to(result.package.package_dir).as_posix()}"
                   for p in result.package.package_dir.rglob("*") if p.is_file()]
        found, report = find_submission_dir(changed)
        assert report.ok and found, report.summary()
        report = check_package(tmp, rel, pr_author="smoketest", pr_author_id=1, dataset=ds)
        assert report.ok, report.summary()
        print("[4/8] PR checks OK")

        stage = "accept+sign"
        private_pem, public_pem = generate_keypair()
        public_key_path = tmp / "public.pem"
        public_key_path.write_bytes(public_pem)
        accepted = accept(result.package.record, private_pem, public_pem)
        verify_record(accepted, public_pem)
        print("[5/8] acceptance signature OK")

        stage = "promote"
        promoted = promote(accepted, promoted_commit_sha="0" * 40)
        verify_record(promoted, public_pem)
        (result.package.package_dir / "record.json").write_text(json.dumps(promoted))
        print("[6/8] promotion + post-promotion verify OK")

        stage = "board"
        site = render_site(tmp / "submissions", REPO_ROOT / "leaderboard" / "board_config.json",
                           tmp / "site", public_key_path=public_key_path)
        index = (site / "all.html").read_text()
        assert "@smoketest" in index and "45.6% paper" in index
        pages = sum(1 for _ in site.rglob("*.html"))
        print(f"[7/8] board render OK: {pages} pages")

        stage = "tamper detection"
        record = json.loads((result.package.package_dir / "record.json").read_text())
        record["score"]["official_score"] = 1.0
        try:
            verify_record(record, public_pem)
            raise AssertionError("tampered record verified — signature check is broken")
        except Exception as e:
            if "broken" in str(e):
                raise
        print("[8/8] tamper detection OK")

        print("\nSMOKE TEST PASSED — full pipeline functional")
        return 0
    except Exception as e:
        print(f"\nSMOKE TEST FAILED at stage {stage!r}: {e}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
