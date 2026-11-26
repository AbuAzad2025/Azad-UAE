"""The default-tenant repair must not report repairs when no default tenant exists."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from sqlalchemy import Column, Integer, MetaData, String, Table


@contextmanager
def _engine_without_default_tenant():
    def execute(stmt, *args, **kwargs):
        result = MagicMock()
        if "information_schema" in str(stmt):
            result.fetchall.return_value = []
        else:
            result.scalar.return_value = None  # no row with slug='default'
        return result

    conn = MagicMock()
    conn.execute.side_effect = execute
    txn = MagicMock()
    txn.__enter__ = MagicMock(return_value=conn)
    txn.__exit__ = MagicMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = txn
    yield engine


def test_no_default_tenant_means_nothing_was_repaired():
    from services.maintenance_service import MaintenanceService

    tenants_tbl = Table("tenants", MetaData(), Column("id", Integer), Column("slug", String(50)))
    with (
        patch("services.maintenance_service._maintenance_engine", _engine_without_default_tenant),
        patch("services.maintenance_service.Table", return_value=tenants_tbl),
    ):
        assert MaintenanceService.fix_default_tenant_metadata() == []


def test_no_default_tenant_is_not_a_maintenance_action():
    from services.maintenance_service import MaintenanceService

    @contextmanager
    def engine():
        conn = MagicMock()
        conn.execute.return_value.scalar.return_value = 0  # no duplicate slugs
        txn = MagicMock()
        txn.__enter__ = MagicMock(return_value=conn)
        txn.__exit__ = MagicMock(return_value=False)
        e = MagicMock()
        e.connect.return_value = txn
        e.begin.return_value = txn
        yield e

    with (
        patch("services.maintenance_service._maintenance_engine", engine),
        patch.object(MaintenanceService, "fix_default_tenant_metadata", return_value=[]),
        patch.object(MaintenanceService, "regenerate_default_backup", return_value="No default tenant found"),
    ):
        result = MaintenanceService.run_default_tenant_maintenance(dry_run=False)
    assert result["patched"] == []
    assert result["action_needed"] is False
