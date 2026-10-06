"""The expert debrief shown after scoring (PRD R8)."""

from dataclasses import dataclass

from risk_trainer.domain.models import FindingKey, Scenario
from risk_trainer.domain.scoring import PREFERRED_POINTS, ScoreResult
from risk_trainer.domain.submission import Answer, Submission
from risk_trainer.domain.treatments import APPROVER_LABELS, Approver, Treatment

# Why the learner's chosen approver isn't the best fit. Phrased as what's typical under an
# organization's governance, not as absolute rules.
APPROVER_WHY: dict[str, str] = {
    Approver.SECURITY_TEAM: (
        "Security typically advises on risk rather than accepting it. The security team's job "
        "is to make the risk clear so the person who owns it can make an informed decision."
    ),
    Approver.IT_OPERATIONS: (
        "IT operations typically runs the system but doesn't own the business risk it carries. "
        "Acceptance usually sits with whoever owns the affected asset or process."
    ),
    Approver.BUSINESS_RISK_OWNER: (
        "Under most organizations' governance, a risk of this size typically goes beyond what "
        "a single business owner accepts on their own, so it usually goes to executive "
        "leadership or the risk committee."
    ),
    Approver.SENIOR_MANAGEMENT: (
        "Executive leadership typically delegates a risk like this to the business owner of "
        "the affected asset or process, who is closest to the trade-off."
    ),
    "senior_management_acceptable": (
        "Executive leadership can accept this risk, but the business owner typically already "
        "has the authority for it under the organization's governance, so it doesn't need to "
        "go higher."
    ),
}


@dataclass(frozen=True, slots=True)
class DebriefRow:
    finding_id: str
    title: str
    learner_treatment: Treatment
    learner_approver: Approver | None
    learner_rationale: str
    expert_treatment: Treatment
    points: int
    max_points: int
    expert_rationale: str
    key_considerations: tuple[str, ...]
    why_not: str | None
    approver_feedback: str | None


@dataclass(frozen=True, slots=True)
class Debrief:
    rows: tuple[DebriefRow, ...]
    total: int
    maximum: int
    percent: int
    overall_debrief: str
    common_traps: tuple[str, ...]
    job_tip: str | None
    exam_tip: str | None
    note: str


def approver_feedback(key: FindingKey, answer: Answer) -> str | None:
    """Who should approve and why, when the learner accepted with an approver that isn't correct."""
    approvers = key.approvers
    if answer.treatment is not Treatment.ACCEPT or answer.approver is None or approvers is None:
        return None
    if not approvers.correct or answer.approver in approvers.correct:
        return None
    who = " or ".join(APPROVER_LABELS[a] for a in approvers.correct)
    reason_key: str = answer.approver
    if answer.approver is Approver.SENIOR_MANAGEMENT and answer.approver in approvers.acceptable:
        reason_key = "senior_management_acceptable"
    return f"Who should approve: {who}. {APPROVER_WHY[reason_key]}"


def build_debrief(scenario: Scenario, submission: Submission, result: ScoreResult) -> Debrief:
    rows: list[DebriefRow] = []
    for finding in scenario.findings:
        key = scenario.answer_key.findings[finding.id]
        answer = submission.answer_for(finding.id)
        why_not = None
        if answer.treatment is not key.preferred:
            why_not = key.why_not.get(answer.treatment)
        rows.append(
            DebriefRow(
                finding_id=finding.id,
                title=finding.title,
                learner_treatment=answer.treatment,
                learner_approver=answer.approver,
                learner_rationale=answer.rationale,
                expert_treatment=key.preferred,
                points=result.points_for(finding.id),
                max_points=PREFERRED_POINTS,
                expert_rationale=key.expert_rationale,
                key_considerations=tuple(key.key_considerations),
                why_not=why_not,
                approver_feedback=approver_feedback(key, answer),
            )
        )
    answer_key = scenario.answer_key
    return Debrief(
        rows=tuple(rows),
        total=result.total,
        maximum=result.maximum,
        percent=result.percent,
        overall_debrief=answer_key.overall_debrief,
        common_traps=tuple(answer_key.common_traps),
        job_tip=answer_key.job_tip,
        exam_tip=answer_key.exam_tip,
        note=submission.note,
    )
