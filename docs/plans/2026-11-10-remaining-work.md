# Remaining Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the benchmark programme: prove every task check is honest, re-run the models that were measured against retired tasks, add the Gemini/ChatGPT frontier comparison, and clean up what is left.

**Architecture:** Keep the sandbox as the single scorer. Every result flows from an artifact + the current check set into `results/`; only `benchmarks/compare/<provider>/` is committed. The plan adds no new scoring concepts — it closes the gaps the 2026-11-10 audit exposed.

**Tech Stack:** Python 3.11+, Typer CLI, httpx, Chrome DevTools Protocol (screenshots), stdlib PNG decoder, LM Studio REST API, pytest.

**Spec:** `docs/benchmarks/scoring_reference.md`, `docs/benchmarks/model_failures.md`, `SCOREBOARD.md`, and the 2026-11-10 audit.

## Global Constraints

- One model loaded at a time; never run two benchmarks concurrently.
- `results/` stays gitignored; only frontier artifacts under `benchmarks/compare/` are committed.
- A check may only fail an artifact for a property the prompt actually asked for.
- A non-run is `not_measured`, never `0.00`.
- No model is deleted without the user's explicit confirmation.
- Every task ends with a passing test and a commit.

---

## Audit results (2026-11-10, this round)

Verified now, with `tools/audit_tasks.py` and `tools/audit_screenshots.py`:

| Finding | Evidence | Status |
|---|---|---|
| Pure white render is caught | `measure_png(255,255,255)` → `flat`, `has_content=False` | fixed (test added) |
| `renders_content` accepted `weak` frames | a page with sd 3-6 passed a 3D task | fixed: minecraft requires verdict `ok` |
| `deep_research_report` still had the gap-wording trap | `mentions_uncertainty` only accepted "not stated/provided/mentioned" | fixed: same broad pattern as `research_synthesis` |
| `email_and_calendar` rejected "Subject line:" | regex `Subject:\s*\S+` | fixed |
| `creative_3d_voxel_island` never parsed its JS | regex-only checks on `scene.js` | fixed: critical `js_parses` on `.js` artifacts |
| Report tasks had no render check | white/hidden page could score on text alone | fixed: `renders_content` on both report tasks |
| `deep_research_online` prompt is not self-contained | prompt tells the model to run the CLI, which a chat model cannot do | open, Task 4 |
| `minecraft_world` prompt asks for a hero + animated sky, no check | `grep has_hero` returns nothing | open, Task 5 |
| `creative_3d_voxel_island` prompt asks for camera/Three.js, no check | no `has_camera`/`uses_three` | open, Task 5 |
| `web_fetch_brief` is a JSON-shape test, not a web test | task has no network and no fetch | document only, Task 6 |
| `blender_city` vs `blender_city_bridge` overlap | both build a city; one renders frames | keep both, Task 6 |

No stored screenshot is currently blank/flat except the two already-vetoed
artifacts (Bonsai blank, gpt-oss flat). The pure-white case you saw is the same
class and is now classified `flat` and failed.

---

## Task 1: Frontier prompt pack and import path

**Files:**
- Modify: `tools/export_prompts.py`
- Create: `benchmarks/compare/PROMPTS_ALL.md` (generated)
- Test: `tests/test_export_prompts.py`

**Interfaces:**
- Produces: `build_desktop_bundle()` also writes `PROMPTS_ALL.md` with all six prompts in copy-paste blocks and the import command per task.

- [ ] **Step 1: Write the failing test**

```python
def test_desktop_bundle_has_single_prompt_sheet(monkeypatch, tmp_path):
    monkeypatch.setattr(export, "DESKTOP", tmp_path / "bundle")
    export.export_prompts()
    export.build_desktop_bundle()
    text = (tmp_path / "bundle" / "PROMPTS_ALL.md").read_text(encoding="utf-8")
    for task_id in export.TASKS:
        assert f"## {task_id}" in text
    assert "compare_models.py --provider chatgpt" in text
```

- [ ] **Step 2: Run it, expect failure** — `pytest tests/test_export_prompts.py -q`

- [ ] **Step 3: Implement** — build the sheet from `SANDBOX_TASKS[task].prompt`, one fenced `text` block per task, plus the import command and the artifact name.

