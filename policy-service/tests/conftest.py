import sys
from pathlib import Path

import pytest

# Make `app` importable when pytest is run from policy-service/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO_ROOT = Path(__file__).resolve().parents[2]
REQUESTS_DIR = REPO_ROOT / "requests"


@pytest.fixture()
def requests_dir() -> Path:
    return REQUESTS_DIR
