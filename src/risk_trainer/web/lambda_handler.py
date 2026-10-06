"""AWS Lambda entry point: `risk_trainer.web.lambda_handler.handler` (PRD R12, R13).

Mangum translates Function URL events to ASGI. The app is built on the first invocation of
each execution environment: settings come from the environment, and both secrets are read
from SSM SecureString parameters, so neither is ever in a Lambda environment variable.
"""

from typing import TYPE_CHECKING, Any

from mangum import Mangum
from pydantic import SecretStr

from risk_trainer.config import (
    ORIGIN_VERIFY_MIN_LENGTH,
    SESSION_SECRET_MIN_LENGTH,
    ConfigError,
    Settings,
)
from risk_trainer.storage.parameters import get_secure_string, make_client
from risk_trainer.web.app import create_app

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient

_handler: Mangum | None = None


def resolve_secrets(settings: Settings, client: SSMClient) -> Settings:
    """Settings with the session and origin-verify secrets loaded from SSM.

    model_copy skips validation, so the minimum lengths are checked here.
    """
    updates: dict[str, SecretStr] = {}
    for field, param, minimum in (
        ("session_secret", settings.session_secret_param, SESSION_SECRET_MIN_LENGTH),
        ("origin_verify_secret", settings.origin_verify_param, ORIGIN_VERIFY_MIN_LENGTH),
    ):
        if not param:
            continue
        value = get_secure_string(client, param)
        if len(value.get_secret_value()) < minimum:
            raise ConfigError(f"parameter {param} must be at least {minimum} characters")
        updates[field] = value
    return settings.model_copy(update=updates)


def build_handler(settings: Settings | None = None, client: SSMClient | None = None) -> Mangum:
    loaded = settings if settings is not None else Settings()
    resolved = resolve_secrets(loaded, client or make_client(loaded.aws_region))
    return Mangum(create_app(resolved), lifespan="off")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    global _handler  # one app per execution environment, built on first use
    if _handler is None:
        _handler = build_handler()
    response: dict[str, Any] = _handler(event, context)
    return response
