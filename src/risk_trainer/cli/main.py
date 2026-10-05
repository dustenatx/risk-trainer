"""The `rt` command line (PRD R2, R3)."""

from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from risk_trainer.content.lifecycle import approve as approve_scenario
from risk_trainer.content.lifecycle import retire as retire_scenario
from risk_trainer.content.repository import validate_tree
from risk_trainer.domain.errors import LifecycleError, ScenarioInvalid

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Risk Trainer content tools.")

ContentDir = Annotated[
    Path,
    typer.Option("--content-dir", help="Content root holding drafts/ and scenarios/."),
]


@app.command()
def validate(content_dir: ContentDir = Path("content")) -> None:
    """Validate every scenario file under content/."""
    if not content_dir.is_dir():
        typer.echo(f"{content_dir}: not a directory")
        raise typer.Exit(code=1)
    reports = validate_tree(content_dir)
    failed = [report for report in reports if report.errors]
    for report in failed:
        for error in report.errors:
            typer.echo(f"{report.path}: {error.path}: {error.message}")
    typer.echo(f"{len(reports)} file(s) checked, {len(failed)} with errors.")
    if failed:
        raise typer.Exit(code=1)


@app.command()
def approve(
    scenario_id: Annotated[str, typer.Argument(help="Scenario ID, e.g. rt-001-five-findings.")],
    reviewer: Annotated[str, typer.Option("--reviewer", help="Name of the human reviewer.")],
    content_dir: ContentDir = Path("content"),
) -> None:
    """Approve a draft and move it to content/scenarios/. Human use only."""
    try:
        path = approve_scenario(content_dir, scenario_id, reviewer, date.today())
    except (LifecycleError, ScenarioInvalid) as exc:
        _fail(scenario_id, exc)
    typer.echo(f"Approved {scenario_id}: {path}")


@app.command()
def retire(
    scenario_id: Annotated[str, typer.Argument(help="Scenario ID to retire.")],
    content_dir: ContentDir = Path("content"),
) -> None:
    """Retire an approved scenario so the build excludes it. Human use only."""
    try:
        path = retire_scenario(content_dir, scenario_id)
    except (LifecycleError, ScenarioInvalid) as exc:
        _fail(scenario_id, exc)
    typer.echo(f"Retired {scenario_id}: {path}")


def _fail(scenario_id: str, exc: LifecycleError | ScenarioInvalid) -> NoReturn:
    if isinstance(exc, ScenarioInvalid):
        typer.echo(f"Refused: {scenario_id} is invalid; the file is unchanged.")
        for error in exc.errors:
            typer.echo(f"  {error.path}: {error.message}")
    else:
        typer.echo(f"Refused: {exc}")
    raise typer.Exit(code=1)
