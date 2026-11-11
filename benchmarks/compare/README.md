# Cross-provider comparison

Same task, same prompt, same artifact names — produced by different assistants
and compared mostly visually.

## Layout

```
benchmarks/compare/
  deepseek/          committed reference (DeepSeek V4.1 Flash)
    <task>/<artifact>
  chatgpt/           ChatGPT outputs (same layout)
    <task>/<artifact>
  gemini/            Gemini outputs (same layout)
    <task>/<artifact>
  prompts/           generated prompt files (one per task)
```

Local-model artifacts are not stored here; `--include-bakeoff` reads them from
`results/bakeoff/<model>/<task>/` at compare time.

Task → artifact:

| Task | Artifact |
|---|---|
| `blender_city` | `build_scene.py` |
| `deep_research_report` | `index.html` |
| `email_write` | `email.txt` |
| `minecraft_world` | `index.html` |
| `company_website` | `index.html` |

Use the exact prompts from [`PROMPTS.md`](PROMPTS.md) — they are the same text
the sandbox uses, so the comparison is like-for-like.

## Import an answer

```powershell
# from the clipboard (fences are stripped automatically)
python tools/compare_models.py --provider chatgpt --task minecraft_world --clipboard

# from a saved file
python tools/compare_models.py --provider chatgpt --task minecraft_world --file answer.md
```

## Run the comparison

```powershell
$env:PATH += ";C:\Program Files\Blender Foundation\Blender 5.3"
python tools/compare_models.py --tasks all --include-bakeoff
```

Outputs:

- `results/compare/comparison.md` — score table
- `results/compare/comparison.csv` — Excel-friendly
- `results/compare/gallery.html` — visual side-by-side (open in a browser)
- `results/compare/visuals/` — screenshots (Blender city has no render; the
  gallery prints its `.blend` path instead)
- `results/compare/runs.jsonl` — raw records

Local model outputs can be dropped into `results/compare/local/<model>/<task>/`
(that directory is gitignored); they are included automatically.

## Notes

- The checks are the same ones used by `lab sandbox`; visual comparison is the
  primary goal for the 3D and HTML tasks.
- ChatGPT outputs must be pasted manually; no provider API key is bundled.
- Frontier artifacts are committed; local model results stay out of git.
