"""Standalone CLI wrapper for the bake-off service.

The implementation lives in ``lm_optimizer.services.bakeoff`` so it ships with
the package and is also available as ``lab bakeoff``.
"""

from lm_optimizer.services.bakeoff import main

if __name__ == "__main__":
    raise SystemExit(main())
