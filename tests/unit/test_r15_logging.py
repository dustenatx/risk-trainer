"""R15 — structured JSON logs with a request ID; rationale text never reaches a log line."""

import json
from datetime import datetime

import pytest

from risk_trainer.storage.rate_limits import RateLimitUnavailable
from tests.web_helpers import EXPERT_ANSWERS, client, submit

RATIONALE = "SENTINEL-rationale-7f3a the owner signed the exception"
NOTE = "SENTINEL-note-91bc overall I chose speed"


class OverLimit:
    def hit(self, session_id: str, now: datetime) -> int:
        return 10_000


class Unavailable:
    def hit(self, session_id: str, now: datetime) -> int:
        raise RateLimitUnavailable("throttled")


ANSWERS = {**EXPERT_ANSWERS, "F5.rationale": RATIONALE, "F1.rationale": RATIONALE}


@pytest.mark.parametrize(
    ("limiter", "status"),
    [(None, 200), (OverLimit(), 429), (Unavailable(), 200)],
    ids=["submit", "rate-limited", "limiter-unavailable"],
)
def test_r15_rationale_never_logged(
    capsys: pytest.CaptureFixture[str], limiter: object, status: int
) -> None:
    response = submit(client(rate_limiter=limiter), ANSWERS, note=NOTE)  # type: ignore[arg-type]
    assert response.status_code == status
    err = capsys.readouterr().err
    assert err, "the request produced log lines"
    assert "SENTINEL" not in err


def test_r15_every_log_line_is_json_with_the_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    response = submit(client(rate_limiter=Unavailable()), ANSWERS)
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line]
    request_id = response.headers["x-request-id"]
    app_lines = [line for line in lines if "_aws" not in line]
    assert {line["msg"] for line in app_lines} >= {"rate limit unavailable", "request"}
    post_lines = [line for line in lines if line.get("request_id") == request_id]
    assert len(post_lines) >= 3, "event, metric and access lines all carry the request ID"
