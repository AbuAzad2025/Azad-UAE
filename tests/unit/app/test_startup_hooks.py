"""Factory startup hooks executed when SKIP_SYSTEM_INTEGRITY is absent."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


@contextmanager
def _boot_with_integrity(integrity_mock):
    from app.factory import create_app
    from tests.conftest import TestConfig

    patches = [
        patch("bootstrap.blueprints.register_blueprints"),
        patch("app.factory.register_error_handlers"),
        patch("app.factory.register_context_processors"),
        patch("app.factory.LoggingCore.setup"),
        patch("app.factory.LoggingCore.schedule_cleanup"),
        patch("app.factory.run_system_integrity_check", integrity_mock),
        patch("cli_commands.register_cli_commands"),
    ]
    for p in patches:
        p.start()
    try:
        yield create_app(TestConfig)
    finally:
        for p in reversed(patches):
            p.stop()


@pytest.fixture
def allow_hooks(monkeypatch):
    monkeypatch.delenv("SKIP_SYSTEM_INTEGRITY", raising=False)


class TestFactoryStartupHooks:
    def test_integrity_and_maintenance_hooks_run(self, allow_hooks, mocker):
        from services.maintenance_service import run_default_tenant_maintenance_api as _real_svc  # noqa: F401

        integrity = MagicMock()
        svc = mocker.patch(
            "services.maintenance_service.run_default_tenant_maintenance_api",
            return_value={"action_needed": False},
        )
        with _boot_with_integrity(integrity) as app:
            assert app is not None
        integrity.assert_called_once()
        assert svc.call_count == 1

    def test_maintenance_no_action_branch_logged(self, allow_hooks, mocker, caplog):
        mocker.patch(
            "services.maintenance_service.run_default_tenant_maintenance_api",
            return_value={"action_needed": False},
        )
        with _boot_with_integrity(MagicMock()), caplog.at_level(logging.INFO):
            pass
        assert any("no action needed" in r.getMessage() for r in caplog.records)
