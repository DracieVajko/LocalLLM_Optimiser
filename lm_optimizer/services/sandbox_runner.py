"""Sandbox runners: execute a sandbox task in an isolated workdir.

Implements the execution half of the master spec section 13:

- The model writes files into an isolated workdir; nothing outside it is
  touched.
- Network is off by default; only whitelisted executables may run.
- Every execution has a timeout and bounded output.
- The repair loop re-runs the task with evidence-only feedback.
- Artifacts are listed for retention; commands are sanitized before they
  are ever shown to the user.

The runner is intentionally conservative: it runs commands with the
platform's shell in a cwd that is the isolated workdir, with a timeout, and
records stdout/stderr/exit code. It does NOT sandbox the OS - it is a
workdir + allowlist + timeout policy, which is what a cross-platform
tool can honestly promise.
"""

from __future__ import annotations

import gzip
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime as _dt
from pathlib import Path

from lm_optimizer.logging_config import get_logger
from lm_optimizer.services.best_effort import log_best_effort

logger = get_logger(__name__)

_FENCE_LINE = re.compile(r"^\s*```[a-zA-Z0-9_+.-]*\s*$")
_CODE_START = re.compile(
    r"^\s*(export\b|import\b|const\b|let\b|var\b|function\b|class\b|async\b)"
)
_PY_START = re.compile(r"^\s*(import\b|from\b|def\b|class\b|#!)")
_HTML_START = re.compile(r"^\s*(<!doctype\s+html|<html\b)", re.IGNORECASE)


def extract_payload(text: str, filename: str) -> str:
    """Trim reasoning preamble and markdown fences from a model artifact.

    Reasoning models often emit a thinking trace ("We need to…") before the
    actual code. Writing that into ``scene.js`` / ``index.html`` makes the
    artifact unparseable and the sandbox score meaningless. The extraction is
    deliberate and conservative: it only moves the start of the file to the
    first line that looks like real content for that file type.
    """
    if not text:
        return text
    # Remove fence lines anywhere (``` or ```js on their own line). Keep the
    # original bytes when nothing needs removing.
    raw_lines = text.splitlines()
    kept_lines = [ln for ln in raw_lines if not _FENCE_LINE.match(ln)]
    if len(kept_lines) != len(raw_lines):
        cleaned = "\n".join(kept_lines)
        if text.endswith("\n"):
            cleaned += "\n"
    else:
        cleaned = text

    suffix = Path(filename).suffix.lower()
    if suffix in (".js", ".mjs", ".cjs", ".ts"):
        start = _first_matching_line(cleaned, _CODE_START)
        if start > 0:
            cleaned = cleaned[start:]
    elif suffix in (".html", ".htm"):
        start = _first_matching_line(cleaned, _HTML_START)
        if start > 0:
            cleaned = cleaned[start:]
    elif suffix == ".py":
        start = _first_matching_line(cleaned, _PY_START)
        if start > 0:
            cleaned = cleaned[start:]
    elif suffix == ".json":
        begin = cleaned.find("{")
        end = cleaned.rfind("}")
        if begin != -1 and end > begin:
            cleaned = cleaned[begin : end + 1]
    return cleaned


def _first_matching_line(text: str, pattern: re.Pattern) -> int:
    """Return the character offset of the first line matching ``pattern``.

    Returns 0 when nothing matches or the match is already the first line.
    """
    offset = 0
    for line in text.splitlines(keepends=True):
        if pattern.match(line):
            return offset
        offset += len(line)
    return 0

from lm_optimizer.services.sandbox_lab import (
    RepairAttempt,
    SandboxPolicy,
    SandboxResult,
    SandboxTask,
    build_repair_feedback,
    repair_penalty,
    score_attempt,
)


@dataclass
class ExecutionResult:
    """Outcome of one command execution."""

    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    error: str = ""


