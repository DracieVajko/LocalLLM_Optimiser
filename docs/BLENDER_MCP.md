# Blender MCP Integration — LM Studio Optimizer

## Overview
Models can generate Blender Python (`bpy`) scripts that create 3D scenes. The
LM Studio Optimizer can benchmark and score these scripts via the
`blender_city` sandbox task and the `code_runner` subprocess harness.

## Prerequisites
1. **Blender 4.2+** installed ([blender.org/download](https://www.blender.org/download/))
2. **MCP-Link server** (free, from [aurafriday.com/downloads](https://aurafriday.com/downloads/)) — exposes Blender's Python API to LLMs via MCP.
3. **MCP-Link Blender add-on** installed in Blender (Edit → Preferences → Get Extensions → search "MCP-Link").

## Setup
1. Start the MCP-Link server on your machine.
2. Open Blender — the add-on auto-connects to the server.
3. In LM Studio, configure the MCP server endpoint (default: `http://127.0.0.1:PORT`).
4. Models can now execute `bpy` code through the MCP tool.

## How the optimizer uses Blender
- `blender_city` sandbox task: model generates a Python script that builds a
  dense low-poly city scene. Scored by: blend file creation, mesh count,
  vertex count, render success, viewport render.
- `code_runner.run_find_duplicates`: crash/hang isolation only (not a security sandbox).
- Generated scripts are executed headless: `blender --background --python script.py`.

## Tips for best results
- Use models with strong Python/code generation (e.g., Swift, Nemotron, Gemma).
- Provide the model with the `bpy` API context in the prompt.
- Set `max_output_tokens` high (2048+) for complex scenes.
- The `blender_city` task requires O(n) mesh generation; O(n²) scripts fail perf checks.

## Troubleshooting
- If Blender MCP fails to connect, check that the MCP-Link server is running and Blender is in Object Mode.
- For headless rendering, ensure `blender` is on PATH.
- On Windows, use forward slashes in file paths inside Python scripts.
"