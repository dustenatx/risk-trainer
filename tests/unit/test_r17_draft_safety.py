"""R17 — save_draft safety: validate first, drafts/ only, forced draft fields, atomic writes,
no symlinks, no clobbering approved scenarios, and overwrite only when asked."""

from pathlib import Path

import pytest
import yaml

from risk_trainer.content import lifecycle
from risk_trainer.content.repository import validate_tree
from risk_trainer.mcp import authoring
from tests.helpers import RT001_DATA, RT001_TEXT, WriteScenario, approved
from tests.mcp_helpers import call, data, tools

RT001_ID = "rt-001-five-findings"
RT001_FILE = f"{RT001_ID}.yaml"


def save(content_dir: Path, text: str = RT001_TEXT, **extra: object) -> dict[str, object]:
    return data(call(content_dir, "save_draft", {"yaml_text": text, **extra}))


def files_under(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if not p.is_dir())


def test_r17_save_draft_writes_valid_scenario(content_dir: Path) -> None:
    result = save(content_dir)
    assert result == {
        "saved": True,
        "path": f"drafts/{RT001_FILE}",
        "replaced": False,
        "errors": [],
    }
    assert (content_dir / "drafts" / RT001_FILE).read_text(encoding="utf-8") == RT001_TEXT
    assert not any(report.errors for report in validate_tree(content_dir))


def test_r17_invalid_scenario_not_written(content_dir: Path) -> None:
    bad = RT001_TEXT.replace("(fictional)", "Inc.", 1)
    result = save(content_dir, bad)
    assert result["saved"] is False
    assert any(e["path"] == "context.organization" for e in result["errors"])  # type: ignore[attr-defined]
    assert files_under(content_dir) == []


def test_r17_forces_draft_status_and_null_review_fields(content_dir: Path) -> None:
    sneaky = (
        RT001_TEXT.replace("status: draft", "status: approved")
        .replace("reviewed_by: null", 'reviewed_by: "Claude"')
        .replace("reviewed_on: null", "reviewed_on: 2026-10-14")
    )
    assert save(content_dir, sneaky)["saved"] is True
    written = yaml.safe_load((content_dir / "drafts" / RT001_FILE).read_text(encoding="utf-8"))
    assert written["status"] == "draft"
    assert written["reviewed_by"] is None
    assert written["reviewed_on"] is None
    assert not any(report.errors for report in validate_tree(content_dir))


def test_r17_forcing_cannot_be_dodged_with_a_quoted_key(content_dir: Path) -> None:
    # A quoted `"status"` key isn't replaced; the forced line then duplicates it, and the
    # strict loader rejects duplicate keys. Nothing is written.
    sneaky = RT001_TEXT.replace("status: draft", '"status": approved')
    assert save(content_dir, sneaky)["saved"] is False
    assert files_under(content_dir) == []


@pytest.mark.parametrize(
    "bad_id", ["../../outside", "rt-001-../x", "/var/rt-001-x", "rt-001-x/../../y", "RT-001-X"]
)
def test_r17_filename_from_validated_id_only(content_dir: Path, bad_id: str) -> None:
    text = RT001_TEXT.replace(f"id: {RT001_ID}", f'id: "{bad_id}"', 1)
    result = save(content_dir, text)
    assert result["saved"] is False
    assert any(e["path"] == "id" for e in result["errors"])  # type: ignore[attr-defined]
    assert files_under(content_dir.parent) == []


