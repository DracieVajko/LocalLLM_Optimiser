"""Score and visually compare same-task artifacts from several providers.

Layout: benchmarks/compare/<provider>/<task>/<artifact>
Local model artifacts can live in results/compare/local/<model>/<task>/.

Usage:
    python tools/compare_models.py --tasks all
    python tools/compare_models.py --tasks minecraft_world,blender_city
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from lm_optimizer.services.sandbox_lab import SANDBOX_TASKS, SandboxPolicy
from lm_optimizer.services.sandbox_runner import SandboxRunner, build_command_for

TASKS = {
    "blender_city": "build_scene.py",
    "blender_skyblock": "build_scene.py",
    "deep_research_report": "index.html",
    "email_write": "email.txt",
    "minecraft_world": "index.html",
    "web_dashboard": "index.html",
}
HTML_TASKS = {"deep_research_report", "minecraft_world", "web_dashboard"}

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = ROOT / "benchmarks" / "compare"
LOCAL_DIR = ROOT / "results" / "compare" / "local"
BAKEOFF_DIR = ROOT / "results" / "bakeoff"
OUT = ROOT / "results" / "compare"


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name)[:60] or "provider"


def _ensure_blender() -> None:
    if shutil.which("blender"):
        return
    candidates = [
        Path(r"C:\Program Files\Blender Foundation\Blender 5.3"),
        Path(r"C:\Program Files\Blender Foundation\Blender 5.2"),
        Path(r"C:\Program Files\Blender Foundation\Blender 5.1"),
    ]
    for directory in candidates:
        exe = directory / "blender.exe"
        if exe.exists():
            os.environ["PATH"] = str(directory) + os.pathsep + os.environ["PATH"]
            return


FENCE_RE = re.compile(
    r"```(?:[A-Za-z0-9_+-]*)\s*\n(.*?)```", re.DOTALL
)


def clean_output(text: str) -> str:
    """Return the artifact body, stripping a single markdown code fence if present."""
    text = text.replace("\r\n", "\n").strip()
    match = FENCE_RE.search(text)
    if match:
        return match.group(1).strip() + "\n"
    return text + "\n"


def import_output(provider: str, task: str, source: Path | None, clipboard: bool) -> Path:
    if clipboard:
        try:
            text = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            ).stdout
        except Exception as exc:
            raise SystemExit(f"clipboard read failed: {exc}") from exc
    elif source is not None:
        text = source.read_text(encoding="utf-8", errors="replace")
    else:
        raise SystemExit("--provider/--task need --file <path> or --clipboard")

    destination = PROVIDERS_DIR / _slug(provider) / task / TASKS[task]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(clean_output(text), encoding="utf-8")
    print(f"[import] {provider} :: {task} -> {destination}")
    return destination


def discover(root: Path):
    if not root.exists():
        return
    for provider_dir in sorted(root.iterdir()):
        if not provider_dir.is_dir():
            continue
        for task_dir in sorted(provider_dir.iterdir()):
            if not task_dir.is_dir() or task_dir.name not in TASKS:
                continue
            artifact = task_dir / TASKS[task_dir.name]
            if artifact.exists():
                yield provider_dir.name, task_dir.name, artifact


def discover_bakeoff(root: Path):
    """Yield the newest artifact per (model, task) from results/bakeoff."""
    if not root.exists():
        return
    for model_dir in sorted(root.iterdir()):
        if not model_dir.is_dir():
            continue
        for task_dir in sorted(model_dir.iterdir()):
            if not task_dir.is_dir() or task_dir.name not in TASKS:
                continue
            artifact_name = TASKS[task_dir.name]
            runs = sorted(
                (d for d in task_dir.iterdir() if d.is_dir()),
                key=lambda d: d.name,
                reverse=True,
            )
            for run in runs:
                artifact = run / artifact_name
                if artifact.exists() and artifact.stat().st_size > 0:
                    yield model_dir.name, task_dir.name, artifact
                    break


def score(provider: str, task: str, artifact: Path, stamp: str) -> dict:
    definition = replace(SANDBOX_TASKS[task], max_repair_attempts=0)
    workdir = OUT / "runs" / _slug(provider) / task / stamp
    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=definition.timeout_s,
        allowed_executables=definition.allowed_executables,
    )
    runner = SandboxRunner(
        task=definition,
        policy=policy,
        workdir=workdir,
        command=build_command_for(definition),
        model=provider,
    )
    content = artifact.read_text(encoding="utf-8", errors="replace")
    result = runner.run(lambda feedback: content)
    payload = result.as_dict()
    return {
        "provider": provider,
        "task": task,
        "score": payload.get("final_score"),
        "pass": payload.get("final_success"),
        "repairs": payload.get("repair_count"),
        "critical": payload.get("critical_failures") or [],
        "artifacts": payload.get("artifacts") or [],
        "workdir": str(workdir),
        "source": str(artifact),
    }


_CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def _browser_exe() -> Path | None:
    for candidate in _CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _html_shot():
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import html_shot

    return html_shot


def screenshot(path: Path, out: Path, full_page: bool = False) -> str | None:
    out.parent.mkdir(parents=True, exist_ok=True)
    uri = path.resolve().as_uri()
    height = 2600 if full_page else 900

    try:
        _html_shot().capture(
            uri,
            out,
            width=1280,
            height=height,
            wait_s=5.0,
            full_page=full_page,
        )
    except Exception as exc:
        print(f"[visual] {path.name}: {type(exc).__name__}: {exc}")
    if out.exists() and out.stat().st_size > 0:
        return out.relative_to(OUT).as_posix()

    cmd = (
        f'npx playwright screenshot --browser=chromium '
        f'--viewport-size="1280,{height}" --wait-for-timeout=4000 '
        f'{"--full-page " if full_page else ""}"{uri}" "{out}"'
    )
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
    except Exception as exc:
        print(f"[visual] {path.name}: {type(exc).__name__}: {exc}")
        return None
    if proc.returncode != 0 or not out.exists():
        print(f"[visual] screenshot failed: {proc.stderr[-200:]}")
        return None
    return out.relative_to(OUT).as_posix()


def visual(row: dict) -> str | None:
    task = row["task"]
    workdir = Path(row["workdir"])
    provider = _slug(row["provider"])
    if task == "blender_city":
        src = workdir / "preview.png"
        if src.exists():
            dst = OUT / "visuals" / f"{provider}_blender_city.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            return dst.relative_to(OUT).as_posix()
    if task == "blender_skyblock":
        src = workdir / "frames" / "frame_0001.png"
        if src.exists():
            dst = OUT / "visuals" / f"{provider}_blender_skyblock.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            return dst.relative_to(OUT).as_posix()
    if task in HTML_TASKS:
        src = workdir / TASKS[task]
        if src.exists():
            dst = OUT / "visuals" / f"{provider}_{task}.png"
            return screenshot(src, dst, full_page=task == "deep_research_report")
    return None


def write_gallery(rows: list[dict], visuals: dict[int, str | None]) -> None:
    cards: list[str] = []
    for index, row in enumerate(rows):
        image = visuals.get(index)
        if image:
            image_html = f'<img src="{html.escape(image)}" alt="preview" />'
        elif row["task"] == "email_write":
            image_html = ""
        else:
            image_html = '<div class="noimg">no visual</div>'
        email_html = ""
        if row["task"] == "email_write":
            try:
                text = Path(row["source"]).read_text(encoding="utf-8")
                email_html = f"<pre>{html.escape(text[:1400])}</pre>"
            except OSError:
                pass
        cards.append(
            f"""
            <article class="card">
              <header><span class="provider">{html.escape(row['provider'])}</span>
                <span class="score">{row['score']}</span></header>
              <div class="task">{html.escape(row['task'])} &middot; pass={row['pass']}</div>
              {image_html}{email_html}
              <div class="meta">{html.escape(row['source'])}</div>
            </article>
            """
        )
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Provider comparison</title>
<style>
body {{ margin:0; padding:28px; background:#0f1720; color:#e7eef6;
  font-family:'Segoe UI',system-ui,sans-serif; }}
h1 {{ margin:0 0 6px; font-size:24px; }}
p.sub {{ color:#9fb2c4; margin:0 0 22px; font-size:13px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; }}
.card {{ background:#18232f; border:1px solid #2a3a4c; border-radius:12px;
  overflow:hidden; }}
header {{ display:flex; justify-content:space-between; align-items:center;
  padding:10px 14px; background:#1d2b3a; }}
.provider {{ font-weight:600; }}
.score {{ font-weight:700; color:#ffd44d; }}
.task {{ padding:8px 14px; color:#9fb2c4; font-size:12px; }}
img {{ width:100%; display:block; background:#0b1118; }}
.noimg {{ padding:40px; text-align:center; color:#6b7f93; }}
pre {{ margin:0; padding:12px 14px; font-size:11px; white-space:pre-wrap;
  max-height:260px; overflow:auto; background:#0b1118; color:#cfe1f2; }}
.meta {{ padding:8px 14px 12px; color:#6b7f93; font-size:11px;
  overflow-wrap:anywhere; }}
</style></head><body>
<h1>Cross-provider comparison</h1>
<p class="sub">Same task, same prompt; score from the sandbox checks, image from the real artifact.</p>
<div class="grid">{''.join(cards)}</div>
</body></html>"""
    (OUT / "gallery.html").write_text(page, encoding="utf-8")


