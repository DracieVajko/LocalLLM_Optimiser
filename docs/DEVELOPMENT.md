# Development setup

## Requirements

| Tool | Needed for | Notes |
|---|---|---|
| Python 3.11+ | everything | 3.12 is what CI uses |
| Node.js | the JavaScript validation tests and the UI syntax check | Node 20+ |
| A Chromium browser (Chrome/Edge) | the pixel checks of rendered HTML | Optional; the checks report "skipped" without it |
| Blender | the `blender_city` task | Optional; the task reports "blender executable not found" without it |
| LM Studio | live runs | Optional; the test suite is mock-based |

```bash
pip install -e ".[dev]"
```

## Running the tests

```bash
python -m pytest -q                     # everything
python -m pytest -q -m unit             # fast unit suite (lm_optimizer/tests)
python -m pytest -q -m integration      # integration/tooling suite (tests/)
python -m pytest tests/test_sandbox_lab.py -v
```

The suite is split over two roots:

* `lm_optimizer/tests/` - unit tests next to the code they cover,
* `tests/` - integration, tooling and API tests.

Both are collected by default; the markers select one side.

## Static checks

```bash
python -m ruff check lm_optimizer tests --select F821   # undefined names
python -m mypy lm_optimizer                              # types
python -c "import glob, subprocess; [subprocess.check_call(['node', '--check', f]) for f in glob.glob('lm_optimizer/ui/static/js/*.js')]"
```

`ruff` runs with the project configuration in `pyproject.toml`
(`target-version = "py311"`, line length 100). CI checks the `F821` rule
(undefined names - it catches import-time regressions that Python 3.14 would
otherwise defer).

## CI

`.github/workflows/ci.yml` runs, for `ubuntu-latest`, `macos-latest` and
`windows-latest`:

1. `uv lock --check` - the lock file must match `pyproject.toml`,
2. `pip install -e ".[dev]"`,
3. `ruff check --select F821`,
4. `python -m pytest -q` - the full suite,
5. a Node syntax check of every UI JavaScript file.

Nothing is skipped per platform: the same suite runs everywhere, and a
platform-specific failure is a real failure.

## Repository layout

```
lm_optimizer/
  api/          FastAPI app, routes (single /api prefix), schemas, websocket
  backends/     BackendClient seam, the Ollama client, the llama.cpp stub
  benchmark/    the fixed benchmark suite definitions
  cli/          Typer commands (main.py plus one module per workflow)
  database/     SQLite access and migrations
  discovery/    model inspection
  domain/       dataclasses (LoadConfiguration filters to server-supported keys)
  hardware/     GPU/CPU/RAM detection per operating system
  profiles/     speed/balanced/context/quality weights
  scoring/      normalisation and the heuristic evaluator
  services/     the core logic (host client, optimizer, sandbox, bake-off, ...)
  storage/      resumable checkpoint store
  ui/           Jinja templates and static JavaScript
tools/          operational helpers (benchmarks, comparisons, audits)
scripts/        small maintenance scripts
docs/           documentation
benchmarks/     committed frontier artifacts and prompts
results/        local run data - git-ignored
data/           local database, logs, presets - git-ignored
```

`lm_optimizer/__init__.py` holds the version; `pyproject.toml` reads it
(dynamic version), and the FastAPI app and the run records take it from
there. There is exactly one place to change.

## Where things live

| Question | File |
|---|---|
| What can LM Studio be asked to do? | `lm_optimizer/services/host/lm_studio.py`, `lm_optimizer/services/parameter_registry.py` |
| How is a configuration searched? | `lm_optimizer/services/optimizer.py`, `speed_search.py`, `quality_ladder.py` |
| What does a sandbox task check? | `lm_optimizer/services/sandbox_lab.py` |
| How is a task executed and repaired? | `lm_optimizer/services/sandbox_runner.py` |
| How are runs kept apart? | `lm_optimizer/services/sandbox_history.py` |
| What does the API expose? | `lm_optimizer/api/routes.py` |
| How is a winner written into LM Studio? | `lm_optimizer/services/lmstudio_defaults.py` |
| How is JavaScript validated? | `lm_optimizer/services/web_validator.py` |
| How is a page measured? | `lm_optimizer/services/html_shot.py`, `render_check.py`, `png_stats.py` |

## Local data

Everything the tool produces at runtime is ignored by Git:

* `results/` - run artifacts, reports, comparisons,
* `data/` - SQLite database, logs, presets,
* `.desloppify/` - the local health-scan history.

Deleting `results/` and `data/` is safe: the next run recreates them.

## Conventions that prevent trouble

* **Read and write text with an explicit UTF-8 encoding.** The Windows
  default (cp1252) raises `UnicodeDecodeError` on files that Linux reads
  happily.
* **Do not rely on the system default for subprocess output either** -
  pass `encoding="utf-8", errors="replace"`.
* **Keep external tools optional.** A missing Node.js, Blender or browser
  must produce a distinct "unavailable" state, never a silent pass.
* **Never measure two things at once.** The model gate exists for that.
