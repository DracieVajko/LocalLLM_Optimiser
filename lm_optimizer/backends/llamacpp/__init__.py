"""llama.cpp backend integration.

Translates optimizer LoadConfiguration objects into llama-server CLI arguments
and manages the llama-server process lifecycle.
"""

from __future__ import annotations

__all__ = ["config", "client"]