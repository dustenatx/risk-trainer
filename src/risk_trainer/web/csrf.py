"""CSRF protection: a per-session token, sent in a hidden field on every POST form.

The session also holds a random session ID, used only to key the per-session submission
counter (R13). Both are random values; neither identifies the learner.
"""

import secrets

from starlette.requests import Request

CSRF_FIELD = "csrf_token"
_SESSION_KEY = "csrf"
_SESSION_ID_KEY = "sid"


def csrf_token(request: Request) -> str:
    """The session's CSRF token, created on first use (with the session ID)."""
    token = request.session.get(_SESSION_KEY)
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session[_SESSION_KEY] = token
    session_id(request)
    return token


def session_id(request: Request) -> str:
    """The session's random ID, created on first use."""
    sid = request.session.get(_SESSION_ID_KEY)
    if not isinstance(sid, str):
        sid = secrets.token_urlsafe(16)
        request.session[_SESSION_ID_KEY] = sid
    return sid


def csrf_valid(request: Request, submitted: str | None) -> bool:
    expected = request.session.get(_SESSION_KEY)
    if not isinstance(expected, str) or not submitted:
        return False
    return secrets.compare_digest(expected, submitted)
