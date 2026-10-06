"""R12 — the origin rejects every request that didn't come through CloudFront."""

import logging

import pytest
from fastapi.testclient import TestClient

from risk_trainer.config import ConfigError, Settings
from risk_trainer.web.app import create_app
from risk_trainer.web.middleware import OriginVerifyMiddleware
from tests.web_helpers import RT001_ID, client, rt001, settings, submit

ORIGIN_SECRET = "o" * 64


def guarded() -> TestClient:
    test_client = client(origin_verify_secret=ORIGIN_SECRET)
    test_client.headers["x-origin-verify"] = ORIGIN_SECRET
    return test_client


@pytest.mark.parametrize("path", ["/", f"/s/{RT001_ID}", "/static/app.css", "/no-such-page"])
def test_r12_missing_origin_header_gets_403(path: str) -> None:
    response = client(origin_verify_secret=ORIGIN_SECRET).get(path)
    assert response.status_code == 403
    assert response.text == "Forbidden"
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("value", ["", "wrong", ORIGIN_SECRET[:-1], ORIGIN_SECRET + "x"])
def test_r12_wrong_origin_header_gets_403(value: str) -> None:
    test_client = client(origin_verify_secret=ORIGIN_SECRET)
    assert test_client.get("/", headers={"x-origin-verify": value}).status_code == 403


def test_r12_duplicate_origin_headers_get_403() -> None:
    test_client = client(origin_verify_secret=ORIGIN_SECRET)
    response = test_client.get(
        "/", headers=[("x-origin-verify", ORIGIN_SECRET), ("x-origin-verify", ORIGIN_SECRET)]
    )
    assert response.status_code == 403


def test_r12_post_without_origin_header_is_rejected_before_parsing() -> None:
    test_client = client(origin_verify_secret=ORIGIN_SECRET)
    response = test_client.post(f"/s/{RT001_ID}", data={"F1.treatment": "avoid"})
    assert response.status_code == 403
    assert response.text == "Forbidden"


def test_r12_correct_origin_header_serves_the_app() -> None:
    test_client = guarded()
    assert test_client.get("/").status_code == 200
    assert submit(test_client).status_code == 200


def test_r12_rejection_is_logged_without_the_header(caplog: pytest.LogCaptureFixture) -> None:
    test_client = client(origin_verify_secret=ORIGIN_SECRET)
    logger = logging.getLogger("risk_trainer.web")
    logger.addHandler(caplog.handler)
    try:
        test_client.get("/", headers={"x-origin-verify": "attacker-guess-1234"})
    finally:
        logger.removeHandler(caplog.handler)
    assert any(getattr(r, "event", None) == "origin_rejected" for r in caplog.records)
    assert "attacker-guess-1234" not in caplog.text


def test_r12_no_guard_when_no_secret_is_configured() -> None:
    # Local runs and rt preview have no CloudFront in front of them.
    assert client().get("/").status_code == 200


def test_r12_app_refuses_to_start_in_lambda_without_origin_secret() -> None:
    lambda_settings = Settings.model_construct(
        **{
            **settings().model_dump(),
            "aws_lambda_function_name": "risk-trainer-prod",
            "storage_backend": "dynamodb",
            "dynamodb_table": "risk-trainer-prod",
        }
    )
    with pytest.raises(ConfigError, match="origin-verify"):
        create_app(lambda_settings, scenarios=[rt001()])


def test_r12_empty_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        OriginVerifyMiddleware(app=lambda *_: None, secret="")  # type: ignore[arg-type]
