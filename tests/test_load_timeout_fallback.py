"""Load-response timeout fallback: accept a model the server did load."""

import asyncio

import pytest

from lm_optimizer.domain.models import LoadConfiguration
from lm_optimizer.services import lm_studio
from lm_optimizer.services.lm_studio import LMStudioClient


class _SlowClient(LMStudioClient):
    def __init__(self, instance: dict | None):
        super().__init__("http://127.0.0.1:1234")
        self.instance = instance
        self.polls = 0

    async def _request_with_retry(self, *args, **kwargs):
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    async def _wait_for_loaded_instance(self, model_id: str):
        self.polls += 1
        return self.instance


def test_load_accepts_loaded_instance_when_response_is_lost(monkeypatch):
    monkeypatch.setattr(lm_studio, "LOAD_RESPONSE_TIMEOUT_S", 0.01)
    client = _SlowClient(
        {
            "model": "m",
            "instance_id": "inst-1",
            "config": {"context_length": 4096, "flash_attention": True},
        }
    )

    result = asyncio.run(
        client.load_model("m", LoadConfiguration(context_length=4096))
    )

    assert result.success is True
    assert result.identifier == "inst-1"
    assert result.loaded_config is not None
    assert result.loaded_config.context_length == 4096
    assert client.polls == 1


def test_load_fails_when_no_instance_appears(monkeypatch):
    monkeypatch.setattr(lm_studio, "LOAD_RESPONSE_TIMEOUT_S", 0.01)
    client = _SlowClient(None)

    result = asyncio.run(client.load_model("m", LoadConfiguration(context_length=2048)))

    assert result.success is False
    assert "timed out" in (result.error or "").lower()
    assert client.polls == 1


def test_success_from_instance_records_echo_mismatch():
    client = LMStudioClient("http://127.0.0.1:1234")
    result = client._success_from_loaded_instance(
        "m",
        {"model": "m", "instance_id": "i", "config": {"context_length": 2048}},
        {"context_length": 4096},
    )

    assert result.success is True
    assert result.echo_mismatches
    assert result.echo_mismatches["context_length"]["requested"] == 4096
