# Where deep-research data comes from

Three different things in this repo are called "deep research". They use very
different data sources, which matters when you compare scores.

## 1. `deep_research_report` — offline, fixed source package

The sandbox task is deliberately offline. The prompt contains five source
blocks (primary, technical, outdated, conflicting, irrelevant) written into
`lm_optimizer/services/sandbox_lab.py` as `RESEARCH_PACKAGE`. The model gets no
network access; it must write the report from that text and nothing else.

This is why the task is scorable: the correct answer is defined by the package.
The checks require citations to the supplied source names, a conflict
resolution, an explicit "the sources do not answer this" statement and a
references section.

- Data source: 5 hand-written paragraphs inside the task definition.
- Deterministic: yes. Same prompt for every model.
- Weakness: it tests *using* sources, not *finding* them.

## 2. `deepresearch-bench` — the official benchmark, no retrieval

`python -m lm_optimizer.cli.main deepresearch-bench` clones
[DeepResearch Bench](https://deepresearch-bench.github.io/) and runs its 100
PhD-level queries through a local LM Studio model. The questions come from
their `data/prompt_data/query.jsonl`.

The model answers from its own weights; the upstream pipeline does not fetch
pages for you. Their RACE (Comprehensiveness, Depth, Instruction-Following,
Readability) and FACT (citation accuracy) evaluators then call a frontier model,
which needs `OPENROUTER_API_KEY` or `OPENAI_API_KEY`.

- Data source: the benchmark's own question file + whatever the model knows.
- Deterministic: questions yes, scores no (LLM judge).
- Needs: internet for the clone, API keys for evaluation.

## 3. `lab research` — online, multi-query, scraped

This is the actual "go and read the web" command:

```powershell
python -m lm_optimizer.cli.main lab research "Do 70B MoE models fit on 24 GB?" --model <model> --queries 4 --sources 6
```

Two modes:

- `--mode agent` (default) — the model is given real tools and drives the loop
  itself (`lm_optimizer/services/research_agent.py`):

  ```
  {"action": "search", "query": "..."}   -> DuckDuckGo results
  {"action": "fetch",  "url": "https://..."} -> page text
  {"action": "finish"}
  ```

  It may only fetch URLs that search returned, every call is recorded in
  `trace.json`, and only fetched pages become citable sources. The report is
  written after the loop from those sources.
- `--mode pipeline` — the fixed plan → search → scrape → write pipeline
  (`lm_optimizer/services/web_research.py`): the model plans N queries, the
  harness scrapes the top pages, then the model writes the report.

Pipeline steps (both modes use the same tools):

1. **plan** — the model splits the question into N focused search queries.
   If it answers with prose instead of a JSON array, the planner falls back to
   query variants (`<question> benchmark`, `<question> limitations`, ...).
2. **search** — each query goes to DuckDuckGo's HTML endpoint
   (`html.duckduckgo.com/html/`). If that returns nothing, the Wikipedia
   opensearch API is used as a fallback. No API key, no paid search.
3. **scrape** — the top 1-2 pages per query are downloaded (2 MB cap, HTML
   only) and reduced to readable text by a stdlib `HTMLParser` that drops
   scripts, styles, nav, footers and forms.
4. **synthesise** — the model writes one HTML report citing sources as
   `[S1]`, `[S2]`, ... using only the scraped text.

Output per run (`results/research/<slug>_<stamp>/`):

| File | Content |
|---|---|
| `report.html` | the generated report |
| `sources.json` | question, planned queries, warnings, and every scraped source id/title/url |
| `raw/S1.txt` … | the exact text that was sent to the model |

Because the raw text is kept, a citation can always be audited: `[S3]` maps to
one URL and one file. That is the property the offline task cannot give you.

Score the result with the dedicated task:

```powershell
python -m lm_optimizer.cli.main lab score-report results/research/<run>/report.html --task deep_research_online
```

`deep_research_online` requires a real HTML document, at least 600 words, three
*or more distinct* `[S#]` citations, a limitations section and a references
section. It does not care which URLs were used, so it also works for reports
produced by other agents.

## Which one should you use?

| Goal | Use |
|---|---|
| Fair, repeatable model comparison | `deep_research_report` |
| Public leaderboard comparison | `deepresearch-bench` |
| Answer a real question with real sources | `lab research` |
| Judge a report from GPT/Gemini/Perplexity/Odysseus | `lab score-report --task deep_research_online` |

## Known limits of the online mode

- DuckDuckGo may rate-limit or change its HTML markup; the parser then returns
  no hits and the run reports `no search results for ...` instead of inventing
  sources.
- Only HTML pages are scraped. PDFs, paywalled articles and JavaScript-only
  pages are skipped.
- Search snippets are not trusted as evidence; only the scraped page text is
  passed to the model.
- The model can still hallucinate a claim next to a valid `[S2]` marker. The
  raw files are the check for that; the automated task only verifies that
  citations exist and are distinct.
