"""Local authoring MCP server over stdio (PRD R16, R17, section 8.1).

Exactly five tools. None approves, retires or deletes a scenario, or edits `status`,
`reviewed_by` or `reviewed_on`; save_draft forces a draft and writes only under
content/drafts/. Tool descriptions are static strings.

Each tool validates its own input with a Pydantic model so that every bad input comes back
as the section 8 envelope `{"error": {"code", "message"}}` with `is_error` set. The SDK still
sees the advertised schema (from those models), but its own argument model accepts anything,
so it never answers with raw validation text. Crashes are caught by the SDK, which returns
only "Error executing tool <name>" and no stack trace.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver.tools import Tool
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError

from risk_trainer.content.lifecycle import atomic_write, set_top_level_keys
from risk_trainer.content.repository import (
    DRAFTS_DIR,
    SCENARIO_SUFFIX,
    SCENARIOS_DIR,
    is_valid_scenario_id,
    location_errors,
    parse_text,
    validate_tree,
)
from risk_trainer.domain.errors import (
    ContentError,
    LifecycleError,
    ScenarioInvalid,
    SubmissionInvalid,
)
from risk_trainer.domain.models import Scenario, Status
from risk_trainer.domain.rules import format_path
from risk_trainer.domain.scoring import score
from risk_trainer.domain.submission import field_name, parse_submission
from risk_trainer.domain.treatments import APPROVER_LABELS, TREATMENT_LABELS

SERVER_NAME = "risk-trainer-authoring"
YAML_TEXT_MAX = 30_000
MAX_ANSWERS = 10

TOOL_NAMES = ("get_schema", "list_scenarios", "validate_scenario", "score_answers", "save_draft")

GET_SCHEMA_DESCRIPTION = (
    "Return the JSON Schema of a Risk Trainer scenario, plus the risk treatment codes and "
    "acceptance approver codes with their labels. Read this before drafting a scenario."
)
LIST_SCENARIOS_DESCRIPTION = (
    "List the scenarios under content/ (id, version, status, title, difficulty). Optionally "
    "filter by status: draft, approved or retired. Files that fail validation are always "
    "listed separately under `invalid` with their path and error count."
)
VALIDATE_SCENARIO_DESCRIPTION = (
    "Validate scenario YAML (at most 30,000 characters) against the schema and content rules. "
    "Returns valid and a list of errors, each with a field path and message. Writes nothing."
)
SCORE_ANSWERS_DESCRIPTION = (
    "Score a set of answers against a scenario's answer key. Give exactly one of scenario_id "
    "(a draft or approved scenario under content/) or yaml_text. answers needs one entry per "
    "finding: finding_id, treatment and, for accept, approver. Returns points, max_points and "
    "per-finding points with the preferred treatment. Writes nothing."
)
SAVE_DRAFT_DESCRIPTION = (
    "Validate scenario YAML and save it as content/drafts/<id>.yaml. The status is always "
    "forced to draft and reviewed_by and reviewed_on to null; only the owner approves content. "
    "Refuses if the ID already exists in content/scenarios/. Refuses if a draft with that ID "
    "already exists, unless overwrite is true. Set overwrite to true only when the owner has "
    "asked for that existing draft to be replaced."
)
DESCRIPTIONS = {
    "get_schema": GET_SCHEMA_DESCRIPTION,
    "list_scenarios": LIST_SCENARIOS_DESCRIPTION,
    "validate_scenario": VALIDATE_SCENARIO_DESCRIPTION,
    "score_answers": SCORE_ANSWERS_DESCRIPTION,
    "save_draft": SAVE_DRAFT_DESCRIPTION,
}

YamlText = Annotated[StrictStr, Field(min_length=1, max_length=YAML_TEXT_MAX)]


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GetSchemaInput(_Input):
    pass


class ListScenariosInput(_Input):
    status: Status | None = None


class ValidateScenarioInput(_Input):
    yaml_text: YamlText


class AnswerInput(_Input):
    finding_id: Annotated[StrictStr, Field(max_length=8)]
    treatment: Annotated[StrictStr, Field(max_length=40)]
    approver: Annotated[StrictStr, Field(max_length=40)] | None = None


class ScoreAnswersInput(_Input):
    scenario_id: Annotated[StrictStr, Field(max_length=64)] | None = None
    yaml_text: YamlText | None = None
    answers: Annotated[list[AnswerInput], Field(min_length=1, max_length=MAX_ANSWERS)]


class SaveDraftInput(_Input):
    yaml_text: YamlText
    overwrite: StrictBool = False


class ToolFailure(Exception):
    """An input or request the tool can't carry out; becomes the section 8 error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _result(data: dict[str, Any], *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))],
        structured_content=data,
        is_error=is_error,
    )


def _error(code: str, message: str) -> CallToolResult:
    return _result({"error": {"code": code, "message": message}}, is_error=True)


def _errors(errors: list[ContentError]) -> list[dict[str, str]]:
    return [{"path": error.path, "message": error.message} for error in errors]


def _validation_message(exc: ValidationError) -> str:
    # Field paths and messages only: never echo the input value back.
    return "; ".join(
        f"{format_path(tuple(error['loc'])) or '(input)'}: {error['msg']}" for error in exc.errors()
    )


