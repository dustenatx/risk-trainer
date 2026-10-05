"""Scenario model (PRD R1, Appendix A). Field rules here; cross-field rules in rules.py."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
)

from risk_trainer.domain.treatments import Approver, Treatment

SCENARIO_ID_PATTERN = r"^rt-[0-9]{3}-[a-z0-9]+(-[a-z0-9]+)*$"
SCENARIO_ID_MAX_LENGTH = 64
FINDING_IDS: tuple[str, ...] = ("F1", "F2", "F3", "F4", "F5")
DEFAULT_REMEDIATION_SLOTS = 2


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


Text = Annotated[StrictStr, AfterValidator(_not_blank)]
ScenarioId = Annotated[
    StrictStr,
    StringConstraints(pattern=SCENARIO_ID_PATTERN, max_length=SCENARIO_ID_MAX_LENGTH),
]
FindingId = Literal["F1", "F2", "F3", "F4", "F5"]
CisspDomain = Annotated[StrictInt, Field(ge=1, le=8)]


class Status(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RETIRED = "retired"


class Difficulty(StrEnum):
    FOUNDATIONAL = "foundational"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Exposure(StrEnum):
    INTERNET_FACING = "internet_facing"
    INTERNAL = "internal"
    SEGMENTED = "segmented"
    THIRD_PARTY = "third_party"
    PROCESS = "process"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Capacity(_Model):
    remediation_slots: Annotated[StrictInt, Field(ge=0)] = DEFAULT_REMEDIATION_SLOTS


class Context(_Model):
    organization: Text
    industry: Text
    size: Text
    risk_appetite: Text
    constraints: list[Text]
    capacity: Capacity


class Signals(_Model):
    cvss_base: Annotated[float, Field(ge=0.0, le=10.0, strict=True)] | None
    known_exploited: StrictBool
    data_involved: Text | None
    compensating_controls_available: list[Text]
    remediation_effort: Effort
    business_owner: Text


class Finding(_Model):
    id: FindingId
    title: Text
    description: Text
    asset: Text
    exposure: Exposure
    signals: Signals


class Approvers(_Model):
    correct: list[Approver] = Field(default_factory=list)
    acceptable: list[Approver] = Field(default_factory=list)


class FindingKey(_Model):
    preferred: Treatment
    acceptable: Annotated[list[Treatment], Field(min_length=1)]
    approvers: Approvers | None = None
    key_considerations: Annotated[list[Text], Field(min_length=2, max_length=4)]
    expert_rationale: Text
    why_not: dict[Treatment, Text] = Field(default_factory=dict)


class AnswerKey(_Model):
    findings: dict[StrictStr, FindingKey]
    overall_debrief: Text
    common_traps: list[Text]
    exam_tip: Text | None = None
    job_tip: Text | None = None


class Scenario(_Model):
    id: ScenarioId
    version: Annotated[StrictInt, Field(ge=1)]
    status: Status
    title: Text
    difficulty: Difficulty
    estimated_minutes: Annotated[StrictInt, Field(ge=1)]
    cissp_domains: Annotated[list[CisspDomain], Field(min_length=1)]
    learning_objectives: Annotated[list[Text], Field(min_length=1)]
    context: Context
    findings: Annotated[list[Finding], Field(min_length=5, max_length=5)]
    answer_key: AnswerKey
    reviewed_by: Text | None = None
    reviewed_on: date | None = None
