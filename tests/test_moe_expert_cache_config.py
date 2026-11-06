"""Regression tests for MoE expert_cache marker selection and connection handling.

These tests verify that:
1. expert_cache tests are excluded from the default pytest suite.
2. Explicit -m expert_cache selection includes them.
3. Connection failures are handled as skips (not failures).
4. Client cleanup happens reliably.
5. Real benchmark exceptions are not hidden as skips.

No live LM Studio server is required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from lm_optimizer.services.host.lm_studio import LMStudioClient
from tests.test_moe_expert_cache import TestMoEExpertCache


def test_expert_cache_excluded_by_default():
    """`pytest -q` should NOT collect expert_cache tests.

    Verifies that pyproject.toml addopts = ["-m", "not expert_cache"]
    effectively excludes expert_cache tests from the default suite.
    """
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'addopts = ["-m", "not expert_cache"]' in pyproject, (
        "pyproject.toml must have addopts = [\"-m\", \"not expert_cache\"] "
        f"to exclude expert_cache tests by default. Got:\n{pyproject}"
    )


def test_expert_cache_included_with_explicit_marker():
    """`pytest -m expert_cache` SHOULD collect expert_cache tests.

    Verifies by checking that the marker is registered in the test file
    and the test file is collectible with -m expert_cache.
    """
    source = Path("tests/test_moe_expert_cache.py").read_text(encoding="utf-8")
    assert "@pytest.mark.expert_cache" in source, (
        "test_moe_expert_cache.py must have @pytest.mark.expert_cache "
        "decorators for the tests to be selectable with -m expert_cache"
    )


def test_expert_cache_excluded_when_explicitly_disabled():
    """`-m "not expert_cache"` should exclude expert_cache tests explicitly."""
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'addopts = ["-m", "not expert_cache"]' in pyproject


@pytest.mark.asyncio
async def test_connection_failure_skips_test():
    """Connection failure during client.connect() should skip, not fail.

    Simulates LM Studio being unavailable. The test should skip with a
    clear reason rather than raising httpx.ConnectError.
    """
    test_instance = TestMoEExpertCache()
    client = LMStudioClient(base_url="http://127.0.0.1:1234")

    async def mock_connect():
        raise httpx.ConnectError("Connection refused")

    client.connect = mock_connect

    with patch("tests.test_moe_expert_cache.LMStudioClient", return_value=client):
        with pytest.raises(pytest.skip.Exception) as exc_info:
            await test_instance.test_expert_cache_affects_speed()
        assert "Cannot connect to LM Studio" in str(exc_info.value)


@pytest.mark.asyncio
async def test_cleanup_happens_on_connection_failure():
    """Client cleanup happens even when connect fails.

    Verifies that client.close() is called even when connect() raises,
    ensuring resources are not leaked.
    """
    test_instance = TestMoEExpertCache()
    client = LMStudioClient(base_url="http://127.0.0.1:1234")
    close_called = False

    async def mock_connect():
        raise httpx.ConnectError("Connection refused")

    async def mock_close():
        nonlocal close_called
        close_called = True

    client.connect = mock_connect
    client.close = mock_close

    with patch("tests.test_moe_expert_cache.LMStudioClient", return_value=client):
        try:
            await test_instance.test_expert_cache_affects_speed()
        except pytest.skip.Exception:
            pass

    assert close_called, "client.close() should be called even after connection failure"


@pytest.mark.asyncio
async def test_real_exception_not_hidden_as_skip():
    """Real exceptions (not connection errors) should propagate, not be skipped.

    If get_models() raises a ValueError (not a connection error), the test
    should propagate it rather than skipping.
    """
    test_instance = TestMoEExpertCache()
    client = LMStudioClient(base_url="http://127.0.0.1:1234")

    async def mock_connect():
        client._connected = True

    async def mock_get_models():
        raise ValueError("Unexpected server error")

    client.connect = mock_connect
    client.get_models = mock_get_models
    client._client = AsyncMock()
    client._connected = True

    with patch("tests.test_moe_expert_cache.LMStudioClient", return_value=client):
        with pytest.raises(ValueError):
            await test_instance.test_expert_cache_affects_speed()