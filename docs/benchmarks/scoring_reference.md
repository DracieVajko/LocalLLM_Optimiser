# Scoring reference

`tests/test_scoring_reference.py` is the source of truth for the sandbox
scoring system. It runs the committed frontier artifacts ("must score 1.0")
and tiny synthetic bad artifacts ("must score low / be vetoed") through the
same harness used by `lab sandbox`.

Run it with:

```powershell
python -m pytest tests/test_scoring_reference.py -v
```

## Reference table (verified 2026-11-10)

| Case | Score | Pass | Critical failures |
|---|---:|---|---|
| `minecraft_world` good artifact | **1.000** | yes | — |
| `minecraft_world` empty file | **0.000** | no | `html_not_empty`, `single_file_html` |
| `minecraft_world` wrong content (no Three.js) | **0.320** | no | — |
| `minecraft_world` external asset (`.png`) | **<1.0** | no | negative check fails |
| `minecraft_world` JS syntax error (duplicate function) | **0.000** | no | `js_parses` |
| `company_website` good artifact | **1.000** | yes | — |
| `company_website` empty file | **0.000** | no | `html_not_empty` |
| `company_website` JS syntax error (unbalanced paren) | **0.000** | no | `js_parses` |
| `company_website` JS body without a form | **<1.0** | no | `has_contact_form` |
| `email_write` good artifact | **1.000** | yes | — |
| `email_write` without Subject | **0.000** | no | `has_subject` |
| `blender_skyblock` valid artifacts | **1.000** | yes | — |
| `blender_skyblock` broken Blender run | **0.000** | no | `blend_runs`, `blend_is_binary`, `blend_min_size` |

## Audit findings fixed

1. **Critical failures were not a veto.** A Blender run that failed every
   artifact check still kept a high weighted score (about 0.71) because the
   regex checks passed. Critical checks now zero the score.
2. **Empty HTML could score 0.5 on the web task.** Negative checks ("no
   external scripts/styles") are satisfied by an empty file. `html_not_empty`
   is now a critical check (at least 50 characters).
3. **Regex checks matched prose.** A page saying "no Three.js, no voxels"
   passed `has_threejs`/`has_voxel_cubes`. The checks now require real code
   constructs (`<script src=...three...js>`, `BoxGeometry(`, `InstancedMesh(`,
   `grass:`, `stone:`, `water:`, `PerspectiveCamera`, `.lookAt(`,
   `requestAnimationFrame(`).
4. **`blend_runs` was not scored.** A Blender crash could be hidden by a
   stale `scene.blend` from a previous attempt. `blend_runs` is now a critical
   custom check, and `blend_is_binary`/`blend_min_size` remain critical.
5. **`blender_city_bridge` wrote the script to the wrong artifact.** Its
   artifact list started with `scene.blend`, so the runner wrote the Python
   text there and executed the wrong file. The list now starts with
   `build_scene.py` and the task validates the `.blend` and frames like
   `blender_skyblock`.
6. **Prompt/scoring mismatch.** The prompt asked for first-person controls and
   block editing while the intended output is an automatic orbit scene. The
   prompt now asks for an orbiting camera and the check is `has_camera`.
7. **A page with broken JavaScript scored 1.0.** `minecraft_world` and
   `company_website` were checked only by regexes, so an HTML file whose inline
   script does not parse still earned full marks while rendering nothing. Both
   tasks now run every inline script through `node --check` (`js_parses`,
   critical). Import maps and JSON script blocks are skipped. Real examples
   caught this way: a duplicate `generateWorld` function (Nemotron 74B
   minecraft), an unbalanced parenthesis (gpt-oss company site), a Python-style
   keyword argument `getTerrainHeight(x, y: 0, z)` (Bonsai minecraft) and a
   stray `...` spread (Swift company site).
8. **Prose in `index.html` passed the HTML checks.** The qwen 9B company-site
   artifact was ten lines of reasoning that *described* a viewport tag and a
   media query, and still scored 0.81 because the regexes matched the
   description. `html_document` (critical) now requires the file itself to
   start with `<!DOCTYPE html>` or `<html>` after optional comments.
9. **`has_table_or_grid` was too literal.** A page using
   `display: grid` or `grid-template` in CSS failed. Both forms now count.
10. **`has_subject` rejected legitimate wording.** The prompt says "Subject
    line"; the check demanded the exact string `Subject:` at byte 0, so
    `Subject line: ...` and a leading `**` failed. The pattern now accepts
    `Subject`/`Subject line` with `:` or `-` after optional leading
    non-word characters. A reasoning dump before the email still fails, which
    is intended.
11. **Blender syntax errors were only found by running Blender.** A model
    script with an `IndentationError` cost a full headless render before
    failing. `is_python_code` is now a critical check on all Blender tasks, so
    the syntax error is reported instead.

## What the reference does not prove

Static regex checks cannot prove that the page is visually correct or that the
3D scene matches the prompt. `js_parses` proves the script is syntactically
valid, not that it runs without a runtime error. The committed example is
additionally verified by a headless Chromium screenshot
(`minecraft_world_preview.png`, captured through
`tools/html_shot.py` so asynchronous scene building finishes first) and a real
Blender run (120 frames + `scene.blend`), which cover the visual side. Use
`tools/compare_models.py` to put those visuals side by side.
