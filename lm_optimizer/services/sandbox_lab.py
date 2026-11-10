"""Sandbox Lab: web / research / blender tasks, repair loop, isolation.

Implements the master spec (LM_STUDIO_OPTIMISER_MASTER_SPEC_SK.md) section 13:

- 13.1 Web/HTML sandbox with precise acceptance criteria and automatic
  evaluation (build/runtime status, required files, console errors, network
  policy, functional tests, responsive screenshots, accessibility, visual
  overflow/overlap, maintainability).
- 13.2 Research sandbox: closed-source controlled package (primary,
  technical, outdated, conflicting and irrelevant sources) and open-web
  research. Penalize invented sources and non-existent citations.
- 13.3 Blender/3D sandbox: exact script exit code, .blend file, required
  objects, materials, camera, lights, keyframes, frame range, rendered
  frames, non-black frames, visible motion, composition.
- 13.4 Repair loop: max N attempts; the model receives stdout/stderr, failing
  tests, relevant screenshot and the remaining repair budget - never the
  solution. First-pass success and final success are reported separately.
  Penalty: first pass 100%, after one repair 90%, after two 80%.
- 13.5 Security: isolated workdir, network off by default, process timeout,
  CPU/RAM/disk limits, no host secrets, whitelist of executables, artifact
  retention, and no display of model-generated commands without sanitising.

The task DEFINITIONS and the evaluation LOGIC here are pure and offline
testable; the actual execution lives in the runner that talks to the
sandbox host.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SandboxTaskKind(str, Enum):
    WEB = "web"
    RESEARCH = "research"
    BLENDER = "blender"
    TEXT = "text"  # plain generation; scored only when checks are supplied


@dataclass
class SandboxCheck:
    """One acceptance criterion of a sandbox task.

    `negate=True` inverts the check: for a regex, a MATCH means FAIL
    (used for "must not contain an external script" style criteria).
    """

    name: str
    kind: str  # "files" | "regex" | "json" | "exit_code" | "custom"
    value: Any = None
    weight: float = 1.0
    critical: bool = False
    negate: bool = False


@dataclass
class SandboxTask:
    """A sandbox task definition (prompt + acceptance criteria)."""

    id: str
    kind: SandboxTaskKind
    title: str
    prompt: str
    checks: list[SandboxCheck] = field(default_factory=list)
    max_repair_attempts: int = 2
    timeout_s: float = 300.0
    network_allowed: bool = False
    allowed_executables: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    max_output_tokens: int = 2048
    network_allowed: bool = False


# --- 13.1 Web task --------------------------------------------------------

WEB_TASK = SandboxTask(
    id="web_dashboard",
    kind=SandboxTaskKind.WEB,
    title="Responsive metrics dashboard",
    prompt=(
        "Build a self-contained HTML dashboard (single file, no external "
        "network calls) that shows four metrics, a filter, a model detail "
        "view, a light/dark theme toggle, and works on both mobile and "
        "desktop widths. Output ONLY the complete HTML starting with "
        "<!DOCTYPE html>, no markdown fences, no explanations."
    ),
    checks=[
        SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{50,}", weight=1.0, critical=True),
        SandboxCheck("has_viewport", "regex", r'name=["\']viewport["\']', weight=1.0),
        SandboxCheck("has_media_query", "regex", r"@media", weight=1.0),
        SandboxCheck("has_theme_toggle", "regex", r"(dark|theme)", weight=1.0),
        SandboxCheck("no_external_scripts", "regex", r"<script[^>]+src=[\"']https?://", weight=1.5, negate=True),
        SandboxCheck("no_external_styles", "regex", r"<link[^>]+href=[\"']https?://", weight=1.5, negate=True),
        SandboxCheck("has_table_or_grid", "regex", r"(<table|role=[\"']grid|class=[\"'][^\"']*grid)", weight=1.0),
    ],
    max_repair_attempts=2,
    timeout_s=300.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("index.html",),
)


# --- 13.3 Minecraft-style voxel world (single HTML) -------------------------

MINECRAFT_BASE_PROMPT = (
    "Create one single HTML file named index.html — a Minecraft-style voxel "
    "world rendered with Three.js loaded from a CDN. No build step, no "
    "bundler, no server, no external assets (no images, sounds or zip "
    "files); everything except Three.js must be inside this one file.\n\n"
    "The page must contain:\n"
    "- A hero section that feels like a tiny Minecraft world.\n"
    "- Procedural terrain made of colored cubes (grass green, dirt brown, "
    "  stone gray, water blue).\n"
    "- Smooth 60fps rendering with requestAnimationFrame.\n"
    "- A camera that automatically orbits the floating island (no player "
    "  controls are required).\n"
    "- Animated sky / day-night feel (moving sun or color gradient).\n"
    "- Clean, modern, commented code.\n\n"
    "Output ONLY the complete HTML in a markdown code fence starting with "
    "```html and ending with ```. Do not include any other text."
)


def build_minecraft_prompt(scene_brief: str = "") -> str:
    """Return the base skyblock prompt with an optional user scene variation.

    The variation is appended as an extra instruction, so the model still
    builds a floating skyblock island; only the requested details change
    (for example fewer trees, a lighthouse, a bigger pond or a farm).
    """
    brief = (scene_brief or "").strip()
    if not brief:
        return MINECRAFT_BASE_PROMPT
    return (
        MINECRAFT_BASE_PROMPT
        + "\n\nScene variation (the result must still be a floating skyblock "
        "island with the base grass/dirt/stone terrain): "
        + brief
    )


MINECRAFT_WORLD_TASK = SandboxTask(
    id="minecraft_world",
    kind=SandboxTaskKind.WEB,
    title="Minecraft-style voxel world (single HTML)",
    prompt=MINECRAFT_BASE_PROMPT,
    checks=[
        SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{50,}", weight=1.0, critical=True),
        SandboxCheck("single_file_html", "regex", r"<!DOCTYPE\s+html|<html\b", weight=1.0, critical=True),
        SandboxCheck("has_threejs", "regex", r"<script[^>]+src=[\"'][^\"']*three[^\"']*\.js", weight=1.0),
        SandboxCheck("has_voxel_cubes", "regex", r"(BoxGeometry\s*\(|InstancedMesh\s*\()", weight=1.5),
        SandboxCheck("has_grass", "regex", r"(grassTop|grassSide|grass\s*[:=]|0x4caf50|#4caf50)", weight=1.0),
        SandboxCheck("has_stone", "regex", r"(stone\s*[:=]|stoneTop|0x8b939b|#8b939b|#808080)", weight=1.0),
        SandboxCheck("has_water", "regex", r"(water\s*[:=]|waterMat|0x2f7fd4|#2f7fd4|#3a8fe0)", weight=1.0),
        SandboxCheck("has_camera", "regex", r"(PerspectiveCamera|\.lookAt\s*\()", weight=1.5),
        SandboxCheck("has_render_loop", "regex", r"(requestAnimationFrame\s*\(|function\s+animate\s*\()", weight=1.5),
        SandboxCheck("no_external_assets", "regex", r"\.(png|jpg|jpeg|gif|zip)\b", weight=1.0, negate=True),
    ],
    max_repair_attempts=2,
    timeout_s=300.0,
    max_output_tokens=8192,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("index.html",),
)

#: Closed-source research package: primary, technical, outdated, conflicting
#: and irrelevant sources. The model must handle the conflict and must not
#: invent citations.
RESEARCH_PACKAGE: dict[str, str] = {
    "primary_official": (
        "The LM Studio REST API v1 exposes POST /api/v1/models/load with the "
        "parameters context_length, flash_attention, offload_kv_cache_to_gpu, "
        "eval_batch_size, physical_batch_size, parallel, context_checkpoints, "
        "num_experts and speculative_draft_max_tokens. Unknown keys are "
        "rejected with HTTP 400 unrecognized_keys before the model is loaded."
    ),
    "technical_secondary": (
        "The llama.cpp server exposes speculative decoding through "
        "--spec-type draft-mtp and the MTP head shipped with Qwen3.8 models. "
        "On a dense 27B at Q4_K_M the acceptance rate of n=3 drafts was about "
        "73% and decode throughput rose from 31.2 to 40.3 tok/s on a V100."
    ),
    "outdated_source": (
        "Older guides state that a 27B Q4_K_M model needs 17.5 GB of VRAM "
        "and therefore cannot run on consumer cards at all. This guidance "
        "predates 3-bit quants and KV cache quantization."
    ),
    "conflicting_source": (
        "A community benchmark claims Q3_K_M is faster than Q4_K_M because the "
        "model is smaller, while another claims the opposite because Q3 "
        "requires more dequantization steps. Both were measured on Apple "
        "Silicon, where the Q3 kernel is known to be unusually slow."
    ),
    "irrelevant_source": (
        "A blog post about the history of the BASIC programming language "
        "describes how early microcomputers stored programs on cassette tapes."
    ),
}

RESEARCH_TASK = SandboxTask(
    id="research_synthesis",
    kind=SandboxTaskKind.RESEARCH,
    title="Source-grounded research synthesis",
    prompt=(
        "Using ONLY the provided source documents below, answer: which load "
        "parameters does the LM Studio REST API v1 accept, what is the "
        "measured effect of MTP speculative decoding on a dense 27B, and "
        "how should the conflicting Q3/Q4 speed claim be resolved? "
        "Cite every claim by source name. If the sources do not answer "
        "something, say so explicitly.\n\n"
        "SOURCE DOCUMENTS:\n"
        "--- primary_official ---\n{primary_official}\n\n"
        "--- technical_secondary ---\n{technical_secondary}\n\n"
        "--- outdated_source ---\n{outdated_source}\n\n"
        "--- conflicting_source ---\n{conflicting_source}\n\n"
        "--- irrelevant_source ---\n{irrelevant_source}\n\n"
        "END OF SOURCES.\n"
    ).format(**RESEARCH_PACKAGE),
    checks=[
        SandboxCheck("cites_primary", "regex", r"primary_official", weight=2.0, critical=True),
        SandboxCheck("cites_technical", "regex", r"technical_secondary", weight=1.5),
        SandboxCheck("cites_conflicting", "regex", r"conflicting_source", weight=1.0),
        SandboxCheck("no_irrelevant_source", "regex", r"cassette", weight=2.0, negate=True),
        SandboxCheck("mentions_unknown", "regex", r"(not (stated|provided|mentioned)|no (information|mention))", weight=1.0),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=(),
    artifacts=(),
)


# --- 13.3 Blender task ----------------------------------------------------

BLENDER_TASK = SandboxTask(
    id="blender_skyblock",
    kind=SandboxTaskKind.BLENDER,
    title="Minecraft-inspired Skyblock scene",
    prompt=(
        "Write a Blender Python script named build_scene.py that builds a "
        "floating block island scene: a grass/dirt/stone block island, a "
        "tree, a chest, a block avatar, a sun light, and a camera that "
        "orbits the island. Save the .blend file as scene.blend first, then "
        "render frames 1-120 into the frames/ directory with a path relative "
        "to the saved file (scene.render.filepath = '//frames/frame_') and "
        "call bpy.ops.render.render(animation=True). Output ONLY the complete "
        "Python script in a markdown code fence, starting with ```python "
        "and ending with ```. Do not include any other text."
    ),
    checks=[
        SandboxCheck("script_defines_scene", "regex", r"(bpy\.ops\.mesh|primitive_cube|primitive_plane)", weight=2.0, critical=True),
        SandboxCheck("has_grass_material", "regex", r"(grass|meadow|green)", weight=1.5),
        SandboxCheck("has_tree", "regex", r"(tree|trunk|leaves|foliage)", weight=1.5),
        SandboxCheck("has_chest", "regex", r"chest", weight=1.0),
        SandboxCheck("has_camera", "regex", r"(Camera|camera)", weight=1.0),
        SandboxCheck("has_light", "regex", r"(Light|SUN|sun)", weight=1.0),
        SandboxCheck("has_keyframes", "regex", r"keyframe_insert", weight=1.5),
        SandboxCheck("has_frame_range", "regex", r"frame_(start|end)", weight=1.0),
        SandboxCheck("saves_blend", "regex", r"save_as_mainfile", weight=1.0, critical=True),
        SandboxCheck("renders", "regex", r"bpy\.ops\.render", weight=1.0),
        SandboxCheck("blend_runs", "custom", None, weight=1.0, critical=True),
        SandboxCheck("blend_is_binary", "custom", None, weight=2.0, critical=True),
        SandboxCheck("blend_min_size", "custom", None, weight=1.0, critical=True),
        SandboxCheck("frames_rendered", "custom", None, weight=1.0),
    ],
    max_repair_attempts=2,
    timeout_s=600.0,
    max_output_tokens=6144,
    network_allowed=False,
    allowed_executables=("blender",),
    artifacts=("build_scene.py", "scene.blend", "frames/"),
)


# --- 13.4 Agentic tasks (email / calendar / web fetch) --------------------

EMAIL_TASK = SandboxTask(
    id="email_write",
    kind=SandboxTaskKind.TEXT,
    title="Professional follow-up email",
    prompt=(
        "Write a concise professional follow-up email to a client after a "
        "project kickoff. Include a Subject line, a greeting, a 2-3 sentence "
        "body with the next step and a concrete deadline, and a closing. "
        "Output only the email, with no placeholders such as [name]."
    ),
    checks=[
        SandboxCheck("has_subject", "regex", r"^Subject:\s*\S+", weight=2.0, critical=True),
        SandboxCheck("has_greeting", "regex", r"\b(Dear|Hello|Hi)\b", weight=1.0),
        SandboxCheck(
            "has_closing",
            "regex",
            r"\b(Best regards|Kind regards|Sincerely|Best,)\b",
            weight=1.0,
        ),
        SandboxCheck(
            "has_next_step_and_deadline",
            "regex",
            r"(next step|deadline|by\s+\w+)",
            weight=1.5,
        ),
        SandboxCheck("no_placeholders", "regex", r"\[[^\]]+\]", weight=2.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=180.0,
    max_output_tokens=1024,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("email.txt",),
)

CALENDAR_TASK = SandboxTask(
    id="calendar_event",
    kind=SandboxTaskKind.TEXT,
    title="Create a calendar event JSON",
    prompt=(
        "Create one calendar event for a 45-minute project kickoff on "
        "2026-11-10 starting at 10:00 Europe/Bratislava. Return ONLY a JSON "
        "object with title, start, end, attendees (alice@example.com and "
        "bob@example.com), and location 'Meet'. Use ISO 8601 datetimes."
    ),
    checks=[
        SandboxCheck(
            "has_required_keys",
            "json",
            ["title", "start", "end", "attendees", "location"],
            weight=3.0,
            critical=True,
        ),
        SandboxCheck("start_iso", "regex", r"2026-11-10T10:00", weight=2.0),
        SandboxCheck("end_iso", "regex", r"2026-11-10T10:45", weight=2.0),
        SandboxCheck("has_attendees", "regex", r"alice@example\.com", weight=1.0),
        SandboxCheck("no_markdown_fence", "regex", r"```", weight=1.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=180.0,
    max_output_tokens=1024,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("calendar.json",),
)

EMAIL_CALENDAR_TASK = SandboxTask(
    id="email_and_calendar",
    kind=SandboxTaskKind.TEXT,
    title="Email + calendar from meeting notes",
    prompt=(
        "From these notes: 'Kickoff with Acme on 2026-11-10 at 10:00 "
        "Europe/Bratislava; attendees alice@example.com and "
        "bob@example.com; next step send the API draft by 2026-11-07.' "
        "The kickoff is scheduled for 45 minutes (10:00–10:45 "
        "Europe/Bratislava). Write (1) a short follow-up email with Subject "
        "and next step, then the separator line '--- CALENDAR ---', then "
        "(2) one JSON object with title, start, end, attendees, location. "
        "Use ISO 8601 datetimes: start 2026-11-10T10:00, end 2026-11-10T10:45. "
        "No markdown fences."
    ),
    checks=[
        SandboxCheck("has_subject", "regex", r"Subject:\s*\S+", weight=2.0, critical=True),
        SandboxCheck("has_next_step", "regex", r"2026-11-07|next step", weight=1.5),
        SandboxCheck("has_calendar_separator", "regex", r"--- CALENDAR ---", weight=1.0),
        SandboxCheck("calendar_start", "regex", r"2026-11-10T10:00", weight=2.0),
        SandboxCheck("calendar_end", "regex", r"2026-11-10T10:45", weight=2.0),
        SandboxCheck("calendar_keys", "regex", r"\"(title|start|end|attendees|location)\"", weight=2.0),
        SandboxCheck("no_markdown_fence", "regex", r"```", weight=1.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=2048,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("response.txt",),
)

WEB_FETCH_TASK = SandboxTask(
    id="web_fetch_brief",
    kind=SandboxTaskKind.TEXT,
    title="Web fetch brief (tool-use protocol)",
    prompt=(
        "You have a web_fetch tool. For https://www.nvidia.com/en-us/geforce/"
        "graphics-cards/rtx-3060/ return ONLY a JSON object with keys "
        "'tool' ('web_fetch'), 'url', 'title', 'facts' (2 bullet strings) and "
        "'citation'. If you cannot fetch, return {'tool':'web_fetch',"
        "'url':...,'error':'network unavailable'} instead of inventing facts."
    ),
    checks=[
        SandboxCheck("is_json", "json", ["tool", "url"], weight=2.0, critical=True),
        SandboxCheck("tool_is_web_fetch", "regex", r"\"tool\"\s*:\s*\"web_fetch\"", weight=2.0),
        SandboxCheck("has_nvidia_url", "regex", r"nvidia\.com", weight=1.0),
        SandboxCheck("has_facts_or_error", "regex", r"(\"facts\"|\"error\")", weight=1.5),
        SandboxCheck("no_markdown_fence", "regex", r"```", weight=1.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=180.0,
    max_output_tokens=1024,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("web_fetch.json",),
)


# --- 13.5 Web search / deep research / scraping ---------------------------

WEB_SEARCH_TASK = SandboxTask(
    id="web_search",
    kind=SandboxTaskKind.TEXT,
    title="Web search + scraping script",
    prompt=(
        "Write a Python script that performs web research on the topic "
        "'RTX 3060 Laptop GPU 6 GB VRAM local LLM inference'. The script "
        "must: (1) define a list of 3+ search queries, (2) show how it would "
        "fetch a page with a proper User-Agent and timeout, (3) extract text "
        "with BeautifulSoup or similar, (4) handle network errors gracefully, "
        "(5) print a short summary of findings. Output ONLY the Python code, "
        "in a markdown code fence. Do not actually access the network in this "
        "sandbox - this is a code-quality task, not a live crawl."
    ),
    checks=[
        # Real Python code, not a markdown fence: the runner strips fences from
        # the artifact before writing it, so requiring "```python" could never
        # pass a genuine solution. Anchored per line so a cleaned artifact and a
        # fenced one both score correctly.
        SandboxCheck(
            "is_python_code",
            "regex",
            r"(?m)^\s*(import\s|from\s+\w+\s+import|def\s+\w+|class\s+\w+|#!)",
            weight=2.0,
            critical=True,
        ),
        SandboxCheck("has_queries", "regex", r"(queries|search|q\s*=)", weight=1.5),
        SandboxCheck("has_user_agent", "regex", r"(User-Agent|user.agent)", weight=1.5),
        SandboxCheck("has_timeout", "regex", r"(timeout|Timeout)", weight=1.0),
        SandboxCheck("has_error_handling", "regex", r"(try|except|Exception)", weight=1.5),
        SandboxCheck("has_extraction", "regex", r"(BeautifulSoup|soup|\.get_text|\.text)", weight=1.5),
        SandboxCheck("has_summary", "regex", r"(summary|print|findings)", weight=1.0),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=3072,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("web_search.py",),
)

DEEP_RESEARCH_TASK = SandboxTask(
    id="deep_research",
    kind=SandboxTaskKind.TEXT,
    title="Deep research plan",
    prompt=(
        "Create a deep research plan for the question: 'Can a 70B MoE model "
        "run well on consumer hardware with 24 GB VRAM?' Your plan must "
        "include: (1) 3+ specific sub-questions, (2) 3+ search strategies / "
        "queries, (3) criteria for evaluating source quality, (4) how you "
        "would resolve conflicting claims, (5) a concise synthesized answer "
        "based on what you already know, marked as preliminary. Output only "
        "the plan, no markdown fences."
    ),
    checks=[
        SandboxCheck("has_subquestions", "regex", r"(sub.?question|1\.|2\.|3\.)", weight=2.0, critical=True),
        SandboxCheck("has_search_strategy", "regex", r"(search|query|strategy)", weight=1.5),
        SandboxCheck("has_source_criteria", "regex", r"(source|quality|credible|reliable)", weight=1.5),
        SandboxCheck("has_conflict_resolution", "regex", r"(conflict|contradict|resolve|discrepanc)", weight=1.5),
        SandboxCheck("has_synthesis", "regex", r"(synthesis|preliminary|conclusion)", weight=1.5),
        SandboxCheck("no_markdown_fence", "regex", r"```", weight=1.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=3072,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("deep_research.txt",),
)


CREATIVE_3D_TASK = SandboxTask(
    id="creative_3d_voxel_island",
    kind=SandboxTaskKind.TEXT,
    title="Procedural voxel floating island (Creative 3D)",
    prompt=(
        "Build a fully procedural 3D voxel floating island inspired by Minecraft Skyblock. "
        "Output ONLY a single JavaScript module file named scene.js that exports exactly one "
        "function: createScene({ THREE, random }) which returns a THREE.Group containing the "
        "entire scene. Do NOT generate HTML, CSS, camera, lights, renderer, or OrbitControls - "
        "the benchmark runtime provides those. Build geometry procedurally with BoxGeometry etc. "
        "No external assets, textures, or network requests. Use the provided random() for any "
        "randomness. Required: irregular floating island (grass surface, dirt/stone underside "
        "narrowing downward), at least 3 trees (cubic trunks + green canopies), red apples on "
        "trees, at least 1 blue waterfall, smaller vegetation. Organize into named groups: "
        "VoxelIsland (root), Terrain, Trees, Waterfall, Vegetation. Output valid JavaScript only, "
        "no markdown fences."
    ),
    checks=[
        SandboxCheck("exports_create_scene", "regex", r"export\s+function\s+createScene", weight=2.0, critical=True),
        SandboxCheck("returns_group", "regex", r"new\s+THREE\.Group", weight=2.0),
        SandboxCheck("has_terrain_group", "regex", r"\.name\s*=\s*[\"']Terrain[\"']", weight=1.5),
        SandboxCheck("has_trees_group", "regex", r"\.name\s*=\s*[\"']Trees[\"']", weight=1.5),
        SandboxCheck("has_waterfall_group", "regex", r"\.name\s*=\s*[\"']Waterfall[\"']", weight=1.5),
        SandboxCheck("has_vegetation_group", "regex", r"\.name\s*=\s*[\"']Vegetation[\"']", weight=1.0),
        SandboxCheck("uses_random", "regex", r"random\s*\(", weight=1.0),
        SandboxCheck("no_html", "regex", r"<[a-z]", weight=1.0, negate=True),
        SandboxCheck("no_markdown_fence", "regex", r"```", weight=1.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("scene.js",),
)

BLENDER_CITY_TASK = SandboxTask(
    id="blender_city_bridge",
    kind=SandboxTaskKind.BLENDER,
    title="Small city with bridge",
    prompt=(
        "Write a Blender Python script that builds a small city of 4-6 cubic buildings of "
        "varying heights connected by a bridge across a gap, with a sun light and a camera that "
        "orbits the city. Set frame range 1-120, save scene.blend first, render the frames "
        "into frames/ using a path relative to the saved file "
        "(scene.render.filepath = '//frames/frame_'), and call "
        "bpy.ops.render.render(animation=True). "
        "Use primitive cubes for buildings and the bridge. Place buildings at varied locations "
        "and heights. The bridge should connect two building clusters."
    ),
    checks=[
        SandboxCheck("script_defines_scene", "regex", r"(bpy\.ops\.mesh|primitive_cube|primitive_plane)", weight=2.0, critical=True),
        SandboxCheck("has_buildings", "regex", r"(cube|building|block)", weight=1.5),
        SandboxCheck("has_bridge", "regex", r"(bridge|span|connect)", weight=1.5),
        SandboxCheck("has_camera", "regex", r"(Camera|camera)", weight=1.0),
        SandboxCheck("has_light", "regex", r"(Light|SUN|sun)", weight=1.0),
        SandboxCheck("has_keyframes", "regex", r"keyframe_insert", weight=1.5),
        SandboxCheck("has_frame_range", "regex", r"frame_(start|end)", weight=1.0),
        SandboxCheck("saves_blend", "regex", r"save_as_mainfile", weight=1.0, critical=True),
        SandboxCheck("renders", "regex", r"bpy\.ops\.render", weight=1.0),
        SandboxCheck("blend_runs", "custom", None, weight=1.0, critical=True),
        SandboxCheck("blend_is_binary", "custom", None, weight=2.0, critical=True),
        SandboxCheck("blend_min_size", "custom", None, weight=1.0, critical=True),
        SandboxCheck("frames_rendered", "custom", None, weight=1.0),
    ],
    max_repair_attempts=2,
    timeout_s=600.0,
    max_output_tokens=6144,
    network_allowed=False,
    allowed_executables=("blender",),
    artifacts=("build_scene.py", "scene.blend", "frames/"),
)

BLENDER_CITY_PREVIEW_TASK = SandboxTask(
    id="blender_city",
    kind=SandboxTaskKind.BLENDER,
    title="Low-poly city with one preview",
    prompt=(
        "Write a Blender Python script that builds a simple low-poly city: "
        "4-8 cubic buildings of varied heights on a ground plane, a road, "
        "a sun light and a camera looking at the city. Save the scene first "
        "as scene.blend, then render exactly ONE preview image named "
        "preview.png (PNG, at least 640x480) using "
        "bpy.ops.render.render(write_still=True). Do NOT render an animation "
        "and do not create a frames/ directory. Output ONLY the complete "
        "Python script in a markdown code fence starting with ```python and "
        "ending with ```."
    ),
    checks=[
        SandboxCheck("script_defines_scene", "regex", r"(bpy\.ops\.mesh|primitive_cube|primitive_plane)", weight=2.0, critical=True),
        SandboxCheck("has_buildings", "regex", r"(building|cube|block)", weight=1.5),
        SandboxCheck("has_ground", "regex", r"(ground|road|plane|floor)", weight=1.0),
        SandboxCheck("has_camera", "regex", r"(Camera|camera)", weight=1.0),
        SandboxCheck("has_light", "regex", r"(Light|SUN|sun)", weight=1.0),
        SandboxCheck("saves_blend", "regex", r"save_as_mainfile", weight=1.0, critical=True),
        SandboxCheck("renders_still", "regex", r"write_still\s*=\s*True", weight=1.5),
        SandboxCheck("no_animation", "regex", r"(animation\s*=\s*True|frame_end\s*=\s*[2-9])", weight=1.0, negate=True),
        SandboxCheck("blend_runs", "custom", None, weight=1.0, critical=True),
        SandboxCheck("blend_is_binary", "custom", None, weight=2.0, critical=True),
        SandboxCheck("blend_min_size", "custom", None, weight=1.0, critical=True),
        SandboxCheck("preview_rendered", "custom", None, weight=1.5, critical=True),
    ],
    max_repair_attempts=2,
    timeout_s=300.0,
    max_output_tokens=6144,
    network_allowed=False,
    allowed_executables=("blender",),
    artifacts=("build_scene.py", "scene.blend", "preview.png"),
)


DEEP_RESEARCH_REPORT_TASK = SandboxTask(
    id="deep_research_report",
    kind=SandboxTaskKind.WEB,
    title="Deep research HTML report (RACE/FACT simplified)",
    prompt=(
        "You are a deep research agent. Write a single self-contained HTML "
        "report answering the question: 'What are the real limits of running "
        "a 70B MoE model on consumer hardware with 24 GB VRAM, and how should "
        "conflicting Q3/Q4 speed claims be resolved?'\n\n"
        "Use ONLY the sources below. Cite every factual claim with the source "
        "name in square brackets, e.g. [primary_official]. Do not invent "
        "sources. If the sources do not answer something, say so explicitly. "
        "Include: a title, an executive summary, at least four sections with "
        "headings, a 'Conflicting claims' section, a 'Limitations and "
        "uncertainty' section, and a References section. Render as a clean "
        "print-ready HTML page (inline CSS, no external assets).\n\n"
        "SOURCES:\n"
        "--- primary_official ---\n" + RESEARCH_PACKAGE["primary_official"] + "\n\n"
        "--- technical_secondary ---\n" + RESEARCH_PACKAGE["technical_secondary"] + "\n\n"
        "--- outdated_source ---\n" + RESEARCH_PACKAGE["outdated_source"] + "\n\n"
        "--- conflicting_source ---\n" + RESEARCH_PACKAGE["conflicting_source"] + "\n\n"
        "--- irrelevant_source ---\n" + RESEARCH_PACKAGE["irrelevant_source"] + "\n\n"
        "END OF SOURCES."
    ),
    checks=[
        SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{1000,}", weight=1.0, critical=True),
        SandboxCheck("single_file_html", "regex", r"<!DOCTYPE\s+html|<html\b", weight=1.0, critical=True),
        SandboxCheck("has_title", "regex", r"<title>\s*\S+", weight=1.0),
        SandboxCheck("has_report_headings", "regex", r"(<h2|<h3)", weight=1.5),
        SandboxCheck("min_words", "min_words", 800, weight=1.5),
        SandboxCheck("cites_primary", "regex", r"primary_official", weight=2.0, critical=True),
        SandboxCheck("cites_technical", "regex", r"technical_secondary", weight=1.5),
        SandboxCheck("cites_conflicting", "regex", r"conflicting_source", weight=1.5),
        SandboxCheck("no_irrelevant_source", "regex", r"cassette", weight=2.0, negate=True),
        SandboxCheck("mentions_uncertainty", "regex", r"(not (stated|provided|mentioned)|no (information|mention)|uncertain|limitation)", weight=1.0),
        SandboxCheck("has_references", "regex", r"(references|bibliography|sources)", weight=1.0),
        SandboxCheck("no_external_assets", "regex", r"\.(png|jpg|jpeg|gif|zip)\b", weight=1.0, negate=True),
    ],
    max_repair_attempts=2,
    timeout_s=300.0,
    max_output_tokens=6144,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("index.html",),
)


SANDBOX_TASKS: dict[str, SandboxTask] = {
    t.id: t
    for t in (
        WEB_TASK,
        RESEARCH_TASK,
        BLENDER_TASK,
        BLENDER_CITY_TASK,
        BLENDER_CITY_PREVIEW_TASK,
        EMAIL_TASK,
        CALENDAR_TASK,
        EMAIL_CALENDAR_TASK,
        WEB_FETCH_TASK,
        WEB_SEARCH_TASK,
        DEEP_RESEARCH_TASK,
        DEEP_RESEARCH_REPORT_TASK,
        CREATIVE_3D_TASK,
        MINECRAFT_WORLD_TASK,
    )
}

#: Canonical alias used by the optimizer's post-run sandbox stage. Exactly
#: the same registry object - one source of truth for built-in tasks.
BUILTIN_TASKS: dict[str, SandboxTask] = SANDBOX_TASKS


def get_task_by_id(task_id: str) -> SandboxTask | None:
    """Resolve a built-in sandbox task by stable id (None when unknown)."""
    return SANDBOX_TASKS.get(task_id)


# --- Custom prompt schema + limits (spec §6.3) -----------------------------

CUSTOM_PROMPT_MAX_CHARS = 8000
CUSTOM_MAX_OUTPUT_TOKENS = 8192
CUSTOM_TIMEOUT_MIN_S = 30.0
CUSTOM_TIMEOUT_MAX_S = 3600.0
CUSTOM_TEMPERATURE_MIN = 0.0
CUSTOM_TEMPERATURE_MAX = 2.0

#: Display kind -> task kind. `text` stays a plain TEXT task.
_CUSTOM_KIND_MAP = {
    "text": SandboxTaskKind.TEXT,
    "html": SandboxTaskKind.WEB,
    "web": SandboxTaskKind.WEB,
    "scene": SandboxTaskKind.BLENDER,
    "blender": SandboxTaskKind.BLENDER,
    "research": SandboxTaskKind.RESEARCH,
}


def _stable_custom_id(prompt: str) -> str:
    """Deterministic id for a custom prompt (stable across processes)."""
    import hashlib

    return "custom_" + hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]


def validate_custom_prompt(spec: dict) -> dict:
    """Validate and normalise one custom sandbox prompt (spec §6.3).

    Enforces prompt/token/timeout/temperature limits and a valid kind.
    Raises ValueError with an actionable message on invalid input.
    """
    if not isinstance(spec, dict):
        raise ValueError("custom prompt must be an object")
    prompt = str(spec.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("custom prompt requires a non-empty 'prompt'")
    if len(prompt) > CUSTOM_PROMPT_MAX_CHARS:
        raise ValueError(
            f"custom prompt is {len(prompt)} chars; limit is {CUSTOM_PROMPT_MAX_CHARS}"
        )

    raw_kind = str(spec.get("kind") or "text").lower()
    kind = _CUSTOM_KIND_MAP.get(raw_kind)
    if kind is None:
        raise ValueError(
            f"unknown custom prompt kind {raw_kind!r}; "
            f"expected one of {', '.join(sorted(_CUSTOM_KIND_MAP))}"
        )

    try:
        max_tokens = int(spec.get("max_output_tokens", 2048))
    except (TypeError, ValueError):
        raise ValueError("max_output_tokens must be an integer") from None
    if not 1 <= max_tokens <= CUSTOM_MAX_OUTPUT_TOKENS:
        raise ValueError(
            f"max_output_tokens must be 1..{CUSTOM_MAX_OUTPUT_TOKENS} (got {max_tokens})"
        )

    try:
        timeout_s = float(spec.get("timeout_s", 300.0))
    except (TypeError, ValueError):
        raise ValueError("timeout_s must be a number") from None
    if not CUSTOM_TIMEOUT_MIN_S <= timeout_s <= CUSTOM_TIMEOUT_MAX_S:
        raise ValueError(
            f"timeout_s must be {CUSTOM_TIMEOUT_MIN_S:.0f}..{CUSTOM_TIMEOUT_MAX_S:.0f} "
            f"(got {timeout_s})"
        )

    try:
        temperature = float(spec.get("temperature", 0.2))
    except (TypeError, ValueError):
        raise ValueError("temperature must be a number") from None
    if not CUSTOM_TEMPERATURE_MIN <= temperature <= CUSTOM_TEMPERATURE_MAX:
        raise ValueError(
            f"temperature must be {CUSTOM_TEMPERATURE_MIN}..{CUSTOM_TEMPERATURE_MAX}"
        )

    checks_raw = spec.get("checks") or []
    if not isinstance(checks_raw, list):
        raise ValueError("checks must be a list")
    checks: list[SandboxCheck] = []
    for i, c in enumerate(checks_raw):
        if not isinstance(c, dict) or not c.get("name") or not c.get("kind"):
            raise ValueError(f"checks[{i}] requires 'name' and 'kind'")
        if c["kind"] not in ("files", "regex", "json", "exit_code"):
            raise ValueError(
                f"checks[{i}].kind must be files/regex/json/exit_code"
            )
        checks.append(
            SandboxCheck(
                name=str(c["name"]),
                kind=str(c["kind"]),
                value=c.get("value"),
                weight=float(c.get("weight", 1.0)),
                critical=bool(c.get("critical", False)),
                negate=bool(c.get("negate", False)),
            )
        )

    return {
        "id": str(spec.get("id") or _stable_custom_id(prompt)),
        "name": str(spec.get("name") or "Custom task")[:120],
        "prompt": prompt,
        "kind": kind.value,
        "task_kind": kind,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "timeout_s": timeout_s,
        "checks": checks,
        # No expected criteria -> human review only, never a fabricated score.
        "manual_review_only": not checks,
    }


# --- 13.5 Security --------------------------------------------------------


def _basename_any(path_token: str) -> str:
    """Basename for both Windows and POSIX path styles.

    ``Path(...).name`` is host-dependent: on POSIX a Windows-style path is a
    single filename, so separators must be handled explicitly. This keeps
    policy checks and display sanitisation identical on every CI runner.
    """
    cleaned = str(path_token).strip().strip('"').strip("'")
    return re.split(r"[\\/]", cleaned)[-1]


@dataclass
class SandboxPolicy:
    """Isolation and resource policy (spec 13.5)."""

    workdir: Path
    network_enabled: bool = False
    timeout_s: float = 300.0
    max_output_bytes: int = 2_000_000
    cpu_seconds: int = 120
    memory_mb: int = 4096
    disk_mb: int = 512
    allowed_executables: tuple[str, ...] = ()
    artifact_retention: str = "keep_last_10"

    def is_command_allowed(self, command: str) -> bool:
        """Only whitelisted executables may run."""
        if not self.allowed_executables:
            return False
        try:
            parts = shlex.split(command, posix=False)
        except ValueError:
            return False
        if not parts:
            return False
        exe = _basename_any(parts[0]).lower()
        if exe.endswith(".exe"):
            exe = exe[: -len(".exe")]
        return exe in {e.lower().removesuffix(".exe") for e in self.allowed_executables}

    def sanitize_command(self, command: str) -> str:
        """Render a command for display without leaking host paths."""
        try:
            parts = shlex.split(command, posix=False)
        except ValueError:
            return "<unparsable command>"
        if not parts:
            return ""
        exe = _basename_any(parts[0])
        return " ".join([exe, *parts[1:]])


# --- 13.4 Repair loop -----------------------------------------------------


@dataclass
class RepairAttempt:
    """One attempt of a sandbox task."""

    attempt: int
    output: str = ""
    exit_code: int | None = None
    passed: bool = False
    score: float = 0.0
    error: str = ""
    duration_s: float = 0.0
    #: What the model is told for the NEXT attempt.
    feedback: str = ""


def build_repair_feedback(
    task: SandboxTask,
    attempt: int,
    stdout: str = "",
    stderr: str = "",
    failing_checks: list[str] | None = None,
    screenshot: str | None = None,
) -> str:
    """Feedback for the next repair attempt (spec 13.4).

    The model gets the failure EVIDENCE and the remaining budget - never the
    solution.
    """
    remaining = max(0, task.max_repair_attempts - attempt)
    lines = [
        f"The previous attempt FAILED validation ({attempt}/{task.max_repair_attempts}).",
        "",
        "Failing acceptance criteria:",
    ]
    for check in failing_checks or []:
        lines.append(f"  - {check}")
    if stdout.strip():
        lines += ["", "stdout (tail):", stdout.strip()[-1500:]]
    if stderr.strip():
        lines += ["", "stderr (tail):", stderr.strip()[-1500:]]
    if screenshot:
        lines += ["", f"screenshot: {screenshot}"]
    lines += [
        "",
        f"Remaining repair attempts: {remaining}.",
        "Fix the failing criteria. Do not rewrite unrelated parts.",
    ]
    if remaining == 0:
        lines.append("This is the LAST attempt - make it count.")
    return "\n".join(lines)


def score_attempt(
    task: SandboxTask,
    files: dict[str, str],
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 0,
    custom_results: dict[str, tuple[bool, str]] | None = None,
) -> tuple[float, list[str], list[str]]:
    """Evaluate one attempt against the task's checks.

    Returns (score, failing_check_names, critical_failures). A critical
    failure zeroes the score: it vetoes the attempt instead of merely
    lowering the aggregate.
    """
    total = 0.0
    weight_sum = 0.0
    failing: list[str] = []
    critical: list[str] = []

    def _strip_md_fences(text: str) -> str:
        """Strip ```...``` markdown fences from text, returning inner content."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n", 1)
            if len(lines) > 1:
                # Remove opening ```lang line
                rest = lines[1]
                if rest.endswith("```"):
                    rest = rest[:-3].rstrip()
                return rest
        return text

    # A Python artifact is valid when it actually parses. This is stronger than
    # any regex and fence-independent (real solutions are stored without fences,
    # but scoring must accept a fenced paste too).
    if any(c.name == "is_python_code" for c in task.checks):
        py_text = "\n".join(
            _strip_md_fences(text)
            for name, text in files.items()
            if name.endswith(".py")
        )
        if py_text:
            try:
                compile(py_text, "<sandbox>", "exec")
                custom_results = {
                    **(custom_results or {}),
                    "is_python_code": (True, "compiles"),
                }
            except SyntaxError as exc:
                custom_results = {
                    **(custom_results or {}),
                    "is_python_code": (False, f"syntax error: {exc.msg}"),
                }

    for check in task.checks:
        ok = False
        detail = ""
        if custom_results and check.name in custom_results:
            ok, detail = custom_results[check.name]
        elif check.kind == "files":
            required = [str(f) for f in (check.value or [])]
            ok = all(f in files for f in required)
            detail = f"missing={[f for f in required if f not in files]}" if not ok else "ok"
        elif check.kind == "regex":
            pattern = str(check.value or "")
            haystack = "\n".join(files.values()) + "\n" + stdout + "\n" + stderr
            hit = re.search(pattern, haystack, re.IGNORECASE | re.DOTALL) is not None
            if check.negate:
                ok = not hit
                detail = "forbidden pattern present" if hit else "clean"
            else:
                ok = hit
                detail = "hit" if hit else "miss"
        elif check.kind == "exit_code":
            ok = exit_code == 0
            detail = f"exit={exit_code}"
        elif check.kind == "json":
            try:
                combined = "\n".join(files.values())
                doc = json.loads(_strip_md_fences(combined))
                ok = all(k in doc for k in (check.value or []))
                detail = "ok" if ok else "missing keys"
            except Exception:
                ok = False
                detail = "invalid json"
        elif check.kind == "min_words":
            combined = "\n".join(files.values())
            text = re.sub(
                r"<style[\s\S]*?</style>|<script[\s\S]*?</script>",
                " ",
                combined,
                flags=re.IGNORECASE,
            )
            text = re.sub(r"<[^>]+>", " ", text)
            words = len(re.findall(r"\w+", text))
            target = int(check.value or 0)
            ok = words >= target
            detail = f"{words} words (min {target})"
        else:
            ok = False
            detail = f"unknown check kind {check.kind}"
        total += check.weight if ok else 0.0
        weight_sum += check.weight
        if not ok:
            failing.append(f"{check.name} ({detail})")
            if check.critical:
                critical.append(f"{check.name} ({detail})")
    score = (total / weight_sum) if weight_sum else 0.0
    if critical:
        # A critical check is a veto, not a partial deduction: an artifact
        # that cannot be used must not keep a high aggregate score.
        score = 0.0
    return score, failing, critical


def repair_penalty(attempt_index: int) -> float:
    """Score multiplier per attempt (spec 13.4).

    First pass 100%, after one repair 90%, after two repairs 80%.
    """
    return {0: 1.0, 1: 0.9, 2: 0.8}.get(attempt_index, 0.8)


@dataclass
class SandboxResult:
    """Full sandbox run result (spec 13.1/13.4)."""

    task_id: str
    first_pass_success: bool = False
    final_success: bool = False
    repair_count: int = 0
    final_score: float = 0.0
    penalized_score: float = 0.0
    attempts: list[RepairAttempt] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "first_pass_success": self.first_pass_success,
            "final_success": self.final_success,
            "repair_count": self.repair_count,
            "final_score": round(self.final_score, 4),
            "penalized_score": round(self.penalized_score, 4),
            "attempts": [
                {
                    "attempt": a.attempt,
                    "passed": a.passed,
                    "score": round(a.score, 4),
                    "error": a.error,
                    "duration_s": round(a.duration_s, 1),
                }
                for a in self.attempts
            ],
            "artifacts": list(self.artifacts),
            "critical_failures": list(self.critical_failures),
            "error": self.error,
        }
