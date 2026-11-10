"""Cross-backend model gate: check loaded models before loading another one.

The gate is deliberately conservative:

- It probes LM Studio, Ollama and llama.cpp for already-loaded models.
- It never unloads a model it did not load.
- When every slot is busy it waits and re-checks instead of failing the job.
- Only after the configured timeout does it try fallback models.
- On release it unloads exactly the model the gate loaded.

The number of concurrently loaded models is a policy decision, not a hardware
guess: ``MODEL_GATE_MAX_LOADED_MODELS`` defaults to 1 (one model at a time,
including ours). A user with more VRAM can set 2, 3, ...
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from lm_optimizer.config import ModelGateConfig, config as default_config
from lm_optimizer.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class LoadedModel:
    """One model instance reported as loaded by a backend."""

    backend: str
    model: str
    instance_id: str | None = None
    context_length: int | None = None


@dataclass
class BackendProbe:
    """Result of probing one backend endpoint."""

    backend: str
    url: str
    reachable: bool
    loaded: list[LoadedModel] = field(default_factory=list)
    error: str = ""


@dataclass
class ModelLease:
    """A granted model slot.

    ``loaded_by_gate`` is True only when this gate performed the load; only
    those leases are unloaded on release. A reused model (already loaded by
    another process) is left untouched.
    """

    model: str
    loaded_by_gate: bool
    load_s: float = 0.0
    #: False when the server loaded the model but never answered the load call,
    #: so ``load_s`` is the response timeout rather than a measurement.
    load_measured: bool = True
    backend: str = ""
    reused: bool = False
    fallback: bool = False


class ModelGateTimeout(RuntimeError):
    """No free slot was obtained before the timeout and no fallback worked."""


def _backend_name(client: Any) -> str:
    name = type(client).__name__.lower()
    if "lmstudio" in name:
        return "lm-studio"
    if "ollama" in name:
        return "ollama"
    if "llama" in name:
        return "llama.cpp"
    return name or "client"


def _probe_targets(active_client: Any) -> list[tuple[str, str, str]]:
    """Return (backend, url, kind) probes, with the active client's backend last."""
    targets: list[tuple[str, str, str]] = [
        (
            "lm-studio",
            default_config.lm_studio.base_url.rstrip("/") + "/api/v1/models",
            "lmstudio",
        ),
        (
            "ollama",
            default_config.ollama_base_url.rstrip("/") + "/api/ps",
            "ollama",
        ),
        (
            "llama.cpp",
            default_config.llamacpp_base_url.rstrip("/") + "/v1/models",
            "llamacpp",
        ),
    ]
    if active_client is None:
        return targets
    base_url = getattr(active_client, "base_url", None)
    if not base_url:
        return targets
    backend = _backend_name(active_client)
    suffix = {
        "lm-studio": "/api/v1/models",
        "ollama": "/api/ps",
        "llama.cpp": "/v1/models",
    }.get(backend, "/v1/models")
    kind = {
        "lm-studio": "lmstudio",
        "ollama": "ollama",
        "llama.cpp": "llamacpp",
    }.get(backend, "llamacpp")
    # The active backend wins over the config default with the same name.
    targets = [t for t in targets if t[0] != backend]
    targets.append((backend, base_url.rstrip("/") + suffix, kind))
    return targets


