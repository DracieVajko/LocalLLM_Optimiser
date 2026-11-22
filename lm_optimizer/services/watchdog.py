"""Configurable watchdog for LLM model loading priority.

Two modes:

* **Priority mode** (``priority=True``): the automated task owns the GPU.
  Any model loaded by a third party (the user, another process) is evicted
  so our working model keeps running.

* **Non-priority mode** (``priority=False``): the user owns the GPU. When a
  third party loads a model while we are running, we pause, unload our model,
  let the foreign model work, and resume once it is released. If the wait
  exceeds ``wait_timeout_s`` (default 1 hour) we fall back to the API backend
  by raising :class:`WatchdogTimeout`.

The watchdog polls LM Studio (and Ollama / llama.cpp) for loaded models and
signals pause/resume through an :class:`asyncio.Event`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from lm_optimizer.config import WatchdogConfig, config as default_config
from lm_optimizer.logging_config import get_logger

logger = get_logger(__name__)

FALLBACK_TO_API = "fallback_to_api"


class WatchdogTimeout(RuntimeError):
    """Raised when a non-priority watchdog waited too long for a free slot."""


@dataclass
class WatchdogState:
    paused: bool = False
    pause_reason: str = ""
    external_model: str | None = None
    started_wait: float | None = None


class Watchdog:
    """Monitors LM Studio for external model loads and manages priority."""

    def __init__(
        self,
        *,
        our_model: str,
        config: WatchdogConfig | None = None,
        base_url: str = "http://127.0.0.1:1234",
        pause_event: asyncio.Event | None = None,
        resume_event: asyncio.Event | None = None,
        on_pause: Callable[[], Awaitable[None]] | None = None,
        on_resume: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.our_model = our_model
        self.config = config or WatchdogConfig()
        self.base_url = base_url.rstrip("/")
        self.pause_event = pause_event or asyncio.Event()
        self.resume_event = resume_event or asyncio.Event()
        self.resume_event.set()  # start resumed
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.state = WatchdogState()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self.config.enabled:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check()
            except Exception as exc:  # noqa: BLE001
                logger.warning("watchdog check failed", error=str(exc)[:160])
            await asyncio.sleep(self.config.poll_interval_s)

    async def _check(self) -> None:
        loaded = await self._loaded_models()
        external = [m for m in loaded if m != self.our_model]
        if not external:
            # No external model: if we were paused, resume.
            if self.state.paused:
                await self._resume()
            return

        ext = external[0]
        if self.config.priority:
            # Evict the external model.
            await self._unload(ext)
            logger.info("watchdog evicted external model (priority mode)", model=ext)
            return

        # Non-priority: yield to the external model.
        if not self.state.paused:
            self.state.paused = True
            self.state.external_model = ext
            self.state.started_wait = time.monotonic()
            self.pause_event.clear()
            self.resume_event.clear()
            if self.on_pause is not None:
                await self.on_pause()
            logger.info("watchdog paused for external model", model=ext)

        # Check timeout.
        waited = time.monotonic() - (self.state.started_wait or time.monotonic())
        if waited >= self.config.wait_timeout_s:
            if self.config.fallback_to_api:
                raise WatchdogTimeout(
                    f"waited {waited:.0f}s for {ext} to release; "
                    "falling back to API"
                )
            logger.warning("watchdog timeout but fallback disabled", waited=waited)

    async def _resume(self) -> None:
        self.state.paused = False
        self.state.external_model = None
        self.state.started_wait = None
        if self.on_resume is not None:
            await self.on_resume()
        self.resume_event.set()
        self.pause_event.set()
        logger.info("watchdog resumed")

    async def _loaded_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/api/v1/models")
                r.raise_for_status()
                data = r.json()
        except Exception:  # noqa: BLE001
            return []
        out: list[str] = []
        for item in data.get("models", []):
            if not isinstance(item, dict):
                continue
            if item.get("loaded_instances"):
                out.append(str(item.get("key") or item.get("id") or ""))
        return out

    async def _unload(self, model: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Find instance id
                r = await client.get(f"{self.base_url}/api/v1/models")
                r.raise_for_status()
                for item in r.json().get("models", []):
                    if str(item.get("key") or item.get("id")) != model:
                        continue
                    for inst in item.get("loaded_instances") or []:
                        iid = inst.get("id") if isinstance(inst, dict) else None
                        if iid:
                            await client.post(
                                f"{self.base_url}/api/v1/models/unload",
                                json={"instance_id": iid},
                            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("watchdog unload failed", model=model, error=str(exc)[:120])
