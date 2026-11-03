"""Root pytest configuration: mark unit vs integration tests by path."""

import pytest


def pytest_collection_modifyitems(config, items):
    """Apply the unit/integration marker from the test root.

    ``lm_optimizer/tests/`` is the unit suite and ``tests/`` is the
    integration/tooling suite. Marking here keeps the 130+ files unchanged
    while making ``pytest -m unit`` / ``-m integration`` reliable.
    """
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "/lm_optimizer/tests/" in path:
            item.add_marker(pytest.mark.unit)
        elif "/tests/" in path:
            item.add_marker(pytest.mark.integration)
