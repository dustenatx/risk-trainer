"""Risk treatments and acceptance approvers (PRD sections 4.1 and 4.2)."""

from enum import StrEnum


class Treatment(StrEnum):
    AVOID = "avoid"
    MITIGATE_REMEDIATE = "mitigate_remediate"
    MITIGATE_COMPENSATE = "mitigate_compensate"
    TRANSFER = "transfer"
    ACCEPT = "accept"


class Response(StrEnum):
    """The four CISSP risk responses. Both mitigate treatments map to MITIGATE."""

    AVOID = "avoid"
    MITIGATE = "mitigate"
    TRANSFER = "transfer"
    ACCEPT = "accept"


class Approver(StrEnum):
    SECURITY_TEAM = "security_team"
    IT_OPERATIONS = "it_operations"
    BUSINESS_RISK_OWNER = "business_risk_owner"
    SENIOR_MANAGEMENT = "senior_management"


TREATMENT_LABELS: dict[Treatment, str] = {
    Treatment.AVOID: "Avoid — stop the activity",
    Treatment.MITIGATE_REMEDIATE: 'Mitigate: remediate ("fix")',
    Treatment.MITIGATE_COMPENSATE: 'Mitigate: compensating control ("reduce")',
    Treatment.TRANSFER: "Transfer / share",
    Treatment.ACCEPT: "Accept",
}

RESPONSE_OF: dict[Treatment, Response] = {
    Treatment.AVOID: Response.AVOID,
    Treatment.MITIGATE_REMEDIATE: Response.MITIGATE,
    Treatment.MITIGATE_COMPENSATE: Response.MITIGATE,
    Treatment.TRANSFER: Response.TRANSFER,
    Treatment.ACCEPT: Response.ACCEPT,
}

APPROVER_LABELS: dict[Approver, str] = {
    Approver.SECURITY_TEAM: "Security team",
    Approver.IT_OPERATIONS: "IT operations (runs the system)",
    Approver.BUSINESS_RISK_OWNER: "Business owner of the affected asset or process",
    Approver.SENIOR_MANAGEMENT: "Executive leadership / risk committee",
}
