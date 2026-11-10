"""Reasoning level pass-through tests for the sandbox chat helper."""

from __future__ import annotations

import pytest

from lm_optimizer.cli.lab import _chat


class FakeClient:
    def __init__(self):
        self.kwargs = None

    async def chat_completion(self, **kwargs):
        self.kwargs = kwargs
        return {"choices": [{"message": {"content": "ok"}}]}


@pytest.mark.asyncio
async def test_chat_passes_arbitrary_reasoning_level():
    client = FakeClient()
    result = await _chat(client, "m", "p", 16, reasoning="xhigh")
    assert result == "ok"
    assert client.kwargs["reasoning"] == "xhigh"


@pytest.mark.asyncio
async def test_chat_default_reasoning_omits_key():
    client = FakeClient()
    await _chat(client, "m", "p", 16, reasoning="default")
    assert client.kwargs["reasoning"] is None


@pytest.mark.asyncio
async def test_chat_low_medium_high_are_forwarded():
    for level in ("low", "medium", "high", "on", "off"):
        client = FakeClient()
        await _chat(client, "m", "p", 16, reasoning=level)
        assert client.kwargs["reasoning"] == level
