"""R15 — custom metrics as CloudWatch EMF lines: attempts and 429s, within the free allowance."""

import json
from datetime import datetime
from typing import Any

import pytest

from risk_trainer.storage.rate_limits import RateLimitUnavailable
from risk_trainer.web.metrics import Metric, emf_line
from tests.web_helpers import EXPERT_ANSWERS, client, form_fields, submit

FREE_CUSTOM_METRICS = 10


class OverLimit:
    def hit(self, session_id: str, now: datetime) -> int:
        return 10_000


class Unavailable:
    def hit(self, session_id: str, now: datetime) -> int:
        raise RateLimitUnavailable("throttled")


def metric_lines(err: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in err.splitlines() if line.startswith('{"_aws"')]


def counts(err: str) -> dict[str, int]:
    found: dict[str, int] = {}
    for doc in metric_lines(err):
        for directive in doc["_aws"]["CloudWatchMetrics"]:
            for metric in directive["Metrics"]:
                found[metric["Name"]] = found.get(metric["Name"], 0) + doc[metric["Name"]]
    return found


def test_r15_emf_document_shape() -> None:
    doc = json.loads(emf_line("RiskTrainer", Metric.ATTEMPTS, now_ms=1_791_288_000_000))
    assert doc == {
        "_aws": {
            "Timestamp": 1_791_288_000_000,
            "CloudWatchMetrics": [
                {
                    "Namespace": "RiskTrainer",
                    "Dimensions": [[]],
                    "Metrics": [{"Name": "Attempts", "Unit": "Count"}],
                }
            ],
        },
        "Attempts": 1,
        "request_id": None,
    }


def test_r15_custom_metric_count_within_free_allowance() -> None:
    # No dimensions, so each name is exactly one custom metric.
    assert len(Metric) <= FREE_CUSTOM_METRICS
    assert {m.value for m in Metric} == {"Attempts", "RateLimited", "RateLimitUnavailable"}


def test_r15_attempt_metric_per_recorded_attempt(capsys: pytest.CaptureFixture[str]) -> None:
    test_client = client()
    submit(test_client)
    submit(test_client)  # a fresh form, so a second distinct attempt
    assert counts(capsys.readouterr().err) == {"Attempts": 2}


def test_r15_duplicate_submission_is_not_counted(capsys: pytest.CaptureFixture[str]) -> None:
    test_client = client()
    fields = form_fields(test_client.get("/s/rt-001-five-findings").text)
    for _ in range(2):
        response = test_client.post("/s/rt-001-five-findings", data={**fields, **EXPERT_ANSWERS})
        assert response.status_code == 200
    assert counts(capsys.readouterr().err) == {"Attempts": 1}


def test_r15_rate_limited_metric(capsys: pytest.CaptureFixture[str]) -> None:
    assert submit(client(rate_limiter=OverLimit())).status_code == 429
    assert counts(capsys.readouterr().err) == {"RateLimited": 1}


def test_r15_rate_limit_unavailable_metric(capsys: pytest.CaptureFixture[str]) -> None:
    assert submit(client(rate_limiter=Unavailable())).status_code == 200
    assert counts(capsys.readouterr().err) == {"RateLimitUnavailable": 1, "Attempts": 1}


def test_r15_metric_lines_are_bare_json_with_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = submit(client())
    docs = metric_lines(capsys.readouterr().err)
    assert len(docs) == 1
    assert docs[0]["request_id"] == response.headers["x-request-id"]
