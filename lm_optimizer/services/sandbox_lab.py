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
    VISION = "vision"  # image description; scored by keyword overlap


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
    #: Human-facing hint shown to the model during repair. Must never reveal
    #: the check name, the expected value, the regex, counts or any fact about
    #: the image. Empty -> generic line is used instead.
    hint: str = ""
    #: Internal diagnostic detail from the last score_attempt run. Never shown
    #: to the model (build_repair_feedback ignores it); kept for error messages
    #: and debugging only.
    detail: str = ""


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
    image_path: str = ""
    max_output_tokens: int = 2048
    network_allowed: bool = False
    experimental: bool = False


# --- 13.1 Web task: company marketing site ---------------------------------

WEB_TASK = SandboxTask(
    id="company_website",
    kind=SandboxTaskKind.WEB,
    title="Company marketing website",
    prompt=(
        "Build a complete single-file marketing website for a fictional "
        "company called \"Northwind Studio\", a small design and engineering "
        "consultancy. Everything must live in one index.html: inline CSS, no "
        "build step, no external assets, no network calls (no CDN fonts, "
        "images, scripts or stylesheets).\n\n"
        "The page must contain:\n"
        "- A sticky header with the company name and section navigation.\n"
        "- A hero section with a headline, one sentence of supporting copy and "
        "a primary call-to-action button.\n"
        "- A services section with at least three services, each with a title "
        "and a short description.\n"
        "- An about section that explains who the company is.\n"
        "- At least one customer testimonial with a named author.\n"
        "- A contact section with a working-looking form (name, email, "
        "message) and a submit button.\n"
        "- A footer with the company name and a copyright line.\n"
        "- Responsive layout that works on mobile (<= 600px) and desktop, with "
        "a real media query.\n"
        "- Accessible markup: semantic sections, one h1, labels for inputs.\n\n"
        "Output ONLY the complete HTML document starting with <!DOCTYPE html>, "
        "no markdown fences, no explanations."
    ),
    checks=[
        SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
        SandboxCheck("html_document", "custom", None, weight=2.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{50,}", weight=1.0, critical=True),
        SandboxCheck("has_viewport", "regex", r'name=["\']viewport["\']', weight=1.0),
        SandboxCheck("has_media_query", "regex", r"@media", weight=1.0),
        SandboxCheck("has_header_nav", "regex", r"(<header|<nav)", weight=1.0),
        SandboxCheck("has_hero_h1", "regex", r"<h1[^>]*>\s*\S+", weight=1.5),
        SandboxCheck("has_services", "regex", r"(service|what we do|expertise)", weight=1.0),
        SandboxCheck("has_about", "regex", r"(about|who we are|our story)", weight=1.0),
        SandboxCheck("has_testimonial", "regex", r"(testimonial|quote|said)", weight=1.0),
        SandboxCheck("has_contact_form", "regex", r"<form[\s\S]*?(<input|<textarea)", weight=1.5),
        SandboxCheck("has_footer", "regex", r"<footer", weight=1.0),
        SandboxCheck("has_cta", "regex", r"(class=[\"'][^\"']*(btn|button|cta)|<button)", weight=1.0),
        SandboxCheck("min_words", "min_words", 150, weight=1.0),
        SandboxCheck("no_external_scripts", "regex", r"<script[^>]+src=[\"']https?://", weight=1.5, negate=True),
        SandboxCheck("no_external_styles", "regex", r"<link[^>]+href=[\"']https?://", weight=1.5, negate=True),
        SandboxCheck("no_external_assets", "regex", r"\.(png|jpg|jpeg|gif|webp|svg)\b", weight=1.0, negate=True),
        SandboxCheck("js_parses", "custom", None, weight=1.5, critical=True),
        SandboxCheck("renders_content", "custom", None, weight=2.0, critical=True),
    ],
    max_repair_attempts=1,
    timeout_s=300.0,
    max_output_tokens=6144,
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
        SandboxCheck("html_document", "custom", None, weight=2.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{50,}", weight=1.0, critical=True),
        SandboxCheck("single_file_html", "regex", r"<!DOCTYPE\s+html|<html\b", weight=1.0, critical=True),
        SandboxCheck("has_threejs", "regex", r"(<script[^>]+src=[\"'][^\"']*three|three\.module\.js|import\s*\(\s*[\"'][^\"']*three|[\"']three[\"']\s*:\s*[\"'])", weight=1.0),
        SandboxCheck("has_voxel_cubes", "regex", r"(BoxGeometry\s*\(|InstancedMesh\s*\()", weight=1.5),
        SandboxCheck("has_grass", "regex", r"(grassTop|grassSide|grass\s*[:=]|0x4caf50|#4caf50)", weight=1.0),
        SandboxCheck("has_stone", "regex", r"(stone\s*[:=]|stoneTop|0x8b939b|#8b939b|#808080)", weight=1.0),
        SandboxCheck("has_water", "regex", r"(water\s*[:=]|waterMat|0x2f7fd4|#2f7fd4|#3a8fe0)", weight=1.0),
        SandboxCheck("has_camera", "regex", r"(PerspectiveCamera|\.lookAt\s*\()", weight=1.5),
        SandboxCheck("has_render_loop", "regex", r"(requestAnimationFrame\s*\(|function\s+animate\s*\()", weight=1.5),
        SandboxCheck("no_external_assets", "regex", r"\.(png|jpg|jpeg|gif|zip)\b", weight=1.0, negate=True),
        SandboxCheck("js_parses", "custom", None, weight=1.5, critical=True),
        SandboxCheck("renders_content", "custom", "canvas", weight=2.0, critical=True),
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
        SandboxCheck("mentions_unknown", "regex", r"(not\s+(stated|provided|mentioned|specified|answered|covered|given|clear)|no\s+(information|mention|data|answer|evidence)|unclear|unknown|insufficient|cannot\s+(be\s+)?determin|does\s+not\s+(say|state|specify|answer|cover))", weight=1.0),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=(),
    artifacts=(),
)


# --- 13.3 Blender task: dense city, .blend only, no renders ----------------

CITY_MAP_LAYOUT = """##..##..##..
##..##..##..
............
##..##..##..
##..##..##..
~~~~~~~~~~~~
PP..##..##..
##..##..##..
............
##..##..##..
##..##..##..
............"""

BLENDER_CITY_TASK = SandboxTask(
    id="blender_city",
    kind=SandboxTaskKind.BLENDER,
    title="Dense low-poly city from a map excerpt",
    prompt=(
        "Target environment: Blender 5.3, the `bpy` Python API, run headless as\n"
        "`blender --background --python build_scene.py`. Blender 5.x notes that\n"
        "matter here: `bpy.context.scene.collection` is read-only, so create a\n"
        "new collection and link it; the camera op is\n"
        "`bpy.ops.object.camera_add`, the light op `bpy.ops.object.light_add`,\n"
        "and saving is `bpy.ops.wm.save_as_mainfile(filepath='scene.blend')`.\n"
        "Do NOT use pre-5.x idioms (e.g. assigning `scene.collection.name`).\n\n"
        "Working skeleton (verified on Blender 5.3 - extend it, do not replace\n"
        "the collection handling):\n"
        "```python\n"
        "import bpy\n"
        "for o in list(bpy.data.objects):\n"
        "    bpy.data.objects.remove(o, do_unlink=True)\n"
        "root = bpy.data.collections.new('City')\n"
        "bpy.context.scene.collection.children.link(root)\n"
        "def cube(name, loc, scale, coll):\n"
        "    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)\n"
        "    ob = bpy.context.object\n"
        "    ob.name = name\n"
        "    ob.scale = scale\n"
        "    for c in list(ob.users_collection):\n"
        "        c.objects.unlink(ob)\n"
        "    coll.objects.link(ob)\n"
        "    return ob\n"
        "bpy.ops.object.camera_add(location=(30, -30, 25))\n"
        "bpy.context.scene.camera = bpy.context.object\n"
        "bpy.ops.object.light_add(type='SUN', location=(10, 10, 30))\n"
        "bpy.ops.wm.save_as_mainfile(filepath='scene.blend')\n"
        "```\n\n"
        "Build a dense low-poly city in Blender from the map excerpt below. "
        "Each character is one 4 m cell and the grid is 12 x 12 cells.\n\n"
        "MAP (rows top to bottom):\n"
        + CITY_MAP_LAYOUT
        + "\n\n"
        "Legend: '#' is a city block that must contain 2-4 separate buildings, "
        "'.' is a street (keep it clear of buildings, 2 cells wide), '~' is a "
        "river running across the city, 'P' is a park with trees.\n\n"
        "Requirements:\n"
        "- Build the entire grid, not a subset: at least 60 buildings total, "
        "spread over every '#' block.\n"
        "- Vary the heights: ordinary buildings 2-8 floors, at least 3 landmark "
        "towers of 20 m or more, so the skyline is not flat.\n"
        "- The park needs at least 4 trees (trunk plus foliage).\n"
        "- The river must be a separate flat mesh, not a hole in the ground.\n"
        "- One ground plane under everything, streets visible as lighter strips.\n"
        "- A sun light and one camera framing the city from above at an angle.\n"
        "- Give the scene and the main collections clear names.\n"
        "- Save the scene as scene.blend. Do NOT render anything: no "
        "preview.png, no frames directory, no images of any kind, and do not "
        "call bpy.ops.render.\n\n"
        "Blender API reference (use EXACTLY these calls, do not invent "
        "new ones):\n"
        "- Add a mesh: bpy.ops.mesh.primitive_cube_add(size=1, location=(x,y,z))\n"
        "- Add a plane: bpy.ops.mesh.primitive_plane_add(size=N, location=(x,y,z))\n"
        "- Add a cylinder: bpy.ops.mesh.primitive_cylinder_add(radius=R, depth=D, location=(x,y,z))\n"
        "- Add a camera: bpy.ops.object.camera_add(location=(x,y,z))\n"
        "- Add a sun light: bpy.ops.object.light_add(type='SUN', location=(x,y,z))\n"
        "- Select all: bpy.ops.object.select_all(action='SELECT')\n"
        "- Delete selected: bpy.ops.object.delete()\n"
        "- Save: bpy.ops.wm.save_as_mainfile(filepath='scene.blend')\n"
        "- Set object name: obj.name = 'Name'\n"
        "- Link to collection: bpy.context.scene.collection.children.link(collection)\n"
        "- Create collection: bpy.data.collections.new('Name')\n\n"
        "Output ONLY the complete Python script in a markdown code fence "
        "starting with ```python and ending with ```. Do not include any other "
        "text."
    ),
    checks=[
        SandboxCheck("script_defines_scene", "regex", r"(bpy\.ops\.mesh|primitive_cube|primitive_plane)", weight=2.0, critical=True),
        SandboxCheck("has_buildings", "regex", r"(building|tower|block)", weight=1.5),
        SandboxCheck("has_streets", "regex", r"(street|road|avenue)", weight=1.0),
        SandboxCheck("has_park", "regex", r"(park|tree|foliage)", weight=1.0),
        SandboxCheck("has_river", "regex", r"(river|water)", weight=1.0),
        SandboxCheck("has_camera", "regex", r"(Camera|camera)", weight=1.0),
        SandboxCheck("has_light", "regex", r"(Light|SUN|sun)", weight=1.0),
        SandboxCheck("is_python_code", "custom", None, weight=2.0, critical=True),
        SandboxCheck("saves_blend", "regex", r"save_as_mainfile", weight=1.0, critical=True),
        SandboxCheck("no_render", "regex", r"bpy\.ops\.render", weight=1.5, negate=True, critical=True),
        SandboxCheck("blend_runs", "custom", None, weight=1.0, critical=True),
        SandboxCheck("blend_is_binary", "custom", None, weight=2.0, critical=True),
        SandboxCheck("blend_min_size", "custom", None, weight=1.0, critical=True),
        SandboxCheck("blend_has_camera", "custom", None, weight=1.0),
        SandboxCheck("blend_has_light", "custom", None, weight=1.0),
        SandboxCheck("city_mesh_count", "custom", None, weight=2.0, critical=True),
        SandboxCheck("city_height_variety", "custom", None, weight=1.5),
        SandboxCheck("city_footprint", "custom", None, weight=1.0),
    ],
    max_repair_attempts=1,
    timeout_s=600.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=("blender",),
    artifacts=("build_scene.py", "scene.blend"),
)


# --- 13.4 Agentic tasks (email / calendar / web fetch) --------------------

EMAIL_TASK = SandboxTask(
    id="email_write",
    kind=SandboxTaskKind.TEXT,
    title="Professional follow-up email (multi-part)",
    prompt=(
        "You are an executive assistant. A client meeting just happened. "
        "Here is the meeting transcript:\n\n"
        "Alice (client): 'We need the new dashboard by end of Q3. The current "
        "version is too slow and the export feature is broken.'\n"
        "Bob (PM): 'Understood. We'll prioritize the dashboard and fix the export. "
        "Can we have a demo by next Friday?'\n"
        "Alice: 'Yes, that works. Also, please send us the updated timeline.'\n"
        "Bob: 'Will do. I'll send it by Wednesday.'\n\n"
        "TASK 1: Write a 3-5 sentence summary of the meeting (key decisions and "
        "next steps). Output it under a heading '## Summary'.\n\n"
        "TASK 2: Write a professional follow-up email to Alice based on the "
        "summary. Include a Subject line, a greeting, a body with the next step "
        "and a concrete deadline, and a closing. Output it under a heading "
        "'## Email'. Output only the two sections, no extra text."
    ),
    checks=[
        SandboxCheck("has_summary", "regex", r"##\s*Summary", weight=2.0, critical=True),
        SandboxCheck("has_email", "regex", r"##\s*Email", weight=2.0, critical=True),
        SandboxCheck("has_subject", "regex", r"Subject(?:\s+line)?\s*[:\-]\s*\S+", weight=2.0, critical=True),
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
            r"(next step|deadline|by\s+\w+|Wednesday|Friday)",
            weight=1.5,
        ),
        SandboxCheck("no_placeholders", "regex", r"\[[^\]]+\]", weight=2.0, negate=True),
        SandboxCheck("summary_min_words", "min_words", 20, weight=1.0),
        SandboxCheck("email_min_words", "min_words", 30, weight=1.0),
    ],
    max_repair_attempts=1,
    timeout_s=300.0,
    max_output_tokens=1024,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("email.txt",),
)

MULTILINGUAL_TASK = SandboxTask(
    id="language_puzzle",
    kind=SandboxTaskKind.TEXT,
    title="Multi-language word puzzles (declension, tenses, morphology)",
    prompt=(
        "You are a linguist. Answer each of the following 12 questions. "
        "For each, give ONLY the correct form, no explanation.\n\n"
        "1. Slovak declension: genitive singular of 'diet (child).\n"
        "2. Slovak declension: instrumental plural of 'mesto' (city).\n"
        "3. English: past tense of 'run'.\n"
        "4. English: third-person singular present of 'go'.\n"
        "5. German: genitive singular of 'das Kind' (the child).\n"
        "6. French: passe compose of 'aller' (to go) for 'je'.\n"
        "7. Spanish: preterito perfecto of 'hablar' (to speak) for 'yo'.\n"
        "8. Italian: passato prossimo of 'andare' (to go) for 'io'.\n"
        "9. Russian: genitive singular of 'kniga' (book).\n"
        "10. Chinese: measure word (classifier) for 'book'.\n"
        "11. Japanese: past tense of 'taberu' (to eat).\n"
        "12. Arabic: plural of 'kitab' (book).\n\n"
        "Output format: numbered list 1-12, one answer per line. "
        "No extra text."
    ),
    checks=[
        SandboxCheck("has_answers", "regex", r"1\.\s*\S", weight=1.0, critical=True),
        SandboxCheck("answer_diet", "regex", r"1\.\s*det", weight=1.5, critical=True),
        SandboxCheck("answer_mesto", "regex", r"2\.\s*mestami", weight=1.5, critical=True),
        SandboxCheck("answer_run", "regex", r"3\.\s*ran\b", weight=1.5, critical=True),
        SandboxCheck("answer_go", "regex", r"4\.\s*goes\b", weight=1.5, critical=True),
        SandboxCheck("answer_kind", "regex", r"5\.\s*des\s+Kindes", weight=1.5, critical=True),
        SandboxCheck("answer_aller", "regex", r"6\.\s*suis\s+all", weight=1.5, critical=True),
        SandboxCheck("answer_hablar", "regex", r"7\.\s*he\s+hablado", weight=1.5, critical=True),
        SandboxCheck("answer_andare", "regex", r"8\.\s*sono\s+andato", weight=1.5, critical=True),
        SandboxCheck("answer_kniga", "regex", r"9\.\s*knigi", weight=1.5, critical=True),
        SandboxCheck("answer_chinese", "regex", r"10\.\s*ben", weight=1.5, critical=True),
        SandboxCheck("answer_taberu", "regex", r"11\.\s*tabeta", weight=1.5, critical=True),
        SandboxCheck("answer_kitab", "regex", r"12\.\s*kutub", weight=1.5, critical=True),
        SandboxCheck("no_placeholders", "regex", r"\[[^\]]+\]", weight=2.0, negate=True),
        SandboxCheck("min_words", "min_words", 12, weight=1.0),
    ],
    max_repair_attempts=1,
    timeout_s=120.0,
    max_output_tokens=512,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("language.txt",),
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
        SandboxCheck("has_subject", "regex", r"Subject(?:\s+line)?\s*[:\-]\s*\S+", weight=2.0, critical=True),
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
        SandboxCheck("js_parses", "custom", None, weight=2.0, critical=True),
    ],
    max_repair_attempts=1,
    timeout_s=240.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("scene.js",),
)

