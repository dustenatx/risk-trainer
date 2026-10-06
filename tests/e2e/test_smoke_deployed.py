"""Launch smoke test against the deployed app (PRD §9 item 4; R12).

Opt-in: runs only with `make smoke SMOKE_BASE_URL=https://<distribution>.cloudfront.net`.
Completing a scenario records one real attempt in the peer counts.
"""

import os

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.flows import answer_all_transfer

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="session")
def deployed_url() -> str:
    url = os.environ.get("SMOKE_BASE_URL", "").rstrip("/")
    if not url:
        pytest.skip("set SMOKE_BASE_URL to the deployed https:// URL")
    assert url.startswith("https://"), "the deployed app is HTTPS only"
    return url


def test_smoke_security_headers(page: Page, deployed_url: str) -> None:
    response = page.goto(f"{deployed_url}/")
    assert response is not None and response.status == 200
    headers = response.all_headers()
    assert headers["strict-transport-security"].startswith("max-age=")
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


def test_smoke_http_redirects_to_https(page: Page, deployed_url: str) -> None:
    response = page.request.get(
        deployed_url.replace("https://", "http://", 1) + "/", max_redirects=0
    )
    assert response.status in (301, 302, 307, 308)
    assert response.headers["location"].startswith("https://")


def test_smoke_complete_a_scenario(page: Page, deployed_url: str) -> None:
    page.goto(f"{deployed_url}/")
    page.locator('a[href^="/s/"]').first.click()
    answer_all_transfer(page)
    page.get_by_role("button", name="Submit my answers").click()
    expect(page.locator("#score")).to_contain_text("points")
    expect(page.locator("section.finding-debrief").first).to_be_visible()
    expect(page.locator("#overall-heading")).to_be_visible()
