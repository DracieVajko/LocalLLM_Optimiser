"""LM Studio client contract tests over httpx.MockTransport."""

import asyncio

import httpx

from lm_optimizer.services.lm_studio import LMStudioClient


def _models_payload():
    return {
        "models": [
            {
                "key": "publisher/model",
                "display_name": "Model",
                "architecture": "llama",
                "quantization": {"name": "Q4_K_M"},
                "max_context_length": 8192,
                "size_bytes": 123,
            }
        ]
    }


def test_list_models_over_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json=_models_payload())
        # Capability probes: unknown model -> recognized key.
        return httpx.Response(404, json={"error": {"code": "model_not_found"}})

    client = LMStudioClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    async def flow():
        await client.connect(echo_probe=False)
        try:
            return await client.list_models(force_refresh=True)
        finally:
            await client.close()

    models = asyncio.run(flow())

    assert len(models) == 1
    assert models[0].id == "publisher/model"
    assert models[0].name == "Model"
    assert models[0].context_limit == 8192


def test_http_error_propagates():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = LMStudioClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )

    async def flow():
        # connect() tolerates capability-detection failure...
        await client.connect(echo_probe=False)
        try:
            # ...but an explicit list request surfaces the HTTP error.
            await client.list_models(force_refresh=True)
        finally:
            await client.close()

    try:
        asyncio.run(flow())
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 500
    else:  # pragma: no cover - the assertion below is the failure path
        raise AssertionError("expected HTTPStatusError")
