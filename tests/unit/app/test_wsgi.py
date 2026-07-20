"""Unit tests for wsgi.py — the production WSGI entrypoint (gunicorn target).

Mirrors the boot-module pattern established in test_app_entry.py: the module
is executed from its file location so its top-level code runs for real.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask

ROOT = Path(__file__).resolve().parents[3]
WSGI_PY = ROOT / "wsgi.py"


def _exec_wsgi(spec_name="azad_wsgi_entry"):
    if spec_name in sys.modules:
        del sys.modules[spec_name]
    spec = importlib.util.spec_from_file_location(spec_name, WSGI_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestWsgiEntry:
    def test_import_exposes_flask_app_instance(self):
        mod = _exec_wsgi()
        assert isinstance(mod.app, Flask)
        assert hasattr(mod.app, "test_client")

    def test_app_is_exported_in_module_all(self):
        mod = _exec_wsgi(spec_name="azad_wsgi_entry_all")
        assert mod.__all__ == ["app"]

    def test_boot_uses_canonical_factory(self):
        fake_app = MagicMock()
        with patch("app.factory.create_app", return_value=fake_app) as mock_create:
            mod = _exec_wsgi(spec_name="azad_wsgi_entry_wired")
        mock_create.assert_called_once_with()
        assert mod.app is fake_app
