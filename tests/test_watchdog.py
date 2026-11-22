"""Watchdog priority modes: evict foreign models, or yield to them."""

from __future__ import annotations

import asyncio

import pytest

from lm_optimizer.services.watchdog import (
    Watchdog,
    WatchdogConfig,
    WatchdogTimeout,
)


class FakeWatchdog(Watchdog):
    """Watchdog with the HTTP calls replaced by in-memory state."""

    def __init__(self, loaded: list[str], **kwargs):
        super().__init__(our_model="ours", **kwargs)
        self.loaded = list(loaded)
        self.unloaded: list[str] = []
        self.resumed = False

    async def _loaded_models(self) -> list[str]:
        return list(self.loaded)

    async def _unload(self, model: str) -> None:
        self.unloaded.append(model)
        if model in self.loaded:
            self.loaded.remove(model)


def _config(**overrides) -> WatchdogConfig:
    base = dict(enabled=True, priority=False, poll_interval_s=0.01, wait_timeout_s=60.0, fallback_to_api=True)
    base.update(overrides)
    return WatchdogConfig(**base)


def test_priority_mode_evicts_foreign_model() -> None:
    async def run():
        dog = FakeWatchdog(["ours", "foreign"], config=_config(priority=True))
        await dog._check()
        return dog

    dog = asyncio.run(run())
    assert dog.unloaded == ["foreign"]
    assert dog.loaded == ["ours"]
    assert dog.state.paused is False


def test_non_priority_mode_pauses_for_foreign_model() -> None:
    async def run():
        paused = []
        resumed = []

        async def on_pause():
            paused.append(True)

        async def on_resume():
            resumed.append(True)

        dog = FakeWatchdog(
            ["ours", "foreign"],
            config=_config(priority=False),
            on_pause=on_pause,
            on_resume=on_resume,
        )
        await dog._check()
        first = dog.state.paused
        # Foreign model releases; next check resumes.
        dog.loaded = ["ours"]
        await dog._check()
        return dog, first, paused, resumed

    dog, first, paused, resumed = asyncio.run(run())
    assert first is True
    assert dog.state.paused is False
    assert paused == [True]
    assert resumed == [True]
    assert dog.unloaded == []


def test_non_priority_timeout_falls_back_to_api() -> None:
    async def run():
        dog = FakeWatchdog(
            ["ours", "foreign"],
            config=_config(priority=False, wait_timeout_s=0.0),
        )
        await dog._check()  # records started_wait
        await dog._check()  # 0s >= 0s -> timeout
        return dog

    with pytest.raises(WatchdogTimeout):
        asyncio.run(run())


def test_disabled_watchdog_does_not_start() -> None:
    async def run():
        dog = FakeWatchdog([], config=_config(enabled=False))
        await dog.start()
        return dog

    dog = asyncio.run(run())
    assert dog._task is None