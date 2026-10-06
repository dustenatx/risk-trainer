"""DynamoDB attempt store (PRD R9). One table keyed by pk/sk.

- Attempt: pk=ATTEMPT#<submit_id>, sk=ATTEMPT, with expires_at (TTL, epoch seconds).
- Aggregate: pk=AGG#<scenario_id>#v<version>, sk=AGG, with counters n and F1#avoid etc.

Each submission is one transaction: a conditional Put of the attempt (so a resubmitted form
isn't counted twice) and an ADD to the aggregate counters.
"""

from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from risk_trainer.domain.peers import counter_name
from risk_trainer.storage.attempts import (
    AttemptRecord,
    PeerCounts,
    StorageError,
    expires_at,
)

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.client import DynamoDBClient

ATTEMPTS_COUNTER = "n"
CLIENT_CONFIG = Config(
    connect_timeout=2,
    read_timeout=3,
    retries={"total_max_attempts": 3, "mode": "standard"},
)


def make_client(region: str | None) -> DynamoDBClient:
    return boto3.client("dynamodb", region_name=region, config=CLIENT_CONFIG)


def aggregate_pk(scenario_id: str, version: int) -> str:
    return f"AGG#{scenario_id}#v{version}"


class DynamoAttemptStore:
    def __init__(self, client: DynamoDBClient, table: str) -> None:
        self._client = client
        self._table = table

    def record(self, attempt: AttemptRecord) -> bool:
        choices: dict[str, Any] = {}
        for choice in attempt.choices:
            entry: dict[str, Any] = {"treatment": {"S": choice.treatment.value}}
            if choice.approver is not None:
                entry["approver"] = {"S": choice.approver.value}
            choices[choice.finding_id] = {"M": entry}

        counters = [ATTEMPTS_COUNTER] + [
            counter_name(c.finding_id, c.treatment) for c in attempt.choices
        ]
        names = {f"#c{i}": name for i, name in enumerate(counters)}
        update = "ADD " + ", ".join(f"{placeholder} :one" for placeholder in names)
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table,
                            "Item": {
                                "pk": {"S": f"ATTEMPT#{attempt.submit_id}"},
                                "sk": {"S": "ATTEMPT"},
                                "scenario_id": {"S": attempt.scenario_id},
                                "scenario_version": {"N": str(attempt.scenario_version)},
                                "choices": {"M": choices},
                                "score": {"N": str(attempt.score)},
                                "max_score": {"N": str(attempt.max_score)},
                                "submitted_at": {"S": attempt.submitted_at.isoformat()},
                                "expires_at": {"N": str(expires_at(attempt.submitted_at))},
                            },
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table,
                            "Key": {
                                "pk": {
                                    "S": aggregate_pk(attempt.scenario_id, attempt.scenario_version)
                                },
                                "sk": {"S": "AGG"},
                            },
                            "UpdateExpression": update,
                            "ExpressionAttributeNames": names,
                            "ExpressionAttributeValues": {":one": {"N": "1"}},
                        }
                    },
                ]
            )
        except ClientError as exc:
            if _is_duplicate(exc):
                return False
            raise StorageError("could not record the attempt") from exc
        except BotoCoreError as exc:
            raise StorageError("could not record the attempt") from exc
        return True

    def peer_counts(self, scenario_id: str, version: int) -> PeerCounts:
        try:
            response = self._client.get_item(
                TableName=self._table,
                Key={"pk": {"S": aggregate_pk(scenario_id, version)}, "sk": {"S": "AGG"}},
                ConsistentRead=False,
            )
        except (ClientError, BotoCoreError) as exc:
            raise StorageError("could not read peer counts") from exc
        item = response.get("Item", {})
        counters = {
            name: int(value["N"])
            for name, value in item.items()
            if name not in ("pk", "sk") and "N" in value
        }
        attempts = counters.pop(ATTEMPTS_COUNTER, 0)
        return PeerCounts(attempts, counters)


def _is_duplicate(exc: ClientError) -> bool:
    if exc.response.get("Error", {}).get("Code") != "TransactionCanceledException":
        return False
    reasons: list[dict[str, Any]] = exc.response.get("CancellationReasons", [])  # type: ignore[assignment]
    return bool(reasons) and reasons[0].get("Code") == "ConditionalCheckFailed"