- [ ] **Step 4: Run the test** — expect PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(compare): one prompt sheet for external providers"`.

## Task 2: Import the Gemini / ChatGPT answers

**Files:**
- Modify: none (use `tools/compare_models.py`)
- Create: `benchmarks/compare/gemini/<task>/index.html`, `benchmarks/compare/chatgpt/<task>/index.html`
- Test: manual verification via `python tools/compare_models.py --tasks all --include-bakeoff`

**Interfaces:**
- Consumes: the prompt sheet from Task 1.

- [ ] **Step 1: For each provider/task, paste the answer into the importer**

```powershell
python tools/compare_models.py --provider gemini --task company_website --clipboard
```

- [ ] **Step 2: Verify the file landed and the fence was stripped**

```powershell
Get-Content benchmarks/compare/gemini/company_website/index.html -TotalCount 3
```

Expected: starts with `<!DOCTYPE html>`.

- [ ] **Step 3: Score and screenshot**

```powershell
$env:PATH += ";C:\Program Files\Blender Foundation\Blender 5.3"
python tools/compare_models.py --tasks all --include-bakeoff
```

- [ ] **Step 4: Check the pixel verdict column** in `results/scoreboard.md` and the gallery; a frontier answer that renders blank/flat fails exactly like a local one.

- [ ] **Step 5: Commit** — `git add benchmarks/compare/gemini benchmarks/compare/chatgpt; git commit -m "data(compare): gemini and chatgpt frontier answers"`.

## Task 3: Re-measure local models against the renamed tasks

**Files:**
- Modify: `tools/retry_failed.py` (task list only)
- Output: `results/bakeoff/<model>/company_website/`, `results/retry/*.log`

**Interfaces:**
- Consumes: `lab bakeoff --models <id> --tasks company_website --safe --no-thinking`.

- [ ] **Step 1: Update the retry plan** to `company_website` for e4b, bonsai, swift, gpt-oss, qwen9b, gemma (the ones with a web score under the retired dashboard task).

- [ ] **Step 2: Run one model at a time**

```powershell
python tools/retry_failed.py --only e4b --timeout-min 30
python tools/retry_failed.py --only bonsai --timeout-min 30
python tools/retry_failed.py --only swift --timeout-min 30
```

- [ ] **Step 3: Verify no run is `not_measured`** — `python tools/explain_failures.py --task company_website`.

- [ ] **Step 4: Rebuild the scoreboard** — `python tools/scoreboard.py`.

- [ ] **Step 5: Commit docs only** (results are gitignored) — update `SCOREBOARD.md` numbers.

## Task 4: Make `deep_research_online` a real, self-contained task

**Files:**
- Modify: `lm_optimizer/services/sandbox_lab.py` (prompt only)
- Test: `tests/test_sandbox_lab.py`

**Interfaces:**
- Produces: a prompt a chat model can answer without the CLI; the task remains scoring-only for `lab research` output, which is documented.

- [ ] **Step 1: Write the failing test**

```python
def test_deep_research_online_prompt_is_self_contained():
    task = SANDBOX_TASKS["deep_research_online"]
    assert "lab research" not in task.prompt
    assert "S1" in task.prompt and "cite" in task.prompt.lower()
```

- [ ] **Step 2: Run it, expect failure.**

- [ ] **Step 3: Rewrite the prompt** as a research brief: "You are a research agent with web access. Answer <question>. Cite every claim as [S1], [S2]…; list the source URLs in References; state what you could not verify." Keep the checks unchanged.

- [ ] **Step 4: Run the test** — expect PASS.

- [ ] **Step 5: Commit.**

## Task 5: Close the remaining prompt/check gaps

**Files:**
- Modify: `lm_optimizer/services/sandbox_lab.py`
- Test: `tests/test_sandbox_lab.py`

**Interfaces:**
- Produces: `has_hero`, `has_sky_change` on `minecraft_world`; `uses_three`, `has_camera` on `creative_3d_voxel_island`.

- [ ] **Step 1: Write the failing tests**

```python
def test_minecraft_checks_hero_and_sky():
    names = {c.name for c in SANDBOX_TASKS["minecraft_world"].checks}
    assert {"has_hero", "has_sky_change"} <= names

def test_creative_3d_checks_three_and_camera():
    names = {c.name for c in SANDBOX_TASKS["creative_3d_voxel_island"].checks}
    assert {"uses_three", "has_camera"} <= names
```

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Add the checks**

