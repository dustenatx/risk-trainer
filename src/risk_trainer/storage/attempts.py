"""Attempt records and the store interface (PRD R9).

A record holds structured choices only: no rationale text, overall note, IP address or user
agent. Raw attempts carry a TTL; aggregate counters persist. Nothing in v1 reads raw attempts
back. Any read added later must drop expired records with `not_expired`, because DynamoDB
deletes expired items on its own schedule (typically within a few days).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from risk_trainer.domain.treatments import Approver, Treatment

ATTEMPT_TTL = timedelta(days=180)


@dataclass(frozen=True, slots=True)
class Choice:
    finding_id: str
    treatment: Treatment
    approver: Approver | None


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    submit_id: str
    scenario_id: str
    scenario_version: int
    choices: tuple[Choice, ...]
    score: int
    max_score: int
    submitted_at: datetime


@dataclass(frozen=True, slots=True)
class PeerCounts:
    attempts: int
    counters: dict[str, int]


class StorageError(Exception):
    """The attempt store could not be reached or rejected the request."""


def expires_at(submitted_at: datetime) -> int:
    """TTL value: submission time plus 180 days, in Unix epoch seconds."""
    return int((submitted_at + ATTEMPT_TTL).timestamp())


def not_expired(expires: int, now: datetime | None = None) -> bool:
    """True while a raw attempt is inside its retention window."""
    current = now or datetime.now(UTC)
    return expires > int(current.timestamp())


class AttemptStore(Protocol):
    def record(self, attempt: AttemptRecord) -> bool:
        """Store the attempt and bump the aggregates. False if submit_id was already recorded."""
        ...

    def peer_counts(self, scenario_id: str, version: int) -> PeerCounts:
        """Aggregate counters for one scenario version."""
        ...
