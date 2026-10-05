import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.helpers import RT001_DATA, WriteScenario


@pytest.fixture
def rt001() -> dict[str, Any]:
    """A fresh, mutable copy of the rt-001 reference scenario."""
    return copy.deepcopy(RT001_DATA)


@pytest.fixture
def content_dir(tmp_path: Path) -> Path:
    root = tmp_path / "content"
    (root / "drafts").mkdir(parents=True)
    (root / "scenarios").mkdir()
    return root


@pytest.fixture
def write_scenario(content_dir: Path) -> WriteScenario:
    """Write a scenario dict (or raw text) into content/<folder>/<name>."""

    def write(data: dict[str, Any] | str, folder: str = "drafts", name: str | None = None) -> Path:
        if isinstance(data, str):
            text = data
            name = name or "rt-001-five-findings.yaml"
        else:
            text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            name = name or f"{data['id']}.yaml"
        path = content_dir / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return write
