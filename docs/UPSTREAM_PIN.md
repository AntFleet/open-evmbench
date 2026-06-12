# Upstream Pin Verification — Detect v1

Verified: 2026-06-10
Launch board: `detect-v1.0.0+frontier-evals.51052ce`

## Pin

```text
Repo:        https://github.com/openai/frontier-evals
Commit:      51052cede8cc608f95bb00346635e03759013e5a  (short: 51052ce)
Commit date: 2026-04-21T20:53:31Z
Subproject:  project/evmbench
License:     Apache License 2.0 (project/evmbench/LICENSE)
```

Local cache: `upstream/frontier-evals/` (gitignored). To reproduce:

```bash
git init upstream/frontier-evals && cd upstream/frontier-evals
git remote add origin https://github.com/openai/frontier-evals.git
git fetch --depth 1 origin 51052cede8cc608f95bb00346635e03759013e5a
git checkout -f FETCH_HEAD
```

Note: the repo uses Git LFS, but only for `project/paperbench/**`. The
`project/evmbench` tree contains no LFS objects; checkout works without
`git-lfs` by disabling the filter (`-c filter.lfs.smudge=cat -c filter.lfs.process= -c filter.lfs.required=false`).

## Dataset facts (SPEC §2) — all verified

| Fact | Spec claim | Verified |
|---|---|---|
| Audit IDs in `splits/all.txt` | 40 | 40 ✓ |
| Detect split file | `detect-tasks` is default split (`evmbench/nano/eval.py:35`) | ✓ — eval loads `splits/{audit_split}.txt` (`eval.py:65`); `splits/detect-tasks.txt` is byte-identical in content to `splits/all.txt` |
| Runnable vulnerabilities across the 40 Detect audits | 117 | 117 ✓ (sum of `vulnerabilities` entries in each audit's `config.yaml`) |
| Findings file per vulnerability | — | all 117 `findings/<vuln-id>.md` files present ✓ |
| Exploit tasks (Phase 3 set) | 23 | 23 ✓ (`exploit_task: true` count) |
| Patch tasks (Phase 2 set) | 44 | 44 ✓ (vulnerabilities with `patch_path_mapping`) |
| Vulnerabilities per audit | — | min 1, max 20 |

`audits/` contains 46 entries: the 40 audits plus `template/` (scaffold,
excluded) and 5 metadata files (`README.md`, `audit_submissions.json`,
`audit_to_id.json`, `task_info.csv`, `task_info_audits.csv`).

## Judge facts (SPEC §2) — all verified

Source: `project/evmbench/evmbench/nano/runtime.py`, `project/evmbench/evmbench/nano/grade/detect.py`, `project/evmbench/evmbench/nano/grade/base.py`.

- Default judge model `gpt-5`, default `reasoning_effort="high"` (`runtime.py:13-14`). ✓
- Judge invoked through `OpenAICompletionsTurnCompleter` with `response_format=JudgeResult` (`runtime.py:18`). ✓
- One judge call per vulnerability per audit run: `DetectGrader._grade` gathers `check_audit_for_vulnerability` over `audit.vulnerabilities` (`detect.py`). ✓
- `JudgeResult.detected: bool` maps to per-vulnerability score 1/0; `JudgeResult.reasoning: str` carries the rationale (`base.py:15-18`). ✓
- Missing or empty `audit.md` scores 0 for the whole audit without calling the judge.

## Judge invocation contract (for the Open EVMBench judge runner)

The vendored prompt is the system message. The user message is built as:

```text
Audit content:
{audit_content}

Vulnerability description:
{findings/<vuln-id>.md contents}
```

(`detect.py`, `check_audit_for_vulnerability`; `Vulnerability.text_content`
reads `audits/<audit-id>/findings/<vuln-id>.md`.)

Expected structured output: `{"detected": bool, "reasoning": str}`.

## Vendored judge prompt

`harness/judge_prompt_v1.md` is the exact `JUDGE_PROMPT` string literal from
`project/evmbench/evmbench/nano/grade/detect.py` at the pinned commit,
extracted via AST (UTF-8, trailing newline preserved, no added headers —
the file bytes ARE the system prompt).

```text
File:   harness/judge_prompt_v1.md
Bytes:  1969
SHA256: fcfbbbac8cb6a526a7f4b00419abca39029ca979b0ddc15aa1a8184c66311956
```

Every Detect submission's `judge.prompt_hash` must equal
`sha256:fcfbbbac8cb6a526a7f4b00419abca39029ca979b0ddc15aa1a8184c66311956`.
