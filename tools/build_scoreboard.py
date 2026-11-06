"""Build an honest cross-model scoreboard from existing result files.

Why this exists
---------------
`results/sandbox_runs.jsonl` mixes three kinds of evidence and the campaign
`*-best.md` files carry a `score` column that is normalised *within* one run
(so it is not comparable across models). This tool produces the two artefacts
that ARE comparable:

- `results/scoreboard.csv`  - machine readable, one row per model
- `results/SCOREBOARD.md`   - readable, with every exclusion stated

Rules (deliberate, see docs/plans/SANDBOX-V2-REDESIGN.md):

1. A sandbox task that the harness cannot pass or cannot fail is EXCLUDED from
   the capability score, but still shown with its reason. Truth over coverage.
2. A row whose error is a harness timeout ("no workdir") is UNKNOWN, not zero.
3. Rows reconstructed by tools/backfill_sandbox_runs.py are marked
   `reconstructed`; they never outrank a real run for the same model/task.
4. Absolute metrics only in the ranking: gen tok/s, TTFT, quality, context.
   The optimizer's relative `score` is printed but never sorted on.

Usage
-----
    python tools/build_scoreboard.py
    python tools/build_scoreboard.py --results results --out results
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from statistics import mean

# --- task validity registry ------------------------------------------------

#: Why a task cannot contribute to the capability score. Empty = valid.
TASK_STATUS: dict[str, str] = {
    "blender_skyblock": "BROKEN: artifact is text renamed to scene.blend; "
    "blender is never executed (sandbox_runner.py:294, lab.py:789)",
    "research_synthesis": "BROKEN: source documents are never injected into the "
    "prompt (sandbox_lab.py:143); also no_irrelevant_source lacks negate=True",
    "email_and_calendar": "BROKEN: check demands end=10:45 but the notes never "
    "state a duration (sandbox_lab.py:285)",
    "web_dashboard": "BROKEN: regex checks score prose as HTML; "
    "has_viewport vs has_viewport_meta name mismatch",
}

TASK_ORDER = [
    "web_search",
    "web_fetch_brief",
    "email_write",
    "calendar_event",
    "deep_research",
    "web_dashboard",
    "email_and_calendar",
    "research_synthesis",
    "blender_skyblock",
]

#: A harness-level timeout, not a model failure.
TIMEOUT_ERROR = "no workdir"

# --- optimizer best.md parsing --------------------------------------------


def _grab(text: str, pattern: str, default: str = "") -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return default
    return (match.group(1) if match.groups() else match.group(0)).strip()


def parse_best_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "model": _grab(text, r"Model ID: (.+)") or path.name.removesuffix("-best.md"),
        "quant": _grab(text, r"Quantization: (.+)", "?"),
        "gen_tok_s": _grab(text, r"Generation: ([\d.]+) tok/s", "?"),
        "prompt_tok_s": _grab(text, r"Prompt: ([\d.]+) tok/s", "?"),
        "ttft_ms": _grab(text, r"Est\. TTFT: (\d+) ms", "?"),
        "quality": _grab(text, r"Quality: ([\d.]+)", "?"),
        "context": _grab(text, r"- Context: (\d+)", "?"),
        "tested": _grab(text, r"winner of (\d+) tested", "1"),
        "verify": _grab(text, r"Verification: (\w+)", "?"),
        "channel": _grab(text, r"Load channel: (\w+)", "?"),
        # Printed for information only. NOT used for ranking.
        "run_relative_score": round(
            sum(
                float(x)
                for x in re.findall(
                    r"normalized [\d.]+ x weight [\d.]+ = ([\d.]+)", text
                )
            ),
            3,
        ),
    }


# --- sandbox rows ----------------------------------------------------------


def load_sandbox_rows(path: Path) -> dict[tuple[str, str], dict]:
    """Best evidence per (model, task).

    Real runs beat reconstructed rows; later timestamps beat earlier ones.
    """
    best: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return best
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (row.get("model", ""), row.get("task", ""))
        rank = (0 if row.get("backfilled") else 1, row.get("ts", ""))
        current = best.get(key)
        if current is None or rank > (
            (0 if current.get("backfilled") else 1),
            current.get("ts", ""),
        ):
            best[key] = row
    return best


def classify(row: dict | None) -> tuple[str, float | None]:
    """-> (status, score). status in {ok, timeout, missing}."""
    if row is None:
        return "missing", None
    if (row.get("error") or "").startswith(TIMEOUT_ERROR):
        return "timeout", None
    return "ok", float(row.get("final_score") or 0.0)


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


# --- report ----------------------------------------------------------------


def build(results_dir: Path, out_dir: Path) -> int:
    optimizer = sorted(
        (parse_best_md(p) for p in results_dir.glob("*-best.md")),
        key=lambda o: o["model"],
    )
    sandbox = load_sandbox_rows(results_dir / "sandbox_runs.jsonl")

    models: list[str] = [o["model"] for o in optimizer]
    for model, _task in sandbox:
        if model not in models:
            models.append(model)

    opt_by_model = {o["model"]: o for o in optimizer}
    valid_tasks = [t for t in TASK_ORDER if t not in TASK_STATUS]

    csv_path = out_dir / "scoreboard.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["model", "quant", "gen_tok_s", "ttft_ms", "quality", "context",
             "configs_tested", "load_verify"]
            + [f"sandbox_{t}" for t in TASK_ORDER]
            + ["capability_avg", "tasks_measured", "tasks_timeout"]
        )
        for model in models:
            opt = opt_by_model.get(model, {})
            cells: list[str] = []
            scores: list[float] = []
            timeouts = 0
            for task in TASK_ORDER:
                status, score = classify(sandbox.get((model, task)))
                if status == "ok":
                    cells.append(f"{score:.2f}")
                    if task in valid_tasks:
                        scores.append(score)
                elif status == "timeout":
                    cells.append("TMO")
                    timeouts += 1
                else:
                    cells.append("-")
            writer.writerow(
                [model, opt.get("quant", "?"), opt.get("gen_tok_s", "?"),
                 opt.get("ttft_ms", "?"), opt.get("quality", "?"),
                 opt.get("context", "?"), opt.get("tested", "?"),
                 opt.get("verify", "?")]
                + cells
                + [f"{mean(scores):.3f}" if scores else "",
                   len(scores), timeouts]
            )

    lines = [
        "# Scoreboard — comparable metrics only",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `tools/build_scoreboard.py` "
        "from `results/*-best.md` + `results/sandbox_runs.jsonl`.",
        "",
        "**Read this first**",
        "",
        "- `gen tok/s` / `TTFT` / `quality` / `context` are absolute and comparable.",
        "- `score` from `*-best.md` is normalised **within one run** and is NOT",
        "  comparable across models. It is not shown here; see §6.1 of",
        "  `results/DEBUG-REPORT-20261106.md`.",
        "- `TMO` = the harness killed the run (900 s subprocess timeout), not a",
        "  model failure. `-` = never measured.",
        "- Tasks listed under *Excluded* cannot be passed or cannot fail. Their",
        "  cells are shown for history but never enter `capability_avg`.",
        "",
        "## Optimizer: throughput and quality",
        "",
        "| model | quant | gen tok/s | TTFT ms | quality | ctx | configs | load verify |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    ranked = sorted(
        optimizer,
        key=lambda o: (
            -_as_float(o["gen_tok_s"]),
            -_as_float(o["quality"]),
        ),
    )
    for opt in ranked:
        lines.append(
            f"| {opt['model']} | {opt['quant']} | {opt['gen_tok_s']} | "
            f"{opt['ttft_ms']} | {opt['quality']} | {opt['context']} | "
            f"{opt['tested']} | {opt['verify']} |"
        )

    lines += [
        "",
        "`configs` = 1 means the campaign tested a single configuration: that is the",
        "default load, not an optimum.",
        "",
        "## Sandbox capability (valid tasks only)",
        "",
        "| model | " + " | ".join(valid_tasks) + " | capability_avg | measured |",
        "| --- | " + " | ".join("---" for _ in valid_tasks) + " | --- | --- |",
    ]
    cap_rows = []
    for model in models:
        cells, scores, measured = [], [], 0
        for task in valid_tasks:
            status, score = classify(sandbox.get((model, task)))
            if status == "ok":
                cells.append(f"{score:.2f}")
                scores.append(score)
                measured += 1
            elif status == "timeout":
                cells.append("TMO")
            else:
                cells.append("-")
        cap_rows.append(
            (model, cells, mean(scores) if scores else -1.0, measured)
        )
    for model, cells, avg, measured in sorted(cap_rows, key=lambda r: -r[2]):
        avg_text = fmt(avg if avg >= 0 else None, 3)
        lines.append(
            f"| {model} | " + " | ".join(cells) + f" | {avg_text} | {measured} |"
        )

    lines += [
        "",
        "## Excluded tasks (and why)",
        "",
        "| task | reason |",
        "| --- | --- |",
    ]
    for task in TASK_ORDER:
        if task in TASK_STATUS:
            lines.append(f"| `{task}` | {TASK_STATUS[task]} |")

    lines += [
        "",
        "## Harness timeouts",
        "",
        "These rows are UNKNOWN, not zero. They are caused by",
        "`tools/sandbox_all_models.py:78` (`timeout=900`) cutting the CLI off",
        "mid-run; a 20-70B model needs longer than that on a 6 GB GPU.",
        "",
        "| model | timed out tasks |",
        "| --- | --- |",
    ]
    for model in models:
        missing = [
            task
            for task in TASK_ORDER
            if classify(sandbox.get((model, task)))[0] == "timeout"
        ]
        if missing:
            lines.append(f"| {model} | {', '.join(missing)} |")

    out_md = out_dir / "SCOREBOARD.md"
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {csv_path}")
    print(f"wrote {out_md}")
    print(
        f"models={len(models)} valid_tasks={len(valid_tasks)} "
        f"excluded={len(TASK_STATUS)} sandbox_rows={len(sandbox)}"
    )
    return 0


def _as_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results", type=Path)
    parser.add_argument("--out", default="results", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    return build(args.results, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
