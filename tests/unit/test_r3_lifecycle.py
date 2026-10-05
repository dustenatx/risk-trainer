"""R3 — approve and retire. Every test works on a tmp_path copy, never the repo's content/."""

import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from risk_trainer.cli.main import app
from risk_trainer.content.lifecycle import approve, retire, set_top_level_keys
from risk_trainer.content.repository import load_publishable, validate_tree
from risk_trainer.domain.errors import LifecycleError, ScenarioInvalid
from tests.helpers import RT001_TEXT, WriteScenario, approved

ID = "rt-001-five-findings"
TODAY = datetime.date(2026, 10, 5)
runner = CliRunner()

COMMENTED = "# Owner note: keep this comment.\n" + RT001_TEXT


@pytest.fixture
def draft(write_scenario: WriteScenario) -> Path:
    return write_scenario(COMMENTED)


def test_r3_approve_sets_fields_and_moves(content_dir: Path, draft: Path) -> None:
    target = approve(content_dir, ID, "Dusten Harrison", TODAY)
    assert target == content_dir / "scenarios" / f"{ID}.yaml"
    assert not draft.exists()
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["status"] == "approved"
    assert data["reviewed_by"] == "Dusten Harrison"
    assert data["reviewed_on"] == TODAY
    assert all(not r.errors for r in validate_tree(content_dir))


def test_r3_approve_uses_iso_today(content_dir: Path, draft: Path) -> None:
    target = approve(content_dir, ID, "Owner", TODAY)
    assert "\nreviewed_on: 2026-10-05\n" in target.read_text(encoding="utf-8")


def test_r3_cli_approve_uses_todays_date(content_dir: Path, draft: Path) -> None:
    result = runner.invoke(
        app, ["approve", ID, "--reviewer", "Owner", "--content-dir", str(content_dir)]
    )
    assert result.exit_code == 0, result.output
    text = (content_dir / "scenarios" / f"{ID}.yaml").read_text(encoding="utf-8")
    assert f"reviewed_on: {datetime.date.today().isoformat()}" in text


def test_r3_approve_preserves_comments_and_formatting(content_dir: Path, draft: Path) -> None:
    before = draft.read_text(encoding="utf-8")
    after = approve(content_dir, ID, "Owner", TODAY).read_text(encoding="utf-8")
    changed = {
        line
        for line in set(before.splitlines()) ^ set(after.splitlines())
        if not line.startswith(("status:", "reviewed_by:", "reviewed_on:"))
    }
    assert changed == set()
    assert after.startswith("# Owner note: keep this comment.\n")
    assert "    description: >-\n" in after


def test_r3_reviewer_is_quoted_safely(content_dir: Path, draft: Path) -> None:
    target = approve(content_dir, ID, 'O\'Brien: "CISSP" # not a comment', TODAY)
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert data["reviewed_by"] == 'O\'Brien: "CISSP" # not a comment'


@pytest.mark.parametrize("reviewer", ["", "   ", "line\nbreak", "x" * 101])
def test_r3_approve_rejects_bad_reviewer(content_dir: Path, draft: Path, reviewer: str) -> None:
    before = draft.read_bytes()
    with pytest.raises(LifecycleError):
        approve(content_dir, ID, reviewer, TODAY)
    assert draft.read_bytes() == before


def test_r3_approve_invalid_leaves_file_unchanged(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    rt001["context"]["organization"] = "Real Corp"
    draft = write_scenario(rt001)
    before = draft.read_bytes()
    result = runner.invoke(
        app, ["approve", ID, "--reviewer", "Owner", "--content-dir", str(content_dir)]
    )
    assert result.exit_code == 1
    assert "context.organization" in result.output
    assert draft.read_bytes() == before
    assert list((content_dir / "scenarios").iterdir()) == []


def test_r3_approve_refuses_existing_target(
    content_dir: Path, draft: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    existing = write_scenario(approved(rt001), folder="scenarios")
    before = existing.read_bytes()
    with pytest.raises(LifecycleError, match="already exists"):
        approve(content_dir, ID, "Owner", TODAY)
    assert existing.read_bytes() == before
    assert draft.exists()


@pytest.mark.parametrize("scenario_id", ["rt-404-missing", "../etc/passwd", "rt-001-X"])
def test_r3_approve_unknown_or_bad_id(content_dir: Path, scenario_id: str) -> None:
    result = runner.invoke(
        app, ["approve", scenario_id, "--reviewer", "Owner", "--content-dir", str(content_dir)]
    )
    assert result.exit_code == 1
    assert result.output.startswith("Refused:")


def test_r3_approve_refuses_symlink(content_dir: Path, tmp_path: Path) -> None:
    real = tmp_path / "real.yaml"
    real.write_text(RT001_TEXT, encoding="utf-8")
    (content_dir / "drafts" / f"{ID}.yaml").symlink_to(real)
    with pytest.raises(LifecycleError, match="symlink"):
        approve(content_dir, ID, "Owner", TODAY)


def test_r3_retire_sets_status_retired(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    path = write_scenario(approved(rt001), folder="scenarios")
    result = runner.invoke(app, ["retire", ID, "--content-dir", str(content_dir)])
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["status"] == "retired"
    assert data["reviewed_by"] == "Test Reviewer"


def test_r3_retire_refuses_non_approved(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    path = write_scenario(approved(rt001), folder="scenarios")
    retire(content_dir, ID)
    before = path.read_bytes()
    with pytest.raises(LifecycleError, match="only approved"):
        retire(content_dir, ID)
    assert path.read_bytes() == before


def test_r3_retire_refuses_draft(content_dir: Path, draft: Path) -> None:
    with pytest.raises(LifecycleError, match="no scenario"):
        retire(content_dir, ID)


def test_r3_retire_refuses_invalid(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    bad = approved(rt001)
    bad["title"] = ""
    write_scenario(bad, folder="scenarios")
    with pytest.raises(ScenarioInvalid):
        retire(content_dir, ID)


def test_r3_publishable_excludes_retired_and_drafts(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    write_scenario(dict(rt001, id="rt-003-draft"))
    write_scenario(approved(rt001, "rt-001-five-findings"), folder="scenarios")
    write_scenario(approved(rt001, "rt-002-retired"), folder="scenarios")
    retire(content_dir, "rt-002-retired")
    assert [s.id for s in load_publishable(content_dir)] == [ID]


def test_r3_publishable_fails_on_invalid_approved(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    bad = approved(rt001)
    bad["title"] = ""
    write_scenario(bad, folder="scenarios")
    with pytest.raises(ScenarioInvalid):
        load_publishable(content_dir)


def test_r3_set_top_level_keys_replaces_block_values_and_appends() -> None:
    text = "a: 1\nreviewed_by: >-\n  old\n  name\nb: 2\n"
    out = set_top_level_keys(text, {"reviewed_by": '"New"', "reviewed_on": "2026-10-05"})
    assert out == 'a: 1\nreviewed_by: "New"\nb: 2\nreviewed_on: 2026-10-05\n'


def test_r3_set_top_level_keys_ignores_nested_and_comments() -> None:
    text = "# status: draft\nctx:\n  status: nested\nstatus: draft"
    out = set_top_level_keys(text, {"status": "approved"})
    assert out == "# status: draft\nctx:\n  status: nested\nstatus: approved\n"
