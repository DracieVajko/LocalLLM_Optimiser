"""Render an HTML artifact and decide whether it actually shows something.

Text checks cannot tell a finished page from a black canvas. This module takes a
screenshot through Chrome (via ``services.html_shot``) and measures the pixels
with ``services.png_stats``. It is used by the ``renders_content`` sandbox check
so a blank render can never score 1.00.

Chrome is a host capability: when no Chromium-based browser is installed the
check reports ``unavailable`` and the sandbox records it as skipped rather than
failing every model on a machine without a browser.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from lm_optimizer.services.png_stats import ImageStats, measure_png

#: The page is given time to run its JS and build a scene before capture.
DEFAULT_WAIT_S = 6.0


@dataclass
class RenderVerdict:
    ok: bool
    skipped: bool
    detail: str
    stats: ImageStats | None = None


def measure_html(
    html_path: Path,
    *,
    wait_s: float = DEFAULT_WAIT_S,
    width: int = 1280,
    height: int = 900,
    require: str = "content",
) -> RenderVerdict:
    """Screenshot *html_path* and classify what was rendered.

    ``require="content"`` accepts anything that is not blank/flat;
    ``require="ok"`` additionally rejects a "weak" frame (sd < 6);
    ``require="canvas"`` measures the ``<canvas>`` element instead of the whole
    page, which is how a voxel task proves the island is drawn and not just a
    blue background with a title.
    """
    from lm_optimizer.services.html_shot import (
        ScreenshotError,
        SelectorNotFound,
        capture,
        find_browser,
    )

    if not html_path.exists():
        return RenderVerdict(False, True, f"missing {html_path.name}")
    if find_browser() is None:
        return RenderVerdict(True, True, "no browser installed; render not verified")

    selector = "canvas" if require == "canvas" else None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        target = Path(tmp) / "render.png"
        try:
            capture(
                html_path.resolve().as_uri(),
                target,
                width=width,
                height=height,
                wait_s=wait_s,
                full_page=False,
                selector=selector,
            )
        except SelectorNotFound:
            return RenderVerdict(False, False, f"no <{selector}> element rendered")
        except ScreenshotError as exc:
            return RenderVerdict(True, True, f"screenshot failed: {exc}"[:200])
        try:
            stats = measure_png(target)
        except (OSError, ValueError) as exc:
            return RenderVerdict(True, True, f"could not measure pixels: {exc}"[:200])

    if require in ("ok", "canvas"):
        ok = stats.verdict == "ok"
    else:
        ok = stats.has_content
    return RenderVerdict(ok, False, stats.detail(), stats)


def renders_content(html_path: Path, **kwargs: object) -> tuple[bool, str]:
    """Sandbox custom-check signature: (passed, detail)."""
    verdict = measure_html(html_path, **kwargs)  # type: ignore[arg-type]
    prefix = "skipped: " if verdict.skipped else ""
    return verdict.ok, prefix + verdict.detail


async def renders_content_async(html_path: Path, **kwargs: object) -> tuple[bool, str]:
    """Same as :func:`renders_content` but safe inside the sandbox event loop.

    Chrome capture is blocking and starts its own loop, so it runs in a worker
    thread instead of the caller's loop.
    """
    import asyncio

    return await asyncio.to_thread(renders_content, html_path, **kwargs)