def _run[M: BaseModel](
    model: type[M], raw: dict[str, Any], handler: Callable[[M], dict[str, Any]]
) -> CallToolResult:
    """Validate raw arguments with `model`, run the handler, and map failures to the envelope."""
    try:
        args = model.model_validate({k: v for k, v in raw.items() if v is not None})
    except ValidationError as exc:
        return _error("invalid_input", _validation_message(exc))
    try:
        return _result(handler(args))
    except ToolFailure as exc:
        return _error(exc.code, exc.message)


class AuthoringTools:
    """The tool bodies, bound to one content root."""

    def __init__(self, content_dir: Path) -> None:
        self.content_dir = content_dir

    def get_schema(self, _: GetSchemaInput) -> dict[str, Any]:
        return {
            "scenario_schema": Scenario.model_json_schema(),
            "treatments": [
                {"code": t.value, "label": label} for t, label in TREATMENT_LABELS.items()
            ],
            "approvers": [
                {"code": a.value, "label": label} for a, label in APPROVER_LABELS.items()
            ],
        }

    def list_scenarios(self, args: ListScenariosInput) -> dict[str, Any]:
        scenarios: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        for report in validate_tree(self.content_dir):
            if report.errors or report.scenario is None:
                invalid.append(
                    {
                        "path": report.path.relative_to(self.content_dir).as_posix(),
                        "valid": False,
                        "error_count": len(report.errors),
                    }
                )
                continue
            scenario = report.scenario
            if args.status is not None and scenario.status is not args.status:
                continue
            scenarios.append(
                {
                    "id": scenario.id,
                    "version": scenario.version,
                    "status": scenario.status.value,
                    "title": scenario.title,
                    "difficulty": scenario.difficulty.value,
                    "valid": True,
                }
            )
        scenarios.sort(key=lambda entry: str(entry["id"]))
        return {"scenarios": scenarios, "invalid": invalid}

    def validate_scenario(self, args: ValidateScenarioInput) -> dict[str, Any]:
        try:
            parse_text(args.yaml_text)
        except ScenarioInvalid as exc:
            return {"valid": False, "errors": _errors(exc.errors)}
        return {"valid": True, "errors": []}

    def score_answers(self, args: ScoreAnswersInput) -> dict[str, Any]:
        if (args.scenario_id is None) == (args.yaml_text is None):
            raise ToolFailure("invalid_input", "Give exactly one of scenario_id or yaml_text.")
        if args.yaml_text is not None:
            try:
                scenario = parse_text(args.yaml_text)
            except ScenarioInvalid as exc:
                raise ToolFailure("invalid_scenario", _joined(exc.errors)) from None
        else:
            scenario = self._find(args.scenario_id or "")

        items: list[tuple[str, str]] = []
        for answer in args.answers:
            items.append((field_name(answer.finding_id, "treatment"), answer.treatment))
            if answer.approver is not None:
                items.append((field_name(answer.finding_id, "approver"), answer.approver))
        try:
            submission = parse_submission(scenario, items, require_rationale=False)
        except SubmissionInvalid as exc:
            raise ToolFailure("invalid_answers", _joined(exc.errors)) from None

        result = score(scenario, submission)
        return {
            "points": result.total,
            "max_points": result.maximum,
            "per_finding": [
                {
                    "finding_id": finding.finding_id,
                    "points": finding.points,
                    "preferred": scenario.answer_key.findings[finding.finding_id].preferred.value,
                }
                for finding in result.findings
            ],
        }

    def save_draft(self, args: SaveDraftInput) -> dict[str, Any]:
        drafts = self.content_dir / DRAFTS_DIR

        def refused(path: str, errors: list[ContentError]) -> dict[str, Any]:
            return {"saved": False, "path": path, "replaced": False, "errors": _errors(errors)}

        try:
            text = set_top_level_keys(
                args.yaml_text,
                {"status": Status.DRAFT.value, "reviewed_by": "null", "reviewed_on": "null"},
            )
            scenario = parse_text(text)
        except LifecycleError as exc:
            return refused("", [ContentError("(yaml)", str(exc))])
        except ScenarioInvalid as exc:
            return refused("", exc.errors)

        # The file name comes only from the validated ID (R1 pattern), never from input paths.
        if not is_valid_scenario_id(scenario.id):
            return refused("", [ContentError("id", "not a valid scenario ID")])
        name = f"{scenario.id}{SCENARIO_SUFFIX}"
        target = drafts / name
        shown = f"{DRAFTS_DIR}/{name}"

        conflict = self._approved_conflict(scenario.id)
        if conflict is not None:
            return refused(
                shown,
                [
                    ContentError(
                        "id",
                        f"{scenario.id} already exists as {conflict}; save_draft never writes "
                        "to content/scenarios/. Use a new ID.",
                    )
                ],
            )

        location_problem = self._unsafe_location(drafts, target)
        if location_problem is not None:
            return refused(shown, [ContentError("(file)", location_problem)])

        replaced = target.exists()
        if replaced and not args.overwrite:
            return refused(
                shown,
                [
                    ContentError(
                        "id",
                        f"a draft named {shown} already exists. Set overwrite to true only if "
                        "the owner asked for it to be replaced.",
                    )
                ],
            )

        errors = location_errors(scenario, target, self.content_dir)
        if errors:
            return refused(shown, errors)

        drafts.mkdir(exist_ok=True)
        atomic_write(target, text)
        result: dict[str, Any] = {"saved": True, "path": shown, "replaced": replaced, "errors": []}
        if replaced:
            result["message"] = f"Replaced the existing draft {shown}."
        return result

    def _find(self, scenario_id: str) -> Scenario:
        if not is_valid_scenario_id(scenario_id):
            raise ToolFailure("invalid_input", f"{scenario_id!r} is not a valid scenario ID.")
        broken = False
        for report in validate_tree(self.content_dir):
            if (
                report.scenario is not None
                and report.scenario.id == scenario_id
                and not report.errors
                and report.scenario.status in (Status.DRAFT, Status.APPROVED)
            ):
                return report.scenario
            if report.path.name == f"{scenario_id}{SCENARIO_SUFFIX}" and report.errors:
                broken = True
        if broken:
            raise ToolFailure(
                "invalid_scenario", f"{scenario_id} has validation errors; run validate_scenario."
            )
        raise ToolFailure("not_found", f"No draft or approved scenario {scenario_id}.")

    def _approved_conflict(self, scenario_id: str) -> str | None:
        """Where `scenario_id` already lives in content/scenarios/, if anywhere."""
        folder = self.content_dir / SCENARIOS_DIR
        named = folder / f"{scenario_id}{SCENARIO_SUFFIX}"
        if named.exists() or named.is_symlink():
            return f"{SCENARIOS_DIR}/{named.name}"
        for report in validate_tree(self.content_dir):
            if (
                report.scenario is not None
                and report.scenario.id == scenario_id
                and report.path.parent == folder
            ):
                return f"{SCENARIOS_DIR}/{report.path.name}"
        return None

    def _unsafe_location(self, drafts: Path, target: Path) -> str | None:
        """Why writing `target` would leave content/drafts/, or None if it's safe."""
        expected = self.content_dir.resolve() / DRAFTS_DIR
        if drafts.is_symlink():
            return "content/drafts/ is a symlink; refusing to write through it"
        if drafts.exists() and (not drafts.is_dir() or drafts.resolve() != expected):
            return "content/drafts/ resolves outside the content folder; refusing to write"
        if target.is_symlink():
            return f"{DRAFTS_DIR}/{target.name} is a symlink; refusing to write onto it"
        if target.exists() and not target.is_file():
            return f"{DRAFTS_DIR}/{target.name} is not a regular file"
        if target.resolve().parent != expected:
            return "the draft path resolves outside content/drafts/; refusing to write"
        return None


