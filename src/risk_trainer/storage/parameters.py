"""SSM Parameter Store SecureStrings (PRD R13). Values are never logged or returned in errors."""

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import SecretStr

if TYPE_CHECKING:
    from mypy_boto3_ssm.client import SSMClient

CLIENT_CONFIG = Config(
    connect_timeout=2,
    read_timeout=3,
    retries={"total_max_attempts": 3, "mode": "standard"},
)


class ParameterError(Exception):
    """A parameter could not be read, or isn't a SecureString."""


def make_client(region: str | None) -> SSMClient:
    return boto3.client("ssm", region_name=region, config=CLIENT_CONFIG)


def get_secure_string(client: SSMClient, name: str) -> SecretStr:
    """Read and decrypt one SecureString. Plain String parameters are refused."""
    try:
        response = client.get_parameter(Name=name, WithDecryption=True)
    except (ClientError, BotoCoreError) as exc:
        raise ParameterError(f"could not read parameter {name}") from exc
    parameter = response["Parameter"]
    if parameter.get("Type") != "SecureString":
        raise ParameterError(f"parameter {name} must be a SecureString")
    return SecretStr(parameter.get("Value", ""))
