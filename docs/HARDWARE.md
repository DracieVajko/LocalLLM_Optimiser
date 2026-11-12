# Hardware compatibility

This document lists what has actually been exercised, and - just as
important - what has not. Everything here is a statement about *this*
repository's test runs and records, not about what a machine could in theory
do.

## Verified

| Setup | What was run | Result |
|---|---|---|
| Windows 11, NVIDIA RTX 3060 (6 GB VRAM), 16 GB RAM | The full optimisation, sandbox and bake-off workflows against LM Studio's Developer server | Reference environment for every number in the reports |
| Windows, CPU-only inference | Unit tests for the detection and degradation paths | Coded and unit-tested; **no physical CPU-only run was recorded** |

## CI-covered (no live LM Studio session)

The full test suite runs on GitHub Actions for `ubuntu-latest`,
`macos-latest` and `windows-latest`. The suite is mock-based: it exercises
the parsing, scoring, reporting and API layers without a live server.

CI coverage means *the code is portable*, not *a live run was performed on
that platform*. No Linux or macOS session with a real LM Studio server and a
real model is recorded in this repository.

## Not verified

| Setup | Status |
|---|---|
| AMD GPUs (ROCm / Vulkan through LM Studio) | No run recorded. The detection code reads what the OS reports, but no number in this repository comes from AMD hardware |
| Apple Silicon live runs | Unified memory is reported as unified memory (no separate VRAM figure is invented), but no live optimisation run was recorded |
| llama.cpp as an inference backend | The `llama-server` client exists in `lm_optimizer/backends/llamacpp/`, but no CLI command reaches it yet |
| Ollama as an inference backend | Client implemented and mock-tested; no live Ollama server was exercised by the test suite |

## What the tool measures on your machine

* **GPU**: name, count and VRAM. `nvidia-smi` when it is present, otherwise
  the OS APIs; when nothing can be measured the tool reports that instead of
  guessing.
* **Memory**: system RAM, swap usage, per-drive free space.
* **Load behaviour**: the server's own load echo - whether the requested
  context length, flash attention and KV-cache placement were really applied.
* **Speed**: server-side timing (TTFT, prompt tokens, decode tokens per
  second), plus the wall-clock time around the whole request.

## What it estimates (and says so)

* **Model fit**: whether a model fits into the free VRAM. The estimate uses
  the **file size and the bits per weight**, not the parameter count - a 27B
  model at Q1_0 fits a 6 GB card, the same model at Q4 does not. MoE models
  are estimated from their *active* parameters.
* **Community priors** for models that were never measured here. A local
  measurement always outranks a prior.

## Practical limits worth knowing

* **6 GB cards**: context length and KV-cache placement dominate. A large
  context with the KV cache on the GPU is the usual reason a model that
  "fits" fails to load.
* **KV-cache quantization** (Q4 vs Q8) is a GUI-only setting in LM Studio. It
  changes the KV cache size, so it changes how many layers stay on the GPU.
  Whether that helps depends on the model and the context - measure it.
* **CPU threads** are a GUI-only setting too, and they matter most when the
  model does not fit into VRAM.
* **Apple Silicon**: there is one memory pool. The tool reports it as such
  and never pretends there is a separate VRAM budget.

## Reproducing a measurement

```bash
lm-optimizer status                 # what the tool sees
lm-optimizer recommend --vram 6      # what fits
lm-optimizer optimize <model>       # measure, then validate
```

Record the host details from the report (`results/<model>-best.md`): GPU,
VRAM, RAM, driver and the LM Studio version. Without those, a number cannot
be compared with anything.
