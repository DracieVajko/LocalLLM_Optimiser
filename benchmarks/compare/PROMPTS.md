# Copy-paste prompts (identical for every provider)

Send **exactly** one prompt file to DeepSeek, Nemotron (local), ChatGPT and any
other model, then import the answer. Same prompt, same file name, comparable
result.

The canonical prompts live in [`prompts/`](prompts/) — one `.txt` per task,
generated from the sandbox definitions by `python tools/export_prompts.py`.
`python tools/export_prompts.py --desktop` also builds
`Desktop/frontier_bench/` with the prompts, the DeepSeek references and a short
instruction sheet.

| Task | Prompt file | File the model must produce |
|---|---|---|
| `email_write` | `prompts/email_write.txt` | `email.txt` |
| `minecraft_world` | `prompts/minecraft_world.txt` | `index.html` |
| `company_website` | `prompts/company_website.txt` | `index.html` |
| `deep_research_report` | `prompts/deep_research_report.txt` | `index.html` |
| `blender_city` | `prompts/blender_city.txt` | `build_scene.py` |
| `blender_skyblock` | `prompts/blender_skyblock.txt` | `build_scene.py` |

Do not shorten the prompt, add follow-up messages, or ask for a different
design — the comparison only works if every provider gets the same text.

---

# Saving an answer

Copy the whole model answer (fences included are fine), then either:

```powershell
# straight from the clipboard (Windows)
python tools/compare_models.py --provider chatgpt --task company_website --clipboard

# or from a saved file
python tools/compare_models.py --provider chatgpt --task company_website --file answer.md
```

The importer strips a markdown fence and writes
`benchmarks/compare/chatgpt/company_website/index.html`, then the normal run
scores and screenshots it:

```powershell
$env:PATH += ";C:\Program Files\Blender Foundation\Blender 5.3"
python tools/compare_models.py --tasks all --include-bakeoff
```

Open `results/compare/gallery.html` for the visual side-by-side.

Provider folder names are free-form (`chatgpt`, `gemini`, `perplexity`,
`odysseus`, `nemotron`, `qwen9b`, ...). Keep local-model artifacts in
`results/compare/local/<model>/<task>/` so they stay out of git.
