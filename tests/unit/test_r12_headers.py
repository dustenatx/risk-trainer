"""R12 — the app sends every security header itself.

CloudFront's Free plan allows only AWS-managed response-headers policies, and the managed
SecurityHeadersPolicy keeps origin values (it overrides only X-Content-Type-Options).
"""

import pytest

from tests.web_helpers import RT001_ID, client, submit

ORIGIN_SECRET = "o" * 64


def header_sets() -> list[tuple[str, dict[str, str]]]:
    test_client = client()
    responses = [
        ("home", test_client.get("/")),
        ("exercise", test_client.get(f"/s/{RT001_ID}")),
        ("static", test_client.get("/static/app.css")),
        ("not found", test_client.get("/missing")),
        ("result", submit(test_client)),
        ("forbidden POST", test_client.post(f"/s/{RT001_ID}", data={})),
    ]
    return [(name, dict(response.headers)) for name, response in responses]


@pytest.mark.parametrize(
    ("name", "headers"), header_sets(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_r12_security_headers_on_every_response(name: str, headers: dict[str, str]) -> None:
    assert headers["strict-transport-security"] == "max-age=31536000"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"
    csp = headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp
    assert "http:" not in csp and "https:" not in csp, "no third-party script origins"


def test_r12_origin_rejection_still_gets_security_headers() -> None:
    headers = client(origin_verify_secret=ORIGIN_SECRET).get("/").headers
    assert headers["strict-transport-security"] == "max-age=31536000"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
