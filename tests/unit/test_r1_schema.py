"""R1 — scenario schema."""

import datetime
from pathlib import Path
from typing import Any

import pytest

from risk_trainer.content.repository import validate_tree
from risk_trainer.content.yaml_loader import load_yaml
from risk_trainer.domain.errors import ContentError, ScenarioInvalid
from risk_trainer.domain.models import Scenario
from risk_trainer.domain.rules import parse_scenario
from tests.helpers import RT001_TEXT, WriteScenario, approved


def errors_for(data: object) -> list[ContentError]:
    with pytest.raises(ScenarioInvalid) as caught:
        parse_scenario(data)
    return caught.value.errors


def has_error(errors: list[ContentError], path: str, fragment: str = "") -> bool:
    return any(e.path == path and fragment in e.message for e in errors)


def key(data: dict[str, Any], finding_id: str) -> dict[str, Any]:
    entry: dict[str, Any] = data["answer_key"]["findings"][finding_id]
    return entry


def test_r1_rt001_draft_is_valid(rt001: dict[str, Any]) -> None:
    scenario = parse_scenario(rt001)
    assert isinstance(scenario, Scenario)
    assert [f.id for f in scenario.findings] == ["F1", "F2", "F3", "F4", "F5"]


def test_r1_rejects_non_mapping() -> None:
    assert has_error(errors_for(["not", "a", "mapping"]), "(root)")


def test_r1_rejects_missing_key_entry(rt001: dict[str, Any]) -> None:
    del rt001["answer_key"]["findings"]["F3"]
    assert has_error(errors_for(rt001), "answer_key.findings", "F3")


def test_r1_rejects_extra_key_entry(rt001: dict[str, Any]) -> None:
    rt001["answer_key"]["findings"]["F6"] = key(rt001, "F1")
    assert has_error(errors_for(rt001), "answer_key.findings.F6", "no finding")


def test_r1_preferred_must_be_in_acceptable(rt001: dict[str, Any]) -> None:
    key(rt001, "F2")["acceptable"] = ["avoid"]
    assert has_error(errors_for(rt001), "answer_key.findings.F2.acceptable", "mitigate_compensate")


def test_r1_requires_three_response_families(rt001: dict[str, Any]) -> None:
    # Remediate + compensate count as one response, so mitigate + accept is only two.
    key(rt001, "F3").update(preferred="mitigate_compensate", acceptable=["mitigate_compensate"])
    key(rt001, "F3").pop("approvers")
    assert has_error(errors_for(rt001), "answer_key.findings", "at least 3")


def test_r1_three_families_with_both_mitigate_codes_pass(rt001: dict[str, Any]) -> None:
    # rt-001 uses remediate, compensate, transfer and accept: three responses.
    assert parse_scenario(rt001)


def test_r1_foundational_requires_job_tip(rt001: dict[str, Any]) -> None:
    rt001["answer_key"]["job_tip"] = None
    assert has_error(errors_for(rt001), "answer_key.job_tip")


@pytest.mark.parametrize("difficulty", ["intermediate", "advanced"])
def test_r1_intermediate_and_advanced_require_exam_tip(
    rt001: dict[str, Any], difficulty: str
) -> None:
    rt001["difficulty"] = difficulty
    rt001["answer_key"]["exam_tip"] = None
    assert has_error(errors_for(rt001), "answer_key.exam_tip")
    rt001["answer_key"]["exam_tip"] = "An exam tip."
    rt001["answer_key"]["job_tip"] = None
    assert parse_scenario(rt001)


def test_r1_remediate_over_slots_fails(rt001: dict[str, Any]) -> None:
    rt001["context"]["capacity"]["remediation_slots"] = 1
    assert has_error(errors_for(rt001), "answer_key.findings", "remediation_slots is 1")


def test_r1_remediation_slots_default_to_two(rt001: dict[str, Any]) -> None:
    rt001["context"]["capacity"] = {}
    assert parse_scenario(rt001).context.capacity.remediation_slots == 2


def test_r1_accept_requires_correct_approvers(rt001: dict[str, Any]) -> None:
    key(rt001, "F5")["approvers"]["correct"] = []
    assert has_error(errors_for(rt001), "answer_key.findings.F5.approvers.correct")
    key(rt001, "F5").pop("approvers")
    assert has_error(errors_for(rt001), "answer_key.findings.F5.approvers.correct")


def test_r1_accept_only_acceptable_still_requires_approvers(rt001: dict[str, Any]) -> None:
    key(rt001, "F3").pop("approvers")  # F3: transfer preferred, accept acceptable
    assert has_error(errors_for(rt001), "answer_key.findings.F3.approvers.correct")


def test_r1_approvers_forbidden_without_accept(rt001: dict[str, Any]) -> None:
    key(rt001, "F1")["approvers"] = {"correct": ["business_risk_owner"], "acceptable": []}
    assert has_error(errors_for(rt001), "answer_key.findings.F1.approvers", "only allowed")


