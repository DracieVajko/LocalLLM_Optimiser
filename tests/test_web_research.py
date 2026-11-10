"""Online research helpers: parsing, planning and the scrape loop."""

from __future__ import annotations

from typing import Any

import pytest

from lm_optimizer.services.web_research import (
    SearchHit,
    WebResearcher,
    build_report_prompt,
    html_to_text,
    parse_duckduckgo,
    parse_query_plan,
    parse_wikipedia,
    plan_queries,
    Source,
)


def test_html_to_text_drops_scripts_and_nav() -> None:
    html = """
    <html><body>
      <nav>menu menu menu</nav>
      <h1>Title</h1>
      <p>First paragraph with content.</p>
      <script>var secret = 'ignore me';</script>
      <footer>footer text</footer>
    </body></html>
    """
    text = html_to_text(html)
    assert "First paragraph" in text
    assert "secret" not in text
    assert "menu menu" not in text
    assert "footer text" not in text


def test_parse_duckduckgo_unwraps_redirect_links() -> None:
    html = (
        '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=1">'
        "Example A</a>"
        '<a class="result__snippet">Snippet A</a>'
        '<a class="result__a" href="https://example.org/b">Example B</a>'
    )
    hits = parse_duckduckgo(html)

    assert [h.url for h in hits] == ["https://example.com/a", "https://example.org/b"]
    assert hits[0].title == "Example A"
    assert hits[0].snippet == "Snippet A"


def test_parse_wikipedia_opensearch() -> None:
    payload: list[Any] = ["q", ["A", "B"], ["", ""], ["https://en.wikipedia.org/A", "https://en.wikipedia.org/B"]]
    hits = parse_wikipedia(payload)
    assert [h.title for h in hits] == ["A", "B"]
    assert hits[1].url.endswith("/B")


@pytest.mark.parametrize(
    "answer",
    [
        '["q1", "q2", "q3"]',
        '```json\n["q1", "q2", "q3"]\n```',
        'Sure, here you go:\n["q1", "q2", "q3"]',
    ],
)
def test_parse_query_plan_tolerates_wrapping(answer: str) -> None:
    assert parse_query_plan(answer, 3) == ["q1", "q2", "q3"]


def test_parse_query_plan_falls_back_to_lines() -> None:
    assert parse_query_plan("- alpha\n- beta", 5) == ["alpha", "beta"]


async def test_plan_queries_falls_back_when_model_replies_with_prose() -> None:
    async def ask(_prompt: str) -> str:
        return "I cannot produce JSON today."

    queries = await plan_queries("Does a 70B fit on 24 GB?", ask, count=3)

    assert len(queries) == 3
    assert queries[0] == "Does a 70B fit on 24 GB?"


def test_build_report_prompt_includes_each_source() -> None:
    sources = [
        Source(id="S1", title="A", url="https://a.example", text="alpha " * 200),
        Source(id="S2", title="B", url="https://b.example", text="beta " * 200),
    ]
    prompt = build_report_prompt("Why?", sources)

    assert "--- S1 ---" in prompt and "--- S2 ---" in prompt
    assert "https://a.example" in prompt
    assert "Do not invent facts" in prompt


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict | None = None, data: Any = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"content-type": "text/html"}
        self._data = data

    def json(self) -> Any:
        return self._data


class _FakeClient:
    def __init__(self) -> None:
        self.requested: list[str] = []

    async def get(self, url: str, params: dict | None = None, **_: Any) -> _FakeResponse:
        if url.endswith("html.duckduckgo.com/html/"):
            query = (params or {}).get("q", "")
            self.requested.append(f"search:{query}")
            return _FakeResponse(
                200,
                f'<a class="result__a" href="https://page.example/{query}">{query}</a>',
            )
        self.requested.append(url)
        return _FakeResponse(200, "<html><body><p>" + "content " * 200 + "</p></body></html>")

    async def aclose(self) -> None:
        return None


async def test_collect_scrapes_one_page_per_query() -> None:
    fake = _FakeClient()
    researcher = WebResearcher(pages_per_query=1, max_sources=2, client=fake)  # type: ignore[arg-type]

    sources, warnings = await researcher.collect(["alpha", "beta"])

    assert not warnings
    assert [s.id for s in sources] == ["S1", "S2"]
    assert sources[0].url == "https://page.example/alpha"
    assert "content" in sources[0].text
    assert any(r.startswith("search:") for r in fake.requested)


async def test_collect_warns_when_search_returns_nothing() -> None:
    class _Empty:
        async def get(self, url: str, params: dict | None = None, **_: Any) -> _FakeResponse:
            return _FakeResponse(200, "<html>no results</html>", data=["q", [], [], []])

        async def aclose(self) -> None:
            return None

    researcher = WebResearcher(client=_Empty())  # type: ignore[arg-type]
    sources, warnings = await researcher.collect(["nothing"])

    assert sources == []
    assert warnings and "no search results" in warnings[0]


async def test_scrape_skips_short_pages() -> None:
    class _Short:
        async def get(self, url: str, **_: Any) -> _FakeResponse:
            return _FakeResponse(200, "<html><body><p>tiny</p></body></html>")

        async def aclose(self) -> None:
            return None

    researcher = WebResearcher(client=_Short())  # type: ignore[arg-type]
    source = await researcher.scrape(SearchHit(title="t", url="https://x.example"), "S1", "q")

    assert source is None
