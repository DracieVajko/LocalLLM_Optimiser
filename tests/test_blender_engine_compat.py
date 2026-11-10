"""Blender engine aliases must not fail an otherwise valid scene."""

from __future__ import annotations

from pathlib import Path

from lm_optimizer.services.sandbox_runner import (
    _blender_exec_script,
    normalize_render_engine,
)


def test_eevee_alias_is_mapped_to_blender_5_name() -> None:
    script = "scene.render.engine = 'EEVEE'\n"

    assert normalize_render_engine(script) == "scene.render.engine = 'BLENDER_EEVEE'\n"


def test_blender_4_2_alias_is_mapped() -> None:
    script = 'scene.render.engine = "BLENDER_EEVEE_NEXT"\n'

    assert normalize_render_engine(script) == 'scene.render.engine = "BLENDER_EEVEE"\n'


def test_other_engines_and_variables_are_untouched() -> None:
    script = (
        "scene.render.engine = 'CYCLES'\n"
        "label = 'EEVEE'\n"
        "scene.render.engine = user_choice\n"
    )

    assert normalize_render_engine(script) == script


def test_exec_copy_is_written_only_when_needed(tmp_path: Path) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "build_scene.py").write_text(
        "import bpy\nscene.render.engine = 'EEVEE'\n", encoding="utf-8"
    )

    exec_script = _blender_exec_script(workdir)

    assert exec_script is not None
    assert exec_script.name == "build_scene.exec.py"
    assert "BLENDER_EEVEE" in exec_script.read_text(encoding="utf-8")
    # The raw artifact stays untouched for evidence.
    assert "'EEVEE'" in (workdir / "build_scene.py").read_text(encoding="utf-8")


def test_no_exec_copy_for_a_compatible_script(tmp_path: Path) -> None:
    workdir = tmp_path / "run"
    workdir.mkdir()
    (workdir / "build_scene.py").write_text(
        "import bpy\nscene.render.engine = 'BLENDER_EEVEE'\n", encoding="utf-8"
    )

    assert _blender_exec_script(workdir) is None
    assert not (workdir / "build_scene.exec.py").exists()
