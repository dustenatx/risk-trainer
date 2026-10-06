"""Reading and validating scenario files under content/ (PRD R1, R2)."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from risk_trainer.content.yaml_loader import load_yaml
from risk_trainer.domain.errors import ContentError, ScenarioInvalid
from risk_trainer.domain.models import SCENARIO_ID_MAX_LENGTH, SCENARIO_ID_PATTERN, Scenario, Status
from risk_trainer.domain.rules import parse_scenario

DRAFTS_DIR = "drafts"
SCENARIOS_DIR = "scenarios"
SCENARIO_SUFFIX = ".yaml"
MAX_FILE_BYTES = 64 * 1024

_SCENARIO_ID_RE = re.compile(SCENARIO_ID_PATTERN)


@dataclass
class FileReport:
    path: Path
    scenario: Scenario | None = None
    errors: list[ContentError] = field(default_factory=list)


def is_valid_scenario_id(scenario_id: str) -> bool:
    return len(scenario_id) <= SCENARIO_ID_MAX_LENGTH and bool(_SCENARIO_ID_RE.match(scenario_id))


def scenario_files(content_dir: Path) -> list[Path]:
    """Every YAML file under content_dir, sorted for stable output."""
    return sorted(path for path in content_dir.rglob("*") if path.suffix in (".yaml", ".yml"))


def parse_text(text: str) -> Scenario:
    """Parse and validate scenario YAML text. Raises ScenarioInvalid."""
    try:
        data = load_yaml(text)
    except yaml.YAMLError as exc:
        raise ScenarioInvalid([ContentError("(yaml)", _yaml_message(exc))]) from None
    return parse_scenario(data)


def validate_file(path: Path, content_dir: Path) -> FileReport:
    """Validate one file: content rules (R1) plus its name and folder."""
    report = FileReport(path)
    if path.is_symlink():
        report.errors.append(ContentError("(file)", "symlinks are not allowed under content/"))
        return report
    if path.stat().st_size > MAX_FILE_BYTES:
        report.errors.append(ContentError("(file)", f"larger than {MAX_FILE_BYTES} bytes"))
        return report
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        report.errors.append(ContentError("(file)", "not valid UTF-8"))
        return report
    try:
        report.scenario = parse_text(text)
    except ScenarioInvalid as exc:
        report.errors.extend(exc.errors)
        return report
    report.errors.extend(location_errors(report.scenario, path, content_dir))
    return report


def location_errors(scenario: Scenario, path: Path, content_dir: Path) -> list[ContentError]:
    """File name must be `<id>.yaml`; the folder must match the status."""
    errors: list[ContentError] = []
    expected_name = f"{scenario.id}{SCENARIO_SUFFIX}"
    if path.name != expected_name:
        errors.append(ContentError("id", f"file name must be {expected_name}"))

    folder = path.resolve().parent
    if folder == (content_dir / DRAFTS_DIR).resolve():
        if scenario.status is not Status.DRAFT:
            errors.append(ContentError("status", "files in content/drafts/ must be draft"))
        for name, value in (
            ("reviewed_by", scenario.reviewed_by),
            ("reviewed_on", scenario.reviewed_on),
        ):
            if value is not None:
                errors.append(
                    ContentError(name, "must be null in a draft; only rt approve sets it")
                )
    elif folder == (content_dir / SCENARIOS_DIR).resolve():
        if scenario.status is Status.DRAFT:
            errors.append(
                ContentError("status", "files in content/scenarios/ must be approved or retired")
            )
        elif scenario.status is Status.RETIRED:
            for name, value in (
                ("reviewed_by", scenario.reviewed_by),
                ("reviewed_on", scenario.reviewed_on),
            ):
                if value is None:
                    errors.append(ContentError(name, "required when status is retired"))
    else:
        errors.append(
            ContentError("(file)", "scenario files belong in content/drafts/ or content/scenarios/")
        )
    return errors


def validate_tree(content_dir: Path) -> list[FileReport]:
    """Validate every scenario file under content_dir, including repo-wide unique IDs."""
    reports = [validate_file(path, content_dir) for path in scenario_files(content_dir)]
    by_id: dict[str, list[FileReport]] = defaultdict(list)
    for report in reports:
        if report.scenario is not None:
            by_id[report.scenario.id].append(report)
    for scenario_id, same in by_id.items():
        if len(same) > 1:
            others = ", ".join(str(r.path) for r in same)
            for report in same:
                report.errors.append(
                    ContentError(
                        "id", f"scenario ID {scenario_id} is used by more than one file: {others}"
                    )
                )
    return reports


def publishable_reports(content_dir: Path) -> list[FileReport]:
    """Reports for approved scenarios only (no drafts or retired), each with its file path.

    Raises ScenarioInvalid if any file in content/scenarios/ has an error, so neither the app
    nor the build (R14) can start with a broken approved scenario.
    """
    folder = content_dir / SCENARIOS_DIR
    reports = [r for r in validate_tree(content_dir) if r.path.parent == folder]
    errors = [
        ContentError(f"{report.path}: {error.path}", error.message)
        for report in reports
        for error in report.errors
    ]
    if errors:
        raise ScenarioInvalid(errors)
    return [r for r in reports if r.scenario is not None and r.scenario.status is Status.APPROVED]


def load_publishable(content_dir: Path) -> list[Scenario]:
    """Approved scenarios only (no drafts or retired). Raises ScenarioInvalid on any error."""
    return [r.scenario for r in publishable_reports(content_dir) if r.scenario is not None]


def load_previewable(content_dir: Path) -> tuple[list[Scenario], list[FileReport]]:
    """Approved scenarios plus valid drafts, for `rt preview` only. Also returns failed reports."""
    reports = validate_tree(content_dir)
    failed = [r for r in reports if r.errors]
    scenarios = [
        r.scenario
        for r in reports
        if r.scenario is not None
        and not r.errors
        and r.scenario.status in (Status.APPROVED, Status.DRAFT)
    ]
    return scenarios, failed


def _yaml_message(exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or "could not parse YAML"
    if mark is not None:
        return f"line {mark.line + 1}, column {mark.column + 1}: {problem}"
    return str(problem)
