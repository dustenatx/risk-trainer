"""App settings. This is the only module that reads environment variables."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from risk_trainer.domain.peers import DEFAULT_PEER_MIN_SAMPLE

SESSION_SECRET_MIN_LENGTH = 32


class ConfigError(Exception):
    """The app's configuration is unsafe or incomplete; it refuses to start."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    # Required: no default, so a deployment can't silently fall back to memory storage.
    storage_backend: Literal["memory", "dynamodb"]
    session_secret: SecretStr = Field(min_length=SESSION_SECRET_MIN_LENGTH)
    session_cookie_secure: bool = True
    dynamodb_table: str | None = None
    aws_region: str | None = None
    peer_min_sample: int = Field(default=DEFAULT_PEER_MIN_SAMPLE, ge=1)
    content_dir: Path = Path("content")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Set by the Lambda runtime; never set it by hand.
    aws_lambda_function_name: str | None = None

    @model_validator(mode="after")
    def _check_storage(self) -> Self:
        check_storage(self)
        return self


def check_storage(settings: Settings) -> None:
    """Refuse memory storage inside Lambda and a DynamoDB backend without a table."""
    if settings.storage_backend == "memory" and settings.aws_lambda_function_name:
        raise ConfigError("STORAGE_BACKEND=memory is not allowed in Lambda")
    if settings.storage_backend == "dynamodb" and not settings.dynamodb_table:
        raise ConfigError("DYNAMODB_TABLE is required when STORAGE_BACKEND=dynamodb")
