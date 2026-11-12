"""llama.cpp backend integration.

Translates optimizer LoadConfiguration objects into llama-server CLI arguments
and manages the llama-server process lifecycle.
"""

from __future__ import annotations

from lm_optimizer.backends.llamacpp.client import LlamaCppClient
from lm_optimizer.backends.llamacpp.config import LlamaCppArgs

__all__ = ["LlamaCppArgs", "LlamaCppClient"]