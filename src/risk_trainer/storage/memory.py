"""In-memory attempt store for `rt preview` and end-to-end tests. Never used in Lambda."""

from collections import Counter, defaultdict
from threading import Lock

from risk_trainer.domain.peers import counter_name
from risk_trainer.storage.attempts import AttemptRecord, PeerCounts


class MemoryAttemptStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._submit_ids: set[str] = set()
        self._attempts: Counter[tuple[str, int]] = Counter()
        self._counters: defaultdict[tuple[str, int], Counter[str]] = defaultdict(Counter)

    def record(self, attempt: AttemptRecord) -> bool:
        key = (attempt.scenario_id, attempt.scenario_version)
        with self._lock:
            if attempt.submit_id in self._submit_ids:
                return False
            self._submit_ids.add(attempt.submit_id)
            self._attempts[key] += 1
            for choice in attempt.choices:
                self._counters[key][counter_name(choice.finding_id, choice.treatment)] += 1
        return True

    def peer_counts(self, scenario_id: str, version: int) -> PeerCounts:
        key = (scenario_id, version)
        with self._lock:
            return PeerCounts(self._attempts[key], dict(self._counters[key]))
