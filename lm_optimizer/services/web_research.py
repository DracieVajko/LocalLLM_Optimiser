"""Online deep research: plan queries, search, scrape pages, synthesise a report.

The offline ``deep_research_report`` sandbox task scores a report written from a
fixed source package. This module is the online counterpart used by
``lab research``:

1. plan   - the model splits the question into focused sub-queries
2. search - each query goes to DuckDuckGo's HTML endpoint (Wikipedia as a
            fallback when the engine returns nothing)
3. scrape - the top pages per query are fetched and reduced to readable text
4. write  - the model writes an HTML report that cites only the scraped
            sources as ``[S1]``, ``[S2]`` ...

Everything is plain ``httpx`` plus the standard library, so there is no new
dependency and no paid search API. The raw text of every source is written next
to the report, so a citation can always be checked against what was actually
downloaded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 LMStudioOptimiser/1.0"
)

DDG_HTML = "https://html.duckduckgo.com/html/"
WIKI_API = "https://en.wikipedia.org/w/api.php"

MAX_PAGE_BYTES = 2_000_000
MAX_SOURCE_CHARS = 6_000


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str = ""


@dataclass
class Source:
    id: str
    title: str
    url: str
    text: str
    query: str = ""

    def excerpt(self, limit: int = MAX_SOURCE_CHARS) -> str:
        return self.text[:limit]


@dataclass
class ResearchResult:
    question: str
    queries: list[str]
    sources: list[Source]
    report_html: str
    out_dir: Path
    warnings: list[str] = field(default_factory=list)

    def sources_payload(self) -> list[dict[str, str]]:
        return [
            {"id": s.id, "title": s.title, "url": s.url, "query": s.query}
            for s in self.sources
        ]


class _TextExtractor(HTMLParser):
    """Collect visible text, skipping scripts, styles, nav and footers."""

    SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "svg", "form"}
    BLOCK = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "br", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BLOCK and self._skip_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK and self._skip_depth == 0:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.parts.append(text + " ")

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed pages must not abort research
        return ""
    return parser.text()


def parse_duckduckgo(html: str, limit: int = 8) -> list[SearchHit]:
    """Extract result links and snippets from the DuckDuckGo HTML page."""
    hits: list[SearchHit] = []
    pattern = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>'
        r'(?:.*?class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>)?',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        url = _clean_url(match.group("url"))
        if not url:
            continue
        hits.append(
            SearchHit(
                title=_strip_tags(match.group("title")),
                url=url,
                snippet=_strip_tags(match.group("snippet") or ""),
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def _clean_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//duckduckgo.com/l/?uddg="):
        from urllib.parse import unquote

        url = url.split("uddg=", 1)[1].split("&", 1)[0]
        return unquote(url)
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return ""


def parse_wikipedia(payload: dict[str, Any]) -> list[SearchHit]:
    """Turn an opensearch response into hits."""
    titles = payload[1] if len(payload) > 1 else []
    urls = payload[3] if len(payload) > 3 else []
    return [
        SearchHit(title=title, url=url, snippet="")
        for title, url in zip(titles, urls, strict=False)
    ]


def plan_query_prompt(question: str, count: int) -> str:
    return (
        "You are planning web research. Break the question below into "
        f"{count} short, specific search queries that together cover it. "
        "Return ONLY a JSON array of strings, no prose, no markdown.\n\n"
        f"Question: {question}"
    )


def parse_query_plan(text: str, count: int) -> list[str]:
    """Pull a JSON string array out of a model answer, tolerating fences."""
    match = re.search(r"\[[\s\S]*\]", text or "")
    queries: list[str] = []
    if match:
        try:
            data = json.loads(match.group(0))
            queries = [str(item).strip() for item in data if str(item).strip()]
        except json.JSONDecodeError:
            queries = []
    if not queries:
        queries = [line.strip(" -*\t") for line in (text or "").splitlines() if line.strip()]
    return queries[:count]


def build_report_prompt(question: str, sources: Iterable[Source]) -> str:
    blocks = []
    for source in sources:
        blocks.append(
            f"--- {source.id} ---\n"
            f"title: {source.title}\n"
            f"url: {source.url}\n"
            f"{source.excerpt()}\n"
        )
    return (
        "You are a research analyst. Write a single self-contained HTML report "
        f"that answers this question:\n\n{question}\n\n"
        "Rules:\n"
        "- Use ONLY the sources below. Do not invent facts or sources.\n"
        "- Cite every factual claim with the source id in square brackets, "
        "for example [S1] or [S2][S3].\n"
        "- If the sources disagree, say so and explain which is more credible "
        "and why.\n"
        "- Add a 'Limitations' section listing what the sources do not answer.\n"
        "- Include a References section listing every source id, title and URL.\n"
        "- Output inline CSS, no external assets, no markdown fences. Start with "
        "<!DOCTYPE html>.\n\n"
        "SOURCES:\n\n" + "\n".join(blocks)
    )


class WebResearcher:
    """Multi-query search + scrape + synthesis."""

    def __init__(
        self,
        *,
        queries: int = 4,
        results_per_query: int = 4,
        pages_per_query: int = 2,
        max_sources: int = 6,
        timeout_s: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.queries = queries
        self.results_per_query = results_per_query
        self.pages_per_query = pages_per_query
        self.max_sources = max_sources
        self.timeout_s = timeout_s
        self._client = client

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout_s,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def search(self, query: str) -> list[SearchHit]:
        client = await self._http()
        try:
            response = await client.get(DDG_HTML, params={"q": query})
            if response.status_code == 200:
                hits = parse_duckduckgo(response.text, limit=self.results_per_query)
                if hits:
                    return hits
        except httpx.HTTPError:
            pass

        try:
            response = await client.get(
                WIKI_API,
                params={
                    "action": "opensearch",
                    "search": query,
                    "limit": self.results_per_query,
                    "format": "json",
                },
            )
            if response.status_code == 200:
                return parse_wikipedia(response.json())
        except (httpx.HTTPError, json.JSONDecodeError):
            pass
        return []

    async def scrape(self, hit: SearchHit, source_id: str, query: str) -> Source | None:
        client = await self._http()
        try:
            response = await client.get(hit.url)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            return None
        body = response.text[:MAX_PAGE_BYTES]
        text = html_to_text(body)
        if len(text) < 200:
            return None
        return Source(id=source_id, title=hit.title or hit.url, url=hit.url, text=text, query=query)

    async def collect(self, queries: list[str]) -> tuple[list[Source], list[str]]:
        sources: list[Source] = []
        seen_urls: set[str] = set()
        warnings: list[str] = []
        for query in queries:
            hits = await self.search(query)
            if not hits:
                warnings.append(f"no search results for {query!r}")
                continue
            taken = 0
            for hit in hits:
                if taken >= self.pages_per_query or len(sources) >= self.max_sources:
                    break
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                source = await self.scrape(hit, f"S{len(sources) + 1}", query)
                if source is None:
                    continue
                sources.append(source)
                taken += 1
            if len(sources) >= self.max_sources:
                break
        return sources, warnings


async def plan_queries(question: str, ask: Any, count: int = 4) -> list[str]:
    """Ask the model for sub-queries; fall back to question variants."""
    try:
        answer = await ask(plan_query_prompt(question, count))
        planned = parse_query_plan(answer, count)
    except Exception:  # noqa: BLE001 - planning must never abort research
        planned = []
    if len(planned) >= 2:
        return planned
    return [
        question,
        f"{question} benchmark",
        f"{question} limitations",
        f"{question} comparison",
    ][:count]
