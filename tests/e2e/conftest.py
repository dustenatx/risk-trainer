"""Runs the app on 127.0.0.1 in a background thread for Playwright (memory storage)."""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from risk_trainer.storage.memory import MemoryAttemptStore
from risk_trainer.web.app import create_app
from tests.web_helpers import rt001, settings


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    app = create_app(
        settings(session_cookie_secure=False), MemoryAttemptStore(), [rt001()], preview=False
    )
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