def _parse_lmstudio(data: Any) -> list[LoadedModel]:
    loaded: list[LoadedModel] = []
    items = data.get("models", []) if isinstance(data, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        model = str(item.get("key") or item.get("id") or "")
        for inst in item.get("loaded_instances") or []:
            instance_id = inst.get("id") if isinstance(inst, dict) else None
            context_length = None
            if isinstance(inst, dict):
                instance_cfg = inst.get("config") or {}
                if isinstance(instance_cfg, dict):
                    context_length = instance_cfg.get("context_length")
            loaded.append(
                LoadedModel("lm-studio", model, instance_id, context_length)
            )
    return loaded


def _parse_ollama(data: Any) -> list[LoadedModel]:
    loaded: list[LoadedModel] = []
    items = data.get("models", []) if isinstance(data, dict) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        model = str(item.get("name") or item.get("model") or "")
        if model:
            loaded.append(LoadedModel("ollama", model))
    return loaded


def _parse_llamacpp(data: Any) -> list[LoadedModel]:
    loaded: list[LoadedModel] = []
    items = data.get("data", []) if isinstance(data, dict) else []
    if not items and isinstance(data, dict):
        items = data.get("models", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        model = str(item.get("id") or item.get("name") or "")
        if model:
            loaded.append(LoadedModel("llama.cpp", model))
    return loaded


async def probe_backends(
    *,
    settings: ModelGateConfig | None = None,
    active_client: Any = None,
    http_client: httpx.AsyncClient | None = None,
) -> list[BackendProbe]:
    """Probe every configured backend for loaded models.

    Unreachable backends are reported with ``reachable=False`` and do not
    block the gate. A llama.cpp server that exposes only ``/health`` counts
    as one loaded model.
    """
    settings = settings or default_config.model_gate
    timeout_s = float(settings.probe_timeout_s)
    probes: list[BackendProbe] = []
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout_s)
    try:
        for backend, url, kind in _probe_targets(active_client):
            try:
                response = await client.get(url, timeout=timeout_s)
                response.raise_for_status()
                payload = response.json()
                if kind == "lmstudio":
                    loaded = _parse_lmstudio(payload)
                elif kind == "ollama":
                    loaded = _parse_ollama(payload)
                else:
                    loaded = _parse_llamacpp(payload)
                probes.append(BackendProbe(backend, url, True, loaded))
                continue
            except Exception as exc:  # noqa: BLE001 - probe must never crash
                error = f"{type(exc).__name__}: {exc}"[:160]

            if kind == "llamacpp":
                health_url = url.replace("/v1/models", "/health")
                try:
                    health = await client.get(health_url, timeout=timeout_s)
                    if health.status_code == 200:
                        probes.append(
                            BackendProbe(
                                backend,
                                url,
                                True,
                                [LoadedModel("llama.cpp", "llama-server")],
                            )
                        )
                        continue
                except Exception:  # noqa: BLE001 - health is best effort
                    pass
            probes.append(BackendProbe(backend, url, False, error=error))
    finally:
        if owns_client:
            await client.aclose()
    return probes


class ModelGate:
    """Coordinate model loads across backends and wait for a free slot."""

    def __init__(
        self,
        client: Any,
        settings: ModelGateConfig | None = None,
        *,
        probe: Callable[[], Awaitable[list[BackendProbe]]] | None = None,
        sleep: Callable[[float], Awaitable[Any]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.client = client
        self.settings = settings or default_config.model_gate
        self._probe_fn = probe
        self._sleep = sleep or asyncio.sleep
        self._clock = clock or time.monotonic
        self.last_probes: list[BackendProbe] = []

    async def probe(self) -> list[BackendProbe]:
        if self._probe_fn is not None:
            probes = await self._probe_fn()
        else:
            probes = await probe_backends(
                settings=self.settings, active_client=self.client
            )
        self.last_probes = probes
        return probes

    @staticmethod
    def _loaded(probes: list[BackendProbe]) -> list[LoadedModel]:
        return [model for probe in probes for model in probe.loaded]

    @staticmethod
    def _describe(loaded: list[LoadedModel]) -> str:
        if not loaded:
            return "no models loaded"
        return ", ".join(f"{m.backend}:{m.model}" for m in loaded)

    async def _load(
        self, model_id: str, load_config: Any, *, fallback: bool = False
    ) -> ModelLease:
        started = self._clock()
        try:
            response = await self.client.load_model(model_id, load_config)
        except Exception as exc:  # noqa: BLE001 - surface as a gate error
            raise ModelGateTimeout(
                f"load failed for {model_id!r}: {type(exc).__name__}: {exc}"
            ) from exc

        success = getattr(response, "success", None)
        error = getattr(response, "error", None)
        response_received = getattr(response, "response_received", True)
        if isinstance(response, dict):
            if success is None:
                success = response.get("success", True)
            if error is None:
                error = response.get("error")
            response_received = response.get("response_received", True)
        if success is False:
            raise ModelGateTimeout(
                f"load failed for {model_id!r}: {error or 'unknown error'}"
            )
        return ModelLease(
            model=model_id,
            loaded_by_gate=True,
            load_s=round(self._clock() - started, 1),
            load_measured=bool(response_received),
            backend=_backend_name(self.client),
            fallback=fallback,
        )

    async def acquire(
        self,
        model_id: str,
        load_config: Any = None,
        *,
        fallbacks: list[str] | None = None,
    ) -> ModelLease:
        """Load *model_id* when a slot is free, otherwise wait.

        Reuses the model when it is already loaded. Waits up to
        ``wait_timeout_s``, re-checking every ``poll_interval_s``. After the
        timeout, tries the configured fallback models once.
        """
        if not self.settings.enabled:
            return await self._load(model_id, load_config)

        fallback_list = (
            list(fallbacks) if fallbacks is not None else self.settings.fallbacks()
        )
        deadline = self._clock() + float(self.settings.wait_timeout_s)

        while True:
            loaded = self._loaded(await self.probe())
            existing = next((m for m in loaded if m.model == model_id), None)
            if existing is not None:
                requested_ctx = getattr(load_config, "context_length", None)
                if requested_ctx is None and isinstance(load_config, dict):
                    requested_ctx = load_config.get("context_length")
                if (
                    requested_ctx
                    and existing.context_length
                    and int(requested_ctx) != int(existing.context_length)
                ):
                    logger.warning(
                        "model gate: reusing model with a different context",
                        model=model_id,
                        requested_context=requested_ctx,
                        loaded_context=existing.context_length,
                    )
                logger.info(
                    "model gate: reusing loaded model",
                    model=model_id,
                    backend=existing.backend,
                )
                return ModelLease(
                    model=model_id,
                    loaded_by_gate=False,
                    backend=existing.backend,
                    reused=True,
                )

            if len(loaded) < self.settings.max_loaded_models:
                return await self._load(model_id, load_config)

            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            wait_s = min(float(self.settings.poll_interval_s), remaining)
            logger.info(
                "model gate: waiting for a free slot",
                model=model_id,
                loaded=self._describe(loaded),
                max_loaded=self.settings.max_loaded_models,
                wait_s=round(wait_s, 1),
                remaining_s=round(remaining, 1),
            )
            await self._sleep(wait_s)

        # Timeout: one fresh probe, then fallbacks (never a forced unload).
        loaded = self._loaded(await self.probe())
        for fallback in fallback_list:
            if not fallback or fallback == model_id:
                continue
            existing = next((m for m in loaded if m.model == fallback), None)
            if existing is not None:
                logger.warning(
                    "model gate: using already-loaded fallback",
                    model=fallback,
                    backend=existing.backend,
                )
                return ModelLease(
                    model=fallback,
                    loaded_by_gate=False,
                    backend=existing.backend,
                    reused=True,
                    fallback=True,
                )
            if len(loaded) < self.settings.max_loaded_models:
                logger.warning("model gate: loading fallback", model=fallback)
                return await self._load(fallback, load_config, fallback=True)

        raise ModelGateTimeout(
            f"no free model slot for {model_id!r} after "
            f"{self.settings.wait_timeout_s:.0f}s ({self._describe(loaded)})"
        )

    async def release(self, lease: ModelLease) -> bool:
        """Unload only models this gate loaded; reused models stay untouched."""
        if not lease.loaded_by_gate:
            return True
        try:
            if hasattr(self.client, "ensure_unloaded"):
                ok = await self.client.ensure_unloaded(lease.model)
            else:
                ok = await self.client.unload(lease.model)
        except Exception as exc:  # noqa: BLE001 - release must not mask the job
            logger.warning(
                "model gate: release failed", model=lease.model, error=str(exc)
            )
            return False
        if ok is False:
            logger.warning(
                "model gate: model still loaded after release", model=lease.model
            )
        return bool(ok)

    @asynccontextmanager
    async def lease(
        self,
        model_id: str,
        load_config: Any = None,
        *,
        fallbacks: list[str] | None = None,
    ):
        """Acquire and always release, including on exceptions."""
        granted = await self.acquire(
            model_id, load_config, fallbacks=fallbacks
        )
        try:
            yield granted
        finally:
            await self.release(granted)
