import pytest

from conftest import UPSTREAM_DIR, upstream_required
from openevmbench import constants
from openevmbench.dataset import DatasetError, load_detect_dataset


@upstream_required
def test_dataset_counts_match_pin():
    ds = load_detect_dataset(UPSTREAM_DIR)
    assert ds.audit_count == constants.DETECT_AUDIT_COUNT
    assert ds.vulnerability_count == constants.DETECT_VULN_COUNT
    assert ds.commit == constants.UPSTREAM_COMMIT


@upstream_required
def test_vulnerability_ids_normalized():
    ds = load_detect_dataset(UPSTREAM_DIR)
    ids = [v.vulnerability_id for v in ds.vulnerabilities]
    assert len(ids) == len(set(ids)), "vulnerability IDs must be unique"
    for vid in ids:
        audit_id, vuln_id = vid.split(":", 1)
        assert audit_id and vuln_id


@upstream_required
def test_findings_text_loads():
    ds = load_detect_dataset(UPSTREAM_DIR)
    sample = ds.vulnerabilities[0]
    assert sample.text_content().strip()


@upstream_required
def test_exploit_task_count():
    ds = load_detect_dataset(UPSTREAM_DIR)
    assert sum(1 for v in ds.vulnerabilities if v.exploit_task) == 23


def test_missing_cache_raises(tmp_path):
    with pytest.raises(DatasetError, match="upstream cache not found"):
        load_detect_dataset(tmp_path)
