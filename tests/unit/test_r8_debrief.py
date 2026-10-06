"""R8 — the debrief: per-finding table, expert reasoning, traps, tips and approver feedback."""

import re

import pytest

from risk_trainer.domain.debrief import APPROVER_WHY, approver_feedback, build_debrief
from risk_trainer.domain.scoring import score
from risk_trainer.domain.submission import parse_submission
from risk_trainer.domain.treatments import Approver, Treatment
from tests.web_helpers import EXPERT_ANSWERS, client, rt001, submit

SCENARIO = rt001()


def debrief_for(answers: dict[str, str]):  # type: ignore[no-untyped-def]
    submission = parse_submission(SCENARIO, answers.items())
    return build_debrief(SCENARIO, submission, score(SCENARIO, submission))


def test_r8_rows_show_learner_and_expert_choice_and_points() -> None:
    debrief = debrief_for({**EXPERT_ANSWERS, "F2.treatment": "avoid"})
    f2 = debrief.rows[1]
    assert (f2.learner_treatment, f2.expert_treatment, f2.points) == (
        Treatment.AVOID,
        Treatment.MITIGATE_COMPENSATE,
        1,
    )
    assert f2.expert_rationale == SCENARIO.answer_key.findings["F2"].expert_rationale
    assert f2.key_considerations == tuple(SCENARIO.answer_key.findings["F2"].key_considerations)


def test_r8_result_page_contains_debrief_sections() -> None:
    response = submit(client())
    text = response.text
    key = SCENARIO.answer_key
    assert response.status_code == 200
    assert "10 of 10 points (100%)" in text
    assert "Your choices compared with the expert answer" in text
    for fid in ("F1", "F2", "F3", "F4", "F5"):
        assert f'id="debrief-{fid}"' in text
    assert key.common_traps[0][:40] in text.replace("&#39;", "'")
    assert key.job_tip is not None
    assert key.job_tip[:40] in text.replace("&#39;", "'")


def test_r8_shows_exam_tip_and_job_tip_when_both_present() -> None:
    scenario = rt001(difficulty="intermediate")
    data = scenario.answer_key.model_copy(update={"exam_tip": "Exam tip text here."})
    scenario = scenario.model_copy(update={"answer_key": data})
    text = submit(client([scenario])).text
    assert 'class="exam-tip">Exam tip text here.' in text
    assert 'class="job-tip"' in text


def test_r8_wrong_approver_states_who_and_why() -> None:
    debrief = debrief_for({**EXPERT_ANSWERS, "F5.approver": "security_team"})
    feedback = debrief.rows[4].approver_feedback
    assert feedback is not None
    assert feedback.startswith("Who should approve: Business owner of the affected asset")
    assert APPROVER_WHY[Approver.SECURITY_TEAM] in feedback


def test_r8_acceptable_senior_management_gets_its_own_message() -> None:
    debrief = debrief_for({**EXPERT_ANSWERS, "F5.approver": "senior_management"})
    assert APPROVER_WHY["senior_management_acceptable"] in (debrief.rows[4].approver_feedback or "")


def test_r8_correct_approver_gets_no_feedback() -> None:
    assert debrief_for(EXPERT_ANSWERS).rows[4].approver_feedback is None


def test_r8_no_approver_feedback_without_accept() -> None:
    submission = parse_submission(SCENARIO, EXPERT_ANSWERS.items())
    key = SCENARIO.answer_key.findings["F1"]
    assert approver_feedback(key, submission.answer_for("F1")) is None


@pytest.mark.parametrize("message", list(APPROVER_WHY.values()))
def test_r8_approver_why_has_no_absolute_rules(message: str) -> None:
    assert not re.search(r"\b(never|always|must|cannot|can't)\b", message, re.IGNORECASE)
    assert "typically" in message


def test_r8_approver_why_covers_every_approver() -> None:
    assert {str(a) for a in Approver} | {"senior_management_acceptable"} == set(APPROVER_WHY)


def test_r8_why_not_shown_only_when_learner_choice_matches() -> None:
    key = SCENARIO.answer_key.findings["F1"]
    debrief = debrief_for(
        {**EXPERT_ANSWERS, "F1.treatment": "mitigate_compensate", "F2.treatment": "transfer"}
    )
    assert debrief.rows[0].why_not == key.why_not[Treatment.MITIGATE_COMPENSATE]
    assert Treatment.TRANSFER not in SCENARIO.answer_key.findings["F2"].why_not
    assert debrief.rows[1].why_not is None
    assert debrief_for(EXPERT_ANSWERS).rows[0].why_not is None


def test_r8_learner_rationale_echoed_in_response() -> None:
    text = submit(client(), {**EXPERT_ANSWERS, "F1.rationale": "Patch tonight, it is cheap."}).text
    assert "Patch tonight, it is cheap." in text


def test_r8_result_response_is_no_store() -> None:
    test_client = client()
    assert submit(test_client).headers["cache-control"] == "no-store"
    invalid = submit(test_client, {**EXPERT_ANSWERS, "F1.treatment": "nope"})
    assert invalid.status_code == 422
    assert invalid.headers["cache-control"] == "no-store"
