"""R6/R7 — submission rules, enforced by the server whatever the browser sends."""

import pytest

from risk_trainer.domain.errors import SubmissionInvalid
from risk_trainer.domain.submission import parse_submission
from risk_trainer.domain.treatments import Treatment
from tests.web_helpers import EXPERT_ANSWERS, rt001

SCENARIO = rt001()


def errors_for(items: list[tuple[str, str]]) -> list[str]:
    with pytest.raises(SubmissionInvalid) as exc:
        parse_submission(SCENARIO, items)
    return [error.message for error in exc.value.errors]


def with_changes(**changes: str) -> list[tuple[str, str]]:
    answers = {**EXPERT_ANSWERS}
    for key, value in changes.items():
        name = key.replace("__", ".")
        if value == "<drop>":
            answers.pop(name, None)
        else:
            answers[name] = value
    return list(answers.items())


def test_r7_valid_submission_parses() -> None:
    submission = parse_submission(SCENARIO, EXPERT_ANSWERS.items())
    assert [a.finding_id for a in submission.answers] == ["F1", "F2", "F3", "F4", "F5"]


def test_r6_requires_a_treatment_for_every_finding() -> None:
    assert errors_for(with_changes(F3__treatment="<drop>")) == ["Choose a response for F3."]


def test_r7_rejects_unknown_finding_id() -> None:
    messages = errors_for([*EXPERT_ANSWERS.items(), ("F9.treatment", "avoid")])
    assert messages == ["F9 is not a finding in this scenario."]


def test_r7_rejects_duplicate_answer() -> None:
    messages = errors_for([*EXPERT_ANSWERS.items(), ("F1.treatment", "avoid")])
    assert messages == ["This field was sent more than once."]


def test_r7_rejects_unexpected_field() -> None:
    assert errors_for([*EXPERT_ANSWERS.items(), ("score", "10")]) == [
        "This field isn't part of the form."
    ]


def test_r7_rejects_unknown_treatment() -> None:
    assert errors_for(with_changes(F1__treatment="ignore")) == [
        "F1: choose one of the listed responses."
    ]


def test_r6_accept_requires_an_approver() -> None:
    assert errors_for(with_changes(F5__approver="<drop>")) == [
        "F5: choose who approves accepting this risk."
    ]


@pytest.mark.parametrize("length", [10, 600])
def test_r6_accept_rationale_bounds_pass(length: int) -> None:
    parse_submission(SCENARIO, with_changes(F5__rationale="a" * length))


@pytest.mark.parametrize("length", [0, 9])
def test_r6_accept_rationale_too_short(length: int) -> None:
    messages = errors_for(with_changes(F5__rationale="a" * length))
    assert messages == ["F5: accepting a risk needs a rationale of at least 10 characters."]


def test_r6_accept_rationale_whitespace_only_fails() -> None:
    assert errors_for(with_changes(F5__rationale=" " * 20))


def test_r6_rationale_over_600_fails() -> None:
    accepted = errors_for(with_changes(F5__rationale="a" * 601))
    other = errors_for(with_changes(F1__rationale="a" * 601))
    assert accepted == ["F5: keep the rationale to 600 characters or fewer."]
    assert other == ["F1: keep the rationale to 600 characters or fewer."]


def test_r6_rationale_optional_for_other_treatments() -> None:
    submission = parse_submission(SCENARIO, with_changes(F1__rationale=""))
    assert submission.answer_for("F1").rationale == ""


def test_r6_overall_note_bounds() -> None:
    parse_submission(SCENARIO, [*EXPERT_ANSWERS.items(), ("note", "n" * 1200)])
    assert errors_for([*EXPERT_ANSWERS.items(), ("note", "n" * 1201)]) == [
        "Keep the overall note to 1200 characters or fewer."
    ]


def test_r6_remediate_over_slots_rejected() -> None:
    messages = errors_for(with_changes(F2__treatment="mitigate_remediate"))
    assert len(messages) == 1
    assert "capacity for 2" in messages[0]


def test_r6_approver_ignored_for_non_accept() -> None:
    submission = parse_submission(
        SCENARIO, with_changes(F1__approver="security_team", F1__rationale="")
    )
    answer = submission.answer_for("F1")
    assert answer.treatment is Treatment.MITIGATE_REMEDIATE
    assert answer.approver is None


def test_r7_reports_every_problem_at_once() -> None:
    messages = errors_for(with_changes(F1__treatment="<drop>", F2__treatment="<drop>"))
    assert len(messages) == 2
