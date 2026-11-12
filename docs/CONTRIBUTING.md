# Contributing

Thanks for looking at this project. The bar for a change is simple: **it
makes the tool more truthful**, and it comes with a test.

## Ground rules

1. **Measurements stay honest.** A run that could not be measured must never
   look like a score of zero. If a validator cannot run, say so instead of
   passing the check.
2. **Never hide a failure.** Do not disable a test, skip a platform or widen
   a tolerance to get a green pipeline. Fix the cause or report the blocker.
3. **Keep the public interfaces stable.** The CLI commands, the `/api`
   routes and the on-disk formats are used by other people and by the tools
   in `tools/`.
4. **One implementation.** A fix goes into the canonical module, with a
   regression test. A parallel "fixed" copy of a file is not a solution.

## Getting set up

```bash
git clone https://github.com/DracieVajko/LocalLLM_Optimiser.git
cd LocalLLM_Optimiser
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / macOS
pip install -e ".[dev]"
```

Install Node.js (JavaScript validation) and keep LM Studio's Developer server
available if you want to reproduce a live run.

## Before you open a pull request

```bash
python -m pytest -q                              # the whole suite
python -m ruff check lm_optimizer tests --select F821
python -m mypy lm_optimizer
python -c "import glob, subprocess; [subprocess.check_call(['node','--check',f]) for f in glob.glob('lm_optimizer/ui/static/js/*.js')]"
```

The CI workflow runs the suite on Windows, Ubuntu and macOS. A change that
only works on your operating system will be caught there.

## How to structure a change

* **Bug fix** - first a test that fails for the right reason, then the fix.
  Include the platform in the test name when the behaviour is
  platform-specific (`test_..._on_windows`).
* **New sandbox check** - add it to the task definition in
  `lm_optimizer/services/sandbox_lab.py` *and* to the scoring reference in
  `docs/benchmarks/scoring_reference.md`. A check without a validator must
  not be registered.
* **New CLI command or API route** - document it in the README and in
  `docs/`, and add the command to the CLI reference table.
* **Documentation** - keep it close to the code it describes. The README is
  the entry point; the details live in `docs/`.

## Code conventions

* Domain models are dataclasses in `lm_optimizer/domain/`; Pydantic models
  appear only at the HTTP boundary (`lm_optimizer/api/schemas.py`); plain
  dicts/JSON are used at file and subprocess edges.
* Services are stateless functions or small classes; they take their inputs
  as arguments and return data.
* Read and write files with an explicit `encoding="utf-8"`. The default
  encoding differs between Windows and Linux, and that difference has broken
  the CI before.
* Log with the structured logger (`lm_optimizer.logging_config`), never with
  `print` in library code.

## Reporting a bug

Please include:

* what you ran (exact command),
* what you expected and what happened,
* the host details from the report (`GPU`, `VRAM`, `RAM`, LM Studio version),
* the relevant log or the row from `results/*.jsonl`.

A failing command with the output attached is worth more than a description.

## Security

The web UI has no user accounts and is meant for loopback use. If you find a
way to make it do something harmful from another machine, that is a
security bug - report it privately first (GitHub "Report a vulnerability"),
and do not publish a working exploit in an issue.

Never commit credentials. The repository has no secrets, and `.env` is
git-ignored.

## Licence

By contributing you agree that your work is published under the MIT licence
of this repository.
