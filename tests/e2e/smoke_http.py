"""Read-only HTTP helpers for the deployed smoke checks (R9, R12, R14).

Smoke checks run against production after every deploy, so they must never submit a form or
record an attempt. `read_only_client` refuses any method other than GET or HEAD before the
request leaves the runner; a unit test checks that the smoke tests use nothing else.
"""

from html.parser import HTMLParser

import httpx

READ_ONLY_METHODS = frozenset({"GET", "HEAD"})
FINDINGS_PER_SCENARIO = 5


def refuse_writes(request: httpx.Request) -> None:
    """Request hook: fail the test on anything that could change state."""
    if request.method not in READ_ONLY_METHODS:
        raise AssertionError(f"smoke checks are GET only; refused {request.method} {request.url}")


def read_only_client(base_url: str, transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        transport=transport,
        timeout=10.0,
        follow_redirects=False,
        headers={"user-agent": "risk-trainer-smoke"},
        event_hooks={"request": [refuse_writes]},
    )


class PageLinks(HTMLParser):
    """Collects scenario links, the stylesheet href and the number of finding sections."""

    def __init__(self) -> None:
        super().__init__()
        self.scenario_hrefs: list[str] = []
        self.stylesheet_hrefs: list[str] = []
        self.findings = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if tag == "a" and values.get("href", "").startswith("/s/"):
            self.scenario_hrefs.append(values["href"])
        elif tag == "link" and "stylesheet" in values.get("rel", "").split():
            self.stylesheet_hrefs.append(values.get("href", ""))
        elif tag == "section" and "finding" in values.get("class", "").split():
            self.findings += 1


def parse_page(html: str) -> PageLinks:
    links = PageLinks()
    links.feed(html)
    links.close()
    return links
