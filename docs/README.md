# Docs map

| Path | What it is |
|---|---|
| `ARCHITECTURE.md` | Layers, module map and data flow of the whole system. |
| `CONFIGURATION.md` | Every environment variable, its default and what it influences. |
| `HARDWARE.md` | What was verified on which hardware - and what was not. |
| `TROUBLESHOOTING.md` | Symptoms, real causes and the fixes that worked. |
| `CONTRIBUTING.md` | How to contribute a change (and what the bar is). |
| `DEVELOPMENT.md` | Development setup, checks, repository layout. |
| `OPTIMIZATION_METHOD.md` | The full search strategy: phases, gates, failure taxonomy. |
| `OPTIMIZATION_STRATEGY.md` | Why the strategy is shaped that way. |
| `PARAMETERS.md` | The load/inference parameter reference. |
| `LM_STUDIO_DEFAULTS.md` | Per-model load-defaults file: layout, verified echo test, field mapping and safety rules for persisting a winner. |
| `metrics_semantics.md` | What every metric means, how medians vs means are computed, and which values are estimates. |
| `MEASUREMENT_CONTAMINATION.md` | How a polluted machine invalidates a measurement. |
| `benchmarks/` | The published benchmark: prompts, acceptance checks, frontier artifacts and the failure analysis. |
| `specs/LM_STUDIO_OPTIMISER_MASTER_SPEC_SK.md` | **Master product + implementation specification** (the "Delete after everything from this folder is done" folder, archived here). Sections are referenced from the implementation as "spec §N". |
| `agents/OPENCODE_MASTER_PROMPT_LM_STUDIO_OPTIMISER_SK.md` | Agent prompt for a fresh audit/plan pass over the repository. Use it when the code has drifted from the spec, or for a new contributor. |
| `research/lmstudio-api-deep-dive.txt` | Raw research notes on the LM Studio API surface: REST v1 endpoints, SDK-only parameters (K/V cache quantization, CPU threads, mmap, draft model), MTP/speculative decoding, and community benchmark data for 6 GB class hardware. |
| `specs/2026-10-19-llm-judge-design.md` | LLM-as-judge design (Tasks 1-11 of the judge plan). |
| `specs/2026-10-15-auto-run-design.md` | Auto-run orchestration design. |
| `specs/2026-10-02-multi-backend-design.md` | Multi-backend (LM Studio / Ollama) design. |
| `superpowers/plans/` | Implementation plans with step-by-step task lists. |

## How the spec maps onto the code

| Spec section | Implementation |
|---|---|
| §5.2 / §5.3 load + inference parameters | `lm_optimizer/domain/models.py::LoadConfiguration`, `lm_optimizer/services/lm_studio.py` (capability discovery), `lm_optimizer/services/lm_studio_capabilities.py` (what THIS build accepts) |
| §5.4 MTP / speculative decoding | `LoadConfiguration.speculative_draft_*`, `lm_optimizer/services/benchmark.py::_extract_mtp_metrics`, `BenchmarkMetrics.draft_*` |
| §5.5 requested vs applied config | `lm_optimizer/api/client.py` (load echo), `lm_optimizer/services/optimizer.py` (generation.load_verification) |
| §8 Context Explorer | `lm_optimizer/services/context_explorer.py`, CLI `lm-optimizer ctx` and `lm-optimizer lab context-explorer` |
| §9 failure taxonomy | `lm_optimizer/domain/models.py::ConfigurationStatus`, `lm_optimizer/services/context_explorer.py::PointVerdict` |
| §11 real measurement | `lm_optimizer/services/benchmark.py` (server TTFT / prompt / decode split) |
| §12 Quality Lab | `lm_optimizer/services/quality_lab.py`, CLI `lm-optimizer lab quality-lab` |
| §13 Sandbox Lab | `lm_optimizer/services/sandbox_lab.py` (tasky + kritériá + repair loop + security), `lm_optimizer/services/sandbox_runner.py` (izolovaný workdir, allowlist, timeout) |
| §14 Model Duel | `lm_optimizer/services/duel.py`, CLI `lm-optimizer lab duel` |
| §15 Fast/Detailed | `lm_optimizer/cli/main.py` (profily), `tools/granular_suite.py` (rýchly subset) |
| §16 Model Recommender | `lm_optimizer/services/recommender.py`, `lm_optimizer/services/community_benchmarks.py` (community DB s confidence A–D), CLI `lm-optimizer lab recommend` |
| §21 database model | `lm_optimizer/database/repositories.py`, `lm_optimizer/storage/` |

## Not yet implemented (honest list)

### Still genuinely missing

- **Open-web research sandbox**: the closed-package research task ships
  with primary/technical/outdated/conflicting/irrelevant sources; the
  agentic open-web variant would need network access and a query budget.
- **SHA256 model hashing**: the catalog schema carries a `sha256` field but
  the hashes are not computed (the file bytes are not hashed on import).
- **Artifact retention**: `SandboxPolicy.artifact_retention` is recorded but
  no pruning is applied yet.
- **Model catalogue scraping**: the recommender ships a curated catalogue
  of ~10 entries for this hardware class; there is no crawler.
- **KV cache quantization / CPU threads / mmap search** - impossible on this
  LM Studio build over REST (probed: 400 `unrecognized_keys`); they are
  recorded as runtime facts instead.
- **llama.cpp as an inference backend**: the client exists in
  `lm_optimizer/backends/llamacpp/`, but no CLI command reaches it.

### Deliberate limits

- **Blender renders**: the Blender task forbids rendering, so the
  `.blend` is validated structurally (mesh count, height variety, footprint,
  camera, light) and no PNG is produced. Rendering the scene is the user's
  call, not the benchmark's.
- **A validator that is not installed cannot validate.** If Node.js, Blender
  or a browser is missing, the affected check reports that it could not run
  - it never counts as a pass.
