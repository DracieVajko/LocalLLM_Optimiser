"""Tool-calling research agent: the model decides what to search and fetch.

``lab research --mode pipeline`` plans queries up front, scrapes, then writes.
This module is the agent variant: the model is given two tools and drives the
loop itself, one JSON action per turn:

    {"action": "search", "query": "..."}
    {"action": "fetch", "url": "https://..."}
    {"action": "finish"}

Every call is recorded in a trace, and only fetched pages become citable
sources ([S1], [S2]...). The final step asks for the HTML report using the
collected sources.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from lm_optimizer.services.web_research import (
    SearchHit,
    Source,
    WebResearcher,
    build_report_prompt,
)

MAX_STEPS = 8
MAX_RESULTS_SHOWN = 5
MAX_EXCERPT = 1200

SYSTEM_PROMPT = (
    "You are a research agent with two tools.\n"
    "search: {\"action\": \"search\", \"query\": \"...\"}\n"
    "fetch:  {\"action\": \"fetch\", \"url\": \"https://...\"}\n"
    "When you have enough evidence, answer {\"action\": \"finish\"}.\n"
    "Reply with exactly one JSON object per turn and nothing else. "
    "Do not invent URLs: only fetch URLs returned by search."
)


@dataclass
class AgentTraceEntry:
    tool: str
    argument: str
    ok: bool
    detail: str = ""


@dataclass
class AgentResult:
    question: str
    report_html: str
    sources: list[Source] = field(default_factory=list)
    trace: list[AgentTraceEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def trace_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "tool": item.tool,
                "argument": item.argument,
                "ok": item.ok,
                "detail": item.detail,
            }
            for item in self.trace
        ]

    @property
    def tool_calls(self) -> int:
        return sum(1 for item in self.trace if item.tool in ("search", "fetch"))

    @property
    def fetches(self) -> int:
        return sum(1 for item in self.trace if item.tool == "fetch" and item.ok)


def parse_action(text: str) -> dict[str, Any] | None:
    """Extract one JSON action object from a model answer."""
    body = text or ""
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", body)
    if fenced:
        body = fenced.group(1)
    else:
        brace = re.search(r"\{[\s\S]*\}", body)
        body = brace.group(0) if brace else body
    try:
        data = json.loads(body.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action") or "").strip().lower()
    if action not in ("search", "fetch", "finish"):
        return None
    return data


class ResearchAgent:
    """Drive search/fetch through the model, then write the report."""

    def __init__(
        self,
        ask: Callable[[str, int], Awaitable[str]],
        researcher: WebResearcher,
        *,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self._ask = ask
        self._researcher = researcher
        self.max_steps = max_steps

    async def run(self, question: str) -> AgentResult:
        result = AgentResult(question=question, report_html="")
        transcript: list[str] = []
        sources: list[Source] = []
        seen_urls: set[str] = set()
        hits_by_url: dict[str, SearchHit] = {}

        for step in range(self.max_steps):
            prompt = self._step_prompt(question, transcript)
            answer = await self._ask(prompt, 512)
            action = parse_action(answer)
            if action is None:
                transcript.append(
                    "SYSTEM: that was not a valid action JSON; reply with one object."
                )
                result.warnings.append(f"step {step + 1}: unparseable action")
                continue

            kind = str(action["action"]).lower()
            if kind == "finish":
                result.trace.append(AgentTraceEntry("finish", "", True))
                break

            if kind == "search":
                query = str(action.get("query") or "").strip()
                if not query:
                    result.warnings.append(f"step {step + 1}: empty search query")
                    continue
                hits = await self._researcher.search(query)
                for hit in hits:
                    hits_by_url[hit.url] = hit
                listing = "\n".join(
                    f"- {hit.title} :: {hit.url}" for hit in hits[:MAX_RESULTS_SHOWN]
                )
                transcript.append(f"SEARCH {query!r} returned {len(hits)} result(s):\n{listing}")
                result.trace.append(
                    AgentTraceEntry("search", query, bool(hits), f"{len(hits)} result(s)")
                )
                continue

            url = str(action.get("url") or "").strip()
            hit = hits_by_url.get(url)
            if hit is None:
                transcript.append(
                    f"SYSTEM: {url!r} was not returned by search; search first."
                )
                result.trace.append(AgentTraceEntry("fetch", url, False, "url not from search"))
                result.warnings.append(f"step {step + 1}: refused unknown URL {url}")
                continue
            if url in seen_urls:
                transcript.append(f"SYSTEM: {url} is already fetched.")
                continue
            seen_urls.add(url)
            source = await self._researcher.scrape(hit, f"S{len(sources) + 1}", "agent")
            if source is None:
                result.trace.append(AgentTraceEntry("fetch", url, False, "fetch failed"))
                transcript.append(f"FETCH {url} failed; try another result.")
                continue
            sources.append(source)
            result.trace.append(
                AgentTraceEntry("fetch", url, True, f"{len(source.text)} chars")
            )
            transcript.append(
                f"FETCH {url} -> {source.id} ({len(source.text)} chars):\n"
                f"{source.text[:MAX_EXCERPT]}"
            )

        if not sources:
            result.warnings.append("no pages were fetched")
            result.report_html = ""
            result.sources = []
            result.trace = result.trace
            return result

        report = await self._ask(build_report_prompt(question, sources), 8192)
        result.report_html = extract_html(report)
        result.sources = sources
        return result

    def _step_prompt(self, question: str, transcript: list[str]) -> str:
        history = "\n\n".join(transcript) if transcript else "(no calls yet)"
        return (
            f"{SYSTEM_PROMPT}\n\nQUESTION: {question}\n\n"
            f"TRANSCRIPT:\n{history}\n\n"
            "Next action JSON:"
        )


def extract_html(text: str) -> str:
    """Return the HTML document from a model answer, fences stripped."""
    body = (text or "").strip()
    fenced = re.search(r"```(?:html)?\s*([\s\S]*?)```", body)
    if fenced:
        body = fenced.group(1).strip()
    start = body.find("<!DOCTYPE")
    if start < 0:
        start = body.find("<html")
    if start > 0:
        body = body[start:]
    return body


def html_sources(sources: list[Source]) -> list[dict[str, str]]:
    return [{"id": s.id, "title": s.title, "url": s.url} for s in sources]
