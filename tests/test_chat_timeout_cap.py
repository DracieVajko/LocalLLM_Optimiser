"""Chat generation must not block a run for hours on a stalled engine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx

from lm_optimizer.config import config
from lm_optimizer.services.host.lm_studio import CHAT_TIMEOUT_FLOOR_S, LMStudioClient


def _ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={"output": [{"type": "message", "content": "hi"}], "stats": {}},
    )


async def test_small_budget_uses_floor(monkeypatch):
    monkeypatch.setattr(config.lm_studio, "chat_timeout_max", 3600.0)
    client = LMStudioClient(base_url="http://test")
    client._request_with_retry = AsyncMock(return_value=_ok())

    await client.chat_completion("m", "hello", max_output_tokens=64)

    assert client._request_with_retry.await_args.kwargs["timeout_s"] == CHAT_TIMEOUT_FLOOR_S


async def test_large_budget_is_capped(monkeypatch):
    monkeypatch.setattr(config.lm_studio, "chat_timeout_max", 900.0)
    client = LMStudioClient(base_url="http://test")
    client._request_with_retry = AsyncMock(return_value=_ok())

    await client.chat_completion("m", "hello", max_output_tokens=8192)

    assert client._request_with_retry.await_args.kwargs["timeout_s"] == 900.0


async def test_budget_between_floor_and_cap_is_used_as_is(monkeypatch):
    monkeypatch.setattr(config.lm_studio, "chat_timeout_max", 3600.0)
    client = LMStudioClient(base_url="http://test")
    client._request_with_retry = AsyncMock(return_value=_ok())

    await client.chat_completion("m", "hello", max_output_tokens=1200)

    assert client._request_with_retry.await_args.kwargs["timeout_s"] == 1200.0
