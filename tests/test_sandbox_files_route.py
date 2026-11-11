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
