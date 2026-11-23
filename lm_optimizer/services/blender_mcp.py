"""Blender MCP auto-detection and seamless setup.

The goal: a user should not have to install MCP-Link by hand, edit JSON
config files, or guess ports. This module detects Blender, the MCP-Link
server and the LM Studio API, then produces (and optionally writes) the
MCP client configuration that connects them.

Everything here is best-effort and offline: if a dependency is missing the
result explains exactly which step failed and how to fix it.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lm_optimizer.services.blender_locate import find_blender


@dataclass
class BlenderMcpStatus:
    blender_exe: str | None = None
    blender_version: str | None = None
    mcp_server_reachable: bool = False
    mcp_server_url: str | None = None
    mcp_link_addon_present: bool | None = None
    lm_studio_reachable: bool = False
    lm_studio_url: str = "http://127.0.0.1:1234"
    ready: bool = False
    steps: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Candidate ports for the MCP-Link server (aurafriday). We probe all of them
# and accept the first that answers like an MCP server, instead of assuming
# Prism's port (8101) is MCP-Link (it is not).
_MCP_CANDIDATE_PORTS = (8765, 9876, 9800, 8000, 9000, 7860)


def _probe(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def _find_mcp_server() -> tuple[str | None, bool]:
    """Return (url, reachable) for the first MCP-Link-like server."""
    for port in _MCP_CANDIDATE_PORTS:
        url = f"http://127.0.0.1:{port}"
        if _probe(url + "/health") or _probe(url + "/mcp") or _probe(url + "/sse"):
            return url, True
    return None, False


def _blender_version(exe: str | None) -> str | None:
    if not exe:
        return None
    try:
        out = subprocess.check_output(
            [exe, "--version"], text=True, timeout=10, stderr=subprocess.STDOUT
        )
        first = out.splitlines()[0] if out else ""
        return first.strip() or None
    except Exception:
        return None


def detect() -> BlenderMcpStatus:
    st = BlenderMcpStatus()
    steps: list[dict[str, str]] = []

    # 1. Blender
    exe = find_blender()
    st.blender_exe = exe
    st.blender_version = _blender_version(exe)
    if exe:
        steps.append({"step": "blender", "status": "ok", "detail": exe})
    else:
        steps.append({"step": "blender", "status": "missing",
                      "detail": "Install Blender 4.2+ from blender.org"})

    # 2. MCP-Link server (real probe, not Prism)
    url, mcp_ok = _find_mcp_server()
    st.mcp_server_url = url
    st.mcp_server_reachable = mcp_ok
    if mcp_ok:
        steps.append({"step": "mcp_server", "status": "ok", "detail": url})
    else:
        steps.append({"step": "mcp_server", "status": "missing",
                      "detail": "Start MCP-Link server (aurafriday.com/downloads)"})

    # 3. LM Studio
    lm_ok = _probe(st.lm_studio_url + "/v1/models")
    st.lm_studio_reachable = lm_ok
    if lm_ok:
        steps.append({"step": "lm_studio", "status": "ok", "detail": st.lm_studio_url})
    else:
        steps.append({"step": "lm_studio", "status": "missing",
                      "detail": "Start LM Studio and enable the local server"})

    st.steps = steps
    st.ready = bool(exe and mcp_ok and lm_ok)
    return st


def build_mcp_config(st: BlenderMcpStatus) -> dict[str, Any]:
    """Return the LM Studio MCP client config snippet for Blender.

    Written to be copy-pasted into LM Studio's MCP servers list; no editing
    required beyond pasting.
    """
    return {
        "mcpServers": {
            "blender": {
                "url": st.mcp_server_url,
                "transport": "sse",
                "autoConnect": True,
                "description": "Blender Python API (bpy) via MCP-Link",
            }
        }
    }


def _mcp_config_path() -> Path:
    """LM Studio's MCP client config location."""
    return Path.home() / ".lmstudio" / "mcp.json"


def apply_config(st: BlenderMcpStatus | None = None) -> dict[str, Any]:
    """Write the Blender MCP config into LM Studio's mcp.json (seamless).

    Merges with any existing config instead of overwriting it.
    """
    status = st or detect()
    config = build_mcp_config(status)
    path = _mcp_config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        servers = existing.setdefault("mcpServers", {})
        servers.update(config["mcpServers"])
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return {"success": True, "path": str(path), "servers": list(servers.keys())}
    except Exception as e:
        return {"success": False, "error": str(e), "path": str(path)}


def seamless_setup(apply: bool = False) -> dict[str, Any]:
    """One call: detect everything and return config + instructions.

    If ``apply`` is True, the MCP config is written to LM Studio's mcp.json
    automatically (seamless setup).
    """
    st = detect()
    config = build_mcp_config(st)
    instructions = []
    if not st.blender_exe:
        instructions.append("Install Blender 4.2+ from https://www.blender.org/download/")
    if not st.mcp_server_reachable:
        instructions.append("Download and start the MCP-Link server from https://aurafriday.com/downloads/")
        instructions.append("In Blender: Edit -> Preferences -> Get Extensions -> search 'MCP-Link' -> Install")
    if not st.lm_studio_reachable:
        instructions.append("Start LM Studio and enable the local server (port 1234)")
    if st.ready:
        instructions.append("MCP config written to ~/.lmstudio/mcp.json — restart LM Studio to pick it up.")
    result = {
        "status": st.as_dict(),
        "config": config,
        "instructions": instructions,
        "ready": st.ready,
    }
    if apply:
        result["apply"] = apply_config(st)
    return result
