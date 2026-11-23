"""GitHub auto-update for LM Studio Optimizer.

Checks the GitHub repository for a newer release/tag and optionally applies
it (download ZIP -> extract -> replace files, with a backup of the old tree).

Everything is best-effort and offline-safe: if GitHub is unreachable the
result explains the failure and returns the current version without crashing.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lm_optimizer import __version__

GITHUB_REPO = "DracieVajko/LocalLLM_Optimiser"
GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"


@dataclass
class UpdateInfo:
    current: str
    latest: str | None = None
    update_available: bool = False
    source: str = ""  # "release" | "tag" | "commit"
    url: str = ""
    download_url: str = ""
    notes: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of ints."""
    v = (v or "").strip().lstrip("v").lstrip("V")
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _http_get_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "lm-studio-optimizer-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def check_update(timeout: float = 10.0) -> UpdateInfo:
    """Check GitHub for a newer version. Never raises."""
    info = UpdateInfo(current=__version__)
    try:
        # Prefer the latest release.
        try:
            rel = _http_get_json(f"{GITHUB_API}/repos/{GITHUB_REPO}/releases/latest", timeout)
            tag = rel.get("tag_name") or rel.get("name") or ""
            if tag:
                info.latest = tag.lstrip("v").lstrip("V")
                info.source = "release"
                info.url = rel.get("html_url", "")
                info.download_url = rel.get("zipball_url", "")
                info.notes = (rel.get("body") or "")[:500]
        except Exception:
            # Fall back to the latest tag.
            tags = _http_get_json(f"{GITHUB_API}/repos/{GITHUB_REPO}/tags", timeout)
            if isinstance(tags, list) and tags:
                t = tags[0]
                tag = t.get("name", "")
                info.latest = tag.lstrip("v").lstrip("V")
                info.source = "tag"
                info.url = t.get("commit", {}).get("url", "")
                info.download_url = t.get("zipball_url", "")
    except Exception as e:
        info.error = f"GitHub unreachable: {e}"
        return info

    if info.latest and _parse_version(info.latest) > _parse_version(info.current):
        info.update_available = True
    return info


def apply_update(download_url: str | None = None, target_dir: str | None = None) -> dict[str, Any]:
    """Download and apply an update. Returns a result dict, never raises."""
    info = check_update()
    if not info.update_available and not download_url:
        return {"success": False, "reason": "no update available", "current": info.current,
                "latest": info.latest}
    url = download_url or info.download_url
    if not url:
        return {"success": False, "reason": "no download URL", "current": info.current}
    if not target_dir:
        return {
            "success": False,
            "reason": "target_dir is required (refusing to write into the process cwd)",
            "current": info.current,
        }
    target = Path(target_dir).resolve()
    if not (target / "lm_optimizer").is_dir():
        return {
            "success": False,
            "reason": f"{target} does not look like the project root (no lm_optimizer/)",
            "current": info.current,
        }
    backup = None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "update.zip"
            urllib.request.urlretrieve(url, zip_path)
            extract = Path(tmp) / "extracted"
            import zipfile
            with zipfile.ZipFile(zip_path) as zf:
                # Validate before extracting: refuse absolute paths, parent
                # traversal and symlinks (zip-slip protection).
                for member in zf.infolist():
                    name = member.filename.replace("\\", "/")
                    if name.startswith("/") or ".." in name.split("/"):
                        return {"success": False, "reason": f"unsafe archive member: {name}"}
                    mode = (member.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        return {"success": False, "reason": f"symlink in archive: {name}"}
                zf.extractall(extract)
            # The archive has a single top-level directory.
            tops = [p for p in extract.iterdir() if p.is_dir()]
            if not tops:
                return {"success": False, "reason": "empty archive"}
            src = tops[0]
            if not (src / "lm_optimizer").is_dir() or not (src / "pyproject.toml").exists():
                return {"success": False, "reason": "archive is not a project snapshot"}
            # Backup the current tree (excluding data/results/.venv).
            backup = target / f".update-backup-{info.latest}"
            backup.mkdir(exist_ok=True)
            for name in ("lm_optimizer", "tests", "docs", "tools", "benchmarks"):
                src_p = target / name
                if src_p.exists():
                    dst_p = backup / name
                    if dst_p.exists():
                        shutil.rmtree(dst_p)
                    shutil.copytree(src_p, dst_p, dirs_exist_ok=True)
            # Copy updated files over.
            for name in os.listdir(src):
                src_p = src / name
                dst_p = target / name
                if src_p.is_dir():
                    shutil.copytree(src_p, dst_p, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_p, dst_p)
        return {"success": True, "from": info.current, "to": info.latest,
                "backup": str(backup) if backup else None}
    except Exception as e:
        return {"success": False, "reason": str(e), "current": info.current}


def main_check() -> None:
    info = check_update()
    print(f"Current version: {info.current}")
    if info.error:
        print(f"Error: {info.error}")
        return
    print(f"Latest version:  {info.latest or 'unknown'} ({info.source})")
    if info.update_available:
        print(f"UPDATE AVAILABLE: {info.current} -> {info.latest}")
        print(f"URL: {info.url}")
        if info.notes:
            print(f"Notes: {info.notes[:300]}")
    else:
        print("You are up to date.")
