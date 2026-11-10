"""Model gate tests: slot policy, waiting, fallbacks, release, probes."""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest

from lm_optimizer.config import ModelGateConfig
from lm_optimizer.services.model_gate import (
    BackendProbe,
    LoadedModel,
    ModelGate,
    ModelGateTimeout,
    probe_backends,
)


@dataclass
class FakeClient:
    base_url: str = "http://fake"
    loaded: list[str] = field(default_factory=list)
    load_calls: list[str] = field(default_factory=list)
    unload_calls: list[str] = field(default_factory=list)
    fail_load: bool = False

    async def load_model(self, model_id, config=None):
        self.load_calls.append(model_id)
        if self.fail_load:
            return {"success": False, "error": "boom"}
        self.loaded.append(model_id)
        return {"success": True}

    async def ensure_unloaded(self, model_id):
        self.unload_calls.append(model_id)
        if model_id in self.loaded:
            self.loaded.remove(model_id)
        return True


class SequenceProbe:
    """Return a sequence of loaded-model states, then repeat the last one."""

    def __init__(self, states):
        self.states = states
        self.index = 0

    async def __call__(self):
        state = self.states[min(self.index, len(self.states) - 1)]
        self.index += 1
        return [
            BackendProbe(
                "lm-studio",
                "http://fake",
                True,
                [LoadedModel("lm-studio", model) for model in state],
            )
        ]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _settings(**overrides):
    values = dict(
        enabled=True,
        max_loaded_models=1,
        wait_timeout_s=10.0,
        poll_interval_s=3.0,
        probe_timeout_s=0.1,
        fallback_models="",
    )
    values.update(overrides)
    return ModelGateConfig(**values)


async def _no_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_acquire_loads_when_nothing_is_loaded():
    client = FakeClient()
    gate = ModelGate(
        client,
        _settings(),
        probe=SequenceProbe([[]]),
        sleep=_no_sleep,
    )
    lease = await gate.acquire("needed")
    assert lease.loaded_by_gate is True
    assert lease.reused is False
    assert client.load_calls == ["needed"]
    assert await gate.release(lease) is True
    assert client.unload_calls == ["needed"]


@pytest.mark.asyncio
async def test_acquire_reuses_loaded_model_without_unloading_it():
    client = FakeClient(loaded=["needed"])
    gate = ModelGate(
        client,
        _settings(),
        probe=SequenceProbe([["needed"]]),
        sleep=_no_sleep,
    )
    lease = await gate.acquire("needed")
    assert lease.reused is True
    assert lease.loaded_by_gate is False
    assert client.load_calls == []
    await gate.release(lease)
    assert client.unload_calls == []


@pytest.mark.asyncio
async def test_acquire_waits_for_slot_then_loads():
    client = FakeClient()
    clock = FakeClock()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    gate = ModelGate(
        client,
        _settings(wait_timeout_s=10.0, poll_interval_s=3.0),
        probe=SequenceProbe([["other"], ["other"], []]),
        sleep=sleep,
        clock=clock,
    )
    lease = await gate.acquire("needed")
    assert sleeps == [3.0, 3.0]
    assert lease.loaded_by_gate is True
    assert client.load_calls == ["needed"]


@pytest.mark.asyncio
async def test_acquire_times_out_without_fallbacks():
    client = FakeClient()
    clock = FakeClock()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    gate = ModelGate(
        client,
        _settings(wait_timeout_s=5.0, poll_interval_s=2.0),
        probe=SequenceProbe([["other"]]),
        sleep=sleep,
        clock=clock,
    )
    with pytest.raises(ModelGateTimeout):
        await gate.acquire("needed")
    assert sleeps == [2.0, 2.0, 1.0]
    assert client.load_calls == []


@pytest.mark.asyncio
async def test_acquire_uses_already_loaded_fallback_after_timeout():
    client = FakeClient(loaded=["fallback"])
    clock = FakeClock()
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    gate = ModelGate(
        client,
        _settings(wait_timeout_s=3.0, poll_interval_s=2.0),
        probe=SequenceProbe([["other"], ["other"], ["other"], ["other", "fallback"]]),
        sleep=sleep,
        clock=clock,
    )
    lease = await gate.acquire("needed", fallbacks=["fallback"])
    assert lease.fallback is True
    assert lease.reused is True
    assert client.load_calls == []
    await gate.release(lease)
    assert client.unload_calls == []


@pytest.mark.asyncio
async def test_max_two_allows_loading_alongside_one_loaded_model():
    client = FakeClient(loaded=["other"])
    gate = ModelGate(
        client,
        _settings(max_loaded_models=2),
        probe=SequenceProbe([["other"]]),
        sleep=_no_sleep,
    )
    lease = await gate.acquire("needed")
    assert lease.loaded_by_gate is True
    assert client.load_calls == ["needed"]


@pytest.mark.asyncio
async def test_failed_load_raises_gate_timeout():
    client = FakeClient(fail_load=True)
    gate = ModelGate(
        client,
        _settings(),
        probe=SequenceProbe([[]]),
        sleep=_no_sleep,
    )
    with pytest.raises(ModelGateTimeout, match="boom"):
        await gate.acquire("needed")


@pytest.mark.asyncio
async def test_probe_backends_parses_lmstudio_ollama_and_llamacpp():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/models":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "key": "lm-model",
                            "loaded_instances": [{"id": "inst-1"}],
                        },
                        {"key": "idle-model", "loaded_instances": []},
                    ]
                },
            )
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "ollama-model"}]})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "llama-model"}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        probes = await probe_backends(
            settings=_settings(), http_client=http_client
        )
    loaded = sorted(
        (probe.backend, model.model)
        for probe in probes
        for model in probe.loaded
    )
    assert loaded == [
        ("llama.cpp", "llama-model"),
        ("lm-studio", "lm-model"),
        ("ollama", "ollama-model"),
    ]
    assert all(probe.reachable for probe in probes)
