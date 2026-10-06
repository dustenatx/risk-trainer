"""Pure ASGI middleware: security headers, request IDs with error pages, the origin check and
the body limit."""

import logging
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from risk_trainer.domain.submission import MAX_BODY_BYTES
from risk_trainer.web.logging import request_id_var

logger = logging.getLogger("risk_trainer.web")

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "object-src 'none'"
)
SECURITY_HEADERS = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    # CloudFront's managed SecurityHeadersPolicy keeps origin values, so the app sets them (R12).
    "strict-transport-security": "max-age=31536000",
}
ORIGIN_VERIFY_HEADER = b"x-origin-verify"
ErrorRenderer = Callable[[Scope, int, str], Awaitable[tuple[bytes, str]]]


class SecurityHeadersMiddleware:
    """Adds security headers to every response, and Cache-Control: no-store to every POST."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_post = scope["method"] == "POST"

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                if is_post:
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequestContextMiddleware:
    """Gives each request an ID, logs one access line, and turns crashes into a plain 500 page."""

    def __init__(self, app: ASGIApp, render_error: ErrorRenderer) -> None:
        self.app = app
        self.render_error = render_error

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)["x-request-id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            logger.exception("unhandled error", extra={"event": "unhandled_error"})
            if response_started:
                raise
            status = 500
            body, content_type = await self.render_error(scope, 500, request_id)
            await send_with_id(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", content_type.encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)


class OriginVerifyMiddleware:
    """Rejects requests that didn't come through CloudFront (R12).

    CloudFront adds a secret X-Origin-Verify header to every origin request. Requests to the
    Lambda Function URL without it get a bare 403, before the session or body is read.
    """

    def __init__(self, app: ASGIApp, secret: str) -> None:
        if not secret:
            raise ValueError("the origin-verify secret is empty")
        self.app = app
        self._secret = secret.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        values = [value for name, value in scope["headers"] if name == ORIGIN_VERIFY_HEADER]
        if len(values) == 1 and secrets.compare_digest(values[0], self._secret):
            await self.app(scope, receive, send)
            return
        logger.warning("request without origin header", extra={"event": "origin_rejected"})
        body = b"Forbidden"
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Rejects request bodies over the limit with 413 before anything parses them (R7)."""

    def __init__(self, app: ASGIApp, render_error: ErrorRenderer, limit: int = MAX_BODY_BYTES):
        self.app = app
        self.render_error = render_error
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope["headers"]:
            if name == b"content-length" and (not value.isdigit() or int(value) > self.limit):
                await self._reject(scope, send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        request_id = scope.get("state", {}).get("request_id", "")
        body, content_type = await self.render_error(scope, 413, request_id)
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", content_type.encode()),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