def _joined(errors: list[ContentError]) -> str:
    return "; ".join(f"{error.path}: {error.message}" for error in errors)


def build_server(content_dir: Path) -> MCPServer:
    """The authoring server for one content root. Exactly the five section 8.1 tools."""
    tools = AuthoringTools(content_dir)

    # Python parameters accept anything (the SDK passes them through untouched); each body
    # validates with its own model, whose schema is what clients see.
    def get_schema() -> CallToolResult:
        return _run(GetSchemaInput, {}, tools.get_schema)

    def list_scenarios(status: Any = None) -> CallToolResult:
        return _run(ListScenariosInput, {"status": status}, tools.list_scenarios)

    def validate_scenario(yaml_text: Any = None) -> CallToolResult:
        return _run(ValidateScenarioInput, {"yaml_text": yaml_text}, tools.validate_scenario)

    def score_answers(
        scenario_id: Any = None, yaml_text: Any = None, answers: Any = None
    ) -> CallToolResult:
        raw = {"scenario_id": scenario_id, "yaml_text": yaml_text, "answers": answers}
        return _run(ScoreAnswersInput, raw, tools.score_answers)

    def save_draft(yaml_text: Any = None, overwrite: Any = None) -> CallToolResult:
        raw = {"yaml_text": yaml_text, "overwrite": overwrite}
        return _run(SaveDraftInput, raw, tools.save_draft)

    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    definitions: list[tuple[Callable[..., CallToolResult], type[BaseModel], ToolAnnotations]] = [
        (get_schema, GetSchemaInput, read_only),
        (list_scenarios, ListScenariosInput, read_only),
        (validate_scenario, ValidateScenarioInput, read_only),
        (score_answers, ScoreAnswersInput, read_only),
        (
            save_draft,
            SaveDraftInput,
            ToolAnnotations(
                read_only_hint=False,
                destructive_hint=True,  # only with overwrite=true, and only a draft
                idempotent_hint=False,
                open_world_hint=False,
            ),
        ),
    ]
    registered = [
        Tool.from_function(
            fn, description=DESCRIPTIONS[fn.__name__], annotations=annotations
        ).model_copy(update={"parameters": model.model_json_schema()})
        for fn, model, annotations in definitions
    ]
    return MCPServer(SERVER_NAME, tools=registered, log_level="WARNING")