def test_r1_approver_overlap_rejected(rt001: dict[str, Any]) -> None:
    key(rt001, "F5")["approvers"]["acceptable"] = ["business_risk_owner"]
    assert has_error(
        errors_for(rt001), "answer_key.findings.F5.approvers.acceptable", "already listed"
    )


@pytest.mark.parametrize("field", ["correct", "acceptable"])
def test_r1_security_team_never_approver(rt001: dict[str, Any], field: str) -> None:
    key(rt001, "F5")["approvers"][field].append("security_team")
    assert has_error(
        errors_for(rt001), f"answer_key.findings.F5.approvers.{field}", "never accepts"
    )


def test_r1_approved_requires_reviewed_fields(rt001: dict[str, Any]) -> None:
    rt001["status"] = "approved"
    errors = errors_for(rt001)
    assert has_error(errors, "reviewed_by")
    assert has_error(errors, "reviewed_on")
    rt001["reviewed_by"] = "Owner"
    rt001["reviewed_on"] = datetime.date(2026, 10, 5)
    assert parse_scenario(rt001).status == "approved"


def test_r1_duplicate_finding_ids(rt001: dict[str, Any]) -> None:
    rt001["findings"][1]["id"] = "F1"
    errors = errors_for(rt001)
    assert has_error(errors, "findings[1].id", "duplicate finding ID F1")
    assert has_error(errors, "answer_key.findings.F2", "no finding")


