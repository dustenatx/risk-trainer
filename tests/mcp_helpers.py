"""Call the authoring MCP server in-process (R17: tests call every tool in-process)."""

from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.types import CallToolResult, Tool

from risk_trainer.mcp.authoring import build_server


def call(content_dir: Path, name: str, arguments: dict[str, Any] | None = None) -> CallToolResult:
    async def run() -> CallToolResult:
        async with Client(build_server(content_dir)) as client:
            return await client.call_tool(name, arguments or {})

    return anyio.run(run)


def tools(content_dir: Path) -> list[Tool]:
    async def run() -> list[Tool]:
        async with Client(build_server(content_dir)) as client:
            return (await client.list_tools()).tools

    return anyio.run(run)


def data(result: CallToolResult) -> dict[str, Any]:
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content


def error(result: CallToolResult) -> dict[str, str]:
    assert result.is_error
    assert result.structured_content is not None
    envelope: dict[str, str] = result.structured_content["error"]
    assert set(envelope) == {"code", "message"}
    return envelope
