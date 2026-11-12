# LocalLLM Optimiser

[![ci](https://github.com/DracieVajko/LocalLLM_Optimiser/actions/workflows/ci.yml/badge.svg)](https://github.com/DracieVajko/LocalLLM_Optimiser/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![sponsor](https://img.shields.io/badge/sponsor-GitHub-ea4aaa?logo=github)](https://github.com/sponsors/DracieVajko)

**Detect your hardware, benchmark your local models, and find the inference
settings that actually work on your machine.**

LocalLLM Optimiser measures instead of guessing. It loads a model through
[LM Studio](https://lmstudio.ai), sweeps the settings that LM Studio exposes
over REST, and keeps the fastest configuration that still passes a fixed
quality suite. It also runs a model sandbox - small, reproducible tasks with
real acceptance checks - so two models can be compared on the same prompt, and
the resulting artifacts can be inspected.

The project does **not** promise a speed-up. It reports what it measured on
your hardware, with the evidence attached.

---

## 1. Introduction

A local model on the same GPU can differ by 2x in tokens per second depending
on context length, flash attention, KV-cache placement and batch sizes. Those
settings are also the ones that decide whether a 27B model fits into 6 GB of
VRAM at all.

This tool automates that search:

* **Probes** what your LM Studio build actually accepts (unknown keys are
  rejected without loading, so probing is safe).
* **Benchmarks** candidate configurations on your machine - load time,
  generation time, time to first token, memory.
* **Validates** quality with a fixed suite, so the fastest configuration that
  breaks the output never wins.
* **Explains** every result: which configuration won, which ones failed, and
  why.
* **Persists** the winner into LM Studio's per-model load defaults (with a
  backup), so the next load uses it.

Everything runs against a local LM Studio instance. No data leaves your
machine.

## 2. Main capabilities

| Area | What it does | Measured or estimated? |
|---|---|---|
| Hardware detection | GPU name/VRAM, RAM, swap, CPU threads, per-drive free space; Apple Silicon reports unified memory honestly (no fake VRAM) | **Measured** (via `nvidia-smi` / `psutil` / OS APIs) |
| Load-parameter probe | Sends every candidate key to the server, records which are accepted (400 = rejected, no model loaded) | **Measured** (server response) |
| Speed search | Context length × flash attention × KV placement × batch sizes | **Measured** (server timing) |
| Quality suite | 5 fixed tests (instruction, reasoning, long context, coding, structured output) with hard gates | **Measured** (test output) |
| Model fit | Whether a model file fits the free VRAM, based on file size and bits per weight | **Estimated** (labelled as such) |
| Sandbox tasks | 5 core tasks + extended tasks, scored by file/keyword/structure checks, pixels for visual output | **Measured** (checks and pixels) |
| Model bake-off | One model at a time, load time separated from generation time, per-task reports | **Measured** |
| Frontier comparison | Same prompt for a hosted model, imported and scored with the same checks | **Measured** for the artifact, **not** for the provider's own hardware |

## 3. Supported systems

Only combinations that are actually exercised are listed. "CI" means the full
test suite runs there; it does **not** mean a live LM Studio session was
verified there.

| System | Status | Notes |
|---|---|---|
| Windows 10/11 + NVIDIA (CUDA) | **Verified live** | Reference host: RTX 3060 6 GB, 16 GB RAM |
| Windows + CPU only | Coded and unit-tested | No physical CPU-only run was recorded |
| Linux | CI (Ubuntu runner) | Launchers exist (`start.sh`); no live LM Studio run recorded here |
| macOS | CI (macOS runner) | Same as Linux; Apple Silicon memory is reported as unified memory |
| AMD GPU | **Not verified** | No ROCm/Vulkan run was recorded; treat every number as unverified |
| LM Studio (Developer server) | **Verified live** | The only fully supported inference backend |
| Ollama | **Beta** | Client implemented against the documented API, mock-tested only - see [§8](#8-ollama-support-and-its-actual-status) |
| llama.cpp | **Not reachable** | A `llama-server` client exists in `lm_optimizer/backends/llamacpp/`, but no CLI command exposes it yet |

Details and the reasoning behind each row: [`docs/HARDWARE.md`](docs/HARDWARE.md).

## 4. Prerequisites

* **Python 3.11+** (3.12 recommended).
* **LM Studio** with the Developer server enabled (default port `1234`).
* A downloaded model in LM Studio (GGUF).
* **Node.js** - optional, only needed to validate JavaScript in sandbox output.
* **Blender** - optional, only needed for the `blender_city` task.
* A Chromium-based browser (Chrome or Edge) - optional, needed for pixel-level
  checks of rendered HTML.

Everything else (SQLite, the web UI, the reports) ships with the repository.

## 5. Installation

```bash
git clone https://github.com/DracieVajko/LocalLLM_Optimiser.git
cd LocalLLM_Optimiser

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"
```

Optional launchers for Windows (`.bat`) and Linux/macOS (`.sh`) are in the
repository root (`start.bat`, `start.sh`).

## 6. Quick start

```bash
# 1. Is LM Studio reachable, and what does this build accept?
lm-optimizer status

# 2. Which models are downloaded, and how big are they?
lm-optimizer models

# 3. What fits into my VRAM?
lm-optimizer recommend --vram 6

# 4. Benchmark one model across candidate configurations.
lm-optimizer benchmark qwen3.8-9b-distill --context 8192 --style balanced

# 5. Search for the best configuration (speed first, then quality validation).
lm-optimizer optimize qwen3.8-9b-distill --profile balanced

# 6. Run the sandbox suite and compare two models on the same task.
lm-optimizer lab sandbox --task company_website --model qwen3.8-9b-distill
lm-optimizer lab bakeoff --models all --tasks email_write,company_website
```

The web UI is the same functionality with a browser front end:

```bash
python -m lm_optimizer.web_main      # http://127.0.0.1:8080
```

## 7. Connecting LM Studio

1. Start LM Studio and enable the **Developer server** (Developer tab →
   "Start Server"). It listens on `http://127.0.0.1:1234` by default.
2. Check the connection:

   ```bash
   lm-optimizer status
   ```

3. Point the tool at a different server or port if needed:

   ```bash
   lm-optimizer status --base-url http://127.0.0.1:1235
   # or permanently, in .env:
   # LM_STUDIO_BASE_URL=http://127.0.0.1:1235
   ```

Two LM Studio settings **cannot** be changed over REST and must be set in the
GUI:

* **KV-cache quantization** (K/V cache type) - the tool reads the current
  value out of LM Studio's per-model defaults file and records it with every
  run, so a Q4 run and a Q8 run never get mixed up.
* **CPU thread pool size** - recorded the same way.

**Keep "Keep Model in Memory" OFF** while a run is in progress. With it on,
LM Studio does not release the model, the next run cannot get the slot, and
the tool stops fail-closed instead of measuring against a polluted machine.

The tool refuses to score a *remote* LM Studio instance, because the numbers
would describe someone else's hardware.

## 8. Ollama support and its actual status

Ollama is a **beta** backend, not a finished feature:

* The client (`lm_optimizer/backends/ollama/`) implements discovery
  (`/api/tags`), details (`/api/show`), generation (`/api/generate`),
  metrics and the unload protocol.
* It is covered by mocked-HTTPX tests. **No live Ollama server was exercised
  by this repository's test suite.**
* The CLI exposes it explicitly:

  ```bash
  lm-optimizer --backend ollama models
  lm-optimizer ollama-probe --model <tag>
  lm-optimizer ollama-export --model <tag> --param num_ctx=4096 -o best.modelfile.md
  lm-optimizer ollama-apply --file best.modelfile.md --as <tag>:opt --yes
  ```

* The live checklist for a first real run is in
  [`docs/OLLAMA_LIVE_CHECK.md`](docs/OLLAMA_LIVE_CHECK.md).

llama.cpp is **not** usable yet: `lm_optimizer/backends/llamacpp/` contains a
`llama-server` process manager, but no command reaches it. Treat it as
unfinished work, not as a supported backend.

## 9. Hardware detection

`lm-optimizer status` and the `lab recommend` workflow report:

* GPU name, count and VRAM - via `nvidia-smi` where available, with graceful
  degradation when it is not.
* System RAM, swap usage and per-drive free space.
* Apple Silicon: unified memory is reported as such; there is no separate
  VRAM number to pretend.
* A model-fit table based on **file size and bits per weight** - not on the
  parameter count. A 27B model at Q1_0 fits a 6 GB card; the same model at Q4
  does not.

When `nvidia-smi` is missing, the tool says so instead of guessing.

## 10. Running benchmarks

The benchmark suite is the **sandbox**: small tasks with acceptance checks.

Core set (used for model comparisons):

| Task | What it proves |
|---|---|
| `email_write` | Instruction following - reasoning leakage shows up immediately |
| `company_website` | Visual HTML: layout, responsiveness, a real render |
| `minecraft_world` | 3D: a scene is actually drawn (pixel check, not page text) |
| `blender_city` | An openable `.blend` file as the deliverable (no renders) |
| `deep_research_report` | Long-form synthesis with citations |

Extended tasks (`calendar_event`, `web_fetch_brief`, `web_search`,
`deep_research_online`, `deep_research_agent`, `research_synthesis`,
`creative_3d_voxel_island`, ...) are available for targeted questions; see
[`docs/BENCHMARK_TESTS_DETAIL.md`](docs/BENCHMARK_TESTS_DETAIL.md).

```bash
# one model, one task, with the repair loop
lm-optimizer lab sandbox --task blender_city --model prism-ml/bonsai-27b

# a matrix, one model at a time
lm-optimizer lab bakeoff --models qwen3.8-9b-distill,prism-ml/bonsai-27b \
    --tasks email_write,company_website,blender_city --context 4096
```

Results land in `results/bakeoff/runs.jsonl` (git-ignored) with load time,
generation time, tokens, tokens per second and the sandbox score per task.

**Two rules keep the numbers honest:**

* **One model at a time.** The model gate (`MODEL_GATE_MAX_LOADED_MODELS`,
  default 1) makes sure only the model under test is loaded.
* **A run that was not measured is not a zero.** If generation failed or
  returned nothing, the row is `not_measured` - never `0.0`.

The same model, task, prompt and settings is the same test: re-running it
replaces the previous row instead of piling up duplicates. Two runs only count
as different tests when the prompt or the settings (including KV-cache
quantization) differ.

## 11. Model comparison

The same prompt can be given to a local model and to a hosted one, and both
results are scored with the same checks:

```bash
# export the prompts for a hosted assistant
python tools/export_prompts.py --desktop

# import an answer and score it with the local checks
python tools/compare_models.py --provider chatgpt --task minecraft_world --clipboard

# score the newest local bake-off runs as well
python tools/compare_models.py --tasks all --include-bakeoff
```

Outputs land in `results/compare/` (`comparison.md`, `comparison.csv`,
`gallery.html`, `visuals/`). HTML pages are captured with headless Chrome
(SwiftShader), so a Three.js scene renders without a GPU.

Only the frontier artifacts under `benchmarks/compare/` are committed. Local
runs and scores stay in `results/`, which is git-ignored.

## 12. Optimisation recommendations

```bash
lm-optimizer recommend --vram 6          # what fits, and which config to try
lm-optimizer lab recommend               # model recommendations from local data
lm-optimizer fit qwen3.8-9b-distill      # max-context ladder per KV-cache path
lm-optimizer ctx qwen3.8-9b-distill      # context sweep with quality validation
```

`lab recommend` prefers measurements from this machine over community priors.
Fit is decided by file size and bits per weight, and MoE models are estimated
from their *active* parameters.

The full search strategy (prepare → speed → frontier → quality → recovery →
final validation → optional context phase) is documented in
[`docs/OPTIMIZATION_METHOD.md`](docs/OPTIMIZATION_METHOD.md).

## 13. Sandbox

A sandbox task gives a model a prompt, an isolated working directory and a
set of acceptance checks. On failure the model gets the failing checks (never
the solution) and may repair its output once.

```bash
lm-optimizer lab sandbox --task company_website --model <model-id>
lm-optimizer lab sandbox-all --model <model-id> --tasks email_write,company_website
```

What the checks look at:

* **Files** - required artifacts exist.
* **Structure** - HTML parses, has a title, a viewport, a single `h1`, a media
  query, no external scripts or styles, labelled inputs, `alt` attributes.
* **JavaScript** - parsed with `node --check`. Module sources are parsed as
  modules, because some Node versions silently accept a broken `.js` file
  that contains module syntax. If Node is not installed, the JavaScript is
  reported as **not validated** - never as valid.
* **Pixels** - rendered pages are screenshotted and measured (blank/flat
  detection), so a black canvas cannot score as a finished page.
* **Blender** - the produced script is executed with Blender, and the
  resulting `.blend` is inspected (mesh count, height variety, footprint,
  camera, light). The task forbids rendering, so no PNGs are produced.

Without Blender installed, the Blender task fails with an explicit
"blender executable not found" - that is the honest answer, not a silent 0.

The task definitions live in
[`lm_optimizer/services/sandbox_lab.py`](lm_optimizer/services/sandbox_lab.py);
the checks and their semantics are described in
[`docs/benchmarks/scoring_reference.md`](docs/benchmarks/scoring_reference.md).

## 14. Web UI

```bash
python -m lm_optimizer.web_main      # http://127.0.0.1:8080
```

Pages: **Dashboard** (start an optimisation, live status), **History** (runs,
duels, sandbox runs, compare and re-run), **Results** (winner, charts, prompt
/ thinking / output per test, apply or persist the config), **Sandbox**
(model-vs-model duels and per-task history), **Lab** (context explorer,
quality lab, recommender, bake-off), **Experiments**, **Settings**.
Everything the API exposes is under a single `/api` prefix; a websocket
streams progress.

**Security model:** the UI has no user accounts and is meant for loopback use.
It binds `127.0.0.1` by default. Binding to another interface requires both
`LM_OPTIMIZER_ALLOW_REMOTE=1` and `LM_OPTIMIZER_API_TOKEN`; mutating
requests from non-loopback clients must then send `X-API-Token`. Put an
authenticating reverse proxy in front of it for anything wider.

If LM Studio is down, the read-only pages still work and say so.

## 15. History and configuration

* **Runs** are stored in SQLite (`data/optimizer.db`), resumable through
  checkpoints. Pause and resume keep the same run id.
* **Reports** are written as Markdown per model (`results/<model>-best.md`).
* **The winner can be persisted into LM Studio**: `lm-optimizer lab
  save-default <run-id>` merges the validated configuration into LM Studio's
  per-model defaults file, after backing the previous file up. Unknown keys
  (CPU threads, KV-cache quantization, mmap) and prediction presets are
  preserved, and a malformed file is never overwritten.
* **Configuration** comes from environment variables or `.env`. The full
  reference - every setting, its default and what it influences - is in
  [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## 16. Troubleshooting

Short answers for the most common problems; the long version is in
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

| Symptom | Cause | Fix |
|---|---|---|
| `status` cannot connect | Developer server off | Start it in LM Studio (Developer tab) |
| Every run waits ~1 h and fails | A model is still loaded (Keep Model in Memory on) | Turn it off; `lm-optimizer host-watch` shows what is loaded |
| `blender_city` fails with "blender executable not found" | Blender is not installed | Install Blender, or set `BLENDER_PATH` |
| JavaScript is reported as "not validated" | Node.js is missing | Install Node.js, or accept that the check cannot run |
| A score is `0.0` right after a failure | The run was not measured | Check the run status (`not_measured` is not a quality score) |
| Reports do not appear | The run is in a different working directory | Results are written relative to the current directory |

## 17. Development and testing

```bash
pip install -e ".[dev]"

python -m pytest -q                    # the whole suite (mock-based)
python -m pytest -q -m unit            # fast unit suite
python -m pytest -q -m integration     # integration/tooling suite
python -m ruff check lm_optimizer tests --select F821   # undefined names
python -m mypy lm_optimizer             # type check
```

The suite runs on Windows, Ubuntu and macOS in CI (`.github/workflows/ci.yml`)
and needs Node.js for the JavaScript validation tests. The exact test count
moves with the code - the CI log is the source of truth, not this README.

The version lives in exactly one place: `lm_optimizer/__init__.py`. The
package metadata, the FastAPI app and the run records all read it from there.

Layout of the repository: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
Contribution guide: [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).
Development setup in detail: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md).

## Sponsoring

Sponsoring keeps this project alive and honest - it pays for the hardware
matrix (different GPUs, small-VRAM cards, Apple Silicon), the benchmark
infrastructure, and the time that goes into new model support and bug fixes.

```bash
# one-time
gh sponsor create @DracieVajko
# monthly
gh sponsor create --interval monthly @DracieVajko
```

Whatever you choose: bug reports, a failing CI run on a platform I do not own,
or a pull request with a regression test are worth just as much as money.

## License

MIT - see [`LICENSE`](LICENSE).

## Documentation

| Document | What it covers |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Layers, module map, data flow |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | Every setting, its default and its effect |
| [`docs/HARDWARE.md`](docs/HARDWARE.md) | Verified hardware matrix and its limits |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Symptoms, causes, fixes |
| [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) | How to contribute a change |
| [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) | Development setup and checks |
| [`docs/OPTIMIZATION_METHOD.md`](docs/OPTIMIZATION_METHOD.md) | The search strategy in detail |
| [`docs/metrics_semantics.md`](docs/metrics_semantics.md) | What every metric means |
| [`docs/benchmarks/README.md`](docs/benchmarks/README.md) | The published benchmark task |
| [`docs/README.md`](docs/README.md) | Full documentation index |
