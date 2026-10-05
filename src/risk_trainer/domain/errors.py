"""Typed domain errors. Boundaries (CLI, routes, MCP tools) map these to plain messages."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContentError:
    """One problem in a scenario: a dotted field path and a plain-language message."""

    path: str
    message: str


class RiskTrainerError(Exception):
    """Base class for errors that are safe to show to the author or learner."""


class ScenarioInvalid(RiskTrainerError):
    def __init__(self, errors: Sequence[ContentError]) -> None:
        self.errors = list(errors)
        super().__init__(f"scenario is invalid ({len(self.errors)} error(s))")


class LifecycleError(RiskTrainerError):
    """An approve or retire request that can't be carried out."""
