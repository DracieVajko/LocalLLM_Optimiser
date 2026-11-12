"""LM Studio Auto Optimizer - Main package."""

from .config import config
from .logging_config import get_logger, setup_logging

#: The single source of truth for the project version.
#: ``pyproject.toml`` reads it (setuptools dynamic version) and the FastAPI
#: app reports it - there is no second copy to keep in sync.
__version__ = "1.9.0"
__all__ = ["config", "get_logger", "setup_logging"]
