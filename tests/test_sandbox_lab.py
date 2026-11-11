"""Sandbox Lab unit tests (P4, spec section 13)."""
import pytest

from lm_optimizer.services.sandbox_lab import (
    RESEARCH_PACKAGE,
    SANDBOX_TASKS,
    WEB_TASK,
    SandboxCheck,
    SandboxPolicy,
    SandboxResult,
    SandboxTask,
    SandboxTaskKind,
    build_minecraft_prompt,
    build_repair_feedback,
    repair_penalty,
    score_attempt,
)

# --- task definitions ---

def test_all_sandbox_tasks_exist():
    assert set(SANDBOX_TASKS) == {
        "company_website",
        "research_synthesis",
        "creative_3d_voxel_island",
        "email_write",
        "calendar_event",
        "email_and_calendar",
        "web_fetch_brief",
        "web_search",
        "deep_research",
        "minecraft_world",
        "blender_city",
        "deep_research_report",
        "deep_research_online",
        "deep_research_agent",
    }
    kinds = {t.kind for t in SANDBOX_TASKS.values()}
    assert kinds == {
        SandboxTaskKind.WEB,
        SandboxTaskKind.RESEARCH,
        SandboxTaskKind.BLENDER,
        SandboxTaskKind.TEXT,
    }


def test_agentic_web_search_task_scores_good_code():
    task = SANDBOX_TASKS["web_search"]
    good = (
        "```python\n"
        "queries = [\"RTX 3060 LLM\", \"6GB VRAM inference\", \"quantization guide\"]\n"
        "headers = {\"User-Agent\": \"Mozilla/5.0 research\"}\n"
        "try:\n"
        "    resp = requests.get(url, headers=headers, timeout=15)\n"
        "    soup = BeautifulSoup(resp.text, \"html.parser\")\n"
        "    print(soup.get_text()[:500])\n"
        "except Exception as e:\n"
        "    print(\"Network error:\", e)\n"
        "```\n"
    )
    score, failing, critical = score_attempt(task, {"web_search.py": good})
    assert score == 1.0, (failing, critical)


def test_agentic_deep_research_task_scores_good_plan():
    task = SANDBOX_TASKS["deep_research"]
    good = (
        "1. What VRAM does a 70B MoE need?\n"
        "2. Search strategy: site:huggingface.co 70B MoE GGUF\n"
        "3. Source quality: prefer official docs and benchmarks\n"
        "4. Conflicting claims: compare multiple independent tests\n"
        "5. Preliminary synthesis: likely needs offload, not VRAM-only\n"
    )
    score, failing, critical = score_attempt(task, {"deep_research.txt": good})
    assert score == 1.0, (failing, critical)


def test_agentic_email_task_scores_good_output():
    task = SANDBOX_TASKS["email_write"]
    good = (
        "Subject: Kickoff next steps\n\n"
        "Hello Alice,\n\n"
        "Thanks for the kickoff. The next step is to send the API draft by 2026-11-07.\n\n"
        "Best regards,\nBob\n"
    )
    score, failing, critical = score_attempt(task, {"email.txt": good})
    assert score == 1.0, (failing, critical)


def test_agentic_calendar_task_scores_valid_json():
    task = SANDBOX_TASKS["calendar_event"]
    payload = (
        '{"title":"Project kickoff","start":"2026-11-10T10:00:00+01:00",'
        '"end":"2026-11-10T10:45:00+01:00",'
        '"attendees":["alice@example.com","bob@example.com"],'
        '"location":"Meet"}'
    )
    score, failing, critical = score_attempt(task, {"calendar.json": payload})
    assert score == 1.0, (failing, critical)


def test_agentic_web_fetch_accepts_explicit_error():
    task = SANDBOX_TASKS["web_fetch_brief"]
    payload = (
        '{"tool":"web_fetch","url":"https://www.nvidia.com/en-us/geforce/'
        'graphics-cards/rtx-3060/","error":"network unavailable"}'
    )
    score, failing, critical = score_attempt(task, {"web_fetch.json": payload})
    assert score == 1.0, (failing, critical)


def test_every_task_has_criteria_and_prompt():
    for task in SANDBOX_TASKS.values():
        assert task.prompt.strip()
        assert task.checks
        assert task.max_repair_attempts >= 1
        assert task.timeout_s > 0


def test_network_is_off_by_default():
    for task in SANDBOX_TASKS.values():
        assert task.network_allowed is False


def test_research_package_has_all_source_kinds():
    assert "primary_official" in RESEARCH_PACKAGE
    assert "technical_secondary" in RESEARCH_PACKAGE
    assert "outdated_source" in RESEARCH_PACKAGE
    assert "conflicting_source" in RESEARCH_PACKAGE
    assert "irrelevant_source" in RESEARCH_PACKAGE
    # The irrelevant source must be recognisable so it can be penalised.
    assert "cassette" in RESEARCH_PACKAGE["irrelevant_source"].lower()


