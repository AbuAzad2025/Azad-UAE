"""Unit tests for BackupService.create_tenant_manual_backup (tenant self-service).

Guards: owner rejected, tenant required + active, hourly rate limit,
retention keeps newest N, failures are clean dicts (no exceptions).
"""

from __future__ import annotations

import time
from unittest.mock import patch

from services.backup_service import BackupService


def _manual_meta(filename, tenant_id, age_seconds):
    return {
        "filename": filename,
        "backup_scope": "tenant",
        "tenant_id": tenant_id,
        "modified": time.time() - age_seconds,
    }


class TestCreateTenantManualBackup:
    def test_owner_rejected(self, db_session, sample_owner):
        result = BackupService.create_tenant_manual_backup(sample_owner)
        assert result["ok"] is False

    def test_no_active_tenant(self, db_session, sample_user):
        with patch("utils.tenanting.get_active_tenant_id", return_value=None):
            result = BackupService.create_tenant_manual_backup(sample_user)
        assert result == {"ok": False, "error": "no active tenant"}

    def test_inactive_tenant_rejected(self, db_session, sample_tenant, sample_user):
        sample_tenant.is_active = False
        db_session.flush()
        result = BackupService.create_tenant_manual_backup(sample_user)
        assert result["ok"] is False

    def test_rate_limited_within_hour(self, db_session, sample_tenant, sample_user):
        recent = _manual_meta("azad_backup_tenant_demo_recent.tar.gz", sample_tenant.id, 300)
        with patch.object(BackupService, "list_backups", return_value=[recent]):
            result = BackupService.create_tenant_manual_backup(sample_user)
        assert result["ok"] is False
        assert result["error"] == "rate_limited"
        assert result["retry_after_minutes"] >= 1

    def test_success_creates_and_prunes(self, db_session, sample_tenant, sample_user):
        with (
            patch.object(BackupService, "list_backups", return_value=[]),
            patch.object(
                BackupService,
                "create_backup",
                return_value={"filename": "azad_backup_tenant_new.tar.gz", "size_mb": 3},
            ) as created,
        ):
            result = BackupService.create_tenant_manual_backup(sample_user)
        assert result["ok"] is True
        assert result["filename"] == "azad_backup_tenant_new.tar.gz"
        created.assert_called_once()
        kwargs = created.call_args.kwargs
        assert kwargs["scope"] == "tenant"
        assert kwargs["tenant_id"] == sample_tenant.id

    def test_create_failure_returns_clean_error(self, db_session, sample_tenant, sample_user):
        with (
            patch.object(BackupService, "list_backups", return_value=[]),
            patch.object(BackupService, "create_backup", return_value=None),
        ):
            result = BackupService.create_tenant_manual_backup(sample_user)
        assert result == {"ok": False, "error": "backup failed"}


class TestPruneRetention:
    def test_keeps_newest_five(self, db_session):
        metas = [_manual_meta(f"azad_backup_tenant_x_{i}.tar.gz", 4242, age_seconds=7200 + i) for i in range(7)]
        deleted = []
        with (
            patch.object(BackupService, "list_backups", return_value=metas),
            patch.object(BackupService, "delete_backup", side_effect=lambda fn: deleted.append(fn) or True),
        ):
            removed = BackupService._prune_tenant_manual_backups(4242)
        assert removed == 2
        assert len(deleted) == 2
        # Newest five (smallest age) survive.
        assert "azad_backup_tenant_x_0.tar.gz" not in deleted
        assert "azad_backup_tenant_x_1.tar.gz" not in deleted

    def test_ignores_other_tenants_and_auto(self, db_session):
        metas = [
            _manual_meta("azad_backup_tenant_other.tar.gz", 9999, age_seconds=99999),
            {
                "filename": "azad_backup_tenant_x_auto.tar.gz",
                "backup_scope": "tenant",
                "tenant_id": 4242,
                "modified": time.time() - 99999,
            },
        ]
        with (
            patch.object(BackupService, "list_backups", return_value=metas),
            patch.object(BackupService, "delete_backup") as deleted,
        ):
            assert BackupService._prune_tenant_manual_backups(4242) == 0
        deleted.assert_not_called()
