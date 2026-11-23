# Blender MCP Integration — LM Studio Optimizer

## Overview
Models can generate 3D scenes in Blender. The LM Studio Optimizer can benchmark
and score these scripts via the `blender_city` sandbox task and the `code_runner`
subprocess harness. For live control, the optimizer connects to Blender directly
via TCP (port 9876) — **no separate MCP-Link server is needed**.

## Prerequisites
1. **Blender 4.2+** installed ([blender.org/download](https://www.blender.org/download/))
2. **blender-mcp add-on** installed in Blender (auto-installable via
   `uvx mcp-for-blender install-addon`)
3. **LM Studio** running with the local server enabled (port 1234)

## Seamless setup (one command)
```bash
python -m lm_optimizer blender-mcp --apply
```
This auto-detects Blender, the MCP add-on and LM Studio, and prints the status.
If the add-on is missing, it attempts to install it automatically via `uvx`.

## How it works
- The `blender-mcp` add-on (ahujasid's, MIT license) starts a TCP server on
  port 9876 inside Blender.
- LM Studio Optimizer connects directly to this socket and sends JSON commands:
  `execute_code`, `get_scene_info`, `get_viewport_screenshot`, `ping`, etc.
- No separate MCP-Link server, no config files, no copy-paste.

## How the optimizer uses Blender
- `blender_city` sandbox task: model generates a Python script that builds a
  dense low-poly city scene. Scored by: blend file creation, mesh count,
  vertex count, render success.
- `code_runner.run_find_duplicates`: crash/hang isolation only.
- Generated scripts are executed headless: `blender --background --python script.py`.

## text-to-cad (recommended for real CAD)
For manufacturable 3D models, use [text-to-cad](https://github.com/earthtojake/text-to-cad):
```bash
uv tool install cad --python 3.13
cad server start
cad run model.py          # build
cad model export <id> model.glb  # export
cad run render.py         # render (Cycles)
```
This produces STEP/STL/3MF/GLB files from build123d Python scripts, with
Blender rendering via `cad run render.py` (auto-provisions bpy 5.2.3).

## Troubleshooting
- **Blender MCP not detected**: Start Blender with the MCP add-on enabled.
  The add-on's server starts automatically when Blender opens.
- **EEVEE compute shaders fail** (`HW_UNSUPPORTED`): Use Cycles at low samples (16–32)
  instead. The `cad run render.py` flow uses Cycles by default.
- **Model loading guardrail**: LM Studio refuses large models (>14 GB). Adjust
  guardrails in LM Studio Settings → Advanced.
- On Windows, use forward slashes in file paths inside Python scripts.
- For headless rendering, ensure `blender` is on PATH or set `BLENDER_PATH`.

## Honest limits
- Modelling a real product is the slowest step for an agent.
- The agent does not have your taste — use the gates and references.
- Final renders: 5–8 s/frame on RTX 4090; 1–2 h for a 30 s film.
- macOS and Linux are untested for the optimizer itself.