def test_blender_task_checks_all_spec_elements():
    names = {c.name for c in SANDBOX_TASKS["blender_city"].checks}
    for required in (
        "has_camera",
        "has_light",
        "saves_blend",
        "no_render",
        "blend_runs",
        "city_mesh_count",
    ):
        assert required in names
    assert "has_keyframes" not in names
    assert "renders" not in names


# --- scoring ---

def test_score_attempt_perfect_solution():
    from dataclasses import replace
    from pathlib import Path

    from lm_optimizer.services.sandbox_lab import SandboxPolicy
    from lm_optimizer.services.sandbox_runner import SandboxRunner, build_command_for

    reference = (
        Path(__file__).resolve().parents[1]
        / "benchmarks"
        / "deepseek_agent"
        / "company_website"
        / "index.html"
    )
    content = reference.read_text(encoding="utf-8")
    task = replace(WEB_TASK, max_repair_attempts=0)
    workdir = Path("results") / "pytest_perfect"
    runner = SandboxRunner(
        task=task,
        policy=SandboxPolicy(workdir=workdir, network_enabled=False, timeout_s=task.timeout_s),
        workdir=workdir,
        command=build_command_for(task),
    )
    result = runner.run(lambda feedback: content)
    assert result.final_score == pytest.approx(1.0)
    assert not result.attempts[0].failing_checks
    assert not result.critical_failures


def test_score_attempt_flags_external_resources():
    files = {
        "index.html": (
            '<html><head><meta name="viewport" content="x">'
            '<link rel="stylesheet" href="https://cdn.example.com/x.css">'
            "</head><body><div class=\"grid\"></div>"
            "<script src=\"https://cdn.example.com/x.js\"></script></body></html>"
        )
    }
    score, failing, critical = score_attempt(WEB_TASK, files)
    assert score < 1.0
    assert any("external" in f for f in failing)


def test_score_attempt_missing_critical_file():
    score, failing, critical = score_attempt(WEB_TASK, {"other.txt": "x"})
    assert critical
    assert any("index_html_exists" in c for c in critical)


def test_score_attempt_respects_custom_results():
    task = SandboxTask(
        id="t",
        kind=SandboxTaskKind.WEB,
        title="t",
        prompt="p",
        checks=[SandboxCheck("c1", "custom")],
    )
    score, failing, _ = score_attempt(task, {}, custom_results={"c1": (True, "ok")})
    assert score == pytest.approx(1.0)
    assert not failing


# --- repair loop ---

def test_repair_penalty_schedule():
    assert repair_penalty(0) == 1.0
    assert repair_penalty(1) == 0.9
    assert repair_penalty(2) == 0.8
    assert repair_penalty(5) == 0.8


def test_repair_feedback_contains_evidence_not_solution():
    feedback = build_repair_feedback(
        WEB_TASK,
        attempt=0,
        stdout="SyntaxError: unexpected token",
        stderr="line 3",
        failing_checks=["index_html_exists (missing=['index.html'])"],
        screenshot="shot.png",
    )
    assert "index_html_exists" in feedback
    assert "SyntaxError" in feedback
    assert "shot.png" in feedback
    assert "Remaining repair attempts: 1" in feedback


def test_repair_feedback_last_attempt_is_marked():
    feedback = build_repair_feedback(WEB_TASK, attempt=2, failing_checks=["x"])
    assert "LAST attempt" in feedback


def test_sandbox_result_serializes():
    result = SandboxResult(task_id="company_website", first_pass_success=True, final_score=0.9)
    payload = result.as_dict()
    assert payload["first_pass_success"] is True
    assert "attempts" in payload


# --- security policy ---

def test_policy_blocks_unlisted_executables(tmp_path):
    policy = SandboxPolicy(workdir=tmp_path, allowed_executables=("blender",))
    assert policy.is_command_allowed("blender --background --python script.py")
    assert not policy.is_command_allowed("powershell -Command rm -rf C:\\")
    assert not policy.is_command_allowed("curl https://example.com")


def test_policy_with_empty_allowlist_blocks_everything(tmp_path):
    policy = SandboxPolicy(workdir=tmp_path)
    assert not policy.is_command_allowed("python script.py")


def test_policy_sanitizes_displayed_command(tmp_path):
    policy = SandboxPolicy(workdir=tmp_path, allowed_executables=("blender",))
    shown = policy.sanitize_command(
        '"C:\\Program Files\\Blender\\blender.exe" --background --python x.py'
    )
    assert shown.startswith("blender.exe")
    assert "Program Files" not in shown


