"""Shared test helpers and the rt-001 reference fixture."""

import copy
import datetime
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
# Frozen draft copy of rt-001; tests never read live content (rt validate covers that).
RT001_PATH = REPO_ROOT / "tests" / "fixtures" / "rt-001-draft.yaml"
RT001_TEXT = RT001_PATH.read_text(encoding="utf-8")
RT001_DATA: dict[str, Any] = yaml.safe_load(RT001_TEXT)

WriteScenario = Callable[..., Path]


def approved(data: dict[str, Any], scenario_id: str | None = None) -> dict[str, Any]:
    data = copy.deepcopy(data)
    data["status"] = "approved"
    data["reviewed_by"] = "Test Reviewer"
    data["reviewed_on"] = datetime.date(2026, 10, 5)
    if scenario_id:
        data["id"] = scenario_id
    return data


def hcl_blocks(text: str, header: str) -> list[str]:
    """Bodies of HCL blocks (braces included) whose opening matches the `header` regex."""
    found: list[str] = []
    for match in re.finditer(header, text):
        start = text.index("{", match.start())
        depth = 0
        for i in range(start, len(text)):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            if depth == 0:
                found.append(text[start : i + 1])
                break
    return found
