"""Artifact previews must serve both sandbox and bakeoff workdirs, safely."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lm_optimizer.api.main import app


def test_serves_a_sandbox_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "results" / "sandbox" / "company_website" / "run1" / "index.html"
    target.parent.mkdir(parents=True)
    target.write_text("<h1>sandbox</h1>", encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files", params={"file_path": "company_website/run1/index.html"}
    )
    assert response.status_code == 200, response.text
    assert "sandbox" in response.text


def test_serves_a_bakeoff_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = (
        tmp_path / "results" / "bakeoff" / "model" / "company_website" / "stamp" / "index.html"
    )
    target.parent.mkdir(parents=True)
    target.write_text("<h1>bakeoff</h1>", encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files",
        params={"file_path": "model/company_website/stamp/index.html"},
    )
    assert response.status_code == 200, response.text
    assert "bakeoff" in response.text


def test_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results" / "sandbox").mkdir(parents=True)
    (tmp_path / "results" / "secret.txt").write_text("secret", encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files", params={"file_path": "../secret.txt"}
    )
    assert response.status_code == 403


def test_json_artifact_is_served_as_formatted_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "results" / "sandbox" / "task" / "run" / "stats.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"meshes": 64, "ok": true}', encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files", params={"file_path": "task/run/stats.json"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert '<div class="bar">' in response.text
    assert "&quot;meshes&quot;" in response.text  # escaped, safe to embed
    assert "\n  " in response.text  # pretty-printed JSON, not one long line


def test_text_artifact_gets_the_viewer_chrome(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "results" / "sandbox" / "task" / "run" / "build_scene.py"
    target.parent.mkdir(parents=True)
    target.write_text("import bpy\nprint('hi')", encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files", params={"file_path": "task/run/build_scene.py"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert "build_scene.py" in response.text
    assert "<pre>" in response.text
    assert "import bpy" in response.text


def test_invalid_json_is_labeled_not_prettified(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "results" / "sandbox" / "task" / "run" / "broken.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json", encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files", params={"file_path": "task/run/broken.json"}
    )
    assert response.status_code == 200
    assert "invalid JSON" in response.text


def test_html_artifact_stays_raw(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "results" / "sandbox" / "task" / "run" / "index.html"
    target.parent.mkdir(parents=True)
    target.write_text("<h1>scene</h1>", encoding="utf-8")
    response = TestClient(app).get(
        "/api/sandbox/files", params={"file_path": "task/run/index.html"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<div class="bar">' not in response.text  # the browser renders it
