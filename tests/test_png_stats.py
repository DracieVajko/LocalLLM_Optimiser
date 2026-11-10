"""PNG statistics and the renders_content sandbox check."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from lm_optimizer.services import render_check
from lm_optimizer.services.png_stats import measure_png


def _png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    """Write a colour-type-2 PNG from a row-major pixel list."""
    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter type 0
        for x in range(width):
            raw += bytes(pixels[y * width + x])

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def test_black_frame_is_blank(tmp_path: Path) -> None:
    path = tmp_path / "black.png"
    _png(path, 8, 8, [(0, 0, 0)] * 64)

    stats = measure_png(path)

    assert stats.verdict == "blank"
    assert stats.has_content is False


def test_single_colour_frame_is_flat(tmp_path: Path) -> None:
    path = tmp_path / "flat.png"
    _png(path, 8, 8, [(188, 188, 188)] * 64)

    stats = measure_png(path)

    assert stats.verdict == "flat"
    assert stats.has_content is False


def test_mixed_frame_has_content(tmp_path: Path) -> None:
    path = tmp_path / "scene.png"
    pixels = [((x * 37) % 256, (y * 53) % 256, ((x + y) * 29) % 256) for y in range(8) for x in range(8)]
    _png(path, 8, 8, pixels)

    stats = measure_png(path)

    assert stats.verdict == "ok"
    assert stats.has_content is True


def test_render_check_skips_without_browser(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "lm_optimizer.services.html_shot.find_browser", lambda: None
    )
    html = tmp_path / "index.html"
    html.write_text("<html><body>x</body></html>", encoding="utf-8")

    ok, detail = render_check.renders_content(html)

    assert ok is True
    assert detail.startswith("skipped:")
