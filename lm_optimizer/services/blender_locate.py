"""Locate the Blender executable for sandbox execution.

Blender is rarely on PATH on Windows: Store installs expose only the
``blender-launcher.exe`` alias and winget/MSI installs register an
InstallLocation in the uninstall registry. ``build_command_for`` uses this to
build a runnable command, and gets ``None`` when no Blender exists so the
runner records an honest "blender executable not found" instead of exit 1
"'blender' is not recognized".
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_INSTALL_ROOTS = (
    Path("C:/Program Files/Blender Foundation"),
    Path("C:/Program Files (x86)/Blender Foundation"),
    Path(os.environ.get("PROGRAMFILES", "")) / "Blender Foundation",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Blender Foundation",
    Path("C:/Program Files/Steam/steamapps/common/Blender"),
    Path("C:/Program Files (x86)/Steam/steamapps/common/Blender"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps",
)


def find_blender(explicit: str = "") -> str | None:
    """Return the first usable Blender executable, or ``None``.

    Order: explicit argument > ``BLENDER_PATH``/``BLENDER_EXE`` > PATH >
    known install roots > Windows uninstall registry.
    """
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

    for name in (
        "blender",
        "blender.exe",
        "blender-launcher",
        "blender-launcher.exe",
    ):
        found = shutil.which(name)
        if found:
            return found

    for root in _INSTALL_ROOTS:
        try:
            if not root.is_dir():
                continue
            for exe in sorted(root.rglob("blender.exe"), reverse=True):
                return str(exe)
            for exe in sorted(root.rglob("blender-launcher.exe"), reverse=True):
                return str(exe)
        except OSError:
            continue

    if sys.platform == "win32":
        return _from_registry()
    return None


def _from_registry() -> str | None:
    """Winget/MSI installs register an InstallLocation under Uninstall keys."""
    try:
        import winreg
    except ImportError:  # non-Windows
        return None
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
                                display = str(winreg.QueryValueEx(app, "DisplayName")[0])
                                if "blender" not in display.lower():
                                    continue
                                location = str(
                                    winreg.QueryValueEx(app, "InstallLocation")[0]
                                )
                        except OSError:
                            continue
                        if not location:
                            continue
                        for exe in ("blender.exe", "blender-launcher.exe"):
                            candidate = Path(location) / exe
                            if candidate.is_file():
                                return str(candidate)
            except OSError:
                continue
    return None
