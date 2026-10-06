"""The `rt` command line (PRD R2, R3, R5)."""

import ipaddress
import secrets
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from risk_trainer.content.lifecycle import approve as approve_scenario
from risk_trainer.content.lifecycle import retire as retire_scenario
from risk_trainer.content.repository import load_previewable, validate_tree
from risk_trainer.domain.errors import LifecycleError, ScenarioInvalid
from risk_trainer.domain.models import Scenario

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


PREVIEW_HOST = "127.0.0.1"


@app.command()
def preview(
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8000,
    content_dir: ContentDir = Path("content"),
) -> None:
    """Run the app on 127.0.0.1 with drafts visible. Local use only; there is no host option."""
    scenarios, failed = load_previewable(content_dir)
    for report in failed:
        for error in report.errors:
            typer.echo(f"Skipped {report.path}: {error.path}: {error.message}")
    typer.echo(f"Previewing {len(scenarios)} scenario(s) at http://{PREVIEW_HOST}:{port}")
    serve_preview(PREVIEW_HOST, port, content_dir, scenarios)


def serve_preview(host: str, port: int, content_dir: Path, scenarios: list[Scenario]) -> None:
    """Serve the preview app. Refuses any address that isn't loopback: drafts are unapproved."""
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError(f"rt preview only binds to a loopback address, not {host}")
    import uvicorn

    from risk_trainer.config import Settings
    from risk_trainer.storage.memory import MemoryAttemptStore
    from risk_trainer.web.app import create_app

    settings = Settings(
        storage_backend="memory",
        session_secret=secrets.token_urlsafe(32),
        session_cookie_secure=False,
        content_dir=content_dir,
    )
    web_app = create_app(settings, MemoryAttemptStore(), scenarios, preview=True)
    uvicorn.run(web_app, host=host, port=port, log_config=None)


def _fail(scenario_id: str, exc: LifecycleError | ScenarioInvalid) -> NoReturn:
    if isinstance(exc, ScenarioInvalid):
        typer.echo(f"Refused: {scenario_id} is invalid; the file is unchanged.")
        for error in exc.errors:
            typer.echo(f"  {error.path}: {error.message}")
    else:
        typer.echo(f"Refused: {exc}")
    raise typer.Exit(code=1)
