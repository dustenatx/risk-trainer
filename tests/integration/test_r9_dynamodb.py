"""R9 — attempt storage against DynamoDB (moto), plus the same contract for the memory store."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from risk_trainer.domain.treatments import Approver, Treatment
from risk_trainer.storage.attempts import AttemptRecord, AttemptStore, Choice, StorageError
from risk_trainer.storage.dynamodb import CLIENT_CONFIG, DynamoAttemptStore, make_client
from risk_trainer.storage.memory import MemoryAttemptStore

TABLE = "risk-trainer-test"
REGION = "us-east-1"
SUBMITTED = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.fixture
def dynamo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 1, "WriteCapacityUnits": 1},
        )
        yield client


@pytest.fixture(params=["memory", "dynamodb"])
def store(request: pytest.FixtureRequest) -> AttemptStore:
    if request.param == "memory":
        return MemoryAttemptStore()
    request.getfixturevalue("dynamo")
    return DynamoAttemptStore(make_client(REGION), TABLE)


def attempt(submit_id: str = "s" * 22, f5: Treatment = Treatment.ACCEPT) -> AttemptRecord:
    choices = [Choice(f"F{i}", Treatment.MITIGATE_REMEDIATE, None) for i in (1, 2)]
    choices += [Choice("F3", Treatment.TRANSFER, None), Choice("F4", Treatment.AVOID, None)]
    approver = Approver.BUSINESS_RISK_OWNER if f5 is Treatment.ACCEPT else None
    choices.append(Choice("F5", f5, approver))
    return AttemptRecord(
        submit_id=submit_id,
        scenario_id="rt-001-five-findings",
        scenario_version=1,
        choices=tuple(choices),
        score=7,
        max_score=10,
        submitted_at=SUBMITTED,
    )


def test_r9_contract_record_and_count(store: AttemptStore) -> None:
    assert store.record(attempt("a" * 22))
    assert store.record(attempt("b" * 22, f5=Treatment.MITIGATE_COMPENSATE))
    counts = store.peer_counts("rt-001-five-findings", 1)
    assert counts.attempts == 2
    assert counts.counters["F1#mitigate_remediate"] == 2
    assert counts.counters["F5#accept"] == 1
    assert counts.counters["F5#mitigate_compensate"] == 1


def test_r9_contract_duplicate_submit_id_not_counted(store: AttemptStore) -> None:
    assert store.record(attempt())
    assert not store.record(attempt())
    assert store.peer_counts("rt-001-five-findings", 1).attempts == 1


def test_r9_contract_counts_are_per_version(store: AttemptStore) -> None:
    store.record(attempt())
    assert store.peer_counts("rt-001-five-findings", 2).attempts == 0


def test_r9_stored_item_has_only_allowed_fields(dynamo: Any) -> None:
    DynamoAttemptStore(make_client(REGION), TABLE).record(attempt("z" * 22))
    item = dynamo.get_item(
        TableName=TABLE, Key={"pk": {"S": "ATTEMPT#" + "z" * 22}, "sk": {"S": "ATTEMPT"}}
    )["Item"]
    assert set(item) == {
        "pk",
        "sk",
        "scenario_id",
        "scenario_version",
        "choices",
        "score",
        "max_score",
        "submitted_at",
        "expires_at",
    }
    assert set(item["choices"]["M"]["F5"]["M"]) == {"treatment", "approver"}
    assert set(item["choices"]["M"]["F1"]["M"]) == {"treatment"}


def test_r9_ttl_attribute_is_number_epoch_seconds_plus_180_days(dynamo: Any) -> None:
    DynamoAttemptStore(make_client(REGION), TABLE).record(attempt("t" * 22))
    item = dynamo.get_item(
        TableName=TABLE, Key={"pk": {"S": "ATTEMPT#" + "t" * 22}, "sk": {"S": "ATTEMPT"}}
    )["Item"]
    expected = int(datetime(2027, 4, 4, 12, 0, tzinfo=UTC).timestamp())
    assert item["expires_at"] == {"N": str(expected)}


def test_r9_aggregate_item_has_no_ttl(dynamo: Any) -> None:
    DynamoAttemptStore(make_client(REGION), TABLE).record(attempt())
    item = dynamo.get_item(
        TableName=TABLE, Key={"pk": {"S": "AGG#rt-001-five-findings#v1"}, "sk": {"S": "AGG"}}
    )["Item"]
    assert "expires_at" not in item
    assert item["n"] == {"N": "1"}


def test_r9_missing_table_raises_storage_error(dynamo: Any) -> None:
    broken = DynamoAttemptStore(make_client(REGION), "no-such-table")
    with pytest.raises(StorageError):
        broken.record(attempt())
    with pytest.raises(StorageError):
        broken.peer_counts("rt-001-five-findings", 1)


def test_r9_boto3_client_sets_timeouts_and_retries() -> None:
    assert CLIENT_CONFIG.connect_timeout == 2
    assert CLIENT_CONFIG.read_timeout == 3
    assert CLIENT_CONFIG.retries == {"total_max_attempts": 3, "mode": "standard"}