def test_r1_duplicate_scenario_ids_across_repo(
    rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    write_scenario(rt001)
    write_scenario(approved(rt001), folder="scenarios")
    reports = validate_tree(write_scenario(rt001).parent.parent)
    assert len(reports) == 2
    for report in reports:
        assert has_error(report.errors, "id", "more than one file")


@pytest.mark.parametrize(
    "scenario_id",
    ["rt-001-a", "rt-123-five-findings", "rt-999-x1-y2", "rt-001-" + "a" * 57],
)
def test_r1_scenario_id_pattern_accepts(rt001: dict[str, Any], scenario_id: str) -> None:
    rt001["id"] = scenario_id
    assert parse_scenario(rt001).id == scenario_id


@pytest.mark.parametrize(
    "scenario_id",
    [
        "rt-01-short",
        "rt-001",
        "rt-001-",
        "rt-001-Upper",
        "rt-001--double",
        "rt-001-under_score",
        "RT-001-x",
        "../rt-001-x",
        "rt-001-x/../../etc",
        "rt-001-" + "a" * 58,  # 65 characters
    ],
)
def test_r1_scenario_id_pattern_rejects(rt001: dict[str, Any], scenario_id: str) -> None:
    rt001["id"] = scenario_id
    assert has_error(errors_for(rt001), "id")


@pytest.mark.parametrize("bad_id", ["F0", "F6", "f1", "1"])
def test_r1_finding_ids_f1_to_f5(rt001: dict[str, Any], bad_id: str) -> None:
    rt001["findings"][0]["id"] = bad_id
    assert has_error(errors_for(rt001), "findings[0].id")


@pytest.mark.parametrize("count", [4, 6])
def test_r1_exactly_five_findings(rt001: dict[str, Any], count: int) -> None:
    rt001["findings"] = (rt001["findings"] * 2)[:count]
    assert has_error(errors_for(rt001), "findings")


def test_r1_organization_must_end_fictional(rt001: dict[str, Any]) -> None:
    rt001["context"]["organization"] = "Tallgrass Outfitters"
    assert has_error(errors_for(rt001), "context.organization", "(fictional)")


def test_r1_expert_rationale_max_120_words(rt001: dict[str, Any]) -> None:
    key(rt001, "F1")["expert_rationale"] = " ".join(["word"] * 120)
    assert parse_scenario(rt001)
    key(rt001, "F1")["expert_rationale"] = " ".join(["word"] * 121)
    assert has_error(errors_for(rt001), "answer_key.findings.F1.expert_rationale", "121 words")


@pytest.mark.parametrize("count", [1, 5])
def test_r1_key_considerations_2_to_4(rt001: dict[str, Any], count: int) -> None:
    key(rt001, "F1")["key_considerations"] = ["A consideration."] * count
    assert has_error(errors_for(rt001), "answer_key.findings.F1.key_considerations")


@pytest.mark.parametrize("cvss", [-0.1, 10.1, "9.8", True])
def test_r1_cvss_range_and_type(rt001: dict[str, Any], cvss: object) -> None:
    rt001["findings"][0]["signals"]["cvss_base"] = cvss
    assert has_error(errors_for(rt001), "findings[0].signals.cvss_base")


@pytest.mark.parametrize("cvss", [0, 10, 7.5, None])
def test_r1_cvss_accepts_valid(rt001: dict[str, Any], cvss: object) -> None:
    rt001["findings"][0]["signals"]["cvss_base"] = cvss
    assert parse_scenario(rt001)


@pytest.mark.parametrize("domains", [[0], [9], [1, 1], []])
def test_r1_cissp_domains_1_to_8_unique(rt001: dict[str, Any], domains: list[int]) -> None:
    rt001["cissp_domains"] = domains
    assert has_error(errors_for(rt001), "cissp_domains") or has_error(
        errors_for(rt001), "cissp_domains[0]"
    )


def test_r1_rejects_cve_ids(rt001: dict[str, Any]) -> None:
    rt001["findings"][0]["description"] = "Tracked as CVE-2024-12345 by the vendor."
    assert has_error(errors_for(rt001), "findings[0].description", "CVE")


def test_r1_rejects_duplicate_yaml_keys() -> None:
    from yaml import YAMLError

    with pytest.raises(YAMLError, match="duplicate key 'title'"):
        load_yaml(RT001_TEXT.replace("title:", "title: Dup\ntitle:", 1))


def test_r1_yaml_loader_is_safe() -> None:
    from yaml import YAMLError

    with pytest.raises(YAMLError):
        load_yaml("!!python/object/apply:os.system ['true']")


def test_r1_rejects_unknown_fields(rt001: dict[str, Any]) -> None:
    rt001["findings"][0]["signals"]["epss"] = 0.5
    rt001["surprise"] = True
    errors = errors_for(rt001)
    assert has_error(errors, "findings[0].signals.epss")
    assert has_error(errors, "surprise")


@pytest.mark.parametrize("field", ["version", "estimated_minutes"])
def test_r1_rejects_coerced_numbers(rt001: dict[str, Any], field: str) -> None:
    rt001[field] = "1"
    assert has_error(errors_for(rt001), field)


def test_r1_rejects_blank_text(rt001: dict[str, Any]) -> None:
    rt001["title"] = "   "
    assert has_error(errors_for(rt001), "title", "blank")


def test_r1_errors_carry_field_paths(rt001: dict[str, Any]) -> None:
    rt001["findings"][2]["exposure"] = "the internet"
    key(rt001, "F4")["preferred"] = "ignore"
    errors = errors_for(rt001)
    assert has_error(errors, "findings[2].exposure")
    assert has_error(errors, "answer_key.findings.F4.preferred")


def test_r1_filename_must_match_id(rt001: dict[str, Any], write_scenario: WriteScenario) -> None:
    path = write_scenario(rt001, name="rt-001-other-name.yaml")
    (report,) = validate_tree(path.parent.parent)
    assert has_error(report.errors, "id", "rt-001-five-findings.yaml")


def test_r1_folder_status_mismatch_drafts(
    rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    path = write_scenario(approved(rt001))
    (report,) = validate_tree(path.parent.parent)
    assert has_error(report.errors, "status", "must be draft")
    assert has_error(report.errors, "reviewed_by", "must be null")


def test_r1_folder_status_mismatch_scenarios(
    rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    path = write_scenario(rt001, folder="scenarios")
    (report,) = validate_tree(path.parent.parent)
    assert has_error(report.errors, "status", "approved or retired")


def test_r1_retired_requires_reviewed_fields(
    rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    rt001["status"] = "retired"
    path = write_scenario(rt001, folder="scenarios")
    (report,) = validate_tree(path.parent.parent)
    assert has_error(report.errors, "reviewed_by", "retired")


def test_r1_files_outside_known_folders_rejected(
    rt001: dict[str, Any], write_scenario: WriteScenario
) -> None:
    path = write_scenario(rt001, folder="elsewhere")
    (report,) = validate_tree(path.parent.parent)
    assert has_error(report.errors, "(file)", "content/drafts/")


def test_r1_symlinks_rejected(rt001: dict[str, Any], write_scenario: WriteScenario) -> None:
    real = write_scenario(rt001, folder="elsewhere", name="real.txt")
    link = real.parent.parent / "drafts" / "rt-001-five-findings.yaml"
    link.symlink_to(real)
    (report,) = validate_tree(link.parent.parent)
    assert has_error(report.errors, "(file)", "symlink")


def test_r1_oversized_and_non_utf8_files_rejected(write_scenario: WriteScenario) -> None:
    big = write_scenario("x: " + "a" * 70_000, name="rt-001-big.yaml")
    bad = big.parent / "rt-001-bad.yaml"
    bad.write_bytes(b"title: \xff\xfe")
    reports = {r.path.name: r for r in validate_tree(big.parent.parent)}
    assert has_error(reports["rt-001-big.yaml"].errors, "(file)", "larger than")
    assert has_error(reports["rt-001-bad.yaml"].errors, "(file)", "UTF-8")


def test_r1_malformed_yaml_reports_line(write_scenario: WriteScenario) -> None:
    path = write_scenario("id: rt-001-x\ntitle: [unclosed\n")
    (report,) = validate_tree(path.parent.parent)
    assert report.errors[0].path == "(yaml)"
    assert "line" in report.errors[0].message


def test_r1_repo_content_tree_is_valid() -> None:
    root = Path(__file__).resolve().parents[2] / "content"
    assert all(not report.errors for report in validate_tree(root))
