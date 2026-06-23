"""openevmbench CLI: login, clone, run, submit, verify — plus admin commands.

Submitter flow (SPEC §5):
    openevmbench login <token>
    openevmbench clone
    openevmbench run --agent-outputs DIR --judge-model gpt-5 ...
    openevmbench submit --package submissions/phase1/<you>/<id>

Admin commands are used by AntFleet's PR-check and signing pipeline:
    openevmbench admin keygen | accept | reject | promote | yank
    openevmbench check-pr --changed-files ... (GitHub Action entrypoint)

`verify` implements the SPEC §4 third-party verification recipe so anyone
can check an accepted record against antfleet.public_key.pem.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from openevmbench import constants
from openevmbench.accept import accept, promote, reject, yank
from openevmbench.checks import check_package, find_submission_dir
from openevmbench.config import Credentials, load_credentials, save_credentials
from openevmbench.dataset import DatasetError, load_detect_dataset, load_patch_dataset
from openevmbench.judge import OpenAICompatibleJudgeClient
from openevmbench.package import AgentInfo, JudgeInfo, OperatorInfo, RunMeta
from openevmbench.runner import run_detect, run_patch
from openevmbench.signing import generate_keypair, verify_record
from openevmbench.upstream import ensure_upstream


def _die(msg: str, code: int = 1) -> "int":
    print(f"error: {msg}", file=sys.stderr)
    return code


def _github_user(token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "openevmbench-cli",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_login(args: argparse.Namespace) -> int:
    try:
        user = _github_user(args.token)
    except Exception as e:
        return _die(f"token verification against api.github.com failed: {e}")
    creds = Credentials(github_username=user["login"], github_id=int(user["id"]), token=args.token)
    path = save_credentials(creds)
    print(f"logged in as @{creds.github_username} (id {creds.github_id})")
    print(f"credentials stored at {path} (mode 0600)")
    return 0


def cmd_clone(args: argparse.Namespace) -> int:
    dest = ensure_upstream(args.dest)
    ds = load_detect_dataset(dest)
    print(f"upstream pinned at {ds.commit[:12]} — {ds.audit_count} audits / {ds.vulnerability_count} vulnerabilities verified")
    return 0


def _parse_judge_params(pairs: list[str]) -> dict:
    params: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--judge-param must be key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        try:
            params[key] = json.loads(value)
        except json.JSONDecodeError:
            params[key] = value
    return params


def _parse_agent_params(pairs: list[str]) -> dict:
    params: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--agent-param must be key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        try:
            params[key] = json.loads(value)
        except json.JSONDecodeError:
            params[key] = value
    return params


def cmd_run(args: argparse.Namespace) -> int:
    creds = load_credentials()
    if creds is None:
        return _die("not logged in — run `openevmbench login <token>` first")

    if args.mode == "patch":
        return _cmd_run_patch(args, creds)
    return _cmd_run_detect(args, creds)


def _cmd_run_detect(args: argparse.Namespace, creds: Credentials) -> int:
    try:
        judge_params = _parse_judge_params(args.judge_param or [])
        agent_params = _parse_agent_params(args.agent_param or [])
    except ValueError as e:
        return _die(str(e))

    # Auto-pick scaffold sidecar metadata (SPEC §3 amendment, 2026-06-20).
    # The auditor writes ``.openevmbench-scaffold-metadata.json`` next to its
    # output dir. If present AND the operator didn't override via CLI flags,
    # populate agent.params and agent.prompt_hash automatically.
    from pathlib import Path as _Path
    _sidecar_path = _Path(args.agent_outputs).parent / ".openevmbench-scaffold-metadata.json"
    agent_prompt_hash = args.agent_prompt_hash
    if _sidecar_path.is_file():
        try:
            _sidecar = json.loads(_sidecar_path.read_text(encoding="utf-8"))
            if not agent_params and _sidecar.get("params"):
                agent_params = _sidecar["params"]
                print(f"# loaded agent.params from {_sidecar_path}: {agent_params}")
            if not agent_prompt_hash and _sidecar.get("prompt_hash"):
                agent_prompt_hash = _sidecar["prompt_hash"]
                print(f"# loaded agent.prompt_hash from {_sidecar_path}: {agent_prompt_hash}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"# warning: could not read sidecar {_sidecar_path}: {e}")

    api_key = os.environ.get(args.api_key_env, "")
    if not api_key:
        return _die(f"judge API key env var {args.api_key_env} is not set")

    dataset = load_detect_dataset(args.upstream)
    client = OpenAICompatibleJudgeClient(
        model=args.judge_model,
        api_key=api_key,
        base_url=args.judge_base_url,
        params=judge_params,
    )
    tokens_per_task = (
        [int(t) for t in args.tokens_per_task.split(",")] if args.tokens_per_task else []
    )
    result = run_detect(
        dataset=dataset,
        agent_outputs_dir=args.agent_outputs,
        harness_dir=args.harness_dir,
        judge_client=client,
        judge_info=JudgeInfo(model=args.judge_model, params=judge_params),
        operator=OperatorInfo(
            github_username=creds.github_username,
            github_id=creds.github_id,
            affiliation=args.affiliation,
        ),
        agent=AgentInfo(
            model=args.model,
            scaffold_name=args.scaffold_name,
            scaffold_hash=args.scaffold_hash,
            harness_kind=args.harness_kind,
            params=agent_params or None,
            prompt_hash=agent_prompt_hash or None,
        ),
        run_meta=RunMeta(
            tokens_total=args.tokens_total,
            tokens_prompt=args.tokens_prompt,
            tokens_completion=args.tokens_completion,
            tokens_per_task=tokens_per_task,
            wall_clock_ms=args.wall_clock_ms,
            runs_count=args.runs_count,
        ),
        submissions_root=args.out,
    )
    record = result.package.record
    pct = record["score"]["claimed_score"] * 100
    print(f"claimed score: {pct:.1f}%  {result.solved_count}/{record['score']['max_score']}")
    print(f"package: {result.package.package_dir}")
    for warning in result.validation.warnings:
        print(f"warning: {warning}")
    print("next: openevmbench submit --package", result.package.package_dir)
    return 0


def _cmd_run_patch(args: argparse.Namespace, creds: Credentials) -> int:
    try:
        agent_params = _parse_agent_params(args.agent_param or [])
    except ValueError as e:
        return _die(str(e))

    dataset = load_patch_dataset(args.upstream)
    sources_dir = Path(args.sources) if args.sources else None
    if args.docker:
        if sources_dir is not None:
            print("note: --docker ignores --sources (grading runs inside audit containers)")
        sources_dir = None
    elif sources_dir is not None and not sources_dir.is_dir():
        return _die(f"sources dir not found: {sources_dir}")
    elif not args.docker and sources_dir is None:
        print("warning: no --sources and no --docker; diffs will be copied but not graded", file=sys.stderr)

    tokens_per_task = (
        [int(t) for t in args.tokens_per_task.split(",")] if args.tokens_per_task else []
    )
    result = run_patch(
        dataset=dataset,
        agent_outputs_dir=args.agent_outputs,
        sources_dir=sources_dir,
        upstream_repo_dir=args.upstream,
        operator=OperatorInfo(
            github_username=creds.github_username,
            github_id=creds.github_id,
            affiliation=args.affiliation,
        ),
        agent=AgentInfo(
            model=args.model,
            scaffold_name=args.scaffold_name,
            scaffold_hash=args.scaffold_hash,
            harness_kind=args.harness_kind,
            params=agent_params or None,
            prompt_hash=args.agent_prompt_hash or None,
        ),
        run_meta=RunMeta(
            tokens_total=args.tokens_total,
            tokens_prompt=args.tokens_prompt,
            tokens_completion=args.tokens_completion,
            tokens_per_task=tokens_per_task,
            wall_clock_ms=args.wall_clock_ms,
            runs_count=args.runs_count,
        ),
        submissions_root=args.out,
        skip_invariant=not args.with_invariant,
        use_docker=args.docker,
    )
    record = result.package.record
    pct = record["score"]["claimed_score"] * 100
    print(f"claimed score: {pct:.1f}%  {result.solved_count}/{record['score']['max_score']}")
    print(f"package: {result.package.package_dir}")
    if args.docker:
        print("note: graded in Docker audit containers (acceptance-parity path)")
    elif sources_dir is None:
        print("note: no grading performed (reason_code=not-graded)")
    elif not args.with_invariant:
        print("note: host forge with invariant skipped; use --docker for acceptance parity")
    for warning in result.validation.warnings:
        print(f"warning: {warning}")
    print("next: openevmbench submit --package", result.package.package_dir)
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    package_dir = Path(args.package)
    repo_root = Path(args.repo_root).resolve()
    try:
        package_rel = package_dir.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return _die(f"package {package_dir} is not inside repo root {repo_root}")

    try:
        phase = int(package_rel.split("/")[1].replace("phase", ""))
    except (IndexError, ValueError):
        return _die(f"cannot infer phase from package path {package_rel!r}")

    try:
        if phase == 1:
            dataset = load_detect_dataset(args.upstream)
        elif phase == 2:
            dataset = load_patch_dataset(args.upstream)
        else:
            return _die(f"unsupported submission phase {phase}")
    except DatasetError as e:
        return _die(f"cannot load pinned upstream cache for local validation: {e}")

    report = check_package(repo_root, package_rel, pr_author=None, dataset=dataset)
    for warning in report.warnings:
        print(f"warning: {warning}")
    if not report.ok:
        print(report.summary(), file=sys.stderr)
        return _die("local validation failed — fix the package before opening a PR")

    print("local validation passed")
    branch = f"submission/{package_rel.split('/')[-2]}-{package_rel.split('/')[-1][:13]}"
    phase_label = "Detect" if phase == 1 else "Patch"
    print("\nPR-ready package. To submit:")
    print(f"  git checkout -b {branch}")
    print(f"  git add {package_rel}")
    print(f'  git commit -m "Phase {phase} {phase_label} submission {package_rel.split("/")[-1]}"')
    print(f"  gh pr create --repo {args.repo} --title \"Phase {phase} {phase_label} submission\" --fill")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    public_pem = Path(args.public_key).read_bytes()
    try:
        verify_record(record, public_pem)
    except Exception as e:
        return _die(f"verification FAILED: {e}")
    print(
        f"OK: AntFleet acceptance signature verifies "
        f"(signed_at {record['antfleet_acceptance']['signed_at']}, "
        f"official_score {record['score'].get('official_score')})"
    )
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    import datetime

    from openevmbench.render import render_site

    try:
        now = (
            datetime.datetime.fromisoformat(args.now.replace("Z", "+00:00"))
            if args.now
            else None
        )
    except ValueError as e:
        return _die(f"--now must be RFC 3339 / ISO 8601: {e}")
    if now is not None and now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    out = render_site(args.submissions, args.config, args.out, now=now)
    pages = sum(1 for _ in out.rglob("*.html"))
    print(f"rendered {pages} pages to {out}")
    return 0


def cmd_check_pr(args: argparse.Namespace) -> int:
    changed = [p for p in (args.changed_files or "").split("\n") if p.strip()]
    package_rel, report = find_submission_dir(changed)
    if report.ok and package_rel:
        try:
            phase = int(package_rel.split("/")[1].replace("phase", ""))
            if phase == 1:
                dataset = load_detect_dataset(args.upstream)
            elif phase == 2:
                dataset = load_patch_dataset(args.upstream)
            else:
                report.fail("record-invalid", f"unsupported submission phase {phase}")
                dataset = None
        except DatasetError as e:
            report.fail("upstream-cache-invalid", str(e))
            dataset = None
        if dataset is not None:
            pkg_report = check_package(
                args.repo_root,
                package_rel,
                pr_author=args.pr_author,
                pr_author_id=args.pr_author_id,
                dataset=dataset,
            )
            report.failures.extend(pkg_report.failures)
            report.warnings.extend(pkg_report.warnings)
    print(report.summary())
    return 0 if report.ok else 1


def _read_record(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_record(record: dict, path: str) -> None:
    Path(path).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_admin_keygen(args: argparse.Namespace) -> int:
    private_pem, public_pem = generate_keypair()
    private_path, public_path = Path(args.out_private), Path(args.out_public)
    if private_path.exists():
        return _die(f"{private_path} already exists — refusing to overwrite a signing key")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(private_pem)
    private_path.chmod(0o600)
    public_path.write_bytes(public_pem)
    from openevmbench.signing import public_key_fingerprint

    print(f"private key: {private_path} (mode 0600 — NEVER commit)")
    print(f"public key:  {public_path}")
    print(f"fingerprint: {public_key_fingerprint(public_pem)}")
    return 0


def _load_private_key(args: argparse.Namespace) -> bytes:
    env_pem = os.environ.get("ANTFLEET_PRIVATE_KEY_PEM")
    if env_pem:
        return env_pem.encode("utf-8")
    if args.private_key:
        return Path(args.private_key).read_bytes()
    raise SystemExit("error: provide --private-key or ANTFLEET_PRIVATE_KEY_PEM")


def cmd_admin_accept(args: argparse.Namespace) -> int:
    record = _read_record(args.record)
    private_pem = _load_private_key(args)
    public_pem = Path(args.public_key).read_bytes()
    signed = accept(record, private_pem, public_pem, official_score=args.official_score)
    _write_record(signed, args.record)
    verify_record(signed, public_pem)
    print(f"accepted + signed: {args.record} (official_score {signed['score']['official_score']})")
    return 0


def cmd_admin_reject(args: argparse.Namespace) -> int:
    record = _read_record(args.record)
    _write_record(reject(record, args.reason), args.record)
    print(f"rejected: {args.record} ({args.reason})")
    return 0


def cmd_admin_promote(args: argparse.Namespace) -> int:
    record = _read_record(args.record)
    _write_record(promote(record, promoted_commit_sha=args.commit), args.record)
    print(f"promoted: {args.record} (commit {args.commit[:12]})")
    return 0


def cmd_admin_yank(args: argparse.Namespace) -> int:
    record = _read_record(args.record)
    _write_record(yank(record, args.reason), args.record)
    print(f"yanked: {args.record}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openevmbench")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("login", help="store and verify an API token")
    p.add_argument("token")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("clone", help="fetch the pinned upstream benchmark source")
    p.add_argument("--dest", default="upstream/frontier-evals")
    p.set_defaults(func=cmd_clone)

    p = sub.add_parser("run", help="judge agent outputs locally and package a submission")
    p.add_argument(
        "--mode",
        choices=("detect", "patch"),
        default="detect",
        help="detect: LLM-judged audit reports; patch: deterministic diff grading",
    )
    p.add_argument(
        "--agent-outputs",
        required=True,
        help="detect: dir of <audit-id>/audit.md; patch: dir of <audit-id>.diff files",
    )
    p.add_argument(
        "--sources",
        default=None,
        help="patch mode: audit_sources/ checkout root for local grading (see fetch_audit_sources.py)",
    )
    p.add_argument(
        "--with-invariant",
        action="store_true",
        help="patch host mode: run invariant suite (requires forge pin parity; default skips)",
    )
    p.add_argument(
        "--docker",
        action="store_true",
        help="patch mode: grade inside per-audit Docker containers (production / acceptance path)",
    )
    p.add_argument("--upstream", default="upstream/frontier-evals")
    p.add_argument("--harness-dir", default="harness")
    p.add_argument("--out", default="submissions")
    p.add_argument("--judge-model", default=constants.DEFAULT_JUDGE_MODEL)
    p.add_argument("--judge-base-url", default="https://api.openai.com/v1")
    p.add_argument("--judge-param", action="append", metavar="KEY=VALUE",
                   help=f"material judge params; paper-comparable default is reasoning_effort={constants.DEFAULT_JUDGE_REASONING_EFFORT}")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY")
    p.add_argument("--model", required=True, help="agent model name")
    p.add_argument("--scaffold-name", required=True)
    p.add_argument("--scaffold-hash", required=True, help="sha256:<hex> of the scaffold definition")
    p.add_argument("--harness-kind", required=True, choices=list(constants.HARNESS_KINDS))
    p.add_argument(
        "--agent-param", action="append", metavar="KEY=VALUE",
        help="material agent params that affect comparability (e.g. reasoning_effort=high, "
             "temperature=0.7). Recorded under agent.params in record.json so leaderboard "
             "filters can group genuinely-comparable rows.",
    )
    p.add_argument(
        "--agent-prompt-hash", default=None,
        help="sha256:<hex> of the AUDITOR_PROMPT (or whatever system prompt the scaffold "
             "uses). Recorded under agent.prompt_hash so leaderboard can require matching "
             "prompts for fair comparison.",
    )
    p.add_argument("--affiliation", default=None)
    p.add_argument("--tokens-total", type=int, default=0)
    p.add_argument("--tokens-prompt", type=int, default=0)
    p.add_argument("--tokens-completion", type=int, default=0)
    p.add_argument("--tokens-per-task", default="", help="comma-separated per-task token counts")
    p.add_argument("--wall-clock-ms", type=int, default=0)
    p.add_argument("--runs-count", type=int, default=1)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("submit", help="validate a package and print/open the submission PR")
    p.add_argument("--package", required=True)
    p.add_argument("--repo", default="AntFleet/open-evmbench")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--upstream", default="upstream/frontier-evals")
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("verify", help="verify an accepted record's AntFleet signature")
    p.add_argument("--record", required=True)
    p.add_argument("--public-key", default="antfleet.public_key.pem")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("board", help="render the static leaderboard site")
    p.add_argument("--submissions", default="submissions")
    p.add_argument("--config", default="leaderboard/board_config.json")
    p.add_argument("--out", default="leaderboard/site")
    p.add_argument("--now", default=None, help="render-time override (RFC 3339, for tests)")
    p.set_defaults(func=cmd_board)

    p = sub.add_parser("check-pr", help="(CI) run submission checks on PR-changed files")
    p.add_argument("--changed-files", required=True, help="newline-separated changed paths")
    p.add_argument("--pr-author", default=None)
    p.add_argument("--pr-author-id", default=None)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--upstream", default="upstream/frontier-evals")
    p.set_defaults(func=cmd_check_pr)

    admin = sub.add_parser("admin", help="AntFleet pipeline commands")
    admin_sub = admin.add_subparsers(dest="admin_command", required=True)

    p = admin_sub.add_parser("keygen", help="generate the acceptance keypair")
    p.add_argument("--out-private", required=True)
    p.add_argument("--out-public", default="antfleet.public_key.pem")
    p.set_defaults(func=cmd_admin_keygen)

    p = admin_sub.add_parser("accept", help="accept + sign a checked record (in place)")
    p.add_argument("--record", required=True)
    p.add_argument("--private-key", default=None, help="or set ANTFLEET_PRIVATE_KEY_PEM")
    p.add_argument("--public-key", default="antfleet.public_key.pem")
    p.add_argument("--official-score", type=float, default=None)
    p.set_defaults(func=cmd_admin_accept)

    p = admin_sub.add_parser("reject", help="mark a record rejected with a reason")
    p.add_argument("--record", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_admin_reject)

    p = admin_sub.add_parser("promote", help="mark an accepted record promoted")
    p.add_argument("--record", required=True)
    p.add_argument("--commit", required=True, help="public Git commit sha containing the accepted record")
    p.set_defaults(func=cmd_admin_promote)

    p = admin_sub.add_parser("yank", help="invalidate a promoted record")
    p.add_argument("--record", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_admin_yank)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
