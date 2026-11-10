"""The produced .blend must be collected somewhere a human can open it."""

from __future__ import annotations

from pathlib import Path

from lm_optimizer.services.sandbox_runner import collect_blend, looks_like_blend


def _write_blend(path: Path, payload: bytes = b"BLENDER-v300" + b"\x00" * 2048) -> None:
    path.write_bytes(payload)


def test_collect_blend_copies_valid_file(tmp_path: Path) -> None:
    workdir = tmp_path / "run" / "20260101_120000"
    workdir.mkdir(parents=True)
    _write_blend(workdir / "scene.blend")

    collected = collect_blend(workdir, "prism-ml/bonsai-27b", "blender_city", base=tmp_path / "out")

    assert collected
    target = Path(collected)
    assert target.exists()
    assert target.parent == tmp_path / "out" / "prism_ml_bonsai_27b" / "blender_city"
    assert target.name == "20260101_120000.blend"
    assert looks_like_blend(target.read_bytes())


def test_collect_blend_ignores_missing_file(tmp_path: Path) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    assert collect_blend(workdir, "m", "blender_city", base=tmp_path / "out") == ""


def test_collect_blend_rejects_non_blend_bytes(tmp_path: Path) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "scene.blend").write_bytes(b"<html>not a blend</html>" * 100)

    assert collect_blend(workdir, "m", "blender_city", base=tmp_path / "out") == ""
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").rglob("*.blend"))


def test_result_serializes_blend_file() -> None:
    from lm_optimizer.services.sandbox_lab import SandboxResult

    payload = SandboxResult(task_id="blender_city", blend_file="C:/x/scene.blend").as_dict()

    assert payload["blend_file"] == "C:/x/scene.blend"
