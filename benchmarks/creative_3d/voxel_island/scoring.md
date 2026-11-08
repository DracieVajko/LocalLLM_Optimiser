# Creative 3D Benchmark — Scoring Rubric

| Test | Weight | How checked |
| --- | --- | --- |
| JS parses without syntax errors | 10 % | `createScene` import + no console errors |
| `createScene` exported & returns `THREE.Group` | 20 % | Runtime import + `instanceof` check |
| Named groups present (`Terrain`, `Trees`, `Waterfall`, `Vegetation`) | 10 % | Source scan for group names |
| At least 3 trees | 10 % | Source scan / visual |
| At least 1 waterfall | 10 % | Source scan / visual |
| Vegetation / apples present | 10 % | Source scan / visual |
| Camera rotates (screenshot 2 differs from #1) | 15 % | Playwright pixel diff |
| Scene renders in WebGL without errors | 15 % | HUD status = OK |
| **Total** | **100 %** | |

## Quality bands

- **90–100** — Polished, detailed, all groups present, rotates cleanly.
- **70–89** — Functional island, minor gaps, renders.
- **50–69** — Basic blocks, missing groups, or fragile.
- **0–49** — Errors, wrong structure, or nothing renders.

## Vision-model option

A separate vision model can rate visual quality 0–100 against a fixed rubric
(palette, composition, variation). That score is reported alongside — never
mixed into the automatic score — and its compute cost is tracked separately
from the generating model's speed.

## Generation speed

Reported separately: tok/s, total generation time, first-token time. Never part
of the quality score. This lets the optimiser answer: "Model A is faster but
Model B builds a better island."
