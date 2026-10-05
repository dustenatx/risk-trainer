"""Human-only lifecycle commands (PRD R3): approve and retire.

Only the top-level `status`, `reviewed_by` and `reviewed_on` lines change; comments and
formatting elsewhere stay byte-for-byte the same. The result is re-validated before it is
written, and every write goes to a temporary file in the same folder, then a rename.
"""

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from risk_trainer.content.repository import (
    DRAFTS_DIR,
    SCENARIO_SUFFIX,
    SCENARIOS_DIR,
    is_valid_scenario_id,
    location_errors,
    parse_text,
    validate_file,
)
from risk_trainer.domain.errors import LifecycleError, ScenarioInvalid
from risk_trainer.domain.models import Scenario, Status

REVIEWER_MAX_LENGTH = 100


def approve(content_dir: Path, scenario_id: str, reviewer: str, today: date) -> Path:
    """Validate a draft, approve it and move it to content/scenarios/. Returns the new path."""
    reviewer = _check_reviewer(reviewer)
    source = _scenario_path(content_dir, DRAFTS_DIR, scenario_id)
    target = _scenario_path(content_dir, SCENARIOS_DIR, scenario_id, must_exist=False)
    if target.exists() or target.is_symlink():
        raise LifecycleError(f"{target} already exists; refusing to overwrite it")

    _require_valid(source, content_dir)
    text = source.read_bytes().decode("utf-8")
    new_text = set_top_level_keys(
        text,
        {
            "status": Status.APPROVED.value,
            "reviewed_by": json.dumps(reviewer, ensure_ascii=False),
            "reviewed_on": today.isoformat(),
        },
    )
    _require_valid_text(new_text, target, content_dir)

    target.parent.mkdir(exist_ok=True)
    _atomic_write(target, new_text)
    source.unlink()
    return target


def retire(content_dir: Path, scenario_id: str) -> Path:
    """Retire an approved scenario. It stays in content/scenarios/ but is not published."""
    path = _scenario_path(content_dir, SCENARIOS_DIR, scenario_id)
    scenario = _require_valid(path, content_dir)
    if scenario.status is not Status.APPROVED:
        raise LifecycleError(
            f"{scenario_id} is {scenario.status}; only approved scenarios can be retired"
        )
    new_text = set_top_level_keys(
        path.read_bytes().decode("utf-8"), {"status": Status.RETIRED.value}
    )
    _require_valid_text(new_text, path, content_dir)
    _atomic_write(path, new_text)
    return path


def set_top_level_keys(text: str, values: dict[str, str]) -> str:
    """Replace each top-level `key: ...` line (and any indented continuation) with `key: value`.

    Keys that aren't present are appended at the end.
    """
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    out: list[str] = []
    done: set[str] = set()
    skipping = False
    for line in lines:
        if skipping and (line[:1] in (" ", "\t") or not line.strip()):
            continue
        skipping = False
        key = line.split(":", 1)[0] if ":" in line and line[:1] not in (" ", "\t", "#") else None
        if key in values:
            if key in done:
                raise LifecycleError(f"top-level key {key!r} appears more than once")
            out.append(f"{key}: {values[key]}{newline}")
            done.add(key)
            skipping = True
            continue
        out.append(line)
    if out and not out[-1].endswith(("\n", "\r")):
        out[-1] += newline
    out.extend(f"{key}: {value}{newline}" for key, value in values.items() if key not in done)
    return "".join(out)


def _check_reviewer(reviewer: str) -> str:
    reviewer = reviewer.strip()
    if not reviewer:
        raise LifecycleError("--reviewer must not be blank")
    if len(reviewer) > REVIEWER_MAX_LENGTH:
        raise LifecycleError(f"--reviewer must be at most {REVIEWER_MAX_LENGTH} characters")
    if any(not ch.isprintable() for ch in reviewer):
        raise LifecycleError("--reviewer must be a single line of printable text")
    return reviewer


def _scenario_path(
    content_dir: Path, folder: str, scenario_id: str, *, must_exist: bool = True
) -> Path:
    if not is_valid_scenario_id(scenario_id):
        raise LifecycleError(f"{scenario_id!r} is not a valid scenario ID")
    path = content_dir / folder / f"{scenario_id}{SCENARIO_SUFFIX}"
    if path.is_symlink():
        raise LifecycleError(f"{path} is a symlink; refusing to touch it")
    if must_exist and not path.is_file():
        raise LifecycleError(f"no scenario {scenario_id} in content/{folder}/")
    return path


def _require_valid(path: Path, content_dir: Path) -> Scenario:
    report = validate_file(path, content_dir)
    if report.errors or report.scenario is None:
        raise ScenarioInvalid(report.errors)
    return report.scenario


def _require_valid_text(text: str, path: Path, content_dir: Path) -> None:
    scenario = parse_text(text)
    errors = location_errors(scenario, path, content_dir)
    if errors:
        raise ScenarioInvalid(errors)


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
