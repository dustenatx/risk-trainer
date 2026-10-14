"""R16 — the authoring MCP server: `rt mcp`, exactly five tools, structured errors."""

import builtins
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from risk_trainer.cli.main import MCP_SDK_MISSING, app
from risk_trainer.domain.models import Scenario
from risk_trainer.domain.rules import parse_scenario
from risk_trainer.domain.scoring import score
from risk_trainer.domain.submission import parse_submission
from risk_trainer.mcp import authoring
from tests.helpers import REPO_ROOT, RT001_DATA, RT001_TEXT, WriteScenario, approved
from tests.mcp_helpers import call, data, error, tools

RT001_ID = "rt-001-five-findings"
EXPERT = [
    {"finding_id": "F1", "treatment": "mitigate_remediate"},
    {"finding_id": "F2", "treatment": "mitigate_compensate"},
    {"finding_id": "F3", "treatment": "transfer"},
    {"finding_id": "F4", "treatment": "mitigate_remediate"},
    {"finding_id": "F5", "treatment": "accept", "approver": "business_risk_owner"},
]


def with_answer(finding_id: str, **answer: str) -> list[dict[str, str]]:
    return [
        {"finding_id": finding_id, **answer} if a["finding_id"] == finding_id else a for a in EXPERT
    ]


# --- rt mcp ---------------------------------------------------------------------------


def test_r16_rt_mcp_starts_stdio_server(monkeypatch: pytest.MonkeyPatch, content_dir: Path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "mcp.server.MCPServer.run", lambda self, transport="stdio", **_: calls.append(transport)
    )
    result = CliRunner().invoke(app, ["mcp", "--content-dir", str(content_dir)])
    assert result.exit_code == 0, result.output
    assert calls == ["stdio"]
    assert result.output == ""  # stdout belongs to the protocol


def test_r16_rt_mcp_without_sdk_prints_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def no_mcp(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "risk_trainer.mcp.authoring":
            raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_mcp)
    result = CliRunner().invoke(app, ["mcp"])
    assert result.exit_code == 1
    assert result.output.strip() == MCP_SDK_MISSING
    assert "Traceback" not in result.output
    assert "uv sync" in MCP_SDK_MISSING


