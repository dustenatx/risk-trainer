"""R13 — per-session submission limit: POSTs only, 429 above the limit, fails open."""

import logging
from datetime import UTC, datetime, timedelta

import pytest

from risk_trainer.storage.memory import MemoryAttemptStore
from risk_trainer.storage.rate_limits import MemoryRateLimiter, RateLimitUnavailable
from tests.web_helpers import RT001_ID, client, settings, submit

FIXED = datetime(2026, 10, 6, 12, 0, 30, tzinfo=UTC)


class FrozenLimiter:
    """MemoryRateLimiter pinned to one minute, so tests never straddle a window boundary."""

    def __init__(self) -> None:
        self.inner = MemoryRateLimiter()
        self.sessions: list[str] = []

    def hit(self, session_id: str, now: datetime) -> int:
        self.sessions.append(session_id)
        return self.inner.hit(session_id, FIXED)


class BrokenLimiter:
    def hit(self, session_id: str, now: datetime) -> int:
        raise RateLimitUnavailable("throttled")


def test_r13_default_limit_is_60() -> None:
    assert settings().requests_per_session_per_minute == 60


def test_r13_61st_submission_in_a_minute_gets_429() -> None:
    store = MemoryAttemptStore()
    test_client = client(store=store, rate_limiter=FrozenLimiter())
    for _ in range(60):
        assert submit(test_client).status_code == 200
    response = submit(test_client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert "Too many submissions" in response.text
    assert store.peer_counts(RT001_ID, 1).attempts == 60, "the refused submission isn't recorded"


def test_r13_limit_is_configurable() -> None:
    test_client = client(rate_limiter=FrozenLimiter(), requests_per_session_per_minute=2)
    assert [submit(test_client).status_code for _ in range(3)] == [200, 200, 429]


def test_r13_gets_are_never_counted() -> None:
    limiter = FrozenLimiter()
    test_client = client(rate_limiter=limiter, requests_per_session_per_minute=1)
    for path in ["/", f"/s/{RT001_ID}", "/about", "/static/app.css"] * 25:
        assert test_client.get(path).status_code == 200
    assert limiter.sessions == []
    assert submit(test_client).status_code == 200


def test_r13_rejected_csrf_is_not_counted() -> None:
    limiter = FrozenLimiter()
    test_client = client(rate_limiter=limiter)
    test_client.get(f"/s/{RT001_ID}")
    assert test_client.post(f"/s/{RT001_ID}", data={"csrf_token": "forged"}).status_code == 403
    assert limiter.sessions == []


def test_r13_new_session_starts_a_new_count() -> None:
    limiter = FrozenLimiter()
    first = client(rate_limiter=limiter, requests_per_session_per_minute=1)
    assert [submit(first).status_code for _ in range(2)] == [200, 429]
    first.cookies.clear()
    assert submit(first).status_code == 200
    assert len(set(limiter.sessions)) == 2


def test_r13_counter_failure_lets_the_submission_through(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = MemoryAttemptStore()
    test_client = client(store=store, rate_limiter=BrokenLimiter())
    logger = logging.getLogger("risk_trainer.web.exercise")
    logger.addHandler(caplog.handler)
    try:
        response = submit(test_client)
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 200
    assert store.peer_counts(RT001_ID, 1).attempts == 1
    assert any(getattr(r, "event", None) == "rate_limit_unavailable" for r in caplog.records)


def test_r13_memory_limiter_windows_and_sessions() -> None:
    limiter = MemoryRateLimiter()
    assert [limiter.hit("a", FIXED) for _ in range(3)] == [1, 2, 3]
    assert limiter.hit("b", FIXED) == 1
    assert limiter.hit("a", FIXED + timedelta(seconds=29)) == 4, "same clock minute"
    assert limiter.hit("a", FIXED + timedelta(seconds=30)) == 1, "next clock minute"


def test_r13_limit_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUESTS_PER_SESSION_PER_MINUTE", "5")
    assert settings().requests_per_session_per_minute == 5