LONG_CONTEXT_TASK = SandboxTask(
    id="long_context_generation",
    kind=SandboxTaskKind.TEXT,
    title="Long-context coherence (hallucination check)",
    prompt=(
        "Write a detailed, well-structured essay of at least 2000 words about "
        "the history of space exploration. Cover: the early rocket pioneers "
        "(Godard, von Braun), the Space Race (Sputnik, Apollo), the Space "
        "Shuttle era, the ISS, commercial spaceflight (SpaceX, Blue Origin), "
        "and future plans (Mars, Artemis). Use clear headings for each section. "
        "Do not repeat yourself. Every section must contain new information. "
        "Do not hallucinate facts - if you are unsure, say so. End with a "
        "concise conclusion."
    ),
    checks=[
        SandboxCheck("min_length", "min_words", 1500, weight=2.0, critical=True),
        SandboxCheck("has_headings", "regex", r"#{1,3}\s+\w", weight=1.0, critical=True),
        SandboxCheck("no_repeated_paragraphs", "custom", None, weight=2.0, critical=False),
        SandboxCheck("coherent_ending", "custom", None, weight=1.5, critical=True),
    ],
    max_repair_attempts=1,
    timeout_s=300.0,
    max_output_tokens=4096,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("essay.txt",),
)

VISION_DESCRIBE_TASK = SandboxTask(
    id="vision_describe",
    kind=SandboxTaskKind.VISION,
    title="Image description (vision)",
    prompt=(
        "Describe this image in detail. What objects, colors, textures, and "
        "scenes do you see? Be specific and accurate. Do not guess or invent "
        "details that are not visible. Output only the description."
    ),
    checks=[
        SandboxCheck("min_words", "min_words", 10, weight=1.0, critical=True),
        SandboxCheck("mentions_texture", "regex", r"(dirt|soil|ground|texture|surface|brown|earth)", weight=2.0, critical=True),
        SandboxCheck("no_hallucination", "regex", r"(cat|dog|person|car|building|sky|ocean|mountain)", weight=2.0, negate=True),
    ],
    max_repair_attempts=0,
    timeout_s=120.0,
    max_output_tokens=512,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("description.txt",),
    image_path="benchmarks/deepseek_agent/minecraft_world/textures/pixel_perfection/source/default_dirt.png",
    experimental=True,
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
        SandboxCheck("html_document", "custom", None, weight=2.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{1000,}", weight=1.0, critical=True),
        SandboxCheck("single_file_html", "regex", r"<!DOCTYPE\s+html|<html\b", weight=1.0, critical=True),
        SandboxCheck("has_title", "regex", r"<title>\s*\S+", weight=1.0),
        SandboxCheck("has_report_headings", "regex", r"(<h2|<h3)", weight=1.5),
        SandboxCheck("min_words", "min_words", 300, weight=1.5),
        SandboxCheck("cites_primary", "regex", r"primary_official", weight=2.0, critical=True),
        SandboxCheck("cites_technical", "regex", r"technical_secondary", weight=1.5),
        SandboxCheck("cites_conflicting", "regex", r"conflicting_source", weight=1.5),
        SandboxCheck("no_irrelevant_source", "regex", r"cassette", weight=2.0, negate=True),
        SandboxCheck("no_repeated_paragraphs", "custom", None, weight=1.5, critical=False),
        SandboxCheck("coherent_ending", "custom", None, weight=1.0),
        SandboxCheck("mentions_uncertainty", "regex", r"(not\s+(stated|provided|mentioned|specified|answered|covered|given|clear)|no\s+(information|mention|data|answer|evidence)|uncertain|limitation|unclear|unknown|insufficient)", weight=1.0),
        SandboxCheck("has_references", "regex", r"(references|bibliography|sources)", weight=1.0),
        SandboxCheck("no_external_assets", "regex", r"\.(png|jpg|jpeg|gif|zip)\b", weight=1.0, negate=True),
        SandboxCheck("renders_content", "custom", None, weight=1.5, critical=True),
    ],
    max_repair_attempts=2,
    timeout_s=300.0,
    max_output_tokens=6144,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("index.html",),
)