def prune_visuals(visuals: dict[int, str | None]) -> None:
    """Delete screenshots left over from providers no longer in the run."""
    keep = {Path(v).name for v in visuals.values() if v}
    directory = OUT / "visuals"
    if not directory.exists():
        return
    for file in directory.iterdir():
        if file.is_file() and file.name not in keep:
            file.unlink(missing_ok=True)


def _one_line(text: str, limit: int = 120) -> str:
    collapsed = " ".join(str(text).split())
    return collapsed[:limit]


def write_tables(rows: list[dict]) -> None:
    md = ["# Cross-provider comparison", ""]
    md.append("| provider | task | score | pass | critical |")
    md.append("|---|---|---:|---|---|")
    for row in rows:
        md.append(
            f"| {row['provider']} | {row['task']} | {row['score']} | "
            f"{row['pass']} | {_one_line('; '.join(row['critical']))} |"
        )
    (OUT / "comparison.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    with (OUT / "comparison.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["provider", "task", "score", "pass", "critical", "source", "workdir"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "critical": "; ".join(row["critical"])})


def main() -> int:
    global OUT

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default="all", help="comma-separated task ids or 'all'")
    parser.add_argument("--providers-dir", default=str(PROVIDERS_DIR))
    parser.add_argument("--local-dir", default=str(LOCAL_DIR))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--provider", default="", help="Import: provider folder name")
    parser.add_argument("--task", default="", help="Import: task id")
    parser.add_argument("--file", default="", help="Import: file holding the model answer")
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="Import: read the answer from the Windows clipboard",
    )
    parser.add_argument(
        "--include-bakeoff",
        action="store_true",
        help="Also score the newest artifact per model/task in results/bakeoff",
    )
    parser.add_argument(
        "--exclude",
        default="deepseek-agent",
        help=(
            "Comma-separated provider names to skip (default: deepseek-agent, "
            "whose artifacts are committed under benchmarks/compare/deepseek)"
        ),
    )
    args = parser.parse_args()

    OUT = Path(args.out)
    OUT.mkdir(parents=True, exist_ok=True)
    _ensure_blender()

    if args.provider or args.task:
        if not args.provider or not args.task:
            raise SystemExit("--provider and --task must be given together")
        if args.task not in TASKS:
            raise SystemExit(f"unknown task: {args.task}")
        import_output(
            args.provider,
            args.task,
            Path(args.file) if args.file else None,
            args.clipboard,
        )

    selected = (
        list(TASKS)
        if args.tasks.strip().lower() in ("all", "*")
        else [t.strip() for t in args.tasks.split(",") if t.strip()]
    )
    stamps = datetime.now().strftime("%Y%m%d_%H%M%S")
    excluded = {p.strip() for p in args.exclude.split(",") if p.strip()}
    rows: list[dict] = []
    for root in (Path(args.providers_dir), Path(args.local_dir)):
        for provider, task, artifact in discover(root):
            if task not in selected or provider in excluded:
                continue
            print(f"[score] {provider} :: {task}", flush=True)
            rows.append(score(provider, task, artifact, stamps))

    if args.include_bakeoff:
        seen = {(row["provider"], row["task"]) for row in rows}
        for provider, task, artifact in discover_bakeoff(BAKEOFF_DIR):
            if (
                task not in selected
                or provider in excluded
                or (provider, task) in seen
            ):
                continue
            print(f"[score] {provider} :: {task} (bakeoff)", flush=True)
            rows.append(score(provider, task, artifact, stamps))

    visuals: dict[int, str | None] = {}
    if not args.no_screenshots:
        for index, row in enumerate(rows):
            visuals[index] = visual(row)

    prune_visuals(visuals)
    write_tables(rows)
    write_gallery(rows, visuals)
    with (OUT / "runs.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n{len(rows)} artifact(s) scored")
    print(f"table: {OUT / 'comparison.md'}")
    print(f"gallery: {OUT / 'gallery.html'}")
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
