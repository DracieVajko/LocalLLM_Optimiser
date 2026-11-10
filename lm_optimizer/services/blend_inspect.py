"""Inspect a saved .blend file without rendering it.

The city benchmark only produces ``scene.blend`` (no images). To score density
and structure we open the file in background Blender and print one JSON line
with object counts and the world-space bounding box.

The inspection script runs from a temporary directory, never from the sandbox
workdir, so it cannot pollute the text checks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

INSPECT_SCRIPT = r'''
import json
import sys

import bpy
from mathutils import Vector

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
cameras = [o for o in bpy.data.objects if o.type == "CAMERA"]
lights = [o for o in bpy.data.objects if o.type == "LIGHT"]
vertices = sum(len(o.data.vertices) for o in meshes if o.data)

mins = [1e18, 1e18, 1e18]
maxs = [-1e18, -1e18, -1e18]
for obj in meshes:
    for corner in obj.bound_box:
        world = obj.matrix_world @ Vector(corner)
        for axis in range(3):
            mins[axis] = min(mins[axis], world[axis])
            maxs[axis] = max(maxs[axis], world[axis])

heights = [float(o.dimensions.z) for o in meshes]
wide = max(mins[0], mins[1])
size = [maxs[0] - mins[0], maxs[1] - mins[1], maxs[2] - mins[2]] if meshes else [0, 0, 0]
payload = {
    "objects": len(bpy.data.objects),
    "meshes": len(meshes),
    "cameras": len(cameras),
    "lights": len(lights),
    "vertices": vertices,
    "size": [round(value, 2) for value in size],
    "height_max": round(max(heights), 2) if heights else 0.0,
    "height_min": round(min(heights), 2) if heights else 0.0,
    "tall_objects": sum(1 for h in heights if h >= 15.0),
}
print("BLEND_JSON " + json.dumps(payload))
'''


@dataclass
class BlendStats:
    objects: int = 0
    meshes: int = 0
    cameras: int = 0
    lights: int = 0
    vertices: int = 0
    size: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    height_max: float = 0.0
    height_min: float = 0.0
    tall_objects: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.meshes > 0

    def as_dict(self) -> dict[str, object]:
        return {
            "objects": self.objects,
            "meshes": self.meshes,
            "cameras": self.cameras,
            "lights": self.lights,
            "vertices": self.vertices,
            "size": self.size,
            "height_max": self.height_max,
            "height_min": self.height_min,
            "tall_objects": self.tall_objects,
            "error": self.error,
        }


def _blender_exe() -> str | None:
    return shutil.which("blender") or shutil.which("blender.exe")


def inspect_blend(blend_path: Path, *, timeout_s: float = 120.0) -> BlendStats:
    """Open *blend_path* in background Blender and return its statistics."""
    blender = _blender_exe()
    if blender is None:
        return BlendStats(error="blender not on PATH")
    if not blend_path.exists() or blend_path.stat().st_size == 0:
        return BlendStats(error="scene.blend missing")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        script = Path(tmp) / "inspect.py"
        script.write_text(INSPECT_SCRIPT, encoding="utf-8")
        env = dict(os.environ)
        try:
            proc = subprocess.run(
                [
                    blender,
                    "--background",
                    str(blend_path.resolve()),
                    "--python",
                    str(script),
                ],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return BlendStats(error=f"{type(exc).__name__}: {exc}"[:200])

    for line in (proc.stdout or "").splitlines():
        if line.startswith("BLEND_JSON "):
            try:
                payload = json.loads(line[len("BLEND_JSON ") :])
            except json.JSONDecodeError:
                continue
            return BlendStats(**payload)
    detail = (proc.stderr or proc.stdout or "no output").strip().splitlines()
    return BlendStats(error=(detail[-1] if detail else "inspection produced no data")[:200])
