# Configuration reference

Every setting can be provided as an environment variable or in a `.env` file
in the working directory. `.env` is read as UTF-8; environment variables win
over the file. Unknown variables are ignored.

Copy [`.env.example`](../.env.example) to `.env` to get started - it lists the
settings that matter most.

The settings are grouped by prefix. `pydantic-settings` reads them case
insensitively.

## Backend selection

| Variable | Default | Meaning |
|---|---|---|
| `BACKEND` | `lm-studio` | Which inference backend the CLI talks to: `lm-studio`, `ollama` (`llama-cpp` is phase 2 and not reachable) |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API base URL |
| `LLAMACPP_BASE_URL` | `http://127.0.0.1:8080` | `llama-server` base URL (phase 2) |

## LM Studio connection (`LM_STUDIO_`)

| Variable | Default | Meaning |
|---|---|---|
| `LM_STUDIO_BASE_URL` | `http://127.0.0.1:1234` | Developer server address. A non-loopback host is detected and refused for benchmarking: the numbers would describe the other machine |
| `LM_STUDIO_API_VERSION` | *(auto)* | Force `v0` or `v1` instead of auto-detecting |
| `LM_STUDIO_TIMEOUT` | `120` | Request timeout in seconds |
| `LM_STUDIO_CHAT_TIMEOUT_MAX` | `900` | Upper bound for a chat request; long generations need more than the default |
| `LM_STUDIO_MAX_RETRIES` | `3` | Retries per request |
| `LM_STUDIO_RETRY_DELAY` | `2.0` | Delay between retries in seconds |

## Hardware (`HW_`)

| Variable | Default | Meaning |
|---|---|---|
| `HW_GPU_VRAM_GB` | *(auto)* | Override the detected VRAM size |
| `HW_SYSTEM_RAM_GB` | *(auto)* | Override the detected RAM size |
| `HW_GPU_NAME` | *(auto)* | Override the detected GPU name |
| `HW_GPU_COUNT` | `1` | Number of GPUs to assume |

Detected values come from `nvidia-smi` when it is available, with a graceful
fallback to the OS APIs. When the tool cannot measure something, it says so
instead of guessing.

## Optimisation (`OPT_`)

| Variable | Default | Meaning |
|---|---|---|
| `OPT_DEFAULT_PROFILE` | `balanced` | Default profile: `speed`, `balanced`, `context`, `quality`, `custom` |
| `OPT_MINIMUM_QUALITY_SCORE` | `0.8` | Quality gate - a configuration below it never wins |
| `OPT_BENCHMARK_RUNS` | `3` | Repetitions per measurement |
| `OPT_WARMUP_RUNS` | `1` | Warm-up passes before measuring (`0` is faster but noisier) |
| `OPT_BENCHMARK_TIMEOUT` | `300` | Timeout for one benchmark pass |
| `OPT_LOAD_MODEL_TIMEOUT` | `60` | Timeout for one model load |
| `OPT_GENERATION_TIMEOUT` | `300` | Timeout for one generation |

## Model gate (`MODEL_GATE_`)

The gate is what keeps measurements clean: only the model under test may be
loaded.

| Variable | Default | Meaning |
|---|---|---|
| `MODEL_GATE_ENABLED` | `true` | Enable the gate |
| `MODEL_GATE_MAX_LOADED_MODELS` | `1` | How many models may be loaded at once, including ours |
| `MODEL_GATE_WAIT_TIMEOUT_S` | `3600` | How long to wait for a free slot before giving up |
| `MODEL_GATE_POLL_INTERVAL_S` | `180` | How often the slot is re-checked |
| `MODEL_GATE_PROBE_TIMEOUT_S` | `2` | Timeout for the probe that lists loaded models |
| `MODEL_GATE_FALLBACK_MODELS` | *(empty)* | Models to try after the wait times out |

## Web UI (`WEB_UI_`)

| Variable | Default | Meaning |
|---|---|---|
| `WEB_UI_HOST` | `127.0.0.1` | Bind address. A non-loopback bind needs `LM_OPTIMIZER_ALLOW_REMOTE=1` **and** `LM_OPTIMIZER_API_TOKEN` |
| `WEB_UI_PORT` | `8080` | Bind port |

## Storage (`STORAGE_`)

| Variable | Default | Meaning |
|---|---|---|
| `STORAGE_RESULTS_DIR` | `results` | Where reports and run artifacts are written |
| `STORAGE_PROFILES_DIR` | `data/presets` | Saved presets |
| `STORAGE_LOGS_DIR` | `data/logs` | Log files |
| `STORAGE_CONFIG_DIR` | `data` | Configuration directory |
| `STORAGE_DATABASE_PATH` | `data/optimizer.db` | SQLite database with the run history |

All of these are relative to the current working directory unless an absolute
path is given.

## Logging (`LOG_`)

| Variable | Default | Meaning |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `LOG_FORMAT` | `json` | `json` or `text` |

## Safety (`SAFETY_`)

| Variable | Default | Meaning |
|---|---|---|
| `SAFETY_AUTO_UNLOAD_BETWEEN_TESTS` | `true` | Unload the model between test configurations |
| `SAFETY_FORCE_UNLOAD_ON_ERROR` | `true` | Unload the model even when a test fails |
| `SAFETY_CHECKPOINT_INTERVAL` | `60` | Seconds between resumable checkpoints |

## LM Studio per-model defaults

Two settings cannot be sent over REST and are therefore **read** from LM
Studio's own defaults file instead of being set by the tool:

* `llm.load.llama.kCacheQuantizationType` / `vCacheQuantizationType`
  (KV-cache quantization)
* `llm.load.llama.cpuThreadPoolSize` (CPU threads)

The file lives at
`<lmstudio-home>/.internal/user-concrete-model-default-config/<model>.json`.
`lm-optimizer lab save-default <run-id>` writes a validated winner there
(atomically, with a backup of the previous file). Override the home with
`--lmstudio-home` or `LM_OPTIMIZER_LMSTUDIO_HOME`.

The values are recorded with every benchmark run, because a Q4 run and a Q8
run are different tests.

## Environment variables used outside the settings

| Variable | Meaning |
|---|---|
| `LM_OPTIMIZER_ALLOW_REMOTE` | Set to `1` to allow a non-loopback web UI bind (with `LM_OPTIMIZER_API_TOKEN`) |
| `LM_OPTIMIZER_API_TOKEN` | Token that mutating remote requests must send as `X-API-Token` |
| `LM_OPTIMIZER_LMSTUDIO_HOME` | Alternative LM Studio home directory |
| `BLENDER_PATH` | Full path to the Blender executable (the sandbox looks here first) |
