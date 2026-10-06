"""Peer distribution: how other learners answered each finding (PRD R9)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from risk_trainer.domain.treatments import Treatment

DEFAULT_PEER_MIN_SAMPLE = 10


@dataclass(frozen=True, slots=True)
class PeerDistribution:
    attempts: int
    # finding ID -> treatment -> whole percent of attempts
    percents: Mapping[str, Mapping[Treatment, int]]


def counter_name(finding_id: str, treatment: Treatment) -> str:
    """Name of the aggregate counter for one finding and treatment, e.g. "F1#avoid"."""
    return f"{finding_id}#{treatment.value}"


def distribution(
    attempts: int,
    counters: Mapping[str, int],
    finding_ids: Sequence[str],
    min_sample: int,
) -> PeerDistribution | None:
    """Percentages per finding and treatment, or None below the minimum sample."""
    if attempts < max(min_sample, 1):
        return None
    percents = {
        fid: {t: round(counters.get(counter_name(fid, t), 0) * 100 / attempts) for t in Treatment}
        for fid in finding_ids
    }
    return PeerDistribution(attempts=attempts, percents=percents)