def test_policy_sanitizes_posix_path_too(tmp_path):
    policy = SandboxPolicy(workdir=tmp_path, allowed_executables=("blender",))
    shown = policy.sanitize_command('"/usr/local/bin/blender" --background --python x.py')
    assert shown.startswith("blender")
    assert "/usr/local/bin" not in shown


def test_policy_accepts_both_path_styles(tmp_path):
    # Policy checks must not depend on the host that happens to run them.
    policy = SandboxPolicy(workdir=tmp_path, allowed_executables=("blender",))
    assert policy.is_command_allowed(
        '"C:\\Program Files\\Blender\\blender.exe" --background'
    )
    assert policy.is_command_allowed("/usr/local/bin/blender --background")


def test_policy_defaults_are_restrictive(tmp_path):
    policy = SandboxPolicy(workdir=tmp_path)
    assert policy.network_enabled is False
    assert policy.timeout_s > 0
    assert policy.memory_mb > 0
    assert policy.disk_mb > 0

def test_minecraft_world_task_is_a_single_file_web_task():
    task = SANDBOX_TASKS["minecraft_world"]
    assert task.kind is SandboxTaskKind.WEB
    assert task.artifacts == ("index.html",)
    names = {check.name for check in task.checks}
    assert {"index_html_exists", "single_file_html", "has_threejs"} <= names

def test_minecraft_prompt_accepts_scene_variation():
    base = build_minecraft_prompt()
    varied = build_minecraft_prompt("fewer trees, a lighthouse and a bigger pond")
    assert varied.startswith(base)
    assert "fewer trees, a lighthouse and a bigger pond" in varied
    assert "floating skyblock" in varied
    assert build_minecraft_prompt("   ") == base

def test_blender_city_task_is_blend_only_and_forbids_renders():
    task = SANDBOX_TASKS["blender_city"]
    names = {check.name for check in task.checks}
    assert "no_render" in names
    assert "city_mesh_count" in names
    assert "preview_rendered" not in names
    assert "frames_rendered" not in names
    assert "scene.blend" in task.artifacts
    assert "preview.png" not in task.artifacts


def test_deep_research_report_task_is_html_with_citations():
    task = SANDBOX_TASKS["deep_research_report"]
    names = {check.name for check in task.checks}
    assert {"cites_primary", "cites_technical", "cites_conflicting", "min_words"} <= names
    assert task.artifacts == ("index.html",)

import pytest

from lm_optimizer.services.sandbox_lab import (
    SANDBOX_TASKS,
    SandboxCheck,
    SandboxTask,
    SandboxTaskKind,
    score_attempt,
)


def _probe_task() -> SandboxTask:
    """Minimal web task so HTML/JS checks are tested without company content."""
    return SandboxTask(
        id="web_probe",
        kind=SandboxTaskKind.WEB,
        title="probe",
        prompt="x",
        checks=[
            SandboxCheck("index_html_exists", "files", ["index.html"], weight=1.0, critical=True),
            SandboxCheck("html_document", "custom", None, weight=1.0, critical=True),
            SandboxCheck("js_parses", "custom", None, weight=1.0, critical=True),
        ],
        artifacts=("index.html",),
    )


def test_js_parses_flags_syntax_error():
    html = (
        "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body>"
        "<script>function f(){ document.getElementById('a') ).x = 1; }"
        "</script></body></html>"
    )
    score, failing, critical = score_attempt(_probe_task(), {"index.html": html})
    assert score == 0.0
    assert any("js_parses" in name for name in critical)


def test_js_parses_accepts_valid_script():
    html = (
        "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body>"
        "<script>function f(){ return 1; } f();</script>"
        "</body></html>"
    )
    score, failing, critical = score_attempt(_probe_task(), {"index.html": html})
    assert not failing
    assert score == 1.0


def test_js_parses_ignores_import_map_json():
    html = (
        "<!DOCTYPE html><html><head><meta name=\"viewport\"></head><body>"
        "<script type=\"importmap\">{\"imports\": {\"three\": \"https://x/three.js\"}}</script>"
        "<script type=\"module\">import * as THREE from 'three';</script>"
        "</body></html>"
    )
    score, failing, critical = score_attempt(_probe_task(), {"index.html": html})
    assert not any("js_parses" in name for name in failing)
    assert not critical


def test_html_document_rejects_prose_in_index_html():
    prose = (
        "The user wants a company site. I will add a <meta name=\"viewport\"> tag, "
        "a @media query and a <footer> element."
    )
    score, failing, critical = score_attempt(
        SANDBOX_TASKS["company_website"], {"index.html": prose}
    )
    assert score == 0.0
    assert any("html_document" in name for name in critical)


