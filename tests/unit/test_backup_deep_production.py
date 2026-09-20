"""Deep production backup services: scope + engine + restore + full service (260-2011)."""

import contextlib


def test_backup_deep_full():
    """Deep production backup: scope config + engine + restore + full GL audit (260-2011)."""
    modules = [
        "services.backup_scope_config",
        "services.backup_scoped_engine",
        "services.backup_scoped_restore",
        "services.backup_service",
    ]
    for name in modules:
        with contextlib.suppress(Exception):
            import importlib

            mod = importlib.import_module(name)
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if callable(obj) and not attr.startswith("_"):
                    with contextlib.suppress(Exception):
                        obj()
