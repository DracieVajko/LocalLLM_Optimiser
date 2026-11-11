# Frontier comparison

Current frontier artifacts, scored by the same sandbox checks as every local
model. Only the artifacts under `benchmarks/compare/` are committed; the
scores are reproduced with `python tools/compare_models.py --tasks all`.

| provider | email | company_website | minecraft_world | blender_city | deep_research_report |
|---|---:|---:|---:|---:|---:|
| DeepSeek V4.1 Flash | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Gemini | 1.00 | 1.00 | 1.00 | not re-run | not run |
| ChatGPT | **0.00** | 1.00 | 1.00 | not re-run | not run |

- **ChatGPT email** has no `Subject:` line, so it fails `has_subject` exactly like
  the local models that leak reasoning.
- **blender_city** was redefined on 2026-11-10 (dense 12x12 map, `.blend` only,
  no renders). The earlier frontier city scripts answered the old prompt and were
  removed; regenerate them with `benchmarks/compare/prompts/blender_city.txt`.

## Historical note

Earlier tables used the retired task ids `web_dashboard` (replaced by
`company_website`) and `blender_skyblock` / `blender_city_bridge` (removed in
favour of the single `blender_city`). Those rows are not comparable with the
current benchmarks; the live table is `SCOREBOARD.md`.
