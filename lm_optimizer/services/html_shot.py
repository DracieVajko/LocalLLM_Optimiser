"""Deterministic HTML screenshots through the Chrome DevTools Protocol.

The plain ``chrome --headless --screenshot`` flag captures the page the moment
the load event fires, so Three.js scenes that build terrain asynchronously and
pages with entry animations are photographed half-rendered. This helper drives
Chrome over CDP instead: it waits for the load event, waits an extra settle
delay, then captures the full page. WebGL runs on SwiftShader, so it works on a
machine without a usable GPU.
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)

MAX_HEIGHT = 8000


class ScreenshotError(RuntimeError):
    """Chrome could not be launched or did not answer on the DevTools port."""


class SelectorNotFound(ScreenshotError):
    """The requested element (e.g. ``canvas``) is not in the document."""


def find_browser() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def capture(
    url: str,
    out: Path,
    *,
    width: int = 1280,
    height: int = 900,
    wait_s: float = 4.0,
    full_page: bool = True,
    debug: bool = False,
    selector: str | None = None,
    browser: Path | None = None,
    launch_timeout_s: float = 20.0,
) -> Path:
    """Screenshot ``url`` into ``out`` and return the path.

    ``selector`` clips the screenshot to one element (e.g. ``"canvas"``), which
    is how the voxel tasks check that the rendered scene exists instead of
    measuring the page chrome around it.
    """
    browser = browser or find_browser()
    if browser is None:
        raise ScreenshotError("no Chromium-based browser found")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = subprocess.Popen(
            [
                str(browser),
                "--headless=new",
                "--hide-scrollbars",
                "--allow-file-access-from-files",
                "--enable-unsafe-swiftshader",
                "--use-angle=swiftshader",
                "--ignore-gpu-blocklist",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--remote-debugging-port=0",
                f"--user-data-dir={profile}",
                f"--window-size={width},{height}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            port = _wait_for_port(
                Path(profile) / "DevToolsActivePort", launch_timeout_s, proc
            )
            asyncio.run(
                _shoot(
                    port,
                    url,
                    out,
                    width=width,
                    height=height,
                    wait_s=wait_s,
                    full_page=full_page,
                    debug=debug,
                    selector=selector,
                )
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    if not out.exists() or out.stat().st_size == 0:
        raise ScreenshotError(f"chrome produced no image for {url}")
    return out


def _note_event(reply: dict, notes: list[str]) -> None:
    method = reply.get("method", "")
    params = reply.get("params") or {}
    if method == "Runtime.exceptionThrown":
        details = params.get("exceptionDetails") or {}
        text = details.get("text") or ""
        exception = (details.get("exception") or {}).get("description") or ""
        notes.append(f"EXCEPTION {text} {exception}".strip())
    elif method == "Runtime.consoleAPICalled":
        kind = params.get("type", "log")
        args = " ".join(
            str((arg.get("value") if "value" in arg else arg.get("description", "")))
            for arg in params.get("args") or []
        )
        notes.append(f"{kind}: {args}")
    elif method == "Log.entryAdded":
        entry = params.get("entry") or {}
        notes.append(f"{entry.get('level')}: {entry.get('text')} {entry.get('url', '')}".strip())


def _read_port(port_file: Path) -> str | None:
    """Read Chrome's DevTools port file.

    Chrome keeps the file open while it starts, so a concurrent read can fail
    with a sharing violation on Windows (``PermissionError``). That is a
    transient condition: return ``None`` and let the caller retry.
    """
    try:
        return port_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _wait_for_port(port_file: Path, timeout_s: float, proc=None) -> int:
    """Wait for Chrome to publish its DevTools port.

    ``proc`` (optional) is the browser process: if it dies while we wait, the
    wait ends immediately with a clear error instead of burning the timeout.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        content = _read_port(port_file)
        if content:
            lines = content.splitlines()
            if lines and lines[0].strip().isdigit():
                return int(lines[0].strip())
        if proc is not None and proc.poll() is not None:
            raise ScreenshotError("chrome exited before opening a DevTools port")
        time.sleep(0.1)
    raise ScreenshotError("chrome did not open a DevTools port")


