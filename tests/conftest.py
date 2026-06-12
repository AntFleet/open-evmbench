import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDS_DIR = FIXTURES_DIR / "records"
KEYS_DIR = FIXTURES_DIR / "keys"
UPSTREAM_DIR = REPO_ROOT / "upstream" / "frontier-evals"
HARNESS_DIR = REPO_ROOT / "harness"

upstream_required = pytest.mark.skipif(
    not (UPSTREAM_DIR / "project" / "evmbench").is_dir(),
    reason="upstream cache not fetched (see docs/UPSTREAM_PIN.md)",
)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def harness_dir() -> Path:
    return HARNESS_DIR


def load_fixture(name: str) -> dict:
    return json.loads((RECORDS_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def test_public_pem() -> bytes:
    return (KEYS_DIR / "TEST_ONLY_public.pem").read_bytes()


@pytest.fixture
def test_private_pem() -> bytes:
    return (KEYS_DIR / "TEST_ONLY_private.pem").read_bytes()
