"""Extract, check and (optionally) run a Blender script from a sandbox run.

The sandbox stores the model's answer under `results/sandbox/<task>/<run>/`
(e.g. `results/sandbox/blender_skyblock/20261107_165436/` or
`results/sandbox/blender_city_bridge/...`).

Three things usually stand between that file and a visible scene:

1. the model wraps the code in a ```python fence, so Blender cannot parse it;
2. the answer is sometimes reasoning text rather than code (syntax error);
3. Blender is not on PATH on this machine.

This tool fixes (1), detects (2) and reports (3), then gives you the exact command
(or runs it) that produces `scene.blend` and `render_frames/`.

    python tools/preview_blender.py                     # newest valid run, writes + shows
    python tools/preview_blender.py --list              # score every stored run
    python tools/preview_blender.py --run 20261107_165436 --launch
    python tools/preview_blender.py --task blender_city_bridge --list
"""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

#: Always resolve relative to the repo, so the tool works from any directory
#: (running it from the sandbox run dir used to break `tools/...` and the
#: `results/...` lookup).
ROOT = Path(__file__).resolve().parents[1]
SANDBOX_ROOT = ROOT / "results" / "sandbox"
#: Task dirs that contain blender artifacts.
BLENDER_TASKS = ("blender_skyblock", "blender_city_bridge")
OUT_NAME = "scene_preview.py"
QUICK_NAME = "scene_quick.py"

#: Names that look like a scene builder, in priority order.
_SCENE_FUNCS = ("setup_scene", "build_scene", "create_scene", "make_scene", "scene")
_SETUP_FUNCS = ("setup_render", "setup", "configure_render", "setup_camera")


def split_main(code: str) -> tuple[str, bool]:
    """Return (definitions only, had_main).

    Model scripts end with `if __name__ == "__main__":` followed by the calls.
    The preview needs the definitions so it can drive them itself (render one
    frame instead of fifty); the full run keeps them.
    """
    lines = code.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith("if __name__") and "__main__" in line:
            return "\n".join(lines[:index]).rstrip() + "\n", True
    return code, False


def build_quick(defs: str, functions: list[str], cwd: str) -> str:
    """A controlled main: build the scene, save the .blend, render ONE frame."""
    scene_fn = next((f for f in _SCENE_FUNCS if f in functions), None)
    setup_fn = next((f for f in _SETUP_FUNCS if f in functions), None)
    calls = []
    if scene_fn:
        calls.append(f"{scene_fn}()")
    if setup_fn:
        calls.append(f"{setup_fn}()")
    if not calls:
        calls.append("pass  # no recognisable builder function")
    body = "\n".join(calls)
    return (
        f'import os as _os, sys as _sys\n_os.chdir(r"{cwd}")\n'
        + defs
        + "\n\n# --- preview driver (added by tools/preview_blender.py) ---\n"
        + body
        + "\n\nimport bpy as _bpy\n"
        + "_sc = _bpy.context.scene\n"
        + "_sc.render.resolution_percentage = 50\n"
        + "_sc.frame_set(_sc.frame_start)\n"
        + '_sc.render.filepath = _os.path.join(_os.getcwd(), "preview_frame_")\n'
        + "_bpy.ops.render.render(write_still=True)\n"
        + 'print("PREVIEW_OK", _sc.render.filepath)\n'
    )

#: Markers that separate a real scene script from reasoning text.
MARKERS = (
    ("import bpy", "imports bpy"),
    ("camera_add", "adds a camera"),
    ("light_add", "adds a light"),
    ("primitive_", "creates geometry"),
    ("keyframe_insert", "animates"),
    ("frame_end", "sets a frame range"),
    ("save_as_mainfile", "saves the .blend"),
    ("bpy.ops.render", "renders"),
)


def strip_fences(text: str) -> str:
    """Remove every markdown code fence, keeping the code inside."""
    lines = text.splitlines()
    kept = [ln for ln in lines if not ln.strip().startswith("```")]
    return "\n".join(kept).strip() + "\n"


def find_script(run_dir: Path) -> Path | None:
    for name in ("build_scene.py", "scene.py", "output.py", "scene.blend", "output.txt"):
        candidate = run_dir / name
        if candidate.is_file():
            return candidate
    files = [p for p in run_dir.iterdir() if p.is_file()]
    return files[0] if files else None


