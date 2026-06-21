import json
from pathlib import Path

import pytest

from conftest import UPSTREAM_DIR, upstream_required
from openevmbench import constants
from openevmbench.dataset import DatasetError, load_patch_audit, load_patch_dataset


@upstream_required
def test_patch_dataset_counts_match_pin():
    ds = load_patch_dataset(UPSTREAM_DIR)
    assert ds.audit_count == constants.PATCH_AUDIT_COUNT
    assert ds.vulnerability_count == constants.PATCH_VULN_COUNT
    assert ds.commit == constants.UPSTREAM_COMMIT


@upstream_required
def test_patch_vulnerability_ids_unique():
    ds = load_patch_dataset(UPSTREAM_DIR)
    ids = ds.vulnerability_ids
    assert len(ids) == len(set(ids))


@upstream_required
def test_patch_tasks_json_matches_upstream():
    path = Path("harness") / constants.PATCH_TASKS_FILENAME
    pinned = json.loads(path.read_text(encoding="utf-8"))
    ds = load_patch_dataset(UPSTREAM_DIR)
    assert pinned["vulnerability_count"] == constants.PATCH_VULN_COUNT
    assert tuple(pinned["vulnerability_ids"]) == ds.vulnerability_ids


@upstream_required
def test_load_patch_audit_single():
    audit = load_patch_audit(UPSTREAM_DIR, "2023-07-pooltogether")
    assert audit.audit_id == "2023-07-pooltogether"
    assert len(audit.vulnerabilities) == 2


@upstream_required
def test_missing_patch_audit_raises():
    with pytest.raises(DatasetError, match="not in the"):
        load_patch_audit(UPSTREAM_DIR, "2024-01-canto")
