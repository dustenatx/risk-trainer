"""Cross-cutting web rules from AGENTS.md and PRD section 6: CSP, no inline script, errors."""

import re
from pathlib import Path

import pytest
from fastapi import APIRouter

from risk_trainer.web.app import WEB_DIR, make_templates
from tests.web_helpers import client

TEMPLATES = sorted((WEB_DIR / "templates").glob("*.html"))


def test_csp_has_no_unsafe_inline_or_third_party_origins() -> None:
    csp = client().get("/").headers["content-security-policy"]
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "http" not in csp


def test_security_headers_on_every_response() -> None:
    for path in ("/", "/about", "/missing"):
        headers = client().get(path).headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-request-id"]


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_templates_have_no_inline_script_handlers_or_styles(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", text, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", text, re.IGNORECASE)
    assert not re.search(r"\sstyle\s*=", text, re.IGNORECASE)
    assert not re.search(r"<style", text, re.IGNORECASE)
    assert "|safe" not in text.replace(" ", "")
    for src in re.findall(r'src="([^"]+)"', text, re.IGNORECASE):
        assert src.startswith("/static/")


def test_jinja_autoescape_is_on() -> None:
    env = make_templates().env
    assert env.autoescape is True or env.autoescape("page.html")


def test_learner_text_is_escaped() -> None:
    from tests.web_helpers import EXPERT_ANSWERS, submit

    text = submit(client(), {**EXPERT_ANSWERS, "F1.rationale": "<script>alert(1)</script>"}).text
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_session_cookie_flags() -> None:
    cookie = client().get("/s/rt-001-five-findings").headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie


def test_server_error_shows_request_id_without_trace() -> None:
    test_client = client()
    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("internal detail")

    test_client.app.include_router(router)  # type: ignore[attr-defined]
    response = test_client.get("/boom")
    assert response.status_code == 500
    assert response.headers["x-request-id"] in response.text
    assert "internal detail" not in response.text
    assert "Traceback" not in response.text
    assert response.headers["content-security-policy"]


def test_404_page_shows_request_id() -> None:
    response = client().get("/nope")
    assert response.status_code == 404
    assert response.headers["x-request-id"] in response.text


def test_no_api_docs_exposed() -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client().get(path).status_code == 404
