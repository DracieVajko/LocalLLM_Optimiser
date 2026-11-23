"""Blender MCP client — direct TCP connection to Blender's blender-mcp addon.

The Blender add-on (blender_mcp.py, ahujasid's) listens on TCP port 9876 and
accepts JSON commands. No separate MCP-Link server is needed — this module
talks to Blender directly.

Commands: execute_code, get_scene_info, get_object_info,
get_viewport_screenshot, ping, and PolyHaven/Sketchfab asset helpers.
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import asdict, dataclass, field
from typing import Any

BLENDER_HOST = "127.0.0.1"
BLENDER_PORT = 9876
TIMEOUT = 30.0


@dataclass
class BlenderStatus:
    reachable: bool = False
    scene_info: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _send(command: dict, timeout: float = TIMEOUT) -> dict:
    """Send a JSON command to Blender and return the response."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((BLENDER_HOST, BLENDER_PORT))
        s.sendall((json.dumps(command) + "\n").encode("utf-8"))
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
        if not buf:
            return {"status": "error", "result": {"error": "no response"}}
        try:
            return json.loads(buf.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"status": "error", "result": {"error": f"incomplete response: {buf[:200]!r}"}}
    except Exception as e:
        return {"status": "error", "result": {"error": str(e)}}
    finally:
        try:
            s.close()
        except Exception:
            pass


def ping() -> bool:
    r = _send({"type": "ping", "params": {}}, timeout=5.0)
    return r.get("status") == "success"


def get_scene_info() -> dict[str, Any]:
    return _send({"type": "get_scene_info", "params": {}})


def execute_code(code: str, timeout: float = 60.0) -> dict[str, Any]:
    return _send({"type": "execute_code", "params": {"code": code}}, timeout=timeout)


def get_object_info(name: str) -> dict[str, Any]:
    return _send({"type": "get_object_info", "params": {"object_name": name}})


def get_viewport_screenshot(max_size: int = 800) -> dict[str, Any]:
    return _send({"type": "get_viewport_screenshot", "params": {"max_size": max_size}}, timeout=30.0)


def detect_tcp() -> BlenderStatus:
    """Check if Blender with the MCP addon is reachable."""
    st = BlenderStatus()
    try:
        r = _send({"type": "ping", "params": {}}, timeout=5.0)
        if r.get("status") == "success":
            st.reachable = True
            st.scene_info = get_scene_info().get("result")
        else:
            st.error = r.get("result", {}).get("error", "unknown")
    except Exception as e:
        st.error = str(e)
    return st


def create_primitive(primitive: str, **kwargs) -> dict[str, Any]:
    """Create a primitive in Blender (cube, sphere, cylinder, etc.)."""
    code = f"import bpy\nbpy.ops.mesh.primitive_{primitive}_add(**{kwargs!r})\nprint(bpy.context.active_object.name)"
    return execute_code(code)


def render_scene(filepath: str, engine: str = "CYCLES", samples: int = 16) -> dict[str, Any]:
    """Render the current scene to a file."""
    code = f"""
import bpy
scene = bpy.context.scene
scene.render.engine = '{engine}'
scene.render.filepath = r'{filepath}'
if '{engine}' == 'CYCLES':
    scene.cycles.samples = {samples}
bpy.ops.render.render(write_still=True)
print('RENDER OK', scene.render.filepath)
"""
    return execute_code(code, timeout=300.0)


# --- Seamless setup layer (direct TCP, no separate MCP server needed) ---------

from dataclasses import dataclass as _dc, field as _field
from pathlib import Path as _Path
from typing import Any as _Any


@_dc
class BlenderMcpStatus:
    blender_exe: str | None = None
    blender_version: str | None = None
    mcp_server_reachable: bool = False
    mcp_server_url: str = "tcp://127.0.0.1:9876"
    lm_studio_reachable: bool = False
    lm_studio_url: str = "http://127.0.0.1:1234"
    ready: bool = False
    steps: list[dict[str, str]] = _field(default_factory=list)

    def as_dict(self) -> dict[str, _Any]:
        from dataclasses import asdict
        return asdict(self)


