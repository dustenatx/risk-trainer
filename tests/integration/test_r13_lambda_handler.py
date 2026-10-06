"""R12/R13 — the Lambda entry point: secrets from SSM SecureStrings (moto), Function URL
events through Mangum, and the origin check."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import boto3
import pytest
from moto import mock_aws

from risk_trainer.config import ConfigError, Settings
from risk_trainer.storage.parameters import ParameterError, get_secure_string, make_client
from risk_trainer.web import lambda_handler
from risk_trainer.web.lambda_handler import build_handler, resolve_secrets

REGION = "us-east-2"
SESSION_PARAM = "/risk-trainer/prod/session-secret"
ORIGIN_PARAM = "/risk-trainer/prod/origin-verify"
ORIGIN_VALUE = "a" * 64
LAMBDA_ENV = {
    "AWS_LAMBDA_FUNCTION_NAME": "risk-trainer-prod",
    "STORAGE_BACKEND": "dynamodb",
    "DYNAMODB_TABLE": "risk-trainer-prod",
    "AWS_REGION": REGION,
    "SESSION_SECRET_PARAM": SESSION_PARAM,
    "ORIGIN_VERIFY_PARAM": ORIGIN_PARAM,
}


@pytest.fixture
def ssm(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    for key in ("SESSION_SECRET", "ORIGIN_VERIFY_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in LAMBDA_ENV.items():
        monkeypatch.setenv(key, value)
    with mock_aws():
        client = boto3.client("ssm", region_name=REGION)
        client.put_parameter(Name=SESSION_PARAM, Value="s" * 64, Type="SecureString")
        client.put_parameter(Name=ORIGIN_PARAM, Value=ORIGIN_VALUE, Type="SecureString")
        yield client


def url_event(method: str = "GET", path: str = "/", origin: str | None = None) -> dict[str, Any]:
    """A Lambda Function URL (payload v2) event, as CloudFront's origin request produces it."""
    headers = {"host": "abc123.lambda-url.us-east-2.on.aws", "x-forwarded-proto": "https"}
    if origin is not None:
        headers["x-origin-verify"] = origin
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "accountId": "anonymous",
            "apiId": "abc123",
            "domainName": "abc123.lambda-url.us-east-2.on.aws",
            "domainPrefix": "abc123",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "192.0.2.1",
                "userAgent": "test",
            },
            "requestId": "req-1",
            "routeKey": "$default",
            "stage": "$default",
            "time": "06/Oct/2026:12:00:00 +0000",
            "timeEpoch": 1791288000000,
        },
        "isBase64Encoded": False,
    }


CONTEXT = SimpleNamespace(aws_request_id="req-1", function_name="risk-trainer-prod")


def test_r13_reads_secure_strings(ssm: Any) -> None:
    value = get_secure_string(make_client(REGION), ORIGIN_PARAM)
    assert value.get_secret_value() == ORIGIN_VALUE
    assert ORIGIN_VALUE not in repr(value)


def test_r13_plain_string_parameter_refused(ssm: Any) -> None:
    ssm.put_parameter(Name="/risk-trainer/prod/plain", Value="x" * 64, Type="String")
    with pytest.raises(ParameterError, match="SecureString"):
        get_secure_string(make_client(REGION), "/risk-trainer/prod/plain")


def test_r13_missing_parameter_error_names_it_without_a_value(ssm: Any) -> None:
    with pytest.raises(ParameterError, match="/risk-trainer/prod/missing"):
        get_secure_string(make_client(REGION), "/risk-trainer/prod/missing")


def test_r13_resolve_secrets_loads_both(ssm: Any) -> None:
    resolved = resolve_secrets(Settings(), make_client(REGION))
    assert resolved.session_secret is not None
    assert resolved.origin_verify_secret is not None
    assert resolved.origin_verify_secret.get_secret_value() == ORIGIN_VALUE


def test_r13_short_parameter_value_refused(ssm: Any) -> None:
    ssm.put_parameter(Name=ORIGIN_PARAM, Value="short", Type="SecureString", Overwrite=True)
    with pytest.raises(ConfigError, match="at least 32"):
        resolve_secrets(Settings(), make_client(REGION))


def test_r12_function_url_event_without_origin_header_gets_403(ssm: Any) -> None:
    response = build_handler()(url_event(), CONTEXT)
    assert response["statusCode"] == 403
    assert response["body"] == "Forbidden"


def test_r12_function_url_event_from_cloudfront_is_served(ssm: Any) -> None:
    response = build_handler()(url_event(origin=ORIGIN_VALUE), CONTEXT)
    assert response["statusCode"] == 200
    assert "Risk Trainer" in response["body"]
    headers = {k.lower(): v for k, v in response["headers"].items()}
    assert headers["strict-transport-security"] == "max-age=31536000"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_r13_handler_builds_the_app_once(ssm: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lambda_handler, "_handler", None)
    calls = []
    real = lambda_handler.build_handler

    def counting() -> Any:
        calls.append(1)
        return real()

    monkeypatch.setattr(lambda_handler, "build_handler", counting)
    for _ in range(3):
        assert lambda_handler.handler(url_event(origin=ORIGIN_VALUE), CONTEXT)["statusCode"] == 200
    assert len(calls) == 1
