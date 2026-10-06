"""R13 — the per-session submission counter in DynamoDB (moto)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from risk_trainer.storage.dynamodb import make_client
from risk_trainer.storage.rate_limits import DynamoRateLimiter, RateLimitUnavailable
from tests.integration.conftest import REGION, TABLE

NOW = datetime(2026, 10, 6, 12, 0, 30, tzinfo=UTC)


def test_r13_counts_per_session_per_minute(dynamo: Any) -> None:
    limiter = DynamoRateLimiter(make_client(REGION), TABLE)
    assert [limiter.hit("sid-a", NOW) for _ in range(3)] == [1, 2, 3]
    assert limiter.hit("sid-b", NOW) == 1
    assert limiter.hit("sid-a", NOW + timedelta(seconds=30)) == 1


def test_r13_counter_item_has_ttl_and_no_other_data(dynamo: Any) -> None:
    DynamoRateLimiter(make_client(REGION), TABLE).hit("sid-a", NOW)
    DynamoRateLimiter(make_client(REGION), TABLE).hit("sid-a", NOW + timedelta(seconds=10))
    (item,) = dynamo.scan(TableName=TABLE)["Items"]
    assert item["pk"] == {"S": f"RL#sid-a#{int(NOW.timestamp()) // 60}"}
    assert item["sk"] == {"S": "RL"}
    assert item["n"] == {"N": "2"}
    assert item["expires_at"] == {"N": str(int(NOW.timestamp()) + 120)}, "set once, not extended"
    assert set(item) == {"pk", "sk", "n", "expires_at"}


def test_r13_missing_table_raises_unavailable(dynamo: Any) -> None:
    limiter = DynamoRateLimiter(make_client(REGION), "no-such-table")
    with pytest.raises(RateLimitUnavailable):
        limiter.hit("sid-a", NOW)