def _blender_exe() -> str | None:
    try:
        from lm_optimizer.services.blender_locate import find_blender
        return find_blender()
    except Exception:
        return None


def _addon_installed() -> bool:
    """Check if the blender-mcp addon is installed in Blender."""
    import os
    from pathlib import Path
    # Check common addon locations
    roots = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            roots.append(Path(appdata) / "Blender Foundation")
    roots.append(Path.home() / ".config" / "blender")
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("blender_mcp.py"):
                if p.is_file():
                    return True
        except OSError:
            continue
    return False


def _auto_install_addon() -> dict:
    """Attempt to auto-install the blender-mcp addon via uvx."""
    import shutil
    uvx = shutil.which("uvx")
    if not uvx:
        return {"success": False, "error": "uvx not found (install uv first)"}
    try:
        import subprocess
        result = subprocess.run(
            [uvx, "mcp-for-blender", "install-addon"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip()}
        return {"success": False, "error": result.stderr.strip() or result.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _blender_version(exe: str | None) -> str | None:
    if not exe:
        return None
    try:
        import subprocess
        out = subprocess.check_output([exe, "--version"], text=True, timeout=10, stderr=subprocess.STDOUT)
        return out.splitlines()[0].strip() if out else None
    except Exception:
        return None


def _probe(url: str, timeout: float = 3.0) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def detect() -> BlenderMcpStatus:
    st = BlenderMcpStatus()
    steps = []
    exe = _blender_exe()
    st.blender_exe = exe
    st.blender_version = _blender_version(exe)
    if exe:
        steps.append({"step": "blender", "status": "ok", "detail": exe})
    else:
        steps.append({"step": "blender", "status": "missing",
                      "detail": "Install Blender 4.2+ from blender.org"})

    if not _addon_installed() and exe:
        install_result = _auto_install_addon()
        if install_result["success"]:
            steps.append({"step": "blender_mcp_install", "status": "ok", "detail": "addon installed automatically"})
        else:
            steps.append({"step": "blender_mcp_install", "status": "missing",
                          "detail": f"Could not auto-install: {install_result['error']}"})

    tcp_ok = detect_tcp()
    st.mcp_server_reachable = tcp_ok
    if tcp_ok:
        info = get_scene_info().get("result")
        detail = f"TCP 127.0.0.1:9876 ({info.get('object_count', '?')} objects)" if info else "TCP 127.0.0.1:9876"
        steps.append({"step": "blender_mcp", "status": "ok", "detail": detail})
    else:
        steps.append({"step": "blender_mcp", "status": "missing",
                      "detail": "Start Blender (the addon auto-starts its server on port 9876)"})

    lm_ok = _probe("http://127.0.0.1:1234/v1/models")
    st.lm_studio_reachable = lm_ok
    if lm_ok:
        steps.append({"step": "lm_studio", "status": "ok", "detail": "http://127.0.0.1:1234"})
    else:
        steps.append({"step": "lm_studio", "status": "missing", "detail": "Start LM Studio and enable the local server"})

    st.steps = steps
    st.ready = bool(exe and tcp_ok and lm_ok)
    return st


def build_mcp_config(st: BlenderMcpStatus) -> dict:
    return {"mcpServers": {}}


def apply_config(st=None) -> dict:
    return {"success": True, "note": "Direct TCP — no config file needed. Just run Blender with the MCP add-on enabled."}


def seamless_setup(apply: bool = False) -> dict:
    st = detect()
    instructions = []
    if not st.blender_exe:
        instructions.append("Install Blender 4.2+ from https://www.blender.org/download/")
    if not st.mcp_server_reachable:
        instructions.append("Start Blender (the addon auto-starts its server on port 9876)")
        instructions.append("If the addon is missing: uvx mcp-for-blender install-addon")
    if not st.lm_studio_reachable:
        instructions.append("Start LM Studio and enable the local server (port 1234)")
    if st.ready:
        instructions.append("All set — Blender is reachable via direct TCP. No MCP config file needed.")
    return {
        "status": st.as_dict(),
        "config": build_mcp_config(st),
        "instructions": instructions,
        "ready": st.ready,
        "apply": apply_config(st) if apply else None,
    }
