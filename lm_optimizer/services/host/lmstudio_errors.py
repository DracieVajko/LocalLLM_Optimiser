"""Shared LM Studio HTTP error helpers.

Both the host client (``services/host/lm_studio.py``) and the legacy API client
(``api/client.py``) need to classify the same HTTP 400 shapes: a rejected
reasoning value, a model with no reasoning config, and an unrecognised load
parameter. Keeping one implementation here stops the two copies from drifting.
"""

from __future__ import annotations

import httpx


def error_message(exc: httpx.HTTPStatusError) -> str:
    """Extract the server error message from an HTTP error response."""
    try:
        data = exc.response.json()
        err = data.get("error", data)
        if isinstance(err, dict):
            return str(err.get("message", err))
        return str(err)
    except Exception:  # noqa: BLE001 - a non-JSON body still needs a message
        return f"HTTP {exc.response.status_code}"


def is_reasoning_error(exc: httpx.HTTPStatusError) -> bool:
    """True for any reasoning-key 400 (no-config AND bad-value shapes)."""
    if exc.response.status_code != 400:
        return False
    try:
        err = exc.response.json().get("error", {})
        return err.get("code") == "invalid_value" and "reasoning" in str(
            err.get("message", "")
        ).lower()
    except Exception:  # noqa: BLE001
        return False


def is_no_reasoning_error(exc: httpx.HTTPStatusError) -> bool:
    """True when the model exposes no reasoning config at all.

    Only this shape poisons the remember-set; bad reasoning VALUES on
    supporting models (allowed sets vary: off/on vs full range) retry
    without remembering.
    """
    if exc.response.status_code != 400:
        return False
    try:
        err = exc.response.json().get("error", {})
        return err.get("code") == "invalid_value" and "does not expose reasoning" in str(
            err.get("message", "")
        )
    except Exception:  # noqa: BLE001
        return False


def is_unrecognized_key_error(exc: httpx.HTTPStatusError, key: str) -> bool:
    """True when the server 400s on an unrecognized key naming ``key``."""
    if exc.response.status_code != 400:
        return False
    try:
        err = exc.response.json().get("error", {})
        return err.get("code") == "unrecognized_keys" and key in str(err.get("message", ""))
    except Exception:  # noqa: BLE001
        return False
