"""CSRF protection: a per-session token, sent in a hidden field on every POST form."""

import secrets

from starlette.requests import Request

CSRF_FIELD = "csrf_token"
_SESSION_KEY = "csrf"


def csrf_token(request: Request) -> str:
    """The session's CSRF token, created on first use."""
    token = request.session.get(_SESSION_KEY)
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session[_SESSION_KEY] = token
    return token


def csrf_valid(request: Request, submitted: str | None) -> bool:
    expected = request.session.get(_SESSION_KEY)
    if not isinstance(expected, str) or not submitted:
        return False
    return secrets.compare_digest(expected, submitted)