async def _shoot(
    port: int,
    url: str,
    out: Path,
    *,
    width: int,
    height: int,
    wait_s: float,
    full_page: bool,
    debug: bool = False,
    selector: str | None = None,
) -> None:
    from websockets.asyncio.client import connect

    targets = httpx.get(f"http://127.0.0.1:{port}/json/list", timeout=10).json()
    page = next((t for t in targets if t.get("type") == "page"), None)
    if page is None:
        raise ScreenshotError("chrome exposed no page target")

    async with connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
        counter = 0
        notes: list[str] = []

        async def call(method: str, **params: object) -> dict:
            nonlocal counter
            counter += 1
            message_id = counter
            await ws.send(
                json.dumps({"id": message_id, "method": method, "params": params})
            )
            while True:
                reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                if reply.get("id") == message_id:
                    if "error" in reply:
                        raise ScreenshotError(f"{method}: {reply['error']}")
                    return reply.get("result", {})
                if debug:
                    _note_event(reply, notes)

        await call("Page.enable")
        if debug:
            await call("Runtime.enable")
            await call("Log.enable")
        await call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=False,
        )
        await call("Page.navigate", url=url)
        await asyncio.sleep(wait_s)

        if debug:
            remaining = 0.5
            while remaining > 0:
                try:
                    reply = json.loads(
                        await asyncio.wait_for(ws.recv(), timeout=min(remaining, 0.2))
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    remaining -= 0.2
                    continue
                _note_event(reply, notes)
            for line in notes:
                print(f"[console] {line}")

        element_rect = None
        if selector:
            await call("Runtime.enable")
            result = await call(
                "Runtime.evaluate",
                expression=(
                    "(function(){var el=document.querySelector("
                    + json.dumps(selector)
                    + ");if(!el)return null;var r=el.getBoundingClientRect();"
                    "return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});})()"
                ),
                returnByValue=True,
            )
            value = (result.get("result") or {}).get("value")
            if value:
                element_rect = json.loads(value)
            else:
                raise SelectorNotFound(f"selector {selector!r} not found")

        metrics = await call("Page.getLayoutMetrics")
        css = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
        content_height = min(int(css.get("height") or height), MAX_HEIGHT)
        content_width = int(css.get("width") or width)

        capture_beyond = full_page
        clip = None
        if element_rect and element_rect["w"] > 4 and element_rect["h"] > 4:
            clip = {
                "x": max(0.0, float(element_rect["x"])),
                "y": max(0.0, float(element_rect["y"])),
                "width": float(element_rect["w"]),
                "height": float(element_rect["h"]),
                "scale": 1,
            }
            capture_beyond = False
        elif full_page:
            clip = {
                "x": 0,
                "y": 0,
                "width": max(width, content_width),
                "height": max(height, content_height),
                "scale": 1,
            }
        shot = await call(
            "Page.captureScreenshot",
            format="png",
            captureBeyondViewport=capture_beyond,
            **({"clip": clip} if clip else {}),
        )
        out.write_bytes(base64.b64decode(shot["data"]))


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Screenshot an HTML file via Chrome CDP.")
    parser.add_argument("url", help="file path or http(s) URL")
    parser.add_argument("--out", required=True, help="output PNG path")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--wait", type=float, default=4.0)
    parser.add_argument("--no-full-page", action="store_true")
    parser.add_argument("--debug", action="store_true", help="print console output")
    args = parser.parse_args()

    url = args.url
    if not url.startswith(("http://", "https://", "file://")):
        url = Path(url).resolve().as_uri()
    path = capture(
        url,
        Path(args.out),
        width=args.width,
        height=args.height,
        wait_s=args.wait,
        full_page=not args.no_full_page,
        debug=args.debug,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
