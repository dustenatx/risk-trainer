"""PRD §6 — every page starts with the Bearing Quest family strip: the static lockup image and
the text "project family", with nothing focusable, and no family line left in the footer."""

import re
from html.parser import HTMLParser

import pytest

from risk_trainer.web.app import STATIC_DIR
from risk_trainer.web.assets import CACHE_CURRENT
from tests.web_helpers import RT001_ID, client, static_path

PAGES = ["/", f"/s/{RT001_ID}", "/responses", "/about", "/privacy", "/no-such-page"]
LOCKUP = STATIC_DIR / "bearing-quest-lockup.svg"
NOT_A_COMPANY = re.compile(r"\b(company|firm|clients)\b", re.IGNORECASE)
FOCUSABLE = {"a", "button", "input", "select", "textarea", "iframe"}
VOID = {"img", "br", "hr", "input", "meta", "link", "source", "wbr"}


class _Page(HTMLParser):
    """The header's first element child, every .bq-strip, the strip's contents and footer text."""

    def __init__(self) -> None:
        super().__init__()
        self.in_header = False
        self.header_first: dict[str, str | None] | None = None
        self.header_first_tag = ""
        self.strips = 0
        self.strip_depth = 0
        self.strip_tags: list[tuple[str, dict[str, str | None]]] = []
        self.strip_text: list[str] = []
        self.in_footer = False
        self.footer_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if self.in_header and self.header_first is None:
            self.header_first, self.header_first_tag = values, tag
        if tag == "header":
            self.in_header = True
        if tag == "footer":
            self.in_footer = True
        if self.strip_depth:
            self.strip_tags.append((tag, values))
            if tag not in VOID:
                self.strip_depth += 1
        elif "bq-strip" in (values.get("class") or "").split():
            self.strips += 1
            self.strip_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.strip_depth and tag not in VOID:
            self.strip_depth -= 1
        if tag == "header":
            self.in_header = False
        if tag == "footer":
            self.in_footer = False

    def handle_data(self, data: str) -> None:
        if self.strip_depth:
            self.strip_text.append(data)
        if self.in_footer:
            self.footer_text.append(data)


def parse(path: str) -> _Page:
    parser = _Page()
    parser.feed(client().get(path).text)
    return parser


@pytest.mark.parametrize("path", PAGES)
def test_r12_strip_is_first_in_header(path: str) -> None:
    page = parse(path)
    assert page.strips == 1
    assert page.header_first_tag == "div"
    assert page.header_first is not None
    assert page.header_first.get("class") == "bq-strip"


@pytest.mark.parametrize("path", PAGES)
def test_r12_strip_has_versioned_lockup_and_text(path: str) -> None:
    page = parse(path)
    images = [values for tag, values in page.strip_tags if tag == "img"]
    assert len(images) == 1
    image = images[0]
    assert image.get("alt") == "Bearing Quest"
    assert (image.get("width"), image.get("height")) == ("91", "30")
    assert image.get("src") == static_path("bearing-quest-lockup.svg")
    assert "project family" in " ".join("".join(page.strip_text).split())


def test_r12_lockup_is_served_cached_as_svg() -> None:
    response = client().get(static_path("bearing-quest-lockup.svg"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == CACHE_CURRENT
    assert response.content == LOCKUP.read_bytes()


@pytest.mark.parametrize("path", PAGES)
def test_r12_strip_has_nothing_focusable(path: str) -> None:
    """So the skip link stays the first tab stop."""
    for tag, values in parse(path).strip_tags:
        assert tag not in FOCUSABLE, tag
        assert "tabindex" not in values, tag


@pytest.mark.parametrize("path", PAGES)
def test_r12_footer_has_no_family_line(path: str) -> None:
    footer = " ".join("".join(parse(path).footer_text).split())
    assert "Bearing Quest" not in footer
    assert "Not affiliated with or endorsed by ISC2." in footer


@pytest.mark.parametrize("path", PAGES)
def test_r12_strip_never_calls_bearing_quest_a_company(path: str) -> None:
    page = parse(path)
    alts = [values.get("alt") or "" for _, values in page.strip_tags]
    assert not NOT_A_COMPANY.search(" ".join(["".join(page.strip_text), *alts]))


def test_r12_company_wording_matches_whole_words_only() -> None:
    assert NOT_A_COMPANY.search("our Clients")
    assert not NOT_A_COMPANY.search("confirm the firmware")


def test_r12_lockup_svg_is_inert() -> None:
    svg = LOCKUP.read_text(encoding="utf-8")
    for banned in ("<script", "foreignobject", "<image", "<style"):
        assert banned not in svg.lower(), banned
    assert not re.search(r"\son[a-z]+\s*=", svg, re.IGNORECASE)
    for ref in re.findall(r"""\bhref\s*=\s*["']([^"']*)["']""", svg, re.IGNORECASE):
        assert ref.startswith("#"), ref
    for ref in re.findall(r"""url\(\s*["']?([^"')]*)""", svg, re.IGNORECASE):
        assert ref.startswith("#"), ref
