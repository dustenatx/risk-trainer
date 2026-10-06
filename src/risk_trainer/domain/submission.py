"""A learner's answers and the rules they must meet (PRD R6, R7)."""

from collections.abc import Iterable
from dataclasses import dataclass

from risk_trainer.domain.errors import ContentError, SubmissionInvalid
from risk_trainer.domain.models import Scenario
from risk_trainer.domain.treatments import Approver, Treatment

ACCEPT_RATIONALE_MIN = 10
RATIONALE_MAX = 600
NOTE_MAX = 1200
MAX_BODY_BYTES = 32 * 1024

NOTE_FIELD = "note"
_PARTS = ("treatment", "approver", "rationale")


def field_name(finding_id: str, part: str) -> str:
    """Form field name for one part of a finding's answer, e.g. "F1.treatment"."""
    return f"{finding_id}.{part}"


@dataclass(frozen=True, slots=True)
class Answer:
    finding_id: str
    treatment: Treatment
    approver: Approver | None
    rationale: str


@dataclass(frozen=True, slots=True)
class Submission:
    answers: tuple[Answer, ...]
    note: str

    def answer_for(self, finding_id: str) -> Answer:
        for answer in self.answers:
            if answer.finding_id == finding_id:
                return answer
        raise KeyError(finding_id)


def parse_submission(scenario: Scenario, items: Iterable[tuple[str, str]]) -> Submission:
    """Build a Submission from form fields. Raises SubmissionInvalid listing every problem."""
    finding_ids = [finding.id for finding in scenario.findings]
    allowed = {field_name(fid, part) for fid in finding_ids for part in _PARTS} | {NOTE_FIELD}
    errors: list[ContentError] = []
    values: dict[str, str] = {}
    for name, value in items:
        if name not in allowed:
            prefix = name.split(".", 1)[0]
            if "." in name and prefix not in finding_ids:
                errors.append(ContentError(prefix, f"{prefix} is not a finding in this scenario."))
            else:
                errors.append(ContentError(name, "This field isn't part of the form."))
        elif name in values:
            errors.append(ContentError(name, "This field was sent more than once."))
        else:
            values[name] = value

    answers: list[Answer] = []
    for fid in finding_ids:
        answer = _parse_answer(fid, values, errors)
        if answer is not None:
            answers.append(answer)

    note = values.get(NOTE_FIELD, "").strip()
    if len(note) > NOTE_MAX:
        errors.append(
            ContentError(NOTE_FIELD, f"Keep the overall note to {NOTE_MAX} characters or fewer.")
        )

    slots = scenario.context.capacity.remediation_slots
    remediated = [a.finding_id for a in answers if a.treatment is Treatment.MITIGATE_REMEDIATE]
    if len(remediated) > slots:
        errors.append(
            ContentError(
                "form",
                f"You chose to remediate {len(remediated)} findings, but the team has capacity "
                f"for {slots}. Pick another response for at least {len(remediated) - slots}.",
            )
        )

    if errors:
        raise SubmissionInvalid(errors)
    return Submission(answers=tuple(answers), note=note)


def _parse_answer(fid: str, values: dict[str, str], errors: list[ContentError]) -> Answer | None:
    raw_treatment = values.get(field_name(fid, "treatment"), "")
    rationale = values.get(field_name(fid, "rationale"), "").strip()
    if not raw_treatment:
        errors.append(ContentError(fid, f"Choose a response for {fid}."))
        return None
    try:
        treatment = Treatment(raw_treatment)
    except ValueError:
        errors.append(ContentError(fid, f"{fid}: choose one of the listed responses."))
        return None

    approver: Approver | None = None
    if treatment is Treatment.ACCEPT:
        raw_approver = values.get(field_name(fid, "approver"), "")
        try:
            approver = Approver(raw_approver)
        except ValueError:
            errors.append(ContentError(fid, f"{fid}: choose who approves accepting this risk."))
        if len(rationale) < ACCEPT_RATIONALE_MIN:
            errors.append(
                ContentError(
                    fid,
                    f"{fid}: accepting a risk needs a rationale of at least "
                    f"{ACCEPT_RATIONALE_MIN} characters.",
                )
            )
    if len(rationale) > RATIONALE_MAX:
        errors.append(
            ContentError(fid, f"{fid}: keep the rationale to {RATIONALE_MAX} characters or fewer.")
        )
    return Answer(finding_id=fid, treatment=treatment, approver=approver, rationale=rationale)
