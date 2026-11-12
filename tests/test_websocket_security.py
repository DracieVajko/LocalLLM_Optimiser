"""The WebSocket channel must follow the same remote-token policy as HTTP.

The REST routes are protected by the ``X-API-Token`` middleware for
non-loopback clients. The WebSocket channel streams run state and accepts a
cancel message, so it needs the same check - otherwise a remote client could
read the state of a run and stop it without a token.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lm_optimizer.api.main import app
from lm_optimizer.api.websocket import _remote_client_denied


def _socket(host: str, *, header_token: str = "", query_token: str = ""):
    return SimpleNamespace(
        client=SimpleNamespace(host=host),
        headers={"x-api-token": header_token} if header_token else {},
        query_params={"token": query_token} if query_token else {},
    )


def test_no_token_configured_means_no_restriction(monkeypatch):
    monkeypatch.delenv("LM_OPTIMIZER_API_TOKEN", raising=False)
    assert _remote_client_denied(_socket("10.0.0.5")) is False


def test_loopback_clients_are_never_blocked(monkeypatch):
    monkeypatch.setenv("LM_OPTIMIZER_API_TOKEN", "secret")
    assert _remote_client_denied(_socket("127.0.0.1")) is False
    assert _remote_client_denied(_socket("::1")) is False


def test_remote_client_without_the_token_is_denied(monkeypatch):
    monkeypatch.setenv("LM_OPTIMIZER_API_TOKEN", "secret")
    assert _remote_client_denied(_socket("10.0.0.5")) is True


def test_remote_client_with_the_token_is_allowed(monkeypatch):
    monkeypatch.setenv("LM_OPTIMIZER_API_TOKEN", "secret")
    assert _remote_client_denied(_socket("10.0.0.5", header_token="secret")) is False
    assert _remote_client_denied(_socket("10.0.0.5", query_token="secret")) is False


def test_websocket_from_a_remote_client_without_the_token_is_rejected(monkeypatch):
    monkeypatch.setenv("LM_OPTIMIZER_API_TOKEN", "secret")
    run_id = uuid4()
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/optimize/{run_id}"):
                pass
