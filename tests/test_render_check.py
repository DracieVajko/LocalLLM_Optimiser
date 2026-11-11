"""The canvas-scoped render check must fail a page without a canvas."""

from __future__ import annotations

from pathlib import Path

import pytest

from lm_optimizer.services import render_check
from lm_optimizer.services.html_shot import SelectorNotFound


def test_missing_canvas_fails_instead_of_being_skipped(monkeypatch, tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text("<html><body><h1>Voxel World</h1></body></html>", encoding="utf-8")

    monkeypatch.setattr(
        "lm_optimizer.services.html_shot.find_browser", lambda: Path("chrome.exe")
    )

    def _raise(*_args, **_kwargs):
        raise SelectorNotFound("selector 'canvas' not found")

    monkeypatch.setattr("lm_optimizer.services.html_shot.capture", _raise)

    ok, detail = render_check.renders_content(html, require="canvas")

    assert ok is False
    assert "no <canvas> element" in detail


def test_canvas_verdict_requires_an_ok_frame(monkeypatch, tmp_path: Path) -> None:
    html = tmp_path / "index.html"
    html.write_text("<html><body><canvas></canvas></body></html>", encoding="utf-8")
    png = tmp_path / "shot.png"

    def _capture(_url, out, **_kwargs):
        # A single flat colour, as the failed voxel pages render.
        from tests.test_png_stats import _png

        _png(Path(out), 8, 8, [(70, 130, 180)] * 64)
        return Path(out)

    monkeypatch.setattr(
        "lm_optimizer.services.html_shot.find_browser", lambda: Path("chrome.exe")
    )
    monkeypatch.setattr("lm_optimizer.services.html_shot.capture", _capture)
    monkeypatch.setitem(render_check.measure_html.__globals__, "measure_png", render_check.measure_png)

    ok, detail = render_check.renders_content(html, require="canvas")

    assert ok is False
    assert "flat" in detail
    assert png  # silence unused warning
