"""Deterministic scoring (PRD R7, section 7). Rationale text never affects the score."""

from dataclasses import dataclass

from risk_trainer.domain.models import FindingKey, Scenario
from risk_trainer.domain.submission import Answer, Submission
from risk_trainer.domain.treatments import Treatment

PREFERRED_POINTS = 2
ACCEPTABLE_POINTS = 1


@dataclass(frozen=True, slots=True)
class FindingScore:
    finding_id: str
    points: int


@dataclass(frozen=True, slots=True)
class ScoreResult:
    findings: tuple[FindingScore, ...]
    total: int
    maximum: int

    @property
    def percent(self) -> int:
        return round(self.total * 100 / self.maximum) if self.maximum else 0

    def points_for(self, finding_id: str) -> int:
        return next(f.points for f in self.findings if f.finding_id == finding_id)


def score_answer(key: FindingKey, answer: Answer) -> int:
    if answer.treatment is key.preferred:
        points = PREFERRED_POINTS
    elif answer.treatment in key.acceptable:
        points = ACCEPTABLE_POINTS
    else:
        points = 0
    if answer.treatment is Treatment.ACCEPT and points > 0:
        approvers = key.approvers
        if approvers is None or answer.approver not in approvers.correct:
            if approvers is not None and answer.approver in approvers.acceptable:
                points = max(points - 1, 0)
            else:
                points = 0
    return points


def score(scenario: Scenario, submission: Submission) -> ScoreResult:
    findings = tuple(
        FindingScore(
            finding.id,
            score_answer(
                scenario.answer_key.findings[finding.id], submission.answer_for(finding.id)
            ),
        )
        for finding in scenario.findings
    )
    return ScoreResult(
        findings=findings,
        total=sum(f.points for f in findings),
        maximum=PREFERRED_POINTS * len(scenario.findings),
    )
