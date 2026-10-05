"""Scenario validation (PRD R1): structural parse plus cross-field content rules."""

import re
from collections import Counter
from collections.abc import Iterator

from pydantic import ValidationError

from risk_trainer.domain.errors import ContentError, ScenarioInvalid
from risk_trainer.domain.models import Difficulty, Scenario, Status
from risk_trainer.domain.treatments import RESPONSE_OF, Approver, Treatment

MIN_RESPONSES_COVERED = 3
EXPERT_RATIONALE_MAX_WORDS = 120
FICTIONAL_SUFFIX = "(fictional)"
CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)


def format_path(loc: tuple[int | str, ...]) -> str:
    """Render a Pydantic error location as `findings[2].signals.cvss_base`."""
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else part
    return path or "(root)"


def parse_scenario(data: object) -> Scenario:
    """Validate parsed YAML data; raise ScenarioInvalid listing every error."""
    if not isinstance(data, dict):
        raise ScenarioInvalid([ContentError("(root)", "a scenario must be a YAML mapping")])
    try:
        scenario = Scenario.model_validate(data)
    except ValidationError as exc:
        raise ScenarioInvalid(
            [ContentError(format_path(err["loc"]), err["msg"]) for err in exc.errors()]
        ) from None
    errors = check_rules(scenario)
    if errors:
        raise ScenarioInvalid(errors)
    return scenario


def check_rules(scenario: Scenario) -> list[ContentError]:
    errors: list[ContentError] = []
    errors += _finding_ids(scenario)
    errors += _answer_key_entries(scenario)
    errors += _responses_covered(scenario)
    errors += _remediation_capacity(scenario)
    errors += _tips(scenario)
    errors += _approval_fields(scenario)
    errors += _organization(scenario)
    errors += _cissp_domains(scenario)
    errors += _cve_ids(scenario)
    return errors


def _finding_ids(scenario: Scenario) -> list[ContentError]:
    counts = Counter(finding.id for finding in scenario.findings)
    return [
        ContentError(f"findings[{index}].id", f"duplicate finding ID {finding.id}")
        for index, finding in enumerate(scenario.findings)
        if counts[finding.id] > 1
    ]


def _answer_key_entries(scenario: Scenario) -> list[ContentError]:
    errors: list[ContentError] = []
    finding_ids: set[str] = {finding.id for finding in scenario.findings}
    key = scenario.answer_key.findings
    for missing in sorted(finding_ids - key.keys()):
        errors.append(
            ContentError("answer_key.findings", f"missing an answer-key entry for {missing}")
        )
    for extra in sorted(key.keys() - finding_ids):
        errors.append(ContentError(f"answer_key.findings.{extra}", "no finding has this ID"))

    for finding_id, entry in key.items():
        base = f"answer_key.findings.{finding_id}"
        if entry.preferred not in entry.acceptable:
            errors.append(
                ContentError(
                    f"{base}.acceptable",
                    f"must include the preferred treatment '{entry.preferred}'",
                )
            )
        allows_accept = Treatment.ACCEPT in (entry.preferred, *entry.acceptable)
        approvers = entry.approvers
        if allows_accept and (approvers is None or not approvers.correct):
            errors.append(
                ContentError(
                    f"{base}.approvers.correct",
                    "accept is preferred or acceptable, so at least one correct approver "
                    "is required",
                )
            )
        if not allows_accept and approvers is not None:
            errors.append(
                ContentError(
                    f"{base}.approvers",
                    "only allowed when accept is the preferred or an acceptable treatment",
                )
            )
        if approvers is not None:
            for field, values in (
                ("correct", approvers.correct),
                ("acceptable", approvers.acceptable),
            ):
                if Approver.SECURITY_TEAM in values:
                    errors.append(
                        ContentError(
                            f"{base}.approvers.{field}",
                            "security_team can't approve: security advises on risk "
                            "but never accepts it",
                        )
                    )
            overlap = sorted(set(approvers.correct) & set(approvers.acceptable))
            if overlap:
                errors.append(
                    ContentError(
                        f"{base}.approvers.acceptable",
                        f"already listed as correct: {', '.join(overlap)}",
                    )
                )
        words = len(entry.expert_rationale.split())
        if words > EXPERT_RATIONALE_MAX_WORDS:
            errors.append(
                ContentError(
                    f"{base}.expert_rationale",
                    f"{words} words; the limit is {EXPERT_RATIONALE_MAX_WORDS}",
                )
            )
    return errors


def _responses_covered(scenario: Scenario) -> list[ContentError]:
    covered = {RESPONSE_OF[entry.preferred] for entry in scenario.answer_key.findings.values()}
    if len(covered) >= MIN_RESPONSES_COVERED:
        return []
    names = ", ".join(sorted(covered)) or "none"
    return [
        ContentError(
            "answer_key.findings",
            f"preferred treatments must cover at least {MIN_RESPONSES_COVERED} of avoid, "
            f"mitigate, transfer and accept; they cover {names}",
        )
    ]


def _remediation_capacity(scenario: Scenario) -> list[ContentError]:
    slots = scenario.context.capacity.remediation_slots
    remediated = sorted(
        finding_id
        for finding_id, entry in scenario.answer_key.findings.items()
        if entry.preferred is Treatment.MITIGATE_REMEDIATE
    )
    if len(remediated) <= slots:
        return []
    return [
        ContentError(
            "answer_key.findings",
            f"{len(remediated)} findings prefer mitigate_remediate ({', '.join(remediated)}) "
            f"but context.capacity.remediation_slots is {slots}",
        )
    ]


def _tips(scenario: Scenario) -> list[ContentError]:
    key = scenario.answer_key
    if scenario.difficulty is Difficulty.FOUNDATIONAL and key.job_tip is None:
        return [ContentError("answer_key.job_tip", "required for foundational scenarios")]
    if scenario.difficulty is not Difficulty.FOUNDATIONAL and key.exam_tip is None:
        return [
            ContentError("answer_key.exam_tip", "required for intermediate and advanced scenarios")
        ]
    return []


def _approval_fields(scenario: Scenario) -> list[ContentError]:
    if scenario.status is not Status.APPROVED:
        return []
    return [
        ContentError(field, "required when status is approved")
        for field, value in (
            ("reviewed_by", scenario.reviewed_by),
            ("reviewed_on", scenario.reviewed_on),
        )
        if value is None
    ]


def _organization(scenario: Scenario) -> list[ContentError]:
    if scenario.context.organization.rstrip().endswith(FICTIONAL_SUFFIX):
        return []
    return [ContentError("context.organization", f'must end with "{FICTIONAL_SUFFIX}"')]


def _cissp_domains(scenario: Scenario) -> list[ContentError]:
    if len(set(scenario.cissp_domains)) == len(scenario.cissp_domains):
        return []
    return [ContentError("cissp_domains", "each domain may appear only once")]


def _cve_ids(scenario: Scenario) -> list[ContentError]:
    return [
        ContentError(path, "contains a CVE ID; use no real CVE identifiers")
        for path, text in _strings(scenario.model_dump(mode="json"), ())
        if CVE_PATTERN.search(text)
    ]


def _strings(value: object, loc: tuple[int | str, ...]) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield format_path(loc), value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, (*loc, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, (*loc, index))
