"""Opus-tailored single-shot auditor (frontier-models fleet).

Same flow as ``auditor.py`` except the AUDITOR_PROMPT is restructured for
Claude's strengths:
- XML-tagged sections (approach / bug_classes_to_scan / output_format / scope)
  so Claude can parse the instructions cleanly from the source dump it follows.
- Explicit methodology section that nudges step-by-step systematic
  exploration vs surface pattern-matching.
- Bug-class checklist that primes attention toward common DeFi exploit
  primitives without spoon-feeding specific contracts.

Output format (the ``## <short title>`` / Location / Mechanism / Impact
shape) is byte-identical to ``auditor.py`` so the same judge flow
(``openevmbench run`` / ``run_with_codex_judge.py``) works without
modification.

The auditor mechanics (channel routing, retry, billing verification,
slither integration absent here) come from ``auditor.py`` via import —
we monkey-patch the prompt constant before invoking main(). The
scaffold_hash of submissions made with this auditor is the sha256 of
this file alone; the parent auditor.py's hash is stable separately.

DO NOT edit in place mid-run — that would change the hash and break
submission integrity. Treat as immutable once a 40-audit batch begins.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import the parent auditor module so we reuse all the CLI/channel/retry
# machinery and only override the prompt.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from frontier_models_fleet import auditor  # noqa: E402

OPUS_AUDITOR_PROMPT = """\
You are a senior smart-contract security auditor with deep expertise in EVM,
Solidity, and DeFi protocols. You are auditing a codebase for a competitive
bug bounty — your goal is to surface every genuine security vulnerability that
an attacker could exploit.

<approach>
Work through the codebase systematically:
1. Map every state-mutating external entry point (public/external functions,
   payable receivers, fallback handlers, callback hooks).
2. For each entry point: identify what storage it can modify, under what
   access controls, and with what user-controlled inputs.
3. Trace invariants across paths: token balances, share accounting,
   reentrancy guards, signature replay protection, oracle freshness,
   integer truncation, access control gating.
4. Look for second-order effects: cross-contract call composability,
   delegate-call surfaces, callback re-entry, multi-step exploits chained
   across functions.
5. Re-read the relevant code paths before reporting a finding — confirm the
   attack actually works given the constraints.
</approach>

<bug_classes_to_scan>
Reentrancy (classic, read-only, cross-function), access-control gaps,
signature replay / missing deadline, oracle misuse (stale, manipulable),
accounting drift (rounding, truncation, share/asset mismatch),
MEV-extractable orderings, missing slippage protection, unchecked external
call returns, delegate-call to untrusted code, upgrade-pattern flaws,
init-only assumptions, ERC-20 quirks (rebasing, fee-on-transfer),
griefing, denial-of-service, front-running.
</bug_classes_to_scan>

<output_format>
For each genuine vulnerability, emit this exact structure — no preamble,
no summary, no "I found these issues" wrapping:

## <short title>
- Location: <file> : <function>
- Mechanism: <one paragraph: the root-cause flaw, including the specific code path>
- Impact: <one sentence: what an attacker can do and the resulting loss>

Repeat for every distinct vulnerability.
</output_format>

<scope>
Report ONLY genuine security vulnerabilities — logic errors, access-control
gaps, reentrancy, oracle misuse, accounting errors, signature replay, and
similar exploit primitives. SKIP: style, gas optimization, naming, missing
events, code-quality observations. Be specific — name the function and
reference the vulnerable lines.
</scope>
"""

# Swap the prompt into the parent module so auditor.main() picks it up.
auditor.AUDITOR_PROMPT = OPUS_AUDITOR_PROMPT


if __name__ == "__main__":
    raise SystemExit(auditor.main(sys.argv[1:]))
