# Security

## Submission PR Threat Model

Submission PRs are treated as untrusted data, not code. A valid Phase 1
submission may modify only one directory:

```text
submissions/phase1/<github_handle>/<submission_id>/
```

PRs that touch package code, workflows, scripts, harness files, or any other
repository path are rejected before trusted checks or signing run.

## Workflow Isolation Contract

Pull-request workflows first run a no-secret `prepare` job that allowlists the
changed paths and identifies the single submission directory. Trusted jobs then
check out the base branch, install/run the base branch code, and overlay only
that allowlisted submission directory from the PR head.

The AntFleet private signing key is available only in the protected acceptance
signing job. That job does not install or import code from the PR tree.

## Signature Scope

`antfleet_acceptance.signature` covers the acceptance-time record with the
entire `antfleet_acceptance` object omitted and JCS-canonicalized.

For promoted or yanked records, verification normalizes the payload back to the
accepted form before checking the signature: `state` becomes `accepted`,
`state_reason` becomes `null`, and `promoted_at` / `promoted_commit_sha` are
removed.

The acceptance signature does not cover later Git-log lifecycle metadata such
as `promoted_at`, `promoted_commit_sha`, or a yanked record's post-acceptance
reason. Those fields are public repository history metadata.
