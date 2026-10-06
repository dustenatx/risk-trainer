"""Per-session submission counter (PRD R13).

Counts POST submissions per session per clock minute. It's a courtesy limit: a new session
starts a new count. The abuse backstops are the WAF per-IP rule and Lambda reserved concurrency.

DynamoDB item: pk=RL#<session_id>#<epoch minute>, sk=RL, counter n, TTL expires_at. One
UpdateItem per submission (1 WCU), in the same table as the attempts.
"""

from collections import Counter
from datetime import datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING, Protocol

from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient

WINDOW = timedelta(minutes=1)
# Keep the item a little past its window; DynamoDB deletes expired items within a few days.
RATE_LIMIT_TTL = timedelta(minutes=2)


class RateLimitUnavailable(Exception):
    """The counter couldn't be read or written. Callers let the request through."""


def window_start(now: datetime) -> int:
    """The current one-minute window, as Unix epoch minutes."""
    return int(now.timestamp()) // 60


class RateLimiter(Protocol):
    def hit(self, session_id: str, now: datetime) -> int:
        """Count one submission in the current window and return the window's total."""
        ...


class MemoryRateLimiter:
    """For `rt preview` and tests. Never used in Lambda."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: Counter[tuple[str, int]] = Counter()

    def hit(self, session_id: str, now: datetime) -> int:
        current = window_start(now)
        with self._lock:
            for key in [key for key in self._counts if key[1] < current]:
                del self._counts[key]
            self._counts[(session_id, current)] += 1
            return self._counts[(session_id, current)]


class DynamoRateLimiter:
    def __init__(self, client: DynamoDBClient, table: str) -> None:
        self._client = client
        self._table = table

    def hit(self, session_id: str, now: datetime) -> int:
        current = window_start(now)
        try:
            response = self._client.update_item(
                TableName=self._table,
                Key={"pk": {"S": f"RL#{session_id}#{current}"}, "sk": {"S": "RL"}},
                UpdateExpression="ADD n :one SET expires_at = if_not_exists(expires_at, :exp)",
                ExpressionAttributeValues={
                    ":one": {"N": "1"},
                    ":exp": {"N": str(int((now + RATE_LIMIT_TTL).timestamp()))},
                },
                ReturnValues="UPDATED_NEW",
            )
        except (ClientError, BotoCoreError) as exc:
            raise RateLimitUnavailable("could not update the submission counter") from exc
        return int(response["Attributes"]["n"]["N"])
