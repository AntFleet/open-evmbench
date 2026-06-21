from pathlib import Path

import yaml

WORKFLOWS = Path(".github/workflows")


def _workflow_files():
    return sorted(WORKFLOWS.glob("*.yml"))


def _load(path: Path):
    return yaml.safe_load(path.read_text())


def _job_text(job: dict) -> str:
    return "\n".join(str(step) for step in job.get("steps", []))


def test_all_workflows_have_explicit_permissions():
    for path in _workflow_files():
        data = _load(path)
        assert "permissions" in data, path


def test_signing_secret_job_does_not_editable_install():
    for path in _workflow_files():
        data = _load(path)
        for job_name, job in data.get("jobs", {}).items():
            text = _job_text(job)
            if "ANTFLEET_PRIVATE_KEY_PEM" in text:
                assert "pip install -e ." not in text, (path, job_name)


def test_pull_request_workflows_have_submission_diff_allowlist():
    for path in _workflow_files():
        text = path.read_text()
        if "pull_request:" not in text or "submissions/**" not in text:
            continue
        assert "permissions: {}" in text, path
        assert "prepare:" in text, path
        assert "pr-touches-non-submission-files" in text, path
        assert "submissions/phase[123]/" in text, path
        assert "git diff --name-only" in text or "gh pr view" in text, path