def test_r17_rejects_path_outside_drafts(content_dir: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (content_dir / "drafts").rmdir()
    (content_dir / "drafts").symlink_to(outside, target_is_directory=True)
    result = save(content_dir)
    assert result["saved"] is False
    assert "symlink" in str(result["errors"])
    assert list(outside.iterdir()) == []


def test_r17_refuses_symlink_target(content_dir: Path, tmp_path: Path) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    (content_dir / "drafts" / RT001_FILE).symlink_to(victim)
    for overwrite in (False, True):
        result = save(content_dir, overwrite=overwrite)
        assert result["saved"] is False
        assert "symlink" in str(result["errors"])
    assert victim.read_text(encoding="utf-8") == "keep me"


def test_r17_atomic_write_leaves_no_partial(
    monkeypatch: pytest.MonkeyPatch, content_dir: Path, write_scenario: WriteScenario
) -> None:
    original = write_scenario(RT001_TEXT)
    before = original.read_bytes()

    def failing_replace(self: Path, target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", failing_replace)
    changed = RT001_TEXT.replace("version: 1", "version: 2", 1)
    result = call(content_dir, "save_draft", {"yaml_text": changed, "overwrite": True})
    assert result.is_error
    assert original.read_bytes() == before
    assert files_under(content_dir) == [f"drafts/{RT001_FILE}"]  # no .tmp left behind


def test_r17_save_draft_uses_the_shared_atomic_write() -> None:
    assert authoring.atomic_write is lifecycle.atomic_write


@pytest.mark.parametrize("overwrite", [False, True])
def test_r17_refuses_id_existing_in_scenarios_and_names_it(
    content_dir: Path, write_scenario: WriteScenario, overwrite: bool
) -> None:
    approved_path = write_scenario(approved(RT001_DATA), folder="scenarios")
    before = approved_path.read_bytes()
    result = save(content_dir, overwrite=overwrite)
    assert result["saved"] is False
    assert f"scenarios/{RT001_FILE}" in str(result["errors"])
    assert approved_path.read_bytes() == before
    assert not (content_dir / "drafts" / RT001_FILE).exists()


def test_r17_refuses_id_used_by_a_differently_named_approved_file(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(approved(RT001_DATA), folder="scenarios", name="misnamed.yaml")
    result = save(content_dir, overwrite=True)
    assert result["saved"] is False
    assert "scenarios/misnamed.yaml" in str(result["errors"])


def test_r17_existing_draft_refused_without_overwrite(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    existing = write_scenario(RT001_TEXT)
    hand_edited = RT001_TEXT + "# owner's note\n"
    existing.write_text(hand_edited, encoding="utf-8")
    result = save(content_dir, RT001_TEXT.replace("version: 1", "version: 2", 1))
    assert result["saved"] is False
    assert "overwrite" in str(result["errors"])
    assert existing.read_text(encoding="utf-8") == hand_edited


def test_r17_overwrite_replaces_draft_and_reports_replaced(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    existing = write_scenario(RT001_TEXT)
    changed = RT001_TEXT.replace("version: 1", "version: 2", 1)
    result = save(content_dir, changed, overwrite=True)
    assert result["saved"] is True
    assert result["replaced"] is True
    assert result["message"] == f"Replaced the existing draft drafts/{RT001_FILE}."
    assert existing.read_text(encoding="utf-8") == changed


def test_r17_new_draft_with_overwrite_is_not_reported_as_replaced(content_dir: Path) -> None:
    result = save(content_dir, overwrite=True)
    assert result["saved"] is True
    assert result["replaced"] is False
    assert "message" not in result


def test_r17_overwrite_description_says_only_when_owner_asks(content_dir: Path) -> None:
    description = next(t.description for t in tools(content_dir) if t.name == "save_draft")
    assert description is not None
    assert "overwrite to true only when the owner has asked" in description
    assert "content/scenarios/" in description


def test_r17_every_tool_called_in_process(content_dir: Path) -> None:
    calls = {
        "get_schema": {},
        "list_scenarios": {},
        "validate_scenario": {"yaml_text": RT001_TEXT},
        "score_answers": {
            "scenario_id": RT001_ID,
            "answers": [
                {"finding_id": "F1", "treatment": "mitigate_remediate"},
                {"finding_id": "F2", "treatment": "mitigate_compensate"},
                {"finding_id": "F3", "treatment": "transfer"},
                {"finding_id": "F4", "treatment": "mitigate_remediate"},
                {"finding_id": "F5", "treatment": "accept", "approver": "business_risk_owner"},
            ],
        },
    }
    assert data(call(content_dir, "save_draft", {"yaml_text": RT001_TEXT}))["saved"] is True
    for name, arguments in calls.items():
        data(call(content_dir, name, arguments))
    assert set(calls) | {"save_draft"} == set(authoring.TOOL_NAMES)