DEEP_RESEARCH_ONLINE_TASK = SandboxTask(
    id="deep_research_online",
    kind=SandboxTaskKind.WEB,
    title="Online deep research report (scraped sources)",
    prompt=(
        "Research the question with live web sources: plan several sub-queries, "
        "search the web, scrape the pages you find, and write a single "
        "self-contained HTML report that cites every claim with the scraped "
        "source id in square brackets, for example [S1] or [S2][S3]. Include a "
        "Limitations section and a References section.\n\n"
        "Generate it with: python -m lm_optimizer.cli.main lab research "
        "\"<question>\" --model <model>"
    ),
    checks=[
        SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
        SandboxCheck("html_document", "custom", None, weight=2.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{1000,}", weight=1.0, critical=True),
        SandboxCheck("has_report_headings", "regex", r"(<h2|<h3)", weight=1.5),
        SandboxCheck("min_words", "min_words", 600, weight=1.5),
        SandboxCheck("cites_scraped_source", "regex", r"\[S[1-9]\d*\]", weight=2.0, critical=True),
        SandboxCheck("distinct_citations", "distinct_citations", 3, weight=1.5),
        SandboxCheck("mentions_uncertainty", "regex", r"(limitations|do not answer|uncertain|not covered)", weight=1.0),
        SandboxCheck("has_references", "regex", r"(references|bibliography|sources)", weight=1.0),
        SandboxCheck("no_external_assets", "regex", r"\.(png|jpg|jpeg|gif|webp)\b", weight=1.0, negate=True),
    ],
    max_repair_attempts=1,
    timeout_s=300.0,
    max_output_tokens=8192,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("index.html",),
)


DEEP_RESEARCH_AGENT_TASK = SandboxTask(
    id="deep_research_agent",
    kind=SandboxTaskKind.WEB,
    title="Tool-using research agent (search + fetch trace)",
    prompt=(
        "You are a research agent with two tools, search(query) and fetch(url). "
        "Use them repeatedly: search for sub-questions, fetch the most relevant "
        "pages, and only then write the report. Answer the question 'What are "
        "the real limits of running a 70B MoE model on consumer hardware with "
        "24 GB VRAM?' Cite every factual claim with the id of a page you "
        "actually fetched, for example [S1], and list those URLs in a "
        "References section. Say explicitly what the sources do not answer.\n\n"
        "Produce one self-contained HTML file (inline CSS, no external assets) "
        "plus trace.json with the tool calls you made. Generate it with "
        "python -m lm_optimizer.cli.main lab research \"<question>\" --model <model>."
    ),
    checks=[
        SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
        SandboxCheck("html_document", "custom", None, weight=2.0, critical=True),
        SandboxCheck("html_not_empty", "regex", r"<html[\s\S]{1000,}", weight=1.0, critical=True),
        SandboxCheck("has_report_headings", "regex", r"(<h2|<h3)", weight=1.5),
        SandboxCheck("min_words", "min_words", 600, weight=1.5),
        SandboxCheck("cites_scraped_source", "regex", r"\[S[1-9]\d*\]", weight=2.0, critical=True),
        SandboxCheck("distinct_citations", "distinct_citations", 3, weight=1.5),
        SandboxCheck("has_references", "regex", r"(references|bibliography|sources)", weight=1.0),
        SandboxCheck("traces_tools_used", "tools_used", None, weight=2.0, critical=True),
    ],
    max_repair_attempts=1,
    timeout_s=300.0,
    max_output_tokens=8192,
    network_allowed=False,
    allowed_executables=(),
    artifacts=("index.html", "trace.json"),
)


SANDBOX_TASKS: dict[str, SandboxTask] = {
    t.id: t
    for t in (
        WEB_TASK,
        RESEARCH_TASK,
        BLENDER_CITY_TASK,
        EMAIL_TASK,
        CALENDAR_TASK,
        EMAIL_CALENDAR_TASK,
        WEB_FETCH_TASK,
        WEB_SEARCH_TASK,
        DEEP_RESEARCH_TASK,
        DEEP_RESEARCH_REPORT_TASK,
        DEEP_RESEARCH_ONLINE_TASK,
        DEEP_RESEARCH_AGENT_TASK,
        CREATIVE_3D_TASK,
        MINECRAFT_WORLD_TASK,
        LONG_CONTEXT_TASK,
        VISION_DESCRIBE_TASK,
        MULTILINGUAL_TASK,
    )
}

#: Canonical alias used by the optimizer's post-run sandbox stage. Exactly
#: the same registry object - one source of truth for built-in tasks.
BUILTIN_TASKS: dict[str, SandboxTask] = SANDBOX_TASKS


# --- Vision benchmark manifest ---------------------------------------------


def _load_vision_tasks(base: Path | None = None) -> dict[str, SandboxTask]:
    """Build vision tasks from ``benchmarks/vision/manifest.json``.

    The manifest keeps image files, prompts, expected answers and checks in
    one data file, so adding a new vision test is a data change, not a code
    change. Each task id is prefixed with ``vision_``.
    """
    import json

    root = base or Path(__file__).resolve().parents[2] / "benchmarks" / "vision"
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    tasks: dict[str, SandboxTask] = {}
    for item in manifest.get("images", []):
        image = root / str(item.get("file", ""))
        if not image.is_file():
            continue
        checks: list[SandboxCheck] = []
        for spec in item.get("checks", []):
            checks.append(
                SandboxCheck(
                    str(spec["name"]),
                    str(spec.get("kind", "regex")),
                    spec.get("value"),
                    weight=float(spec.get("weight", 1.0)),
                    critical=bool(spec.get("critical", False)),
                    negate=bool(spec.get("negate", False)),
                )
            )
        task = SandboxTask(
            id=f"vision_{item['id']}",
            kind=SandboxTaskKind.VISION,
            title=str(item.get("title", item["id"])),
            prompt=str(item["prompt"]),
            checks=checks,
            max_repair_attempts=int(item.get("max_repair_attempts", 1)),
            timeout_s=float(item.get("timeout_s", 120.0)),
            max_output_tokens=int(item.get("max_output_tokens", 512)),
            artifacts=(str(item.get("artifact", "description.txt")),),
            image_path=str(image),
            experimental=True,
        )
        tasks[task.id] = task
    return tasks


VISION_TASKS: dict[str, SandboxTask] = _load_vision_tasks()
SANDBOX_TASKS.update(VISION_TASKS)


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


def _normalize_executable(name: str) -> str:
    """Normalise an executable name for the allowlist.

    ``python``, ``python3`` and ``python3.12`` are the same interpreter on
    most systems, and a task that allows ``python`` must not reject
    ``python3`` on Linux/macOS (or vice versa). The same applies to
    ``pip``/``pip3`` and ``node``/``nodejs``.
    """
    value = str(name or "").strip().lower()
    if value.endswith(".exe"):
        value = value[: -len(".exe")]
    for base in ("python", "pip", "pypy"):
        if value == base:
            return base
        if value.startswith(base) and value[len(base):].lstrip("0123456789.") == "":
            return base
    if value in ("nodejs", "node"):
        return "node"
    return value


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
        exe = _normalize_executable(_basename_any(parts[0]))
        return exe in {_normalize_executable(e) for e in self.allowed_executables}

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
    #: Names of the checks that failed on this attempt (with detail).
    failing_checks: list[str] = field(default_factory=list)
    #: What the model is told for the NEXT attempt.
    feedback: str = ""


def build_repair_feedback(
    task: SandboxTask,
    attempt: int,
    stdout: str = "",
    stderr: str = "",
    failing_checks: list[SandboxCheck] | None = None,
    screenshot: str | None = None,
) -> str:
    """Feedback for the next repair attempt (spec 13.4).

    The model gets the failure EVIDENCE (stdout/stderr/screenshot) and the
    remaining budget - never the solution. Each failing criterion is
    described only by its ``hint`` (or a generic line when no hint is set).
    The check name, value, regex, expected counts or any fact about the image
    are never printed, so the model cannot be fed the answer.
    """
    remaining = max(0, task.max_repair_attempts - attempt)
    lines = [
        f"The previous attempt FAILED validation ({attempt}/{task.max_repair_attempts}).",
        "",
        "Failing acceptance criteria:",
    ]
    for check in failing_checks or []:
        hint = (check.hint or "").strip()
        if not hint:
            hint = "A required element is missing or wrong."
        lines.append(f"  - {hint}")
    if stdout.strip():
        lines += ["", "stdout (tail):", stdout.strip()[-1500:]]
    if stderr.strip():
        lines += ["", "stderr (tail):", stderr.strip()[-1500:]]
    if screenshot:
        lines += ["", f"screenshot: {screenshot}"]
    lines += [
        "",
        f"Remaining repair attempts: {remaining}.",
        "Fix the failing criteria.",
    ]
    if remaining == 0:
        lines.append("This is the LAST attempt.")
    return "\n".join(lines)


def score_attempt(
    task: SandboxTask,
    files: dict[str, str],
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 0,
    custom_results: dict[str, tuple[bool, str]] | None = None,
) -> tuple[float, list[SandboxCheck], list[SandboxCheck]]:
    """Evaluate one attempt against the task's checks.

    Returns (score, failing_checks, critical_checks). A critical failure
    zeroes the score: it vetoes the attempt instead of merely lowering the
    aggregate.
    """
    total = 0.0
    weight_sum = 0.0
    failing: list[SandboxCheck] = []
    critical: list[SandboxCheck] = []

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

    if any(c.name == "html_document" for c in task.checks):
        html_bodies = [
            _strip_md_fences(text)
            for name, text in files.items()
            if name.endswith((".html", ".htm"))
        ]
        if not html_bodies:
            verdict = (False, "no .html artifact")
        else:
            body = html_bodies[0].lstrip()
            while body.startswith("<!--"):
                end = body.find("-->")
                if end == -1:
                    break
                body = body[end + 3 :].lstrip()
            head = body[:200].lower()
            ok = head.startswith("<!doctype html") or head.startswith("<html")
            verdict = (ok, "html document" if ok else f"starts with {body[:60]!r}")
        custom_results = {**(custom_results or {}), "html_document": verdict}

    if any(c.name == "js_parses" for c in task.checks):
        html_text = "\n".join(
            _strip_md_fences(text)
            for name, text in files.items()
            if name.endswith((".html", ".htm"))
        )
        scripts: list[str] = []
        module_scripts: list[str] = []
        for match in re.finditer(
            r"<script\b([^>]*)>(.*?)</script>", html_text, re.IGNORECASE | re.DOTALL
        ):
            attrs, body = match.group(1), match.group(2)
            if not body.strip():
                continue
            type_match = re.search(r'type\s*=\s*["\']?([^"\'\s>]+)', attrs, re.IGNORECASE)
            script_type = (type_match.group(1) if type_match else "").lower()
            # Import maps and data blocks are JSON, not JavaScript.
            if script_type and script_type not in (
                "module",
                "text/javascript",
                "application/javascript",
            ):
                continue
            if script_type == "module":
                # A module may use top-level await; a classic script may not.
                module_scripts.append(body)
            else:
                scripts.append(body)
        for name, text in files.items():
            if name.endswith(".js"):
                scripts.append(_strip_md_fences(text))
        if not scripts and not module_scripts:
            verdict = (True, "no JavaScript to validate")
        else:
            from lm_optimizer.services.web_validator import (
                JS_INVALID,
                JS_UNAVAILABLE,
                validate_javascript,
            )

            checks = [
                validate_javascript(scripts),
                validate_javascript(module_scripts, module=True),
            ]
            unavailable = next(
                (c for c in checks if c.state == JS_UNAVAILABLE), None
            )
            invalid = next((c for c in checks if c.state == JS_INVALID), None)
            if unavailable is not None:
                # The JavaScript was never checked - that is not a success.
                verdict = (False, unavailable.detail)
            elif invalid is not None:
                verdict = (False, "; ".join(invalid.errors)[:200] or invalid.detail)
            else:
                verdict = (True, "; ".join(c.detail for c in checks if c.detail)[:200])
        custom_results = {**(custom_results or {}), "js_parses": verdict}

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
        elif check.kind == "tools_used":
            raw = files.get("trace.json", "")
            try:
                trace = json.loads(_strip_md_fences(raw)) if raw else []
            except json.JSONDecodeError:
                trace = []
            calls = [
                item
                for item in trace
                if isinstance(item, dict) and item.get("tool") in ("search", "fetch")
            ]
            fetches = [
                item
                for item in calls
                if item.get("tool") == "fetch" and item.get("ok") is not False
            ]
            urls = {str(item.get("argument") or "") for item in fetches}
            ok = len(calls) >= 3 and len(fetches) >= 2 and len(urls) >= 2
            detail = (
                f"{len(calls)} tool call(s), {len(fetches)} fetch(es), "
                f"{len(urls)} distinct URL(s)"
            )
        elif check.kind == "distinct_citations":
            combined = "\n".join(files.values())
            ids = set(re.findall(r"\[S(\d+)\]", combined))
            target = int(check.value or 1)
            ok = len(ids) >= target
            detail = f"{len(ids)} distinct source(s) cited (min {target})"
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
        elif check.name == "no_repeated_paragraphs":
            combined = "\n".join(files.values())
            text = re.sub(r"<[^>]+>", " ", combined)
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            # Short fragments (headings, captions, credits) are not real paragraphs
            # and must not be counted as repeats.
            candidates = [p for p in paragraphs if len(p.split()) >= 20]
            seen = set()
            repeats = 0
            for p in candidates:
                key = " ".join(p.lower().split()[:20])
                if key in seen:
                    repeats += 1
                seen.add(key)
            tail = text[-200:].strip().lower()
            head = text[:200].strip().lower()
            looped = tail == head and len(text) > 400
            # Allow up to ~10% of paragraphs to repeat (boilerplate / footers).
            allowed = max(1, len(candidates) // 10)
            ok = repeats <= allowed and not looped
            detail = (
                f"paragraphs={len(candidates)} repeats={repeats} "
                f"allowed={allowed} looped_tail={looped}"
            )
        elif check.name == "coherent_ending":
            combined = "\n".join(files.values())
            text = re.sub(r"<[^>]+>", " ", combined)
            words = text.split()
            if len(words) < 100:
                ok = False
                detail = f"too short ({len(words)} words)"
            else:
                head = " ".join(words[:60]).lower()
                tail = " ".join(words[-60:]).lower()
                repeated = head == tail
                last_para = text.strip().rsplit("\n\n", 1)[-1].lower()
                has_conclusion = any(
                    marker in last_para
                    for marker in ("conclusion", "summary", "in summary", "to conclude",
                                   "overall", "in closing", "finally")
                )
                ok = not repeated
                detail = (
                    f"words={len(words)} repeated_tail={repeated} "
                    f"conclusion_marker={has_conclusion}"
                )
        elif check.kind == "custom":
            ok = False
            detail = "custom check did not run (no result recorded)"
        else:
            ok = False
            detail = f"unknown check kind {check.kind}"
        total += check.weight if ok else 0.0
        weight_sum += check.weight
        if not ok:
            check.detail = detail
            failing.append(check)
            if check.critical:
                critical.append(check)
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
    #: Absolute path to a collected .blend file, when the task produced one.
    blend_file: str = ""
    #: ``measured`` when the model produced output that was scored; ``not_measured``
    #: when generation failed or returned nothing, so a 0.0 must not be read as a
    #: quality result.
    status: str = "measured"

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
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
                    "failing_checks": list(a.failing_checks),
                }
                for a in self.attempts
            ],
            "artifacts": list(self.artifacts),
            "critical_failures": list(self.critical_failures),
            "error": self.error,
            "blend_file": self.blend_file,
        }
