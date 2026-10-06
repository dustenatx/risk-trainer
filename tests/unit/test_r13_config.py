"""R13 — secrets live in SSM SecureStrings, never in Lambda environment variables."""

import pytest

from risk_trainer.config import ConfigError, Settings
from risk_trainer.web.app import create_app
from tests.web_helpers import SECRET, rt001, settings

LAMBDA_ENV = {
    "AWS_LAMBDA_FUNCTION_NAME": "risk-trainer-prod",
    "STORAGE_BACKEND": "dynamodb",
    "DYNAMODB_TABLE": "risk-trainer-prod",
    "SESSION_SECRET_PARAM": "/risk-trainer/prod/session-secret",
    "ORIGIN_VERIFY_PARAM": "/risk-trainer/prod/origin-verify",
}


@pytest.fixture
def lambda_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for key in ("SESSION_SECRET", "ORIGIN_VERIFY_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in LAMBDA_ENV.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_r13_lambda_settings_take_parameter_names(lambda_env: pytest.MonkeyPatch) -> None:
    loaded = Settings()
    assert loaded.session_secret is None
    assert loaded.session_secret_param == LAMBDA_ENV["SESSION_SECRET_PARAM"]
    assert loaded.origin_verify_param == LAMBDA_ENV["ORIGIN_VERIFY_PARAM"]


@pytest.mark.parametrize("name", ["SESSION_SECRET", "ORIGIN_VERIFY_SECRET"])
def test_r13_plaintext_secret_refused_in_lambda(lambda_env: pytest.MonkeyPatch, name: str) -> None:
    lambda_env.setenv(name, "p" * 64)
    with pytest.raises(ConfigError, match="must not be set in Lambda"):
        Settings()


@pytest.mark.parametrize("name", ["SESSION_SECRET_PARAM", "ORIGIN_VERIFY_PARAM"])
def test_r13_parameter_names_required_in_lambda(lambda_env: pytest.MonkeyPatch, name: str) -> None:
    lambda_env.delenv(name)
    with pytest.raises(ConfigError, match="required in Lambda"):
        Settings()


def test_r13_local_runs_need_a_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("SESSION_SECRET", "SESSION_SECRET_PARAM", "AWS_LAMBDA_FUNCTION_NAME"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    with pytest.raises(ConfigError, match="SESSION_SECRET"):
        Settings()
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    assert Settings().session_secret is not None


def test_r13_app_refuses_an_unloaded_session_secret() -> None:
    unloaded = Settings.model_construct(
        **{**settings().model_dump(), "session_secret": None, "session_secret_param": "/x"}
    )
    with pytest.raises(ConfigError, match="session secret"):
        create_app(unloaded, scenarios=[rt001()])
