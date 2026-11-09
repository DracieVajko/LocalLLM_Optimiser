"""Regenerate the model bake-off comparison report from results/bakeoff/runs.jsonl.

Produces (next to this tool):
  - comparison.md   human-readable markdown table
  - comparison.csv  opens directly in Excel

Run after every finished model:
    python tools/bakeoff_report.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "bakeoff" / "runs.jsonl"
OUT_MD = ROOT / "comparison.md"
OUT_CSV = ROOT / "comparison.csv"

COLUMNS = [
    "model",
    "task",
    "score",
    "pass",
    "repair",
    "load_s",
    "gen_s",
    "total_s",
    "tokens",
    "tok_s",
    "thinking_chars",
    "context",
    "error",
]


def _rows() -> list[dict]:
    if not RUNS.exists():
        return []
    rows: list[dict] = []
    for line in RUNS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _fmt(x) -> str:
    if x is None or x == "":
        return "-"
    if isinstance(x, float):
        return f"{x:g}"
    return str(x)


def write_markdown(rows: list[dict], path: Path) -> None:
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        by_model.setdefault(r.get("model", "(unknown)"), []).append(r)

    lines: list[str] = []
    lines.append("# Model bake-off comparison")
    lines.append("")
    lines.append("Generated from `results/bakeoff/runs.jsonl`. Generation time includes the model's thinking phase where supported.")
    lines.append("")

    # Per-model totals
    lines.append("## Model totals (load once + all tasks)")
    lines.append("")
    lines.append(
        "| model | mean score | tasks passed | load_s | total gen_s | total_s | tokens | tok/s | thinking_chars |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    order = list(by_model.keys())
    for model in order:
        model_rows = [r for r in by_model[model] if r.get("task") != "(load)" and r.get("task") != "(crash)"]
        load_s = next((r.get("load_s") or 0 for r in by_model[model]), 0)
        gen_s = round(sum(float(r.get("gen_s") or 0) for r in model_rows), 1)
        total_s = round(load_s + gen_s, 1)
        tokens = sum(int(r.get("tokens") or 0) for r in model_rows)
        toks = round(tokens / gen_s, 2) if gen_s else 0.0
        thinking = sum(int(r.get("thinking_chars") or 0) for r in model_rows)
        scores = [float(r["final_score"]) for r in model_rows if r.get("final_score") is not None]
        mean = round(sum(scores) / len(scores), 3) if scores else 0.0
        passed = sum(1 for r in model_rows if r.get("final_success"))
        lines.append(
            f"| {model} | {mean} | {passed}/{len(model_rows)} | {load_s} | {gen_s} | {total_s} | "
            f"{tokens} | {toks} | {thinking} |"
        )
    lines.append("")

    # Per-task detail
    lines.append("## Per-task detail")
    lines.append("")
    lines.append(
        "| model | task | score | pass | repair | load_s | gen_s | total_s | tokens | tok/s | thinking_chars | context | error |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for model in order:
        for r in sorted(by_model[model], key=lambda x: x.get("task", "")):
            task = r.get("task", "(unknown)")
            if task in ("(load)", "(crash)"):
                continue
            lines.append(
                f"| {model} | {task} | {_fmt(r.get('final_score'))} | "
                f"{_fmt(r.get('final_success'))} | {_fmt(r.get('repair_count'))} | "
                f"{_fmt(r.get('load_s'))} | {_fmt(r.get('gen_s'))} | {_fmt(r.get('total_s'))} | "
                f"{_fmt(r.get('tokens'))} | {_fmt(r.get('tok_s'))} | {_fmt(r.get('thinking_chars'))} | "
                f"{_fmt(r.get('context'))} | {_fmt(r.get('error'))[:80]} |"
            )
    lines.append("")

    # KV cache A/B block
    cache_path = ROOT / "results" / "bakeoff" / "cache_ab_*.json"
    import glob as _glob
    cache_files = sorted(_glob.glob(str(cache_path)))
    if cache_files:
        latest = cache_files[-1]
        try:
            data = json.loads(Path(latest).read_text(encoding="utf-8"))
            variants = data.get("variants", [])
            if variants:
                lines.append("## KV cache placement (same weights, context 8192)")
                lines.append("")
                lines.append("| model | context | KV_GPU load_s | KV_RAM load_s | KV_GPU tok/s | KV_RAM tok/s | faster |")
                lines.append("|---|---|---:|---:|---:|---:|---|")
                model_name = data.get("model", "(unknown)")
                context = data.get("context", "-")
                v_by = {v["kv_gpu"]: v for v in variants}
                vgpu = v_by.get(True, {})
                vram = v_by.get(False, {})
                runs_g = vgpu.get("runs", [])
                runs_r = vram.get("runs", [])
                def avg(runs: list[dict], key: str) -> float:
                    vals = [float(x.get(key) or 0) for x in runs if x.get(key) is not None]
                    return round(sum(vals) / len(vals), 2) if vals else 0.0
                load_g = vgpu.get("load_s", "-")
                load_r = vram.get("load_s", "-")
                tok_g = avg(runs_g, "tok_s")
                tok_r = avg(runs_r, "tok_s")
                faster = "GPU" if tok_g >= tok_r else "RAM"
                lines.append(
                    f"| {model_name} | {context} | {load_g} | {load_r} | {tok_g} | {tok_r} | {faster} |"
                )
                lines.append("")
        except (json.JSONDecodeError, OSError):
            pass

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            task = r.get("task", "(unknown)")
            if task in ("(load)", "(crash)"):
                continue
            writer.writerow(
                {
                    "model": r.get("model", ""),
                    "task": task,
                    "score": r.get("final_score", ""),
                    "pass": r.get("final_success", ""),
                    "repair": r.get("repair_count", ""),
                    "load_s": r.get("load_s", ""),
                    "gen_s": r.get("gen_s", ""),
                    "total_s": r.get("total_s", ""),
                    "tokens": r.get("tokens", ""),
                    "tok_s": r.get("tok_s", ""),
                    "thinking_chars": r.get("thinking_chars", ""),
                    "context": r.get("context", ""),
                    "error": r.get("error", ""),
                }
            )


def main() -> int:
    rows = _rows()
    write_markdown(rows, OUT_MD)
    write_csv(rows, OUT_CSV)
    print(f"wrote {OUT_MD}  ({len(rows)} raw records)")
    print(f"wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