def inspect(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    code = strip_fences(raw)
    info: dict = {
        "path": path,
        "bytes": path.stat().st_size,
        "fenced": raw.lstrip().startswith("```"),
        "code": code,
        "syntax": "",
        "functions": [],
        "markers": [label for token, label in MARKERS if token in code],
        "score": 0,
    }
    try:
        tree = ast.parse(code)
        info["syntax"] = "ok"
        info["functions"] = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    except SyntaxError as exc:
        info["syntax"] = f"SyntaxError line {exc.lineno}: {exc.msg}"
    info["score"] = len(info["markers"]) if info["syntax"] == "ok" else 0
    return info


def list_runs(task: str | None = None) -> list[dict]:
    if not SANDBOX_ROOT.exists():
        return []
    tasks = [task] if task else BLENDER_TASKS
    rows = []
    for task_name in tasks:
        task_dir = SANDBOX_ROOT / task_name
        if not task_dir.is_dir():
            continue
        for run_dir in sorted(task_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            script = find_script(run_dir)
            if script is None:
                continue
            rows.append({**inspect(script), "run": run_dir.name, "task": task_name})
    return rows


def file_explorer_open(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - opens the user's editor/explorer
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


def check_blend(path: Path) -> str:
    """Validate a .blend, compressed or not.

    Blender >= 4 saves zstd-compressed by default, so the file starts with
    `28 B5 2F FD` and only the *decompressed* header reads `BLENDER`. A
    validator that insists on a literal `BLENDER` prefix rejects every modern
    .blend.
    """
    try:
        head = path.read_bytes()[:4096]
    except OSError as exc:
        return f"unreadable: {exc}"
    if head[:7] == b"BLENDER":
        return f"valid, uncompressed (format {head[7:9].decode('ascii', 'replace')})"
    if head[:4] == bytes.fromhex("28b52ffd"):
        try:
            from compression import zstd  # Python 3.14+

            full = zstd.ZstdDecompressor().decompress(path.read_bytes())
        except Exception:
            try:
                import zstandard  # optional third-party fallback

                full = zstandard.ZstdDecompressor().decompress(path.read_bytes())
            except Exception:
                return "VALID (zstd magic; cannot decompress here to confirm)"
        if full[:7] == b"BLENDER":
            fmt = full[7:9].decode("ascii", "replace")
            return f"valid, zstd-compressed (format {fmt})"
        return "zstd, but the payload is not a .blend"
    return "NOT a .blend"


def find_blender(explicit: str = "") -> str | None:
    """Locate blender.exe: explicit flag > env var > PATH > known install roots."""
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return str(candidate)
        if candidate.is_dir():
            for name in ("blender.exe", "blender"):
                if (candidate / name).is_file():
                    return str(candidate / name)
        return None

    env = os.environ.get("BLENDER_PATH") or os.environ.get("BLENDER_EXE")
    if env and Path(env).is_file():
        return env

    for name in ("blender", "blender.exe", "blender-launcher", "blender-launcher.exe"):
        found = shutil.which(name)
        if found:
            return found

    guesses = [
        Path("C:/Program Files/Blender Foundation"),
        Path("C:/Program Files (x86)/Blender Foundation"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Blender Foundation",
        Path(os.environ.get("PROGRAMFILES", "")) / "Blender Foundation",
        Path("C:/Program Files/Steam/steamapps/common/Blender"),
        Path("C:/Program Files (x86)/Steam/steamapps/common/Blender"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps",
    ]
    for root in guesses:
        try:
            if not root.is_dir():
                continue
            for exe in sorted(root.rglob("blender.exe"), reverse=True):
                return str(exe)
            for exe in sorted(root.rglob("blender-launcher.exe"), reverse=True):
                return str(exe)
        except OSError:
            continue

    # Registry (winget / MSI installs register an InstallLocation).
    if sys.platform == "win32":
        try:
            import winreg

            keys = (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            )
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub in keys:
                    try:
                        with winreg.OpenKey(hive, sub) as root_key:
                            for index in range(winreg.QueryInfoKey(root_key)[0]):
                                try:
                                    name = winreg.EnumKey(root_key, index)
                                    with winreg.OpenKey(root_key, name) as app:
                                        display = str(
                                            winreg.QueryValueEx(app, "DisplayName")[0]
                                        )
                                        if "blender" not in display.lower():
                                            continue
                                        loc = str(
                                            winreg.QueryValueEx(app, "InstallLocation")[0]
                                        )
                                        if loc and Path(loc).is_dir():
                                            for exe in Path(loc).rglob("blender.exe"):
                                                return str(exe)
                                except OSError:
                                    continue
                    except OSError:
                        continue
        except Exception:
            pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="", help="run directory name, e.g. 20261107_165436")
    ap.add_argument("--task", default="", help="task dir filter (blender_skyblock, blender_city_bridge)")
    ap.add_argument("--list", action="store_true", help="score every stored run")
    ap.add_argument("--launch", action="store_true", help="run Blender if it is installed")
    ap.add_argument(
        "--full",
        action="store_true",
        help="with --launch, render all frames instead of one preview frame",
    )
    ap.add_argument("--no-open", action="store_true", help="do not open the file in an editor")
    ap.add_argument(
        "--blender",
        default="",
        help="explicit path to blender.exe (or set BLENDER_PATH)",
    )
    args = ap.parse_args()

    runs = list_runs(args.task or None)
    if not runs:
        print(f"no sandbox runs under {SANDBOX_ROOT}", file=sys.stderr)
        return 2

    if args.list:
        print(f'{"task":<22}{"run":<20}{"file":<17}{"bytes":>7}  {"syntax":<12}{"marks":>6}  code')
        for r in runs:
            print(
                f'{r.get("task",""):<22}{r["run"]:<20}{r["path"].name:<17}{r["bytes"]:>7}  '
                f'{r["syntax"][:11]:<12}{r["score"]:>6}  {r["syntax"] == "ok" and r["score"] >= 4}'
            )
        print("\ncode=True means: valid Python AND builds a scene (>=4 markers).")
        return 0

    chosen = None
    if args.run:
        chosen = next((r for r in runs if r["run"] == args.run), None)
        if chosen is None:
            print(f"run {args.run} not found", file=sys.stderr)
            return 2
    else:
        valid = [r for r in runs if r["syntax"] == "ok"]
        if not valid:
            print("no syntactically valid script found; run with --list", file=sys.stderr)
            return 1
        chosen = max(valid, key=lambda r: (r["score"], r["bytes"]))

    run_dir = chosen["path"].parent
    target = run_dir / OUT_NAME
    prelude = f'import os as _os\n_os.chdir(r"{run_dir.resolve()}")\n'
    target.write_text(prelude + chosen["code"], encoding="utf-8")

    defs, had_main = split_main(chosen["code"])
    quick = run_dir / QUICK_NAME
    quick.write_text(
        build_quick(defs, chosen["functions"], str(run_dir.resolve())), encoding="utf-8"
    )

    print(f'run ......... {chosen["run"]}')
    print(f'source ...... {chosen["path"]}')
    print(f'bytes ....... {chosen["bytes"]}')
    print(f'fenced ...... {chosen["fenced"]}  (fence stripped into {OUT_NAME})')
    print(f'syntax ...... {chosen["syntax"]}')
    print(f'functions ... {", ".join(chosen["functions"]) or "-"}')
    print(f'builds ...... {", ".join(chosen["markers"]) or "nothing recognisable"}')
    print(f'written ..... {target}')
    print(f'quick ....... {quick}  (definitions + one-frame driver, main block: {had_main})')

    blender = find_blender(args.blender)
    print()
    if blender:
        print(f'blender ..... {blender}')
        script = OUT_NAME if args.full else QUICK_NAME
        cmd = f'"{blender}" --background --python {script}'
        print(f'script ...... {script}{"" if args.full else "  (one frame, 50% resolution)"}')
        print(f'command ..... cd "{run_dir}" && {cmd}')
        if args.launch:
            print("\nrunning...")
            proc = subprocess.run(
                [blender, "--background", "--python", script],
                cwd=str(run_dir),
                capture_output=True,
                text=True,
                timeout=1800,
            )
            tail = (proc.stdout or "")[-1500:]
            err = (proc.stderr or "")[-800:]
            print(tail)
            if err.strip():
                print("stderr:", err)
            print("exit code:", proc.returncode)
            blend = run_dir / "scene.blend"
            frames = sorted(run_dir.glob("preview_frame_*.png")) or sorted(
                run_dir.glob("render_frames/*.png")
            )
            print(
                f'scene.blend .. {"yes, " + str(blend.stat().st_size // 1024) + " KB" if blend.exists() else "MISSING"}'
            )
            if blend.exists():
                print(f"  validity ... {check_blend(blend)}")
            print(f'frames ....... {len(frames)} png' + (f" ({frames[0].name})" if frames else ""))
            for png in frames[:1]:
                file_explorer_open(png)
            if blend.exists():
                file_explorer_open(blend)
    else:
        print("blender ..... NOT FOUND")
        print()
        print("Pass the path explicitly — this works for a portable copy too:")
        print(f'  python tools/preview_blender.py --run {run_dir.name} --launch --blender "D:\\Blender\\blender.exe"')
        print("  (or permanently: setx BLENDER_PATH \"D:\\Blender\\blender.exe\")")
        print()
        print("To find it yourself:")
        print('  cmd>  dir /s /b C:\\blender.exe D:\\blender.exe')
        print()
        print("Without Blender you can still read the script:")
        print(f"  {target}")

    if not args.no_open:
        file_explorer_open(target if not args.launch else run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