def run_command(
    command: str,
    workdir: Path,
    policy: SandboxPolicy,
    timeout_s: float | None = None,
) -> ExecutionResult:
    """Run one command inside the isolated workdir under the policy.

    The command is NOT executed when the executable is not on the
    allowlist - the attempt fails with a clear reason instead.
    """
    started = time.perf_counter()
    if not policy.is_command_allowed(command):
        return ExecutionResult(
            ok=False,
            exit_code=None,
            stdout="",
            stderr="",
            duration_s=0.0,
            error=(
                f"command not allowed by the sandbox policy: "
                f"{policy.sanitize_command(command)}"
            ),
        )
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # Network off by default: no proxy variables, and the policy flag is
    # documented (a true network namespace is out of scope for a
    # cross-platform helper).
    if not policy.network_enabled:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env.pop(key, None)
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s or policy.timeout_s,
            errors="replace",
        )
        return ExecutionResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=proc.stdout[-policy.max_output_bytes :],
            stderr=proc.stderr[-policy.max_output_bytes :],
            duration_s=time.perf_counter() - started,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            ok=False,
            exit_code=None,
            stdout="",
            stderr="",
            duration_s=time.perf_counter() - started,
            error=f"timeout after {timeout_s or policy.timeout_s:.0f}s",
        )
    except Exception as e:  # noqa: BLE001
        return ExecutionResult(
            ok=False,
            exit_code=None,
            stdout="",
            stderr="",
            duration_s=time.perf_counter() - started,
            error=f"{type(e).__name__}: {e}"[:200],
        )