def test_html_document_accepts_comment_before_doctype():
    html = (
        "<!-- generated -->\n<!DOCTYPE html><html><head>"
        "<meta name=\"viewport\"></head><body>ok</body></html>"
    )
    score, failing, critical = score_attempt(_probe_task(), {"index.html": html})
    assert not critical
    assert score == 1.0


def test_email_subject_accepts_subject_line_wording():
    email = (
        "**Subject line:** Kickoff follow-up\n\nHi Sarah,\n\n"
        "Next step is the roadmap, due by Friday 14 November.\n\nBest regards,\nAlex\n"
    )
    score, failing, critical = score_attempt(SANDBOX_TASKS["email_write"], {"email.txt": email})
    assert not any("has_subject" in name for name in failing)


def test_email_subject_rejects_reasoning_dump():
    text = (
        "Thinking Process:\n\n1. Analyse the request.\n\nSubject: Kickoff follow-up\n"
        "Hi Sarah, next step is the roadmap by Friday.\nBest regards,\nAlex\n"
    )
    score, failing, critical = score_attempt(SANDBOX_TASKS["email_write"], {"email.txt": text})
    assert any("has_subject" in name for name in critical)


def test_blender_task_checks_python_syntax_before_running():
    names = {check.name for check in SANDBOX_TASKS["blender_city"].checks}
    assert "is_python_code" in names

def test_deep_research_online_requires_scraped_citations():
    task = SANDBOX_TASKS["deep_research_online"]
    names = {check.name for check in task.checks}
    assert {"cites_scraped_source", "distinct_citations", "has_references"} <= names

    body = (
        "<!DOCTYPE html><html><body>"
        + ("<h2>Section</h2><p>" + ("word " * 200) + "[S1][S2]</p>") * 3
        + "<h2>Limitations</h2><p>sources do not answer it</p>"
        + "<h2>References</h2></body></html>"
    )
    score, failing, critical = score_attempt(task, {"index.html": body})
    assert any("distinct_citations" in name for name in failing)
    assert not critical

def test_research_synthesis_accepts_everyday_gap_wording():
    task = SANDBOX_TASKS["research_synthesis"]
    answer = (
        "The API accepts context_length and flash_attention [primary_official]. "
        "MTP raised decode throughput from 31.2 to 40.3 tok/s [technical_secondary]. "
        "The Q3/Q4 conflict is hardware specific [conflicting_source]. "
        "The exact VRAM cost is not specified in the sources."
    )
    score, failing, critical = score_attempt(task, {"answer.txt": answer})
    assert score == pytest.approx(1.0), failing
    assert not critical

def test_creative_3d_rejects_broken_scene_javascript():
    task = SANDBOX_TASKS["creative_3d_voxel_island"]
    scene = (
        "export function createScene({ THREE, random }) {\n"
        "  const root = new THREE.Group();\n"
        "  root.name = 'Terrain'; root.name = 'Trees';\n"
        "  root.name = 'Waterfall'; root.name = 'Vegetation';\n"
        "  const a = random(); root.add(terrain), trees);\n"
        "  return root;\n"
        "}\n"
    )
    score, failing, critical = score_attempt(task, {"scene.js": scene})
    assert score == 0.0
    assert any("js_parses" in name for name in critical)


def test_email_and_calendar_accepts_subject_line_wording():
    task = SANDBOX_TASKS["email_and_calendar"]
    answer = (
        "Subject line: Kickoff follow-up\n\nHi Alice,\n"
        "Next step is the agenda by 2026-11-07.\n\n--- CALENDAR ---\n"
        '{"title":"Kickoff","start":"2026-11-10T10:00","end":"2026-11-10T10:45",'
        '"attendees":["alice@example.com"],"location":"Room 1"}\n'
    )
    score, failing, critical = score_attempt(task, {"response.txt": answer})
    assert not any("has_subject" in name for name in failing)


def test_deep_research_report_accepts_not_specified_wording():
    task = SANDBOX_TASKS["deep_research_report"]
    html = (
        "<!DOCTYPE html><html><body><h2>Report</h2>"
        + ("<p>" + ("word " * 250) + "[primary_official] [technical_secondary] "
           "[conflicting_source]</p>") * 3
        + "<h2>Limitations</h2><p>The exact VRAM cost is not specified.</p>"
        + "<h2>References</h2><p>sources</p></body></html>"
    )
    score, failing, critical = score_attempt(task, {"index.html": html})
    assert not any("mentions_uncertainty" in name for name in failing)


def test_minecraft_requires_a_strong_render():
    task = SANDBOX_TASKS["minecraft_world"]
    check = next(c for c in task.checks if c.name == "renders_content")
    assert check.value == "canvas"
