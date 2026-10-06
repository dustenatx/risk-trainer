"""R5 — home page, scenario list and `rt preview`."""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from typer.testing import CliRunner

from risk_trainer.cli.main import PREVIEW_HOST, app, serve_preview
from tests.helpers import RT001_TEXT, WriteScenario
from tests.web_helpers import RT001_ID, client, rt001


class _TextIn(HTMLParser):
    """Collects the text inside the element with a given id."""

    def __init__(self, element_id: str) -> None:
        super().__init__()
        self.element_id = element_id
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth:
            self.depth += 1
        elif ("id", self.element_id) in attrs:
            self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)


def text_of(html: str, element_id: str) -> str:
    parser = _TextIn(element_id)
    parser.feed(html)
    return " ".join(parser.parts)


def test_r5_home_explains_in_120_words_or_fewer() -> None:
    intro = text_of(client().get("/").text, "intro")
    words = re.findall(r"\b[\w'\u2019-]+\b", intro)
    assert 40 <= len(words) <= 120


def test_r5_home_links_to_four_responses_page() -> None:
    assert 'href="/responses"' in text_of_section(client().get("/").text)


def text_of_section(html: str) -> str:
    match = re.search(r'<section id="intro".*?</section>', html, re.DOTALL)
    assert match
    return match.group(0)


def test_r5_list_shows_title_difficulty_minutes_domains() -> None:
    scenario = rt001(cissp_domains=[1, 6])
    html = client([scenario]).get("/").text
    assert f'href="/s/{RT001_ID}">{scenario.title}</a>' in html
    assert "Foundational" in html
    assert f"About {scenario.estimated_minutes} minutes" in html
    assert "Domain 1" in html
    assert "Domain 6" in html


def test_r5_app_loads_only_approved_from_content(
    content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(RT001_TEXT)  # a draft
    from risk_trainer.storage.memory import MemoryAttemptStore
    from risk_trainer.web.app import create_app
    from tests.web_helpers import settings

    app_ = create_app(settings(content_dir=content_dir), MemoryAttemptStore())
    assert app_.state.scenarios == {}


def test_r5_preview_shows_drafts_with_banner_on_every_draft_page() -> None:
    test_client = client([rt001(status="draft")], preview=True)
    home = test_client.get("/").text
    assert "Local preview" in home
    assert 'class="tag tag-draft">DRAFT' in home
    exercise = test_client.get(f"/s/{RT001_ID}").text
    assert "<strong>DRAFT</strong>" in exercise
    from tests.web_helpers import submit

    assert "<strong>DRAFT</strong>" in submit(test_client).text


def test_r5_approved_pages_have_no_draft_banner() -> None:
    assert "<strong>DRAFT</strong>" not in client().get(f"/s/{RT001_ID}").text


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10"])  # noqa: S104
def test_r5_preview_refuses_non_loopback_host(host: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="loopback"):
        serve_preview(host, 8000, tmp_path, [])


def test_r5_preview_binds_loopback() -> None:
    assert PREVIEW_HOST == "127.0.0.1"


def test_r5_preview_has_no_host_option() -> None:
    result = CliRunner().invoke(app, ["preview", "--host", "0.0.0.0"])  # noqa: S104
    assert result.exit_code != 0
    assert "No such option" in result.output


def test_r5_preview_starts_server_on_loopback(
    monkeypatch: pytest.MonkeyPatch, content_dir: Path, write_scenario: WriteScenario
) -> None:
    write_scenario(RT001_TEXT)
    calls: dict[str, object] = {}

    def fake_run(web_app: object, host: str, port: int, log_config: object) -> None:
        calls.update(app=web_app, host=host, port=port)

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = CliRunner().invoke(app, ["preview", "--content-dir", str(content_dir)])
    assert result.exit_code == 0, result.output
    assert (calls["host"], calls["port"]) == ("127.0.0.1", 8000)
    assert RT001_ID in calls["app"].state.scenarios  # type: ignore[attr-defined]
