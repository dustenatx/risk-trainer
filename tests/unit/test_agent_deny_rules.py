"""AGENTS.md human gates enforced by Claude Code permission rules (.claude/settings.json)."""

import json
from typing import Any

from tests.helpers import REPO_ROOT

SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def deny_rules() -> list[str]:
    settings: dict[str, Any] = json.loads(SETTINGS.read_text(encoding="utf-8"))
    rules: list[str] = settings["permissions"]["deny"]
    return rules


def test_bootstrap_is_not_editable_by_agents() -> None:
    # Edit rules also cover the Write tool; a Write(path) rule would never be consulted.
    assert "Edit(/infra/bootstrap/**)" in deny_rules()
    assert not any(rule.startswith("Write(") for rule in deny_rules())


def test_recursive_force_delete_is_denied() -> None:
    assert "Bash(rm -rf *)" in deny_rules()


def test_project_settings_grant_no_allow_rules() -> None:
    settings: dict[str, Any] = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert "allow" not in settings["permissions"]
