"""Chat readiness retry: LM Studio may report load before the chat slot is ready."""

import asyncio
from unittest.mock import AsyncMock

import httpx

from lm_optimizer.services.host import lm_studio
from lm_optimizer.services.host.lm_studio import LMStudioClient


def _unloaded_error() -> httpx.HTTPStatusError:
    response = httpx.Response(
        500, json={"error": {"message": "Model is unloaded."}}
    )
    return httpx.HTTPStatusError(
        "500", request=httpx.Request("POST", "http://test/api/v1/chat"), response=response
    )


def test_unloaded_error_detector():
    assert lm_studio._is_model_unloaded_error(_unloaded_error())

    other = httpx.Response(500, json={"error": {"message": "boom"}})
    exc = httpx.HTTPStatusError(
        "500", request=httpx.Request("POST", "http://test"), response=other
    )
    assert not lm_studio._is_model_unloaded_error(exc)


async def test_chat_retries_until_slot_is_ready(monkeypatch):
    client = LMStudioClient(base_url="http://test")
    ok = httpx.Response(
        200,
        json={"output": [{"type": "message", "content": "hi"}], "stats": {}},
    )
    client._request_with_retry = AsyncMock(
        side_effect=[_unloaded_error(), _unloaded_error(), ok]
    )

    async def _no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    result = await client.chat_completion("m", "hello", max_output_tokens=8)

    assert result["choices"][0]["message"]["content"] == "hi"
    assert client._request_with_retry.await_count == 3
