"""App settings. This is the only module that reads environment variables."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from risk_trainer.domain.peers import DEFAULT_PEER_MIN_SAMPLE

SESSION_SECRET_MIN_LENGTH = 32
ORIGIN_VERIFY_MIN_LENGTH = 32
DEFAULT_REQUESTS_PER_SESSION_PER_MINUTE = 60


class ConfigError(Exception):
    """The app's configuration is unsafe or incomplete; it refuses to start."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    # Required: no default, so a deployment can't silently fall back to memory storage.
    storage_backend: Literal["memory", "dynamodb"]
    # Local runs set the secret directly. In Lambda it comes from SSM (the *_param names) and
    # a plaintext value in the environment is refused (R13).
    session_secret: SecretStr | None = Field(default=None, min_length=SESSION_SECRET_MIN_LENGTH)
    session_secret_param: str | None = None
    origin_verify_secret: SecretStr | None = Field(
        default=None, min_length=ORIGIN_VERIFY_MIN_LENGTH
    )
    origin_verify_param: str | None = None
    session_cookie_secure: bool = True
    dynamodb_table: str | None = None
    aws_region: str | None = None
    peer_min_sample: int = Field(default=DEFAULT_PEER_MIN_SAMPLE, ge=1)
    requests_per_session_per_minute: int = Field(
        default=DEFAULT_REQUESTS_PER_SESSION_PER_MINUTE, ge=1
    )
    metrics_namespace: str = Field(default="RiskTrainer", min_length=1, max_length=255)
    content_dir: Path = Path("content")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Set by the Lambda runtime; never set it by hand.
    aws_lambda_function_name: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_storage(self)
        check_secret_sources(self)
        return self


def in_lambda(settings: Settings) -> bool:
    return bool(settings.aws_lambda_function_name)


def check_storage(settings: Settings) -> None:
    """Refuse memory storage inside Lambda and a DynamoDB backend without a table."""
    if settings.storage_backend == "memory" and in_lambda(settings):
        raise ConfigError("STORAGE_BACKEND=memory is not allowed in Lambda")
    if settings.storage_backend == "dynamodb" and not settings.dynamodb_table:
        raise ConfigError("DYNAMODB_TABLE is required when STORAGE_BACKEND=dynamodb")


def check_secret_sources(settings: Settings) -> None:
    """Where secrets may come from, checked when settings are read from the environment.

    In Lambda both secrets must come from SSM SecureString parameters; plaintext values in
    the environment are refused. Elsewhere, the session secret is set directly or by parameter.
    """
    if in_lambda(settings):
        if settings.session_secret is not None or settings.origin_verify_secret is not None:
            raise ConfigError(
                "SESSION_SECRET and ORIGIN_VERIFY_SECRET must not be set in Lambda; "
                "use SESSION_SECRET_PARAM and ORIGIN_VERIFY_PARAM"
            )
        if not settings.session_secret_param or not settings.origin_verify_param:
            raise ConfigError("SESSION_SECRET_PARAM and ORIGIN_VERIFY_PARAM are required in Lambda")
    elif settings.session_secret is None and not settings.session_secret_param:
        raise ConfigError("SESSION_SECRET (or SESSION_SECRET_PARAM) is required")


def check_ready(settings: Settings) -> None:
    """The app can start: secrets are resolved, and Lambda has the origin check (R12)."""
    check_storage(settings)
    if settings.session_secret is None:
        raise ConfigError("the session secret has not been loaded")
    if in_lambda(settings) and settings.origin_verify_secret is None:
        raise ConfigError("the origin-verify secret is required in Lambda")