```python
SandboxCheck("has_hero", "regex", r"(<header|<section)[\s\S]{0,400}<h1", weight=1.0, critical=False),
SandboxCheck("has_sky_change", "regex", r"(sky|sun|day|night)", weight=1.0),
SandboxCheck("uses_three", "regex", r"(THREE\.|new\s+THREE)", weight=1.0),
SandboxCheck("has_camera", "regex", r"(PerspectiveCamera|OrthographicCamera)", weight=1.0),
```

- [ ] **Step 4: Re-score the committed reference artifacts** — both must stay 1.0.

- [ ] **Step 5: Commit.**

## Task 6: Document the tasks that are intentionally not end-to-end

**Files:**
- Modify: `docs/benchmarks/README.md`
- Test: none (documentation)

- [ ] **Step 1: Add a table row per task: what it actually measures.**
  `web_fetch_brief` = JSON-shape compliance, not fetching. `web_search` = written code, not execution. `blender_city_bridge` = animation variant of `blender_city`. `deep_research_online` = scoring target for `lab research`.
- [ ] **Step 2: State the limitation in one sentence per row.**
- [ ] **Step 3: Commit.**

## Task 7: Per-model history on the History page

**Files:**
- Modify: `lm_optimizer/ui/templates/history.html`, `lm_optimizer/ui/static/js/history.js`
- Test: `tests/test_dashboard_api.py` (API shape) + manual CDP check

**Interfaces:**
- Consumes: `GET /api/sandbox/runs` (already grouped client-side on the Sandbox page).
- Produces: the same model → task → runs drill-down on the History page.

- [ ] **Step 1: Add a failing API test** asserting `/api/sandbox/runs` returns `status` and `blend_file`.
- [ ] **Step 2: Implement the group renderer** in `history.js` (reuse the structure from `sandbox.js`, do not duplicate the fetch).
- [ ] **Step 3: Verify in the browser** with `tools/html_shot.py` + a CDP click; no console exception.
- [ ] **Step 4: Commit.**

## Task 8: Harden `lab research`

**Files:**
- Modify: `lm_optimizer/services/web_research.py`
- Test: `tests/test_web_research.py`

**Interfaces:**
- Produces: `WebResearcher` retries a query once on HTTP 429 and reports `rate limited` in `warnings`; identical URLs are deduped across queries (already), and a failed scrape is counted per query.

- [ ] **Step 1: Write the failing test** with a fake client returning 429 then 200; assert one retry and a warning on persistent 429.
- [ ] **Step 2: Implement the retry** (one retry, 2 s back-off, capped).
- [ ] **Step 3: Run the tests.**
- [ ] **Step 4: Commit.**

## Task 9: Model keep/delete (user decision)

**Files:**
- Modify: none until confirmed
- Run: `tools/prune_models.py`

- [ ] **Step 1: Present the list** (flint, 74b, gemma, mirothinker, qwen9b, swift Q4_K_S duplicate).
- [ ] **Step 2: On explicit confirmation, delete in LM Studio**, then `python tools/prune_models.py --yes`.
- [ ] **Step 3: Re-run `tools/scoreboard.py`** and confirm the remaining models are unchanged.

## Task 10: Refresh the docs and the scoreboard

**Files:**
- Modify: `SCOREBOARD.md`, `docs/benchmarks/model_failures.md`, `README.md`
- Test: none

- [ ] **Step 1: Regenerate** `python tools/scoreboard.py` and copy the numbers.
- [ ] **Step 2: Update the failure table** with the retest outcomes.
- [ ] **Step 3: Commit.**

---

## Self-review

- Every audit finding has a task: white/weak render (Task 5 and the fix already
  landed), report wording (done), subject wording (done), JS on `.js`
  artifacts (done), online prompt (Task 4), prompt/check gaps (Task 5),
  documentation of non-e2e tasks (Task 6), UI history (Task 7), research
  hardening (Task 8), model cleanup (Task 9), docs (Task 10).
- No step depends on a symbol another task has not defined.
- Every code task has a failing test first.
