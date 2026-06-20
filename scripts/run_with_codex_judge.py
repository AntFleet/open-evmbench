"""Drop-in equivalent of ``openevmbench run`` that uses codex (gpt-5.5 via
ChatGPT subscription) as the judge instead of the OpenAI API gpt-5 judge.

Same flow as the canonical ``openevmbench run``:

    agent_outputs/<audit-id>/audit.md  →  judge per vulnerability
                                       →  judge_transcript.jsonl
                                       →  record.json
                                       →  validated PR package

The only difference is the judge client: a ``CodexJudgeClient`` that
spawns ``codex exec`` for each judge call, vs. ``OpenAICompatibleJudgeClient``
that POSTs to ``https://api.openai.com/v1/chat/completions``.

Cost framing: codex billing is the operator's ChatGPT Plus/Pro
subscription; there is no per-call OpenAI API charge. The verdict
equivalence with the API gpt-5 judge was measured at 98.29% (115/117)
on the reference submission (see memory entry
``codex-gpt55-judge-equivalent-to-api-gpt5``).

Subscription billing guards (mirroring the auditor's three-layer model):
- ``OPENAI_API_KEY``, ``OPENAI_BASE_URL``, ``OPENAI_ORG_ID``,
  ``OPENAI_ORGANIZATION`` are stripped from the codex subprocess env so
  the call always charges the ChatGPT subscription, not the API.
- ``-c developer_instructions=""`` overrides the user's
  ``~/.codex/config.toml`` block (saves ~175 tokens of personal-config
  noise; codex's own ~23K runtime preamble is unavoidable).
- ``--output-schema`` enforces JudgeResult shape on the model output.

Usage (same arg shape as ``openevmbench run`` except no ``--judge-base-url``
or ``--api-key-env`` since codex doesn't use HTTP):

    python scripts/run_with_codex_judge.py \\
        --agent-outputs runs/gpt-5.5/agent_outputs \\
        --model gpt-5.5 \\
        --scaffold-name frontier-models-fleet-single-shot \\
        --scaffold-hash sha256:745ad0272b... \\
        --harness-kind single-shot \\
        --judge-model gpt-5.5 \\
        --judge-param reasoning_effort=high

The output is a fully signed-ready submission package under
``submissions/phase1/<github>/<uuid>/`` exactly like ``openevmbench run``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from openevmbench import constants  # noqa: E402
from openevmbench.config import load_credentials  # noqa: E402
from openevmbench.dataset import load_detect_dataset  # noqa: E402
from openevmbench.judge import JUDGE_RESULT_SCHEMA, JudgeError  # noqa: E402
from openevmbench.package import AgentInfo, JudgeInfo, OperatorInfo, RunMeta  # noqa: E402
from openevmbench.runner import run_detect  # noqa: E402


CODEX_STRIP_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION",
)


def _scrub_codex_env() -> dict[str, str]:
    env = dict(os.environ)
    for var in CODEX_STRIP_ENV:
        env.pop(var, None)
    return env


@dataclass
class CodexJudgeClient:
    """Implements the ``JudgeClient`` protocol via ``codex exec``.

    ``params`` are passed through as codex config overrides
    (``model_reasoning_effort``). Recorded in ``judge.params`` of the
    submission record verbatim so the verdict is fully reproducible by
    anyone with the same codex version and the same subscription.
    """
    model: str = "gpt-5.5"
    params: dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 300.0
    _schema_path: Path = field(init=False, default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Write JudgeResult schema to a temp file once; codex --output-schema
        # takes a file path. Caller is responsible for life-cycle (we don't
        # delete on process exit — the dir is cleaned by the OS).
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="judge-schema-",
        ) as f:
            json.dump(JUDGE_RESULT_SCHEMA, f)
            self._schema_path = Path(f.name)

    def _build_cmd(self) -> list[str]:
        cmd = [
            "codex", "exec",
            "--model", self.model,
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "-c", 'developer_instructions=""',
            "--output-schema", str(self._schema_path),
            "--json",
        ]
        reasoning_effort = self.params.get("reasoning_effort")
        if reasoning_effort:
            cmd.extend(["-c", f"model_reasoning_effort={reasoning_effort}"])
        cmd.append("-")
        return cmd

    def complete(self, system: str, user: str) -> str:
        """Run one judge call and return the raw JSON-body string.

        For codex, the "system" role gets injected as
        ``developer_instructions`` and "user" goes through stdin. The
        ``-c developer_instructions=...`` shell-quoting is fragile so we
        embed the system prompt inline before the user message and rely
        on the schema enforcement to extract the verdict JSON. (Codex's
        own runtime preamble swamps the system prompt anyway; ordering
        matters less than for the API judge.)
        """
        # The OpenAICompatibleJudgeClient passes system + user as separate
        # roles to the chat API. Codex doesn't have a separate system
        # channel — we concatenate, which mirrors how the consensus
        # reference passes prompts to claude --print.
        prompt = system + "\n\n" + user
        cmd = self._build_cmd()
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=_scrub_codex_env(),
            timeout=self.timeout_s,
            check=False,
        )
        if proc.returncode != 0:
            raise JudgeError(
                f"codex exit {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:500]}"
            )
        # codex --json emits one event per line; the final answer is in
        # the agent_message item of the last item.completed event.
        final_text: str | None = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    final_text = item.get("text", "")
            if event.get("type") == "error":
                raise JudgeError(
                    f"codex error event: {event.get('message','')[:500]}"
                )
        if not final_text:
            raise JudgeError(
                f"codex produced no agent_message; stdout head:\n"
                f"{proc.stdout[:1024]}"
            )
        return final_text


def _parse_kv_params(pairs: list[str], flag_name: str = "--judge-param") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"{flag_name} must be key=value, got {pair!r}")
        k, v = pair.split("=", 1)
        out[k] = v
    return out


def _parse_judge_params(pairs: list[str]) -> dict[str, Any]:
    return _parse_kv_params(pairs, "--judge-param")


def _parse_agent_params(pairs: list[str]) -> dict[str, Any]:
    return _parse_kv_params(pairs, "--agent-param")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent-outputs", required=True,
                        help="dir of <audit-id>/audit.md agent reports")
    parser.add_argument("--upstream", default="upstream/frontier-evals")
    parser.add_argument("--harness-dir", default="harness")
    parser.add_argument("--out", default="submissions")
    parser.add_argument("--judge-model", default="gpt-5.5",
                        help="codex model id (default gpt-5.5; gpt-5.4 also works on most ChatGPT Pro)")
    parser.add_argument("--judge-param", action="append", metavar="KEY=VALUE",
                        help=f"codex judge params; recommended reasoning_effort={constants.DEFAULT_JUDGE_REASONING_EFFORT}")
    parser.add_argument("--judge-timeout-s", type=float, default=300.0)
    parser.add_argument("--model", required=True, help="agent model name")
    parser.add_argument("--scaffold-name", required=True)
    parser.add_argument("--scaffold-hash", required=True)
    parser.add_argument("--harness-kind", required=True,
                        choices=list(constants.HARNESS_KINDS))
    parser.add_argument(
        "--agent-param", action="append", metavar="KEY=VALUE",
        help="material agent params recorded under agent.params for leaderboard "
             "comparability filtering (e.g. reasoning_effort=high)",
    )
    parser.add_argument(
        "--agent-prompt-hash", default=None,
        help="sha256:<hex> of the agent's AUDITOR_PROMPT, recorded under "
             "agent.prompt_hash for prompt-equivalence filtering",
    )
    parser.add_argument("--affiliation", default=None)
    parser.add_argument("--tokens-total", type=int, default=0)
    parser.add_argument("--tokens-prompt", type=int, default=0)
    parser.add_argument("--tokens-completion", type=int, default=0)
    parser.add_argument("--tokens-per-task", default="")
    parser.add_argument("--wall-clock-ms", type=int, default=0)
    parser.add_argument("--runs-count", type=int, default=1)
    args = parser.parse_args(argv)

    creds = load_credentials()
    if creds is None:
        print("error: not logged in — run `openevmbench login <token>` first",
              file=sys.stderr)
        return 1

    try:
        judge_params = _parse_judge_params(args.judge_param or [])
        agent_params = _parse_agent_params(args.agent_param or [])
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    # Auto-pick scaffold sidecar metadata (SPEC §3 amendment, 2026-06-20).
    # The auditor writes ``.openevmbench-scaffold-metadata.json`` next to its
    # output dir. If present AND the operator didn't override via CLI flags,
    # use it to populate agent.params and agent.prompt_hash automatically.
    sidecar_path = Path(args.agent_outputs).parent / ".openevmbench-scaffold-metadata.json"
    agent_prompt_hash = args.agent_prompt_hash
    if sidecar_path.is_file():
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if not agent_params and sidecar.get("params"):
                agent_params = sidecar["params"]
                print(
                    f"# loaded agent.params from {sidecar_path}: {agent_params}",
                    file=sys.stderr,
                )
            if not agent_prompt_hash and sidecar.get("prompt_hash"):
                agent_prompt_hash = sidecar["prompt_hash"]
                print(
                    f"# loaded agent.prompt_hash from {sidecar_path}: {agent_prompt_hash}",
                    file=sys.stderr,
                )
        except (json.JSONDecodeError, OSError) as e:
            print(f"# warning: could not read sidecar {sidecar_path}: {e}", file=sys.stderr)
    # Default to reasoning_effort=high if operator didn't specify, matching
    # the canonical API judge's default for paper-comparable verdicts.
    if "reasoning_effort" not in judge_params:
        judge_params["reasoning_effort"] = constants.DEFAULT_JUDGE_REASONING_EFFORT

    dataset = load_detect_dataset(args.upstream)
    client = CodexJudgeClient(
        model=args.judge_model,
        params=judge_params,
        timeout_s=args.judge_timeout_s,
    )

    tokens_per_task = (
        [int(t) for t in args.tokens_per_task.split(",")] if args.tokens_per_task else []
    )
    print(
        f"# judge: codex {args.judge_model} reasoning_effort={judge_params.get('reasoning_effort')}",
        file=sys.stderr,
    )
    print(
        f"# subscription billing — OPENAI_API_KEY stripped from subprocess env",
        file=sys.stderr,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
