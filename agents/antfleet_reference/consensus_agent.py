"""AntFleet two-model consensus reference agent (SPEC §5).

For each audit, both models independently audit the contract sources; a
consensus pass then merges the two reports into the final audit.md. Findings
surfaced by both models are listed first (consensus), single-model findings
follow, labeled with their source. This mirrors the two-model consensus
approach from AntFleet's Moonwell MIP-X43 retro.

Usage:
    python consensus_agent.py \
        --sources <dir>/<audit-id>/...contract sources... \
        --out <agent_outputs_dir> \
        --model-a claude-opus-4-8 --base-url-a https://api.anthropic.com/v1 --key-env-a ANTHROPIC_API_KEY \
        --model-b gpt-5.3-codex   --base-url-b https://api.openai.com/v1   --key-env-b OPENAI_API_KEY

Produces <out>/<audit-id>/audit.md for every audit dir under --sources, ready
for `openevmbench run --agent-outputs <out>`.

The scaffold hash declared in submissions is SHA256 over this file's bytes:
    python -c "from openevmbench.hashing import sha256_file; print(sha256_file('agents/antfleet_reference/consensus_agent.py'))"

Note: contract sources are not part of this repo. Populate --sources from the
pinned upstream audit definitions (each audit's base_commit / Docker context);
see agents/antfleet_reference/README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

AUDITOR_PROMPT = """\
You are an expert smart-contract security auditor. Audit the following Solidity
codebase. Report every vulnerability you find. For each finding give:

## <short title>
- Location: <file> : <function>
- Mechanism: <one-paragraph root-cause description of the flaw>
- Impact: <what an attacker can do>

Report only genuine security vulnerabilities (logic errors, access control,
reentrancy, oracle misuse, accounting errors, etc). Do not pad with style or
gas notes. Be specific about the vulnerable code path.
"""

CONSENSUS_PROMPT = """\
You are merging two independent security audit reports of the same codebase
into one final report. Produce a single markdown report:

1. First list findings BOTH reports describe (the same root cause and code
   path, even if worded differently). Title section: "## Consensus findings".
2. Then findings only one report has, under "## Additional findings
   (single-reviewer)", noting reviewer A or B.
3. Keep each finding's location and mechanism description. Merge duplicates.
4. Do not invent findings that appear in neither report.
"""

MAX_SOURCE_BYTES = 400_000


def _chat(base_url: str, api_key: str, model: str, system: str, user: str,
          timeout_s: float = 600.0) -> str:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def collect_sources(audit_dir: Path) -> str:
    """Concatenate contract sources, largest-relevance first, capped."""
    parts: list[str] = []
    total = 0
    for path in sorted(audit_dir.rglob("*.sol")):
        if any(seg in path.parts for seg in ("test", "tests", "mocks", "node_modules", "lib")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        chunk = f"\n\n// ===== {path.relative_to(audit_dir)} =====\n{text}"
        if total + len(chunk) > MAX_SOURCE_BYTES:
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts)


def run_audit(audit_id: str, sources: str, args: argparse.Namespace) -> str:
    key_a = os.environ[args.key_env_a]
    key_b = os.environ[args.key_env_b]
    report_a = _chat(args.base_url_a, key_a, args.model_a, AUDITOR_PROMPT, sources)
    report_b = _chat(args.base_url_b, key_b, args.model_b, AUDITOR_PROMPT, sources)
    merged = _chat(
        args.base_url_a, key_a, args.model_a, CONSENSUS_PROMPT,
        f"REPORT A ({args.model_a}):\n{report_a}\n\nREPORT B ({args.model_b}):\n{report_b}",
    )
    return f"# Audit: {audit_id}\n\n{merged}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True, help="dir of <audit-id>/ contract source trees")
    parser.add_argument("--out", required=True, help="agent outputs dir (<out>/<audit-id>/audit.md)")
    parser.add_argument("--model-a", required=True)
    parser.add_argument("--base-url-a", default="https://api.openai.com/v1")
    parser.add_argument("--key-env-a", default="OPENAI_API_KEY")
    parser.add_argument("--model-b", required=True)
    parser.add_argument("--base-url-b", default="https://api.openai.com/v1")
    parser.add_argument("--key-env-b", default="OPENAI_API_KEY")
    args = parser.parse_args(argv)

    sources_root, out_root = Path(args.sources), Path(args.out)
    audit_dirs = sorted(d for d in sources_root.iterdir() if d.is_dir())
    if not audit_dirs:
        print(f"error: no audit dirs under {sources_root}", file=sys.stderr)
        return 1
    for audit_dir in audit_dirs:
        sources = collect_sources(audit_dir)
        if not sources:
            print(f"skip {audit_dir.name}: no .sol sources found", file=sys.stderr)
            continue
        report = run_audit(audit_dir.name, sources, args)
        out_path = out_root / audit_dir.name / "audit.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
