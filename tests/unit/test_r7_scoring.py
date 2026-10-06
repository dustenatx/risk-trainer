"""R7 — deterministic scoring (PRD section 7)."""

import pytest

from risk_trainer.domain.scoring import score, score_answer
from risk_trainer.domain.submission import Answer, Submission, parse_submission
from risk_trainer.domain.treatments import Approver, Treatment
from tests.web_helpers import EXPERT_ANSWERS, rt001

SCENARIO = rt001()
KEYS = SCENARIO.answer_key.findings


def answer(
    fid: str, treatment: Treatment, approver: Approver | None = None, text: str = ""
) -> Answer:
    return Answer(fid, treatment, approver, text)


def test_r7_preferred_scores_two() -> None:
    assert score_answer(KEYS["F2"], answer("F2", Treatment.MITIGATE_COMPENSATE)) == 2


def test_r7_acceptable_scores_one() -> None:
    assert score_answer(KEYS["F2"], answer("F2", Treatment.AVOID)) == 1


def test_r7_other_scores_zero() -> None:
    assert score_answer(KEYS["F2"], answer("F2", Treatment.TRANSFER)) == 0


@pytest.mark.parametrize(
    ("approver", "points"),
    [
        (Approver.BUSINESS_RISK_OWNER, 2),  # correct: no change
        (Approver.SENIOR_MANAGEMENT, 1),  # acceptable: -1
        (Approver.SECURITY_TEAM, 0),  # anything else: 0
        (Approver.IT_OPERATIONS, 0),
    ],
)
def test_r7_accept_points_depend_on_approver(approver: Approver, points: int) -> None:
    assert score_answer(KEYS["F5"], answer("F5", Treatment.ACCEPT, approver)) == points


def test_r7_acceptable_approver_floor_is_zero() -> None:
    # Make accept merely acceptable (1 point); an acceptable approver then takes it to 0.
    key = KEYS["F5"].model_copy(update={"preferred": Treatment.MITIGATE_COMPENSATE})
    assert score_answer(key, answer("F5", Treatment.ACCEPT, Approver.SENIOR_MANAGEMENT)) == 0


def test_r7_total_max_and_percent() -> None:
    submission = parse_submission(SCENARIO, EXPERT_ANSWERS.items())
    result = score(SCENARIO, submission)
    assert (result.total, result.maximum, result.percent) == (10, 10, 100)


def test_r7_same_inputs_same_score() -> None:
    submission = parse_submission(SCENARIO, EXPERT_ANSWERS.items())
    assert score(SCENARIO, submission) == score(SCENARIO, submission)


def test_r7_score_ignores_rationale_text() -> None:
    a = parse_submission(SCENARIO, EXPERT_ANSWERS.items())
    other = {
        **EXPERT_ANSWERS,
        "F5.rationale": "Entirely different words here.",
        "F1.rationale": "x",
    }
    b = parse_submission(SCENARIO, other.items())
    assert score(SCENARIO, a) == score(SCENARIO, b)


def test_r7_percent_rounds_to_whole_number() -> None:
    answers = {**EXPERT_ANSWERS, "F2.treatment": "avoid"}
    result = score(SCENARIO, parse_submission(SCENARIO, answers.items()))
    assert (result.total, result.percent) == (9, 90)


def test_r7_submission_answer_for_unknown_raises() -> None:
    with pytest.raises(KeyError):
        Submission(answers=(), note="").answer_for("F1")
