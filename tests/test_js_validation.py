"""JavaScript validation must never report success for unvalidated code.

``node --check`` is not consistent across Node versions: Node 20 accepts a
``.js`` file that contains module syntax even when the body is broken (the
module-detection retry hides the syntax error), while Node 26 rejects it.
The validator therefore parses module sources as modules and reports a
distinct state whenever it could not validate at all - a silent success is
never acceptable.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from lm_optimizer.services import web_validator as wv

BROKEN_MODULE = (
    "export function createScene({ THREE, random }) {\n"
    "  const a = random(); root.add(terrain), trees);\n"
    "  return root;\n"
    "}\n"
)
VALID_MODULE = "export function createScene() { return 1; }\n"
BROKEN_SCRIPT = "function f() { return; ]\n"

needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="the node runtime is not installed"
)


@needs_node
def test_valid_javascript_is_validated():
    result = wv.validate_javascript([VALID_MODULE])
    assert result.state == wv.JS_VALID
    assert result.passed
    assert result.errors == []


@needs_node
def test_broken_module_is_detected():
    """The CI case: Node 20 hides this syntax error for a .js file."""
    result = wv.validate_javascript([BROKEN_MODULE])
    assert result.state == wv.JS_INVALID
    assert not result.passed
    assert result.errors
    assert "SyntaxError" in result.errors[0]


@needs_node
def test_broken_script_is_detected():
    result = wv.validate_javascript([BROKEN_SCRIPT])
    assert result.state == wv.JS_INVALID
    assert not result.passed


def test_empty_source_is_reported_as_nothing_to_validate():
    result = wv.validate_javascript(["   \n"])
    assert result.state == wv.JS_EMPTY
    assert result.errors == []
    assert "javascript" in result.detail.lower()


def test_missing_runtime_is_not_a_success(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = wv.validate_javascript(["const a = 1;"])
    assert result.state == wv.JS_UNAVAILABLE
    assert not result.passed
    assert "node" in result.detail.lower()


def test_validator_that_cannot_start_is_not_a_success():
    result = wv.validate_javascript(["const a = 1;"], node_path="/nonexistent/node")
    assert result.state == wv.JS_UNAVAILABLE
    assert not result.passed


def test_timeout_is_not_a_success(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="node", timeout=kwargs.get("timeout", 20))

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = wv.validate_javascript(["const a = 1;"], node_path="node")
    assert result.state == wv.JS_UNAVAILABLE
    assert not result.passed
    assert "timed out" in result.detail.lower()


def test_unexpected_output_still_validates(monkeypatch):
    """Only the exit code decides - node may print warnings."""

    class FakeProc:
        returncode = 0
        stdout = "ExperimentalWarning: something happened\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeProc())
    result = wv.validate_javascript(["const a = 1;"], node_path="node")
    assert result.state == wv.JS_VALID
    assert result.passed


@needs_node
def test_a_module_script_is_parsed_as_a_module():
    """A module script may use top-level await - that is valid in a browser."""
    source = "const value = await Promise.resolve(1);\nexport default value;\n"
    result = wv.validate_javascript([source], module=True)
    assert result.state == wv.JS_VALID
    assert result.passed


@needs_node
def test_a_classic_script_may_not_use_top_level_await():
    source = "const value = await Promise.resolve(1);\n"
    result = wv.validate_javascript([source])
    assert result.state == wv.JS_INVALID
    assert not result.passed


def test_sandbox_js_check_fails_when_the_validator_is_unavailable(monkeypatch):
    """An unvalidated script must not pass the critical js_parses check."""
    from lm_optimizer.services import sandbox_lab

    monkeypatch.setattr(shutil, "which", lambda name: None)
    task = sandbox_lab.SANDBOX_TASKS["creative_3d_voxel_island"]
    score, failing, critical = sandbox_lab.score_attempt(
        task, {"scene.js": VALID_MODULE}
    )
    assert score == 0.0
    assert any("js_parses" in name for name in critical)
    assert any("not validated" in name for name in critical)


def test_sandbox_js_check_reports_the_syntax_error(monkeypatch):
    from lm_optimizer.services import sandbox_lab

    monkeypatch.setattr(shutil, "which", lambda name: "node")
    task = sandbox_lab.SANDBOX_TASKS["creative_3d_voxel_island"]
    score, failing, critical = sandbox_lab.score_attempt(
        task, {"scene.js": BROKEN_MODULE}
    )
    assert score == 0.0
    assert any("js_parses" in name for name in critical)
