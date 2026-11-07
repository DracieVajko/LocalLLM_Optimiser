"""llama-server process manager and API client.

Manages the llama-server subprocess lifecycle and provides an async
interface compatible with the BackendClient protocol.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import httpx

from lm_optimizer.logging_config import get_logger

logger = get_logger(__name__)


class LlamaCppClient:
    """Async client for llama-server."""

    backend_name = "llamacpp"

    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url
        self._process: subprocess.Popen[str] | None = None
        self._connected = False

    async def connect(self, *args: Any, **kwargs: Any) -> None:
        """Check if llama-server is reachable."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/health", timeout=5.0)
                if resp.status_code == 200:
                    self._connected = True
                    logger.info("Connected to llama-server", base_url=self.base_url)
                else:
                    raise ConnectionError(f"llama-server health check failed: {resp.status_code}")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to llama-server at {self.base_url}: {e}")

    async def list_models(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """List loaded models (llama-server serves one model at a time)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/models", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", [])
            return []

    async def load_model(
        self,
        model_id: str,
        config: Any,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Load a model by starting llama-server with the given config.

        For llama.cpp, loading means starting the server process with
        the appropriate CLI arguments. The config must include model_path.
        """
        from .config import LlamaCppArgs, from_load_config

        if isinstance(config, LlamaCppArgs):
            args_obj = config
        elif hasattr(config, "to_api_params"):
            # Convert from LoadConfiguration
            args_obj = from_load_config(
                config,
                model_path=getattr(config, "model_path", ""),
            )
        else:
            args_obj = from_load_config(config)

        cmd = ["llama-server"] + args_obj.to_cli_args()
        logger.info("Starting llama-server", cmd=" ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                await self.connect()
                return {"success": True, "loaded_config": config}
            except ConnectionError:
                continue

        raise RuntimeError("llama-server failed to start")

    async def generate(
        self,
        model_id: str,
        prompt: str,
        options: dict | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a completion via the OpenAI-compatible endpoint."""
        opts = options or {}
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": opts.get("temperature", 0.7),
            "max_tokens": opts.get("max_tokens", 256),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=120.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""
                usage = data.get("usage", {})
                return {
                    "choices": [{"message": {"content": content}}],
                    "usage": usage,
                    "_stats": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "tokens_per_second": 0.0,
                    },
                }
            raise RuntimeError(f"Generation failed: {resp.status_code}")

    async def unload(self, model_id: str, *args: Any, **kwargs: Any) -> bool:
        """Unload by terminating the llama-server process."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._connected = False
        return True

    def capabilities(self) -> dict[str, bool | str]:
        """Return backend capabilities."""
        return {
            "backend": "llamacpp",
            "supports_gpu_ratio": True,
            "supports_parallel": True,
            "supports_flash_attn": True,
            "supports_kv_quant": True,
            "supports_rope": True,
            "supports_moe_offload": True,
        }

    async def close(self) -> None:
        """Close the client."""
        await self.unload("")
