"""Measure whether a rendered screenshot actually contains a scene.

The web/minecraft tasks used to be scored from the HTML text only, so a page
that renders a black canvas - or a single flat colour - still scored 1.00.
These helpers read a PNG with the standard library (no Pillow) and classify it:

    blank  dark pixels >= 99 %      nothing rendered
    flat   sd < 2 and tones < 4     one colour, no geometry
    weak   sd < 6                   barely any content
    ok     otherwise

``renders_content`` in the sandbox uses this through ``render_check``.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: Pixels darker than this (0-255 luminance) count as "dark".
DARK_LEVEL = 12
#: Sampling target: measure at most this many pixels.
SAMPLE_PIXELS = 20_000

BLANK_DARK_PCT = 97.0
FLAT_SD = 2.0
FLAT_TONES = 4
WEAK_SD = 6.0


@dataclass
class ImageStats:
    width: int
    height: int
    mean: float
    sd: float
    dark_pct: float
    tones: int

    @property
    def verdict(self) -> str:
        if self.dark_pct >= BLANK_DARK_PCT:
            return "blank"
        if self.sd < FLAT_SD and self.tones < FLAT_TONES:
            return "flat"
        if self.sd < WEAK_SD:
            return "weak"
        return "ok"

    @property
    def has_content(self) -> bool:
        """True unless the image is a blank or single-colour frame."""
        return self.verdict not in ("blank", "flat")

    def detail(self) -> str:
        return (
            f"{self.width}x{self.height} mean={self.mean:.1f} sd={self.sd:.1f} "
            f"dark={self.dark_pct:.0f}% tones={self.tones} verdict={self.verdict}"
        )


def read_png(path: Path) -> tuple[int, int, int, bytes]:
    """Decode an 8-bit PNG to (width, height, channels, pixels)."""
    data = path.read_bytes()
    if data[:8] != PNG_MAGIC:
        raise ValueError("not a PNG file")

    index = 8
    idat = b""
    width = height = None
    bit_depth = color_type = None
    while index < len(data):
        length = struct.unpack(">I", data[index : index + 4])[0]
        chunk_type = data[index + 4 : index + 8]
        chunk = data[index + 8 : index + 8 + length]
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif chunk_type == b"IDAT":
            idat += chunk
        elif chunk_type == b"IEND":
            break
        index += 12 + length

    if width is None or height is None or bit_depth != 8 or color_type not in (2, 6):
        raise ValueError(
            f"unsupported PNG (bit_depth={bit_depth}, color_type={color_type}); "
            "expected 8-bit RGB/RGBA"
        )

    raw = zlib.decompress(idat)
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        filter_type = raw[pos]
        pos += 1
        line = bytearray(raw[pos : pos + stride])
        pos += stride
        if filter_type == 1:
            for x in range(channels, stride):
                line[x] = (line[x] + line[x - channels]) & 255
        elif filter_type == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif filter_type == 3:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif filter_type == 4:
            for x in range(stride):
                left = line[x - channels] if x >= channels else 0
                up = prev[x]
                corner = prev[x - channels] if x >= channels else 0
                estimate = left + up - corner
                pa, pb, pc = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
                predictor = left if (pa <= pb and pa <= pc) else (up if pb <= pc else corner)
                line[x] = (line[x] + predictor) & 255
        out[y * stride : (y + 1) * stride] = line
        prev = line
    return width, height, channels, bytes(out)


def measure_png(path: Path) -> ImageStats:
    """Compute luminance statistics for a PNG file."""
    width, height, channels, pixels = read_png(path)
    total = width * height
    step = max(1, total // SAMPLE_PIXELS)
    luminance: list[int] = []
    for index in range(0, total, step):
        offset = index * channels
        luminance.append(
            (pixels[offset] * 299 + pixels[offset + 1] * 587 + pixels[offset + 2] * 114)
            // 1000
        )
    count = len(luminance)
    mean = sum(luminance) / count
    variance = sum((value - mean) ** 2 for value in luminance) / count
    dark = sum(1 for value in luminance if value < DARK_LEVEL) / count
    tones = len({luminance[i] for i in range(0, count, max(1, count // 3000))})
    return ImageStats(
        width=width,
        height=height,
        mean=mean,
        sd=variance**0.5,
        dark_pct=dark * 100,
        tones=tones,
    )