def apply_retention(base_dir: Path, policy: SandboxPolicy) -> list[Path]:
    """Prune old run directories per the policy (spec §13.5).

    `artifact_retention` is "keep_last_N" (default keep_last_10). Returns the
    directories that were removed. The newest N runs are always kept.
    """
    removed: list[Path] = []
    if not base_dir.is_dir():
        return removed
    try:
        keep = int(str(policy.artifact_retention).split("_")[-1])
    except (TypeError, ValueError):
        keep = 10
    if keep < 0:
        keep = 10
    dirs = [p for p in base_dir.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in dirs[keep:]:
        try:
            shutil.rmtree(stale)
            removed.append(stale)
        except OSError:
            continue
    return removed


def collect_blend(
    workdir: Path,
    model: str,
    task_id: str,
    *,
    base: Path | None = None,
) -> str:
    """Copy the produced ``scene.blend`` somewhere stable for a human to open.

    Model answers are text; the openable ``.blend`` only exists after Blender
    runs the generated script. Keeping a copy under ``results/blends/<model>/
    <task>/`` means the file survives cleanup of the scratch workdir and is easy
    to find in the UI. Returns the absolute path, or an empty string.
    """
    source = workdir / "scene.blend"
    if not source.exists() or source.stat().st_size == 0:
        return ""
    try:
        if not looks_like_blend(source.read_bytes()):
            return ""
    except OSError:
        return ""

    slug = "".join(c if c.isalnum() else "_" for c in model)[:60] or "model"
    stamp = workdir.name or _dt.now().strftime("%Y%m%d_%H%M%S")
    if base is None and "results" not in workdir.parts:
        # Tests and ad-hoc temp workdirs must not drop files into the repo.
        return ""
    target_dir = (base or (Path("results") / "blends")) / slug / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{stamp}.blend"
    try:
        shutil.copyfile(source, target)
    except OSError as exc:
        log_best_effort("best-effort operation failed", exc)
        return ""
    return str(target.resolve())


def read_workdir_files(workdir: Path, limit: int = 50) -> dict[str, str]:
    """Read the text files the model produced (best effort, size limited)."""
    out: dict[str, str] = {}
    if not workdir.exists():
        return out
    count = 0
    for path in sorted(workdir.rglob("*")):
        if count >= limit:
            break
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > 512_000:
                continue
            # POSIX-style relative paths so reports are platform independent.
            rel = path.relative_to(workdir).as_posix()
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        count += 1
    return out


#: Render-engine names written by models trained on other Blender releases.
#: Blender 5.x accepts only BLENDER_EEVEE / BLENDER_WORKBENCH / CYCLES.
_ENGINE_ALIASES = {
    "EEVEE": "BLENDER_EEVEE",
    "EEVEE_NEXT": "BLENDER_EEVEE",
    "BLENDER_EEVEE_NEXT": "BLENDER_EEVEE",
    "BLENDER_EEVEE_LEGACY": "BLENDER_EEVEE",
}
_ENGINE_LINE = re.compile(
    r"(render\.engine\s*=\s*)([\"'])(?P<name>[A-Za-z0-9_]+)\2"
)


def normalize_render_engine(script: str) -> str:
    """Map a known engine alias onto the value this Blender accepts.

    A model trained on Blender 4.2 writes ``BLENDER_EEVEE_NEXT`` and one trained
    on 4.0 writes ``EEVEE``; Blender 5.x renamed it back to ``BLENDER_EEVEE``.
    Only the engine assignment is touched, never geometry or render settings, so
    a valid scene is not rejected for a version rename. The raw script stays on
    disk; the normalised copy is what runs.
    """
    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        mapped = _ENGINE_ALIASES.get(name)
        if mapped is None:
            return match.group(0)
        return f"{match.group(1)}{match.group(2)}{mapped}{match.group(2)}"

    return _ENGINE_LINE.sub(_replace, script)


def _blender_exec_script(workdir: Path) -> Path | None:
    """Write build_scene.exec.py when the engine name needs mapping."""
    script = workdir / "build_scene.py"
    if not script.exists():
        return None
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    normalized = normalize_render_engine(text)
    if normalized == text:
        return None
    target = workdir / "build_scene.exec.py"
    target.write_text(normalized, encoding="utf-8")
    return target


_BLEND_MAGIC = b"BLENDER"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_GZIP_MAGIC = b"\x1f\x8b"


def looks_like_blend(data: bytes) -> bool:
    """Return True when *data* is a Blender file, compressed or not.

    Blender 3.0+ writes zstd-compressed ``.blend`` files by default, so the
    literal ``BLENDER`` magic is only present in uncompressed files. Older
    Blender releases used gzip. Refusing the compressed forms rejected every
    valid file produced by a current Blender install.
    """
    if data[:7] == _BLEND_MAGIC:
        return True
    if data[:4] == _ZSTD_MAGIC:
        try:
            import zstandard
        except ImportError:
            # No decoder installed: the zstd frame magic plus the size gate
            # and a successful Blender exit are the available evidence.
            return True
        try:
            header = zstandard.ZstdDecompressor().decompress(
                data, max_output_size=7
            )
        except Exception:  # noqa: BLE001 - corrupt/unsupported frame
            return False
        return header[:7] == _BLEND_MAGIC
    if data[:2] == _GZIP_MAGIC:
        try:
            return gzip.GzipFile(fileobj=io.BytesIO(data)).read(7) == _BLEND_MAGIC
        except Exception:  # noqa: BLE001 - corrupt gzip stream
            return False
    return False


@dataclass
class SandboxRunner:
    """Executes a sandbox task with the repair loop."""

    task: SandboxTask
    policy: SandboxPolicy
    workdir: Path
    #: Command that runs the model-produced solution (e.g. a python script).
    command: str = ""
    #: Extra checks provided by the host (browser tests, blender validation).
    custom_checks: dict[str, tuple[bool, str]] = field(default_factory=dict)
    #: Model name used for debug output (optional).
    model: str = ""
    #: Write debug.json with per-attempt timings and raw command output.
    debug: bool = True

    def _scoring_files(self, files: dict[str, str]) -> dict[str, str]:
        """Keep only the task's declared artifacts for the text checks.

        Without this, ``blender.log`` and ``debug.json`` (which contains the
        previous failing-check list) end up in the regex haystack and can make a
        check pass or fail for text the model never wrote.
        """
        wanted = [artifact.rstrip("/") for artifact in self.task.artifacts]
        if not wanted:
            return files
        selected: dict[str, str] = {}
        for name, content in files.items():
            if any(name == item or name.startswith(item + "/") for item in wanted):
                selected[name] = content
        return selected or files

    def run(self, generate) -> SandboxResult:
        """Synchronous wrapper around `run_async` (used by the tests)."""
        import asyncio

        return asyncio.run(self.run_async(generate))

    async def run_async(self, generate) -> SandboxResult:
        """Run the task with the repair loop.

        `generate(feedback: str) -> str` (or an async equivalent) is called
        for every attempt; the first call gets an empty feedback string,
        later ones get the evidence-only repair feedback. Async generators
        are awaited - the CLI talks to LM Studio through an async client.
        """
        result = SandboxResult(task_id=self.task.id)
        feedback = ""
        debug_attempts: list[dict] = []
        for attempt in range(self.task.max_repair_attempts + 1):
            started = time.perf_counter()
            gen_started = time.perf_counter()
            try:
                produced = generate(feedback)
                if inspect.isawaitable(produced):
                    produced = await produced
            except Exception as e:  # noqa: BLE001
                result.error = f"{type(e).__name__}: {e}"[:200]
                result.status = "not_measured"
                debug_attempts.append(
                    {
                        "attempt": attempt,
                        "generate_s": round(time.perf_counter() - gen_started, 1),
                        "error": result.error,
                    }
                )
                logger.warning(
                    "sandbox generate failed",
                    task=self.task.id,
                    model=self.model,
                    attempt=attempt,
                    error=result.error,
                )
                break
            gen_s = time.perf_counter() - gen_started
            logger.info(
                "sandbox attempt generated",
                task=self.task.id,
                model=self.model,
                attempt=attempt,
                generate_s=round(gen_s, 1),
                output_chars=len(produced or ""),
            )

            if not (produced or "").strip():
                # A model that returns nothing (crashed engine, empty completion)
                # was never actually measured. Scoring the empty artifact would
                # report a 0.00 quality result for a 0.2 s non-run.
                result.status = "not_measured"
                result.error = result.error or "empty model output"
                debug_attempts.append(
                    {
                        "attempt": attempt,
                        "generate_s": round(gen_s, 1),
                        "output_chars": 0,
                        "error": "empty model output",
                    }
                )
                logger.warning(
                    "sandbox attempt produced no text",
                    task=self.task.id,
                    model=self.model,
                    attempt=attempt,
                )
                break

            # The model returns the file contents; write them into the
            # isolated workdir.
            self._materialise(produced)
            if self.task.kind.value == "blender":
                # A repair attempt must be judged on its own output, not on
                # artifacts left behind by an earlier attempt.
                self._clear_generated_outputs()

            execution = ExecutionResult(
                ok=True, exit_code=0, stdout="", stderr="", duration_s=0.0
            )
            if self.command:
                command = self.command
                if self.task.kind.value == "blender":
                    exec_script = _blender_exec_script(self.workdir)
                    if exec_script is not None:
                        command = command.replace("build_scene.py", exec_script.name)
                        logger.info(
                            "blender engine name normalised for this release",
                            task=self.task.id,
                            script=exec_script.name,
                        )
                execution = run_command(
                    command, self.workdir, self.policy, self.task.timeout_s
                )

            files = self._scoring_files(read_workdir_files(self.workdir))
            # Web tasks get the static HTML/JS validation automatically
            # (spec 13.1 criteria achievable without a browser engine).
            custom = dict(self.custom_checks or {})
            if any(check.name == "renders_content" for check in self.task.checks):
                html_name = next(
                    (
                        name
                        for name in files
                        if name.lower().endswith((".html", ".htm"))
                    ),
                    None,
                )
                if html_name is not None:
                    from lm_optimizer.services.render_check import (
                        renders_content_async,
                    )

                    required = next(
                        (
                            str(check.value or "content")
                            for check in self.task.checks
                            if check.name == "renders_content"
                        ),
                        "content",
                    )
                    ok, detail = await renders_content_async(
                        self.workdir / html_name, require=required
                    )
                    custom["renders_content"] = (ok, detail)
            if self.task.kind.value == "web":
                try:
                    from lm_optimizer.services.web_validator import (
                        validate_web_files,
                    )

                    for check in validate_web_files(files):
                        custom[check.name] = (check.passed, check.detail)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Web validation failed", error=str(e)[:160])

            # Blender tasks: run the produced script with blender, then
            # validate the resulting .blend file is a real binary.
            if self.task.kind.value == "blender" and self.command:
                blend_path = self.workdir / "scene.blend"
                frame_dir = self.workdir / "frames"
                # ``execution`` above already ran the command exactly once.
                exec_result = execution
                custom["blend_runs"] = (
                    exec_result.ok,
                    f"exit={exec_result.exit_code} stderr={exec_result.stderr[:200]}",
                )
                try:
                    (self.workdir / "blender.log").write_text(
                        f"exit={exec_result.exit_code}\n"
                        f"--- stdout ---\n{exec_result.stdout}\n"
                        f"--- stderr ---\n{exec_result.stderr}",
                        encoding="utf-8",
                        errors="replace",
                    )
                except OSError as exc:
                    log_best_effort("best-effort operation failed", exc)
                if blend_path.exists() and blend_path.is_file():
                    data = blend_path.read_bytes()
                    custom["blend_is_binary"] = (
                        looks_like_blend(data),
                        f"size={len(data)} magic={data[:7]!r}",
                    )
                    custom["blend_min_size"] = (
                        len(data) > 16_384,
                        f"size={len(data)} (>16KB)",
                    )
                    needs_stats = any(
                        check.name
                        in (
                            "blend_has_camera",
                            "blend_has_light",
                            "city_mesh_count",
                            "city_height_variety",
                            "city_footprint",
                        )
                        for check in self.task.checks
                    )
                    if needs_stats and looks_like_blend(data):
                        from lm_optimizer.services.blend_inspect import inspect_blend

                        stats = inspect_blend(blend_path)
                        custom["blend_has_camera"] = (
                            stats.cameras >= 1,
                            f"cameras={stats.cameras}",
                        )
                        custom["blend_has_light"] = (
                            stats.lights >= 1,
                            f"lights={stats.lights}",
                        )
                        custom["city_mesh_count"] = (
                            stats.meshes >= 60,
                            f"meshes={stats.meshes} (min 60), vertices={stats.vertices}",
                        )
                        custom["city_height_variety"] = (
                            stats.tall_objects >= 3 and stats.height_max >= 15,
                            f"tall(>=15m)={stats.tall_objects}, max={stats.height_max}m",
                        )
                        custom["city_footprint"] = (
                            max(stats.size) >= 40,
                            f"size={stats.size}",
                        )
                else:
                    custom["blend_is_binary"] = (
                        False,
                        f"scene.blend not created (size={blend_path.stat().st_size if blend_path.exists() else 0})",
                    )
                    custom["blend_min_size"] = (False, "no .blend file")
                if frame_dir.exists() and frame_dir.is_dir():
                    png_count = len(list(frame_dir.glob("*.png")))
                    custom["frames_rendered"] = (
                        png_count > 0,
                        f"{png_count} frame(s) rendered",
                    )
                else:
                    custom["frames_rendered"] = (
                        False,
                        "no frames directory",
                    )
                preview_path = self.workdir / "preview.png"
                if preview_path.exists() and preview_path.is_file():
                    preview_size = preview_path.stat().st_size
                    custom["preview_rendered"] = (
                        preview_size > 1000,
                        f"preview.png size={preview_size}",
                    )
                else:
                    custom["preview_rendered"] = (False, "no preview.png")
                # Merge execution result into score too
                if not exec_result.ok:
                    custom["blender_command_failed"] = (
                        False,
                        f"blender exited {exec_result.exit_code}: {exec_result.stderr[:200]}",
                    )
            score, failing, critical = score_attempt(
                self.task,
                files,
                stdout=execution.stdout,
                stderr=execution.stderr,
                exit_code=execution.exit_code,
                custom_results=custom or None,
            )
            passed = not failing and execution.ok
            record = RepairAttempt(
                attempt=attempt,
                output=produced[:4000],
                exit_code=execution.exit_code,
                passed=passed,
                score=score,
                error=execution.error or ("; ".join(failing)[:300] if failing else ""),
                duration_s=time.perf_counter() - started,
                failing_checks=list(failing),
            )
            result.attempts.append(record)
            debug_attempts.append(
                {
                    "attempt": attempt,
                    "generate_s": round(gen_s, 1),
                    "total_s": round(time.perf_counter() - started, 1),
                    "output_chars": len(produced or ""),
                    "exit_code": execution.exit_code,
                    "exec_ok": execution.ok,
                    "exec_error": execution.error,
                    "stdout_tail": (execution.stdout or "")[-1500:],
                    "stderr_tail": (execution.stderr or "")[-1500:],
                    "failing": failing,
                    "critical": critical,
                    "score": score,
                    "passed": passed,
                    "artifacts": sorted(files.keys()),
                }
            )
            logger.info(
                "sandbox attempt scored",
                task=self.task.id,
                model=self.model,
                attempt=attempt,
                score=score,
                passed=passed,
                failing=failing,
                critical=critical,
                exit_code=execution.exit_code,
            )
            if attempt == 0:
                result.first_pass_success = passed
            if critical:
                result.critical_failures = critical
            if passed:
                result.final_success = True
                result.final_score = score
                result.penalized_score = score * repair_penalty(attempt)
                result.repair_count = attempt
                break
            if attempt == self.task.max_repair_attempts:
                result.final_score = score
                result.penalized_score = score * repair_penalty(attempt)
                result.repair_count = attempt
                break
            feedback = build_repair_feedback(
                self.task,
                attempt=attempt + 1,
                stdout=execution.stdout,
                stderr=execution.stderr,
                failing_checks=failing,
            )
        result.artifacts = sorted(read_workdir_files(self.workdir).keys())
        if self.task.kind.value == "blender":
            result.blend_file = collect_blend(self.workdir, self.model, self.task.id)
        if self.debug:
            try:
                self.workdir.mkdir(parents=True, exist_ok=True)
                (self.workdir / "debug.json").write_text(
                    json.dumps(
                        {
                            "task": self.task.id,
                            "model": self.model,
                            "command": self.command,
                            "attempts": debug_attempts,
                            "final": result.as_dict(),
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                log_best_effort("best-effort operation failed", exc)
        return result

    def _materialise(self, produced: str) -> None:
        """Write the model output into the isolated workdir.

        Artifact names are untrusted input: a name that resolves outside the
        sandbox root is rejected (never written) and falls back to output.txt.

        The model's raw text is written to the first artifact name
        (typically ``build_scene.py`` for blender tasks, ``index.html`` for
        web tasks, etc.). Other artifact names (e.g. ``scene.blend``) are
        produced by running commands, not by writing the model's raw text.
        """
        self.workdir.mkdir(parents=True, exist_ok=True)
        primary = self.task.artifacts[0] if self.task.artifacts else "output.txt"
        if primary.endswith("/"):
            primary = primary.rstrip("/") + "/output.txt"
        # Drop the reasoning preamble / markdown fences before writing the
        # artifact: a code file must start with code, not with "We need to…".
        text = extract_payload(produced or "", primary)
        root = self.workdir.resolve()
        try:
            target = (self.workdir / primary).resolve()
            target.relative_to(root)  # raises ValueError when escaping
        except (ValueError, OSError):
            target = root / "output.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _clear_generated_outputs(self) -> None:
        """Remove artifacts produced by a previous repair attempt."""
        for name in ("scene.blend", "scene.blend1", "blender.log"):
            path = self.workdir / name
            try:
                if path.exists() and path.is_file():
                    path.unlink()
            except OSError as exc:
                log_best_effort("best-effort operation failed", exc)
        frames = self.workdir / "frames"
        try:
            if frames.exists() and frames.is_dir():
                shutil.rmtree(frames)
        except OSError as exc:
            log_best_effort("best-effort operation failed", exc)


def build_command_for(task: SandboxTask) -> str:
    """Default command that executes the produced artifact."""
    if task.kind.value == "blender":
        primary = task.artifacts[0] if task.artifacts else "build_scene.py"
        return f"blender --background --python {primary}"
    if task.kind.value == "web":
        return ""
    return ""


async def run_manual_prompt(
    client,
    model_id: str,
    load_config,
    prompt: str,
    run_id: str = "",
    base_dir: Path | None = None,
    max_output_tokens: int = 2048,
    temperature: float = 0.2,
    timeout_s: float = 300.0,
) -> dict:
    """Generate one custom prompt under the exact optimizer config.

    No checks => no score (spec §6.3): the output is recorded for human review
    with timing only. The model is unloaded in ``finally``.
    """
    import time as _time
    from datetime import datetime as _dt

    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    root = base_dir or (Path("results") / "sandbox")
    safe_run = str(run_id or "adhoc").replace("/", "_").replace("\\", "_")
    workdir = root / safe_run / "custom" / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    requested = load_config.to_dict()
    applied: dict | None = None
    echo_mismatches: dict | None = None
    output = ""
    error: str | None = None
    unloaded = False
    started = _time.perf_counter()

    try:
        try:
            await client.ensure_unloaded(model_id)
        except Exception as exc:
            log_best_effort("best-effort operation failed", exc)
        loaded = await client.load_model(model_id, load_config)
        if not getattr(loaded, "success", False):
            error = f"load failed: {getattr(loaded, 'error', None) or 'unknown'}"
        else:
            if getattr(loaded, "loaded_config", None) is not None:
                applied = loaded.loaded_config.to_dict()
            echo_mismatches = getattr(loaded, "echo_mismatches", None)
            response = await client.chat_completion(
                model=model_id,
                input_text=prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
            choices = response.get("choices") or []
            if choices:
                output = str((choices[0].get("message") or {}).get("content") or "")
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"[:200]
    finally:
        try:
            await client.ensure_unloaded(model_id)
            unloaded = True
        except Exception:
            unloaded = False

    elapsed = max(_time.perf_counter() - started, 1e-6)
    try:
        (workdir / "output.txt").write_text(output, encoding="utf-8")
    except OSError:
        pass

    return {
        "task_id": "custom",
        "task_kind": "text",
        "success": error is None and bool(output),
        "manual_review_only": True,
        "quality_score": None,  # never synthesise a score without criteria
        "output_text": output,
        "output_chars": len(output),
        "elapsed_s": round(elapsed, 2),
        "config_requested": requested,
        "config_applied": applied,
        "echo_mismatches": echo_mismatches,
        "run_id": str(run_id or ""),
        "workdir": str(workdir),
        "error": error,
        "unloaded": unloaded,
    }


async def run_sandbox_task(
    client,
    model_id: str,
    load_config,
    task: "SandboxTask",
    run_id: str = "",
    base_dir: Path | None = None,
    max_output_tokens: int = 4096,
    temperature: float = 0.2,
) -> dict:
    """Run one sandbox task against the EXACT optimizer configuration.

    Contract (spec §6.2):
    - the model is loaded through the same verified client used by the
      optimizer, with the provided LoadConfiguration;
    - the applied (echoed) configuration is recorded next to the result so a
      sandbox run can never be mistaken for proof of a different config;
    - the model is unloaded in a ``finally`` block and the clean-hood state is
      reported (``unloaded``);
    - artifacts stay inside an isolated per-run/per-task workdir.

    Returns a JSON-serializable dict (never raises for task-level failures).
    """
    import time as _time
    from datetime import datetime as _dt

    from lm_optimizer.services.sandbox_lab import SandboxPolicy

    stamp = _dt.now().strftime("%Y%m%d_%H%M%S")
    root = base_dir or (Path("results") / "sandbox")
    safe_run = str(run_id or "adhoc").replace("/", "_").replace("\\", "_")
    workdir = root / safe_run / task.id / stamp
    workdir.mkdir(parents=True, exist_ok=True)

    policy = SandboxPolicy(
        workdir=workdir,
        network_enabled=False,
        timeout_s=task.timeout_s,
        allowed_executables=task.allowed_executables,
    )
    runner = SandboxRunner(
        task=task,
        policy=policy,
        workdir=workdir,
        command=build_command_for(task),
    )

    requested = load_config.to_dict()
    applied: dict | None = None
    echo_mismatches: dict | None = None
    started = _time.perf_counter()
    out: dict

    try:
        # Never stack a second instance of the same model.
        try:
            await client.ensure_unloaded(model_id)
        except Exception as exc:
            log_best_effort("best-effort operation failed", exc)
        loaded = await client.load_model(model_id, load_config)
        if not getattr(loaded, "success", False):
            load_error = getattr(loaded, "error", None) or "load failed"
            out = {
                "task_id": task.id,
                "task_kind": task.kind.value,
                "success": False,
                "error": f"load failed: {load_error}"[:200],
                "config_requested": requested,
                "config_applied": None,
                "echo_mismatches": None,
                "run_id": str(run_id or ""),
                "workdir": str(workdir),
            }
        else:
            if getattr(loaded, "loaded_config", None) is not None:
                applied = loaded.loaded_config.to_dict()
            echo_mismatches = getattr(loaded, "echo_mismatches", None)

            async def _generate(feedback: str) -> str:
                prompt = task.prompt
                if feedback:
                    prompt = (
                        f"{task.prompt}\n\n"
                        "Your previous attempt failed these checks. Use the evidence "
                        f"to fix it (do not ask for the solution):\n{feedback}"
                    )
                response = await client.chat_completion(
                    model=model_id,
                    input_text=prompt,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
                choices = response.get("choices") or []
                if not choices:
                    return ""
                message = choices[0].get("message") or {}
                return str(message.get("content") or "")

            result = await runner.run_async(_generate)
            out = {
                "task_id": task.id,
                "task_kind": task.kind.value,
                "success": bool(result.final_success),
                "result": result.as_dict(),
                "config_requested": requested,
                "config_applied": applied,
                "echo_mismatches": echo_mismatches,
                "run_id": str(run_id or ""),
                "workdir": str(workdir),
            }
    except Exception as e:  # noqa: BLE001 - task failure must not kill the run
        out = {
            "task_id": task.id,
            "task_kind": task.kind.value,
            "success": False,
            "error": f"{type(e).__name__}: {e}"[:200],
            "config_requested": requested,
            "config_applied": applied,
            "echo_mismatches": echo_mismatches,
            "run_id": str(run_id or ""),
            "workdir": str(workdir),
        }
    finally:
        # Guaranteed unload; the flag is reported on the result below.
        try:
            await client.ensure_unloaded(model_id)
            unloaded = True
        except Exception:
            unloaded = False

    out["unloaded"] = unloaded
    out["duration_s"] = round(_time.perf_counter() - started, 1)
    return out
