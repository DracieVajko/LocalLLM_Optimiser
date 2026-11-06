# LM Studio Auto Optimizer — Deep Research Design Document

**Date:** 2026-11-06  
**Source:** Deep research prompt `deepresearch lmstudiuo.txt`  
**Status:** Design (pending implementation)

## 1. Overview

This design document consolidates the deep research findings into a single specification for the LM Studio Auto Optimizer. It covers:

- LM Studio per-model load defaults persistence
- Ollama backend integration
- llama.cpp parameter mapping
- Benchmark & sandbox automation
- Intelligent scheduling & cleanup automation
- Model recommendation logic
- Security & isolation boundaries
- Web UI integration

## 2. LM Studio Default Persistence (Section 1)

### 2.1 Default File Structure

LM Studio stores per-model load defaults in:

```
<lmstudio-home>/.internal/user-concrete-model-default-config/<model>.json
```

Where `<lmstudio-home>` defaults to `~/.lmstudio` and can be overridden via `LM_OPTIMIZER_LMSTUDIO_HOME`.

### 2.2 Supported Load Keys

| Key | Type | Description |
|-----|------|-------------|
| `llm.load.contextLength` | int | Context length |
| `llm.load.llama.flashAttention` | bool | Flash attention |
| `llm.load.offloadKVCacheToGpu` | bool | KV cache on GPU |
| `llm.load.llama.acceleration.offloadRatio` | float | GPU offload ratio (0.0-1.0) |
| `llm.load.llama.evalBatchSize` | int | Eval batch size |
| `llm.load.llama.physicalBatchSize` | int | Physical batch size |
| `llm.load.numParallelSessions` | int | Parallel sessions |
| `llm.load.llama.contextCheckpoints` | int | Context checkpoints |
| `llm.load.llama.cpuThreadPoolSize` | int | CPU thread pool size |
| `llm.load.llama.vCacheQuantizationType` | object | V-cache quantization type |
| `llm.load.llama.kCacheQuantizationType` | object | K-cache quantization type |
| `llm.load.llama.tryMmap` | bool | Memory mapping |
| `llm.load.llama.keepModelInMemory` | bool | Keep model in memory |
| `llm.load.llama.speculativeDecoding.*` | various | Speculative decoding options |

Unknown keys are preserved; malformed files are never overwritten.

### 2.3 Persistence Behavior

- File writes apply on next LM Studio load without restart (verified via `echo_load_config=true`)
- Legacy `.optimizer-backup` recognized by restore
- Timestamped backups keep newest 10 (`optimizer-backup-<utc>`)
- Restore validates JSON before writing; invalid/unreadable files never overwritten
- `diff-default` aligns legacy speculative keys; reports added/changed/unchanged/preserved
- Identical restore is a no-op

## 3. Ollama Backend Integration (Section 2)

### 2.1 Endpoint & Model Loading

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /api/tags` | GET | List models |
| `POST /api/show` | POST | Model details (modelfile, model_info) |
| `POST /api/generate` | POST | Generation (stream=false) |
| `GET /api/ps` | GET | Running models |
| `POST /api/create` | POST | Create new tag |
| `GET /api/version` | GET | Server version |

Ollama does not expose per-model instance IDs like LM Studio. Load happens implicitly on first generate.

### 2.2 Performance Settings

| Ollama Param | llama.cpp Equivalent | Description |
|-------------|---------------------|-------------|
| `num_gpu_layers` | `-ngl` | GPU layer offload |
| `num_ctx` | `-c` | Context window |
| `num_predict` | `--predict` | Max output tokens |
| `num_thread` | `--threads` | Thread count |
| `num_gqa` | `--gqa` | GQA grouping |
| `cache_type_k` / `cache_type_v` | `--k-cache-quantization` / `--v-cache-quantization` | KV cache quant |

### 2.3 Integration

Ollama defaults are persisted separately from LM Studio defaults (different file formats). The optimizer treats them as separate backends. When both backends are available, the recommender uses local measurements from both to produce unified recommendations.

## 4. llama.cpp Parameters (Section 3)

| Flag | Description | Searchable? |
|------|-------------|-------------|
| `-ngl 99` | Full GPU offload | Yes |
| `--n-cpu-moe N` | CPU expert layers for MoE | Manual only |
| `-c N` | Context size | Yes |
| `--batch-size N` | Batch size | Yes |
| `--ubatch-size N` | Micro-batch size | Yes |
| `--mlock` | Lock model in RAM | No (runtime fact) |
| `--no-mmap` | Disable memory mapping | No (runtime fact) |
| `--threads N` | Thread count | Yes |
| `--flash-attn` | Flash attention | Yes |
| `--k-cache-quantization` | KV cache quant (K) | Yes |
| `--v-cache-quantization` | KV cache quant (V) | Yes |

## 5. Benchmark & Sandbox (Section 4)

### 5.1 Intelligent Scheduling

- Ordering: ascending size → MoE before dense → dense last
- VRAM floor: 250–500 MB free
- Speed floor: 5 tok/s default, configurable via `--speed-floor`
- Partial results: `status='partial'` saved before pause
- Resume from partial state without corrupting `best_config_id`

### 5.2 Cleanup Automation

- `clean_tests` command with `--dry-run` and `--failed-count` (default 2)
- Remove artifacts and DB entries with `status='failed'` after consecutive failures
- Only within project folder; never delete outside directory
- Backup files older than `BACKUP_KEEP` = 10 are cleaned

### 5.3 Recommendation Logic

- Input: `model_id` + DB history (`run_repo.get`, `ConfigurationResult` list, `metrics_json`)
- Output: best `LoadConfiguration` with justification
- Missing measurements: fall back to catalog defaults or hardware fingerprint estimates

## 6. Security & Isolation (Section 5)

### 6.1 API Key Isolation

- `LM_OPTIMIZER_ASSISTANT_URL` / `LM_OPTIMIZER_ASSISTANT_KEY` read from `.env`
- Never written to repo/code; never exposed in logs or test output
- Only used when user explicitly sets `.env` and passes `--use-assistant`

### 6.2 Folder Isolation

- All file operations restricted to `LM_OPTIMIZER_LMSTUDIO_HOME` (default: `~/.lmstudio`) and project directory
- No writes to system directories
- No `os.system` or subprocess calls except `nvidia-smi` (read-only)

### 6.3 Web Access

- Default: no web search or external HTTP (only LM Studio `127.0.0.1:1234`)
- Optional `LM_OPTIMIZER_ASSISTANT_URL` with `urllib.request` or `httpx`, timeouts, retries (max 3)

### 6.4 No Live LLM Load Requirement

- No live `load_model` needed for scheduling/recommendation
- `verify-default` uses mock client unless user explicitly confirms live mode
- Live mode gated behind explicit user confirmation; unloads model in `finally`

## 7. Output Format (Section 6)

- Design document: `docs/specs/YYYY-MM-DD-<topic>-design.md`
- Implementation plan: `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`
- CLI/API interfaces documented with exact signatures
- Tests: failing → verification → passing cycle
- Self-review checklist: no placeholders, no contradictions, types consistent
