"""Tool-calling research agent: action parsing and the search/fetch loop."""

from __future__ import annotations

import json

import pytest

from lm_optimizer.services.research_agent import (
    ResearchAgent,
    extract_html,
    parse_action,
)
from lm_optimizer.services.web_research import SearchHit, Source


@pytest.mark.parametrize(
    "answer",
    [
        '{"action": "search", "query": "q"}',
        '```json\n{"action": "search", "query": "q"}\n```',
        'Sure: {"action": "search", "query": "q"} done',
    ],
)
def test_parse_action_tolerates_wrapping(answer: str) -> None:
    assert parse_action(answer) == {"action": "search", "query": "q"}


@pytest.mark.parametrize(
    "answer", ["", "no json here", '{"action": "dance"}', "[1, 2]"]
)
def test_parse_action_rejects_non_actions(answer: str) -> None:
    assert parse_action(answer) is None


def test_extract_html_strips_fences_and_preamble() -> None:
    answer = 'Here you go:\n```html\n<!DOCTYPE html><html><body>x</body></html>\n```'
    assert extract_html(answer) == "<!DOCTYPE html><html><body>x</body></html>"


class _FakeResearcher:
    def __init__(self) -> None:
        self.searches: list[str] = []
        self.scrapes: list[str] = []

    async def search(self, query: str) -> list[SearchHit]:
        self.searches.append(query)
        return [
            SearchHit("One", "https://example.com/one", "snippet"),
            SearchHit("Two", "https://example.com/two", "snippet"),
        ]

    async def scrape(self, hit: SearchHit, source_id: str, query: str) -> Source | None:
        self.scrapes.append(hit.url)
        return Source(id=source_id, title=hit.title, url=hit.url, text="content " * 100)


def _queue_ask(actions: list[str], report: str = "<!DOCTYPE html><html><body>report</body></html>"):
    calls = {"n": 0}

    async def ask(prompt: str, max_tokens: int = 512) -> str:
        calls["n"] += 1
        if "Next action JSON" in prompt:
            index = min(len(actions) - 1, sum(1 for _ in actions[: calls["n"]]) - 1)
            return actions[min(index, len(actions) - 1)]
        return report

    return ask


async def test_agent_searches_fetches_and_writes_report() -> None:
    researcher = _FakeResearcher()
    ask = _queue_ask(
        [
            '{"action": "search", "query": "alpha"}',
            '{"action": "fetch", "url": "https://example.com/one"}',
            '{"action": "fetch", "url": "https://example.com/two"}',
            '{"action": "finish"}',
        ]
    )
    agent = ResearchAgent(ask, researcher, max_steps=6)  # type: ignore[arg-type]

    result = await agent.run("Why?")

    assert researcher.searches == ["alpha"]
    assert researcher.scrapes == ["https://example.com/one", "https://example.com/two"]
    assert [s.id for s in result.sources] == ["S1", "S2"]
    assert result.tool_calls == 3
    assert result.fetches == 2
    assert "<!DOCTYPE html>" in result.report_html
    assert any(entry.tool == "finish" for entry in result.trace)


async def test_agent_refuses_urls_that_did_not_come_from_search() -> None:
    researcher = _FakeResearcher()
    ask = _queue_ask(
        [
            '{"action": "search", "query": "alpha"}',
            '{"action": "fetch", "url": "https://evil.example/x"}',
            '{"action": "fetch", "url": "https://example.com/one"}',
            '{"action": "finish"}',
        ]
    )
    agent = ResearchAgent(ask, researcher, max_steps=6)  # type: ignore[arg-type]

    result = await agent.run("Why?")

    assert "https://evil.example/x" not in researcher.scrapes
    assert result.fetches == 1
    assert any("refused unknown URL" in warning for warning in result.warnings)


async def test_agent_without_sources_returns_no_report() -> None:
    researcher = _FakeResearcher()
    ask = _queue_ask(['{"action": "finish"}'])
    agent = ResearchAgent(ask, researcher, max_steps=2)  # type: ignore[arg-type]

    result = await agent.run("Why?")

    assert result.sources == []
    assert result.report_html == ""
    assert "no pages were fetched" in result.warnings


def test_tools_used_check_requires_real_calls() -> None:
    from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, score_attempt

    task = SANDBOX_TASKS["deep_research_agent"]
    html = (
        "<!DOCTYPE html><html><body>"
        + ("<h2>Section</h2><p>" + ("word " * 200) + "[S1][S2][S3]</p>") * 3
        + "<h2>References</h2></body></html>"
    )
    trace = [
        {"tool": "search", "argument": "q", "ok": True},
        {"tool": "fetch", "argument": "https://a", "ok": True},
        {"tool": "fetch", "argument": "https://b", "ok": True},
    ]

    score, failing, critical = score_attempt(
        task,
        {"index.html": html, "trace.json": json.dumps(trace)},
    )
    assert score == pytest.approx(1.0), failing

    score, failing, critical = score_attempt(
        task,
        {"index.html": html, "trace.json": json.dumps(trace[:1])},
    )
    assert score == 0.0
    assert any("traces_tools_used" in name for name in critical)
