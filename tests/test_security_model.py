"""Remote-mode token guard and host-exposure check."""

import pytest
from fastapi.testclient import TestClient

from lm_optimizer import web_main
from lm_optimizer.api.main import app
from lm_optimizer.config import config


def test_non_loopback_without_opt_in_is_refused(monkeypatch):
    monkeypatch.setattr(config.web_ui, "host", "0.0.0.0")
    monkeypatch.delenv("LM_OPTIMIZER_ALLOW_REMOTE", raising=False)

    with pytest.raises(SystemExit):
        web_main._check_host_exposure()


def test_remote_opt_in_without_token_is_refused(monkeypatch):
    monkeypatch.setattr(config.web_ui, "host", "0.0.0.0")
    monkeypatch.setenv("LM_OPTIMIZER_ALLOW_REMOTE", "1")
    monkeypatch.delenv("LM_OPTIMIZER_API_TOKEN", raising=False)

    with pytest.raises(SystemExit):
        web_main._check_host_exposure()


def test_remote_opt_in_with_token_is_allowed(monkeypatch):
    monkeypatch.setattr(config.web_ui, "host", "0.0.0.0")
    monkeypatch.setenv("LM_OPTIMIZER_ALLOW_REMOTE", "1")
    monkeypatch.setenv("LM_OPTIMIZER_API_TOKEN", "secret")

    web_main._check_host_exposure()  # must not raise


def test_mutating_request_requires_token(monkeypatch):
    monkeypatch.setenv("LM_OPTIMIZER_API_TOKEN", "secret")

    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.post("/api/optimize", json={"model_id": "m"})
        assert missing.status_code == 401

        present = client.post(
            "/api/optimize",
            json={"model_id": "m"},
            headers={"X-API-Token": "secret"},
        )
        assert present.status_code != 401