def test_r16_rt_mcp_reraises_unrelated_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def broken(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "risk_trainer.mcp.authoring":
            raise ModuleNotFoundError("No module named 'yaml'", name="yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken)
    result = CliRunner().invoke(app, ["mcp"])
    assert isinstance(result.exception, ModuleNotFoundError)


# --- tool set ---------------------------------------------------------------------------


def test_r16_exposes_exactly_five_tools(content_dir: Path) -> None:
    names = {tool.name for tool in tools(content_dir)}
    assert names == {
        "get_schema",
        "list_scenarios",
        "validate_scenario",
        "score_answers",
        "save_draft",
    }
    assert names == set(authoring.TOOL_NAMES)


def test_r16_no_tool_approves_retires_deletes_or_edits_review_fields(content_dir: Path) -> None:
    forbidden = re.compile(r"approve|retire|delete|remove|status|reviewed_by|reviewed_on")
    for tool in tools(content_dir):
        assert not forbidden.search(tool.name)
        properties = tool.input_schema.get("properties", {})
        # list_scenarios may filter by status; nothing may set it.
        settable = [p for p in properties if not (tool.name == "list_scenarios" and p == "status")]
        assert not any(forbidden.search(p) for p in settable), (tool.name, settable)


def test_r16_tool_descriptions_are_static(content_dir: Path) -> None:
    for tool in tools(content_dir):
        assert tool.description == authoring.DESCRIPTIONS[tool.name]
    assert authoring.DESCRIPTIONS["get_schema"] == authoring.GET_SCHEMA_DESCRIPTION


# --- get_schema / list_scenarios / validate_scenario ------------------------------------


def test_r16_get_schema_returns_schema_and_codes(content_dir: Path) -> None:
    result = data(call(content_dir, "get_schema"))
    assert result["scenario_schema"] == Scenario.model_json_schema()
    assert {t["code"] for t in result["treatments"]} == {
        "avoid",
        "mitigate_remediate",
        "mitigate_compensate",
        "transfer",
        "accept",
    }
    labels = {a["code"]: a["label"] for a in result["approvers"]}
    assert labels["senior_management"] == "Executive leadership / risk committee"


def test_r16_list_scenarios_filters_by_status(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(RT001_TEXT)
    write_scenario(approved(RT001_DATA, "rt-002-other"), folder="scenarios")
    everything = data(call(content_dir, "list_scenarios"))["scenarios"]
    assert [s["id"] for s in everything] == [RT001_ID, "rt-002-other"]
    drafts = data(call(content_dir, "list_scenarios", {"status": "draft"}))["scenarios"]
    assert drafts == [
        {
            "id": RT001_ID,
            "version": RT001_DATA["version"],
            "status": "draft",
            "title": RT001_DATA["title"],
            "difficulty": RT001_DATA["difficulty"],
            "valid": True,
        }
    ]
    approved_only = data(call(content_dir, "list_scenarios", {"status": "approved"}))
    assert [s["id"] for s in approved_only["scenarios"]] == ["rt-002-other"]


def test_r16_list_scenarios_shows_invalid_files(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(RT001_TEXT)
    write_scenario("id: rt-009-broken\nversion: [unclosed\n", name="rt-009-broken.yaml")
    for arguments in ({}, {"status": "approved"}, {"status": "draft"}):
        result = data(call(content_dir, "list_scenarios", arguments))
        assert result["invalid"] == [
            {"path": "drafts/rt-009-broken.yaml", "valid": False, "error_count": 1}
        ]


def test_r16_list_scenarios_rejects_unknown_status(content_dir: Path) -> None:
    assert error(call(content_dir, "list_scenarios", {"status": "live"}))["code"] == "invalid_input"


def test_r16_validate_scenario_valid_and_invalid(content_dir: Path) -> None:
    assert data(call(content_dir, "validate_scenario", {"yaml_text": RT001_TEXT})) == {
        "valid": True,
        "errors": [],
    }
    bad = RT001_TEXT.replace("(fictional)", "Inc.", 1)
    result = data(call(content_dir, "validate_scenario", {"yaml_text": bad}))
    assert result["valid"] is False
    assert any(e["path"] == "context.organization" for e in result["errors"])


def test_r16_validate_scenario_rejects_oversized_yaml(content_dir: Path) -> None:
    oversized = "#" * (authoring.YAML_TEXT_MAX + 1)
    envelope = error(call(content_dir, "validate_scenario", {"yaml_text": oversized}))
    assert envelope["code"] == "invalid_input"
    assert "yaml_text" in envelope["message"]
    assert oversized not in envelope["message"]


# --- score_answers ----------------------------------------------------------------------


def expected_points(scenario: Scenario, answers: list[dict[str, str]]) -> int:
    items = [(f"{a['finding_id']}.treatment", a["treatment"]) for a in answers] + [
        (f"{a['finding_id']}.approver", a["approver"]) for a in answers if "approver" in a
    ]
    return score(scenario, parse_submission(scenario, items, require_rationale=False)).total


def test_r16_score_answers_by_id_and_by_yaml(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(RT001_TEXT)
    scenario = parse_scenario(RT001_DATA)
    answers = with_answer("F5", treatment="accept", approver="it_operations")
    by_id = data(call(content_dir, "score_answers", {"scenario_id": RT001_ID, "answers": answers}))
    by_yaml = data(
        call(content_dir, "score_answers", {"yaml_text": RT001_TEXT, "answers": answers})
    )
    assert by_id == by_yaml
    assert by_id["points"] == expected_points(scenario, answers)
    assert by_id["max_points"] == 10
    assert [f["finding_id"] for f in by_id["per_finding"]] == ["F1", "F2", "F3", "F4", "F5"]
    assert by_id["per_finding"][0]["preferred"] == "mitigate_remediate"


def test_r16_score_answers_expert_answers_score_full_marks(content_dir: Path) -> None:
    result = data(call(content_dir, "score_answers", {"yaml_text": RT001_TEXT, "answers": EXPERT}))
    assert result["points"] == result["max_points"] == 10


def test_r16_score_answers_finds_approved_scenarios(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(approved(RT001_DATA), folder="scenarios")
    result = call(content_dir, "score_answers", {"scenario_id": RT001_ID, "answers": EXPERT})
    assert data(result)["points"] == 10


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        ({"answers": EXPERT}, "invalid_input"),  # neither source
        ({"scenario_id": RT001_ID, "yaml_text": RT001_TEXT, "answers": EXPERT}, "invalid_input"),
        ({"scenario_id": "rt-404-missing", "answers": EXPERT}, "not_found"),
        ({"scenario_id": "../etc/passwd", "answers": EXPERT}, "invalid_input"),
        ({"yaml_text": "id: [", "answers": EXPERT}, "invalid_scenario"),
        ({"yaml_text": RT001_TEXT, "answers": EXPERT[:4]}, "invalid_answers"),  # missing F5
        ({"yaml_text": RT001_TEXT, "answers": [*EXPERT, EXPERT[0]]}, "invalid_answers"),
        (
            {"yaml_text": RT001_TEXT, "answers": with_answer("F5", treatment="accept")},
            "invalid_answers",
        ),  # accept without an approver
        (
            {
                "yaml_text": RT001_TEXT,
                "answers": with_answer("F2", treatment="mitigate_remediate"),
            },
            "invalid_answers",
        ),  # three remediations, two slots
        (
            {"yaml_text": RT001_TEXT, "answers": with_answer("F1", treatment="ignore")},
            "invalid_answers",
        ),
        ({"yaml_text": RT001_TEXT, "answers": []}, "invalid_input"),
        ({"yaml_text": RT001_TEXT}, "invalid_input"),
    ],
)
def test_r16_score_answers_errors(
    content_dir: Path, write_scenario: WriteScenario, arguments: dict[str, Any], code: str
) -> None:
    write_scenario(RT001_TEXT)
    assert error(call(content_dir, "score_answers", arguments))["code"] == code


def test_r16_score_answers_reports_invalid_stored_scenario(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(RT001_TEXT.replace("(fictional)", "Inc.", 1))
    envelope = error(
        call(content_dir, "score_answers", {"scenario_id": RT001_ID, "answers": EXPERT})
    )
    assert envelope["code"] == "invalid_scenario"


def test_r16_require_rationale_false_skips_only_the_minimum() -> None:
    scenario = parse_scenario(RT001_DATA)
    items = [(f"{a['finding_id']}.treatment", a["treatment"]) for a in EXPERT]
    items.append(("F5.approver", "business_risk_owner"))
    parse_submission(scenario, items, require_rationale=False)  # no rationale: fine
    from risk_trainer.domain.errors import SubmissionInvalid

    with pytest.raises(SubmissionInvalid, match="invalid"):
        parse_submission(scenario, [*items, ("F5.rationale", "x" * 601)], require_rationale=False)


# --- errors -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("list_scenarios", {"status": 7}),
        ("validate_scenario", {}),
        ("validate_scenario", {"yaml_text": 5}),
        ("validate_scenario", {"yaml_text": ""}),
        ("score_answers", {"yaml_text": RT001_TEXT, "answers": "F1=fix"}),
        ("score_answers", {"yaml_text": RT001_TEXT, "answers": [{"finding_id": "F1"}]}),
        ("save_draft", {}),
        ("save_draft", {"yaml_text": RT001_TEXT, "overwrite": "yes"}),
    ],
)
def test_r16_errors_are_structured_never_tracebacks(
    content_dir: Path, tool: str, arguments: dict[str, Any]
) -> None:
    result = call(content_dir, tool, arguments)
    envelope = error(result)
    assert envelope["code"] == "invalid_input"
    text = " ".join(getattr(item, "text", "") for item in result.content)
    assert "Traceback" not in text
    assert 'File "' not in text


def test_r16_internal_crash_returns_only_a_generic_message(
    monkeypatch: pytest.MonkeyPatch, content_dir: Path
) -> None:
    def crash(self: object, _: object) -> dict[str, Any]:
        raise RuntimeError("secret internals at /Users/someone/path.py")

    monkeypatch.setattr(authoring.AuthoringTools, "get_schema", crash)
    result = call(content_dir, "get_schema")
    assert result.is_error
    text = " ".join(getattr(item, "text", "") for item in result.content)
    assert text == "Error executing tool get_schema"


def test_r16_audit_covers_dev_group() -> None:
    """pip-audit (CI runs `make audit`) must see dev dependencies, which include `mcp`."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("\naudit:\n", 1)[1].split("\n\n", 1)[0]
    export = next(line for line in recipe.splitlines() if "uv export" in line)
    assert "--no-dev" not in export
    assert "--only-" not in export
    assert "--no-default-groups" not in export
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "run: make audit" in ci
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dev_group = pyproject.split("[dependency-groups]", 1)[1].split("\n[", 1)[0]
    assert '"mcp>=' in dev_group
