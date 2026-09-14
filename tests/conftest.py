import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib" / "py"))


@pytest.fixture
def example_config():
    return yaml.safe_load((ROOT / "examples" / "config.example.yaml").read_text(encoding="utf-8"))
