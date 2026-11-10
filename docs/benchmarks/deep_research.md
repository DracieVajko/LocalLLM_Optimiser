# Deep research benchmark (RACE/FACT, simplified)

Task id: `deep_research_report`.

Inspired by [DeepResearch Bench](https://deepresearch-bench.github.io/)
(100 PhD-level tasks, RACE for report quality + FACT for citation quality).
This is a **deterministic, offline** simplification: one research question with
a fixed source package, an HTML report, and static checks that mirror the four
RACE dimensions plus citation accuracy.

## Prompt (copy into the model under test)

```text
You are a deep research agent. Write a single self-contained HTML report
answering the question: 'What are the real limits of running a 70B MoE model on
consumer hardware with 24 GB VRAM, and how should conflicting Q3/Q4 speed claims
be resolved?'

Use ONLY the sources below. Cite every factual claim with the source name in
square brackets, e.g. [primary_official]. Do not invent sources. If the sources
do not answer something, say so explicitly. Include: a title, an executive
summary, at least four sections with headings, a 'Conflicting claims' section, a
'Limitations and uncertainty' section, and a References section. Render as a
clean print-ready HTML page (inline CSS, no external assets).

SOURCES:
--- primary_official ---
The LM Studio REST API v1 exposes POST /api/v1/models/load with the parameters
context_length, flash_attention, offload_kv_cache_to_gpu, eval_batch_size,
physical_batch_size, parallel, context_checkpoints, num_experts and
speculative_draft_max_tokens. Unknown keys are rejected with HTTP 400
unrecognized_keys before the model is loaded.

--- technical_secondary ---
The llama.cpp server exposes speculative decoding through --spec-type
draft-mtp and the MTP head shipped with Qwen3.8 models. On a dense 27B at
Q4_K_M the acceptance rate of n=3 drafts was about 73% and decode throughput
rose from 31.2 to 40.3 tok/s on a V100.

--- outdated_source ---
Older guides state that a 27B Q4_K_M model needs 17.5 GB of VRAM and therefore
cannot run on consumer cards at all. This guidance predates 3-bit quants and KV
cache quantization.

--- conflicting_source ---
A community benchmark claims Q3_K_M is faster than Q4_K_M because the model is
smaller, while another claims the opposite because Q3 requires more
dequantization steps. Both were measured on Apple Silicon, where the Q3 kernel
is known to be unusually slow.

--- irrelevant_source ---
A blog post about the history of the BASIC programming language describes how
early microcomputers stored programs on cassette tapes.

END OF SOURCES.
```

## Simplified RACE/FACT mapping

| Dimension (RACE/FACT) | Deterministic check |
|---|---|
| Comprehensiveness | `min_words` (800 text words), 4+ `<h2>/<h3>`, references |
| Depth | conflicting-claims resolution, limitations/uncertainty |
| Instruction-following | one HTML file, title, no external assets, no fences |
| Readability | headings, inline CSS, self-contained page |
| Citation accuracy (FACT) | `cites_primary` (critical), `cites_technical`, `cites_conflicting` |
| Effective citations (FACT) | only supplied source names; `no_irrelevant_source` (cassette) |
| Uncertainty | `mentions_uncertainty` (says what the sources do not answer) |

## Run locally

```powershell
python -m lm_optimizer.cli.main lab bakeoff --models <model-id> --tasks deep_research_report --context 8192 --safe
```

Artifacts: `results/bakeoff/<model>/deep_research_report/<timestamp>/index.html`
plus `debug.json`. Open the HTML in a browser; print to PDF from the browser.

## Compare frontier providers

The prompt is provider-agnostic. Run it in ChatGPT/OpenAI Deep Research, Gemini
Deep Research, Perplexity Deep Research, or Odysseus (PewDiePie), save each
answer as an HTML file, then score it with the same harness:

```powershell
python -m lm_optimizer.cli.main lab score-report reports/openai.html --model "OpenAI Deep Research"
```

Alternatively, use the batch form with one directory per provider:

```powershell
python tools/agent_benchmark.py --tasks deep_research_report ^
  --source reports/openai --model "OpenAI Deep Research" --out results/external
```

Repeat for Gemini, Perplexity and Odysseus. The recorded score is comparable
because the checks and the source package are identical.

**API keys are not included.** The repo only ships the prompt, task and scorer;
connecting a paid provider is the user's choice.

## Reference result

The committed DeepSeek V4.1 Flash artifact
(`benchmarks/deepseek_agent/deep_research_report/index.html`) scores **1.0** on
the deterministic checks.
