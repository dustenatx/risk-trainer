"""PRD §6 — every page's footer carries the Bearing Quest family line, with the mark hidden from
assistive technology so the text is the label."""

import re
from html.parser import HTMLParser

import pytest

from tests.web_helpers import RT001_ID, client

PAGES = ["/", f"/s/{RT001_ID}", "/responses", "/about", "/privacy", "/no-such-page"]
FAMILY_LINE = "Part of the Bearing Quest project family."
NOT_A_COMPANY = re.compile(r"\b(company|firm|clients)\b", re.IGNORECASE)


class _Footer(HTMLParser):
    """The footer's text, its <svg> attributes, and any style attribute inside it."""

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.text: list[str] = []
        self.svgs: list[dict[str, str | None]] = []
        self.styled: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "footer":
            self.depth += 1
        if not self.depth:
            return
        values = dict(attrs)
        if tag == "svg":
            self.svgs.append(values)
        if "style" in values:
            self.styled.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "footer" and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.text.append(data)


def footer(path: str) -> _Footer:
    parser = _Footer()
    parser.feed(client().get(path).text)
    return parser


@pytest.mark.parametrize("path", PAGES)
def test_r12_footer_has_family_line_and_hidden_mark(path: str) -> None:
    found = footer(path)
    assert FAMILY_LINE in " ".join("".join(found.text).split())
    assert len(found.svgs) == 1
    assert found.svgs[0].get("aria-hidden") == "true"
    assert found.svgs[0].get("focusable") == "false"
    assert found.svgs[0].get("class") == "bq-mark"
    assert found.styled == []


@pytest.mark.parametrize("path", PAGES)
def test_r12_footer_never_calls_bearing_quest_a_company(path: str) -> None:
    assert not NOT_A_COMPANY.search("".join(footer(path).text))


def test_r12_company_wording_matches_whole_words_only() -> None:
    assert NOT_A_COMPANY.search("our Clients")
    assert not NOT_A_COMPANY.search("confirm the firmware")
