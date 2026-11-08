"""Tests for sandbox artifact payload extraction (reasoning preamble removal)."""

from __future__ import annotations

from lm_optimizer.services.sandbox_runner import extract_payload


def test_js_strips_reasoning_preamble():
    text = (
        "We need answer user's request. Need produce final output ONLY single "
        "JavaScript module.\n\n"
        "export function createScene({ THREE, random }) {\n"
        "  return new THREE.Group();\n"
        "}\n"
    )
    out = extract_payload(text, "scene.js")
    assert out.startswith("export function createScene")


def test_js_strips_markdown_fences():
    text = "```js\nexport function createScene({ THREE }) {\n  return new THREE.Group();\n}\n```\n"
    out = extract_payload(text, "scene.js")
    assert "```" not in out
    assert out.startswith("export function createScene")


def test_html_starts_at_doctype():
    text = "Requirements:\n- self contained\n\n<!DOCTYPE html>\n<html><body></body></html>"
    out = extract_payload(text, "index.html")
    assert out.startswith("<!DOCTYPE html>")


def test_python_starts_at_import():
    text = "Let me plan the scene.\n\nimport bpy\n\nbpy.ops.mesh.primitive_cube_add()"
    out = extract_payload(text, "build_scene.py")
    assert out.startswith("import bpy")


def test_json_extracts_object():
    text = 'Here is the JSON:\n{"a": 1, "b": [2, 3]}\nDone.'
    out = extract_payload(text, "data.json")
    assert out.startswith("{") and out.endswith("}")


def test_text_artifact_unchanged():
    text = "Dear team,\n\nHere is the summary.\n"
    assert extract_payload(text, "email.txt") == text


def test_code_already_clean_is_unchanged():
    text = "export function createScene({ THREE }) {\n  return new THREE.Group();\n}\n"
    assert extract_payload(text, "scene.js") == text
