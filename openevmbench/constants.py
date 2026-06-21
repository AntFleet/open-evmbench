"""Pinned launch facts for the Detect v1 board.

Every value here was verified against the upstream source on 2026-06-10;
see docs/UPSTREAM_PIN.md for the verification record. Changing any of these
creates a new versioned board (SPEC §8 A6) — never edit in place for a live
board.
"""

UPSTREAM_REPO = "openai/frontier-evals"
UPSTREAM_COMMIT = "51052cede8cc608f95bb00346635e03759013e5a"
UPSTREAM_COMMIT_SHORT = "51052ce"
UPSTREAM_SUBDIR = "project/evmbench"

HARNESS_VERSION = "detect-v1.0.0+frontier-evals.51052ce"

# SHA256 over the UTF-8 bytes of harness/judge_prompt_v1.md (SPEC §4).
JUDGE_PROMPT_SHA256 = "fcfbbbac8cb6a526a7f4b00419abca39029ca979b0ddc15aa1a8184c66311956"
JUDGE_PROMPT_FILENAME = "judge_prompt_v1.md"

DETECT_AUDIT_COUNT = 40
DETECT_VULN_COUNT = 117
DETECT_SPLIT = "detect-tasks"

# The OpenAI-paper-comparable judge group (SPEC §2 Judge).
DEFAULT_JUDGE_MODEL = "gpt-5"
DEFAULT_JUDGE_REASONING_EFFORT = "high"

PHASE_DETECT = 1
MODE_DETECT = "detect"

# Phase 2 Patch board (same upstream pin as Detect; separate harness version).
PHASE_PATCH = 2
MODE_PATCH = "patch"
PATCH_HARNESS_VERSION = "patch-v1.0.0+frontier-evals.51052ce"
PATCH_AUDIT_COUNT = 22
PATCH_VULN_COUNT = 44
PATCH_SPLIT = "patch-tasks"
PATCH_TASKS_FILENAME = "patch_tasks_v1.json"

# Pinned launch acceptance-key fingerprint (SHA256 over antfleet.public_key.pem
# bytes). Rotation procedure: see docs/KEYS.md. Tests assert the committed
# public key matches this value, so accidental DEV-key carryover or unintended
# rotation is caught in CI.
LAUNCH_PUBLIC_KEY_FINGERPRINT = (
    "sha256:d0ad47a590f27d40d89f7bd7008bc3330a46d47101580baead7b959ebd51221b"
)

HARNESS_KINDS = ("single-shot", "retry-loop", "agentic-scaffold")
STATES = ("submitted", "checking", "accepted", "rejected", "promoted", "yanked")
