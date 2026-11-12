# Troubleshooting

Every symptom below was observed on a real machine. The fixes are the ones
that worked.

## LM Studio cannot be reached

**Symptom**: `lm-optimizer status` reports a connection error.

1. Is the Developer server running? LM Studio → Developer tab → *Start
   Server*. It listens on `127.0.0.1:1234` by default.
2. Is the address right? `lm-optimizer status --base-url http://127.0.0.1:1235`.
3. Is a firewall or VPN blocking loopback? Try `curl http://127.0.0.1:1234/api/v1/models`.

## Every run waits an hour and then fails

**Symptom**: the run stops with "no free model slot".

A model is still loaded - usually because LM Studio's **Keep Model in Memory**
is on, so the unload never takes effect.

```bash
lm-optimizer host-watch                  # what is loaded right now
lm-optimizer host-watch --unload-foreign # release what is not ours
```

Then turn *Keep Model in Memory* off in LM Studio and restart the run. The
model gate waits `MODEL_GATE_WAIT_TIMEOUT_S` (default 3600 s) before it gives
up - it never measures against a machine that has somebody else's model
loaded.

## `blender_city` fails with "blender executable not found"

The Blender task needs a real Blender. The sandbox looks for it in this order:

1. `BLENDER_PATH`
2. `PATH`
3. the usual install roots (`C:\Program Files\Blender Foundation\...`,
   `~/Applications`, the Steam folder, the Windows Store alias)
4. the Windows uninstall registry

If none of them has it, the task fails with that explicit message - it is not
a scoring bug. Install Blender, or set `BLENDER_PATH` to the executable, and
run the task again. The text tasks do not need Blender.

## JavaScript is reported as "not validated"

The sandbox validates JavaScript with `node --check`. Without a Node.js
runtime the code cannot be checked, and the tool reports that instead of
pretending the code is fine.

Install Node.js, or accept that the `js_parses` check cannot run on that
machine. The check is critical for the tasks that produce JavaScript, so
those tasks cannot pass without a validator.

> Module sources (`import` / `export`) are parsed as modules. Some Node
> versions silently accept a broken `.js` file that contains module syntax -
> the tool writes the probe file as `.mjs` so the result does not depend on
> the Node version.

## A score of 0.0 after a failure

`0.0` and "not measured" are different things:

* `measured` with score `0.0` - the model answered, and the answer failed the
  checks.
* `not_measured` - generation failed, returned nothing, or the run never
  started. This is **not** a quality score and never enters the ranking.

Check the run's `status` and `error` in the history file
(`results/sandbox_runs.jsonl`) or in the web UI.

## The web UI shows nothing / "offline"

The UI is a thin client over the API. If LM Studio is down, the read-only
pages still load and show a disconnected banner - that is intentional.

If the page itself is empty, open the developer console: a failed API call
usually means the server process is not running.

```bash
python -m lm_optimizer.web_main
```

## The preview panel is empty

The artifact preview is served from `/api/sandbox/files?file_path=...`. If the
iframe stays blank, check the browser network tab for a 404 - the path is
relative to `results/sandbox/` and `results/bakeoff/`.

Text and JSON artifacts are shown in a formatted viewer (JSON is
pretty-printed). HTML artifacts are served raw so the browser can render
them.

## Reports are not where I expect them

Results are written **relative to the current working directory** (`results/`,
`data/`). Run the tool from the repository root, or set `STORAGE_RESULTS_DIR`
and `STORAGE_DATABASE_PATH` to absolute paths.

## The run is slower than expected

* Another process is using the GPU: `nvidia-smi` during the run.
* The model was not fully on the GPU - the load echo in the report shows the
  applied configuration; compare it with the requested one.
* The KV cache is on the GPU and the context is large. Moving the KV cache to
  RAM (`--kv-ram`) frees VRAM for weights at the cost of bandwidth.

## Two runs of the same model disagree

* The machine was busy. Check `lm-optimizer host-watch` and the GPU load.
* The first run was a cold start (model not in memory); the second was warm.
  The bake-off reports load time separately for exactly this reason.
* The KV-cache quantization or the thread count changed between the runs -
  both are recorded with every run now.

## The web UI refuses to bind to another interface

By design. A non-loopback bind needs both:

```bash
export LM_OPTIMIZER_ALLOW_REMOTE=1
export LM_OPTIMIZER_API_TOKEN=<long random token>
```

Mutating requests from a non-loopback client must then send
`X-API-Token: <token>`. Put an authenticating reverse proxy in front for
anything wider.

## The tests fail on my machine but pass in CI

* Install the development dependencies: `pip install -e ".[dev]"`.
* Install Node.js - the JavaScript validation tests need it.
* On Windows, read files as UTF-8 in your own scripts. The repository always
  passes an explicit `encoding="utf-8"`; code that relies on the system
  default (cp1252) breaks on non-ASCII content.
