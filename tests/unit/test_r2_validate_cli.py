"""R2 — `rt validate`."""

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from risk_trainer.cli.main import app
from tests.helpers import RT001_TEXT, WriteScenario, approved

runner = CliRunner()


def run_validate(content_dir: Path) -> Any:
    return runner.invoke(app, ["validate", "--content-dir", str(content_dir)])


def test_r2_exit_zero_on_valid_tree(content_dir: Path, write_scenario: WriteScenario) -> None:
    write_scenario(RT001_TEXT)
    result = run_validate(content_dir)
    assert result.exit_code == 0, result.output
    assert "1 file(s) checked, 0 with errors." in result.output


def test_r2_nonzero_on_invalid(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    rt001["context"]["organization"] = "Real Corp"
    write_scenario(rt001)
    assert run_validate(content_dir).exit_code == 1


def test_r2_prints_file_path_and_message(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    rt001["answer_key"]["findings"]["F5"]["approvers"]["correct"] = ["security_team"]
    path = write_scenario(rt001)
    result = run_validate(content_dir)
    assert (
        f"{path}: answer_key.findings.F5.approvers.correct: "
        "security_team can't approve" in result.output
    )


def test_r2_reports_all_errors_not_first(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    rt001["context"]["organization"] = "Real Corp"
    rt001["answer_key"]["job_tip"] = None
    rt001["context"]["capacity"]["remediation_slots"] = 1
    write_scenario(rt001)
    output = run_validate(content_dir).output
    assert "context.organization" in output
    assert "answer_key.job_tip" in output
    assert "remediation_slots is 1" in output


def test_r2_covers_drafts_and_scenarios(
    content_dir: Path, rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    write_scenario(rt001)
    bad = approved(rt001, scenario_id="rt-002-second")
    bad["title"] = ""
    path = write_scenario(bad, folder="scenarios")
    result = run_validate(content_dir)
    assert result.exit_code == 1
    assert "2 file(s) checked, 1 with errors." in result.output
    assert f"{path}: title:" in result.output


def test_r2_malformed_yaml_reported_not_traceback(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    path = write_scenario("id: rt-001-x\n  bad: [indent\n")
    result = run_validate(content_dir)
    assert result.exit_code == 1
    assert f"{path}: (yaml): line" in result.output
    assert "Traceback" not in result.output


def test_r2_missing_content_dir(tmp_path: Path) -> None:
    result = run_validate(tmp_path / "nope")
    assert result.exit_code == 1
    assert "not a directory" in result.output
