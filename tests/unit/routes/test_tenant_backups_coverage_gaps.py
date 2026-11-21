"""Remaining branches of the tenant self-service backup surface."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def backup_permitted(db_session, sample_role):
    from models import Permission

    perm = db_session.query(Permission).filter_by(code="manage_backups").first()
    if perm is None:
        perm = Permission(code="manage_backups", name="Backups", name_ar="نسخ", category="test")
        db_session.add(perm)
    if perm not in sample_role.permissions:
        sample_role.permissions.append(perm)
    db_session.commit()
    return sample_role


class TestTenantBackupRemainingArcs:
    def test_index_without_active_tenant_redirects(self, auth_client, backup_permitted):
        with patch("routes.tenant_backups.get_active_tenant_id", return_value=None):
            resp = auth_client.get("/backups/", follow_redirects=False)
        assert resp.status_code in (301, 302, 303)

    def test_create_generic_failure_flashes_danger(self, auth_client, backup_permitted):
        with (
            patch(
                "services.backup_service.BackupService.create_tenant_manual_backup",
                return_value={"ok": False, "error": "disk full"},
            ),
            patch("routes.tenant_backups.flash") as flash,
        ):
            resp = auth_client.post("/backups/create", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert flash.call_args.args[1] == "danger"

    def test_download_owned_file(self, auth_client, backup_permitted):
        with (
            patch("services.backup_service.BackupService.sanitize_filename", return_value="own.tar.gz"),
            patch("services.backup_service.BackupService.user_may_access_backup", return_value=True),
            patch("routes.tenant_backups.send_file", return_value="file") as send,
        ):
            resp = auth_client.get("/backups/download/own.tar.gz")
        assert resp.status_code == 200
        assert send.call_args.args[0].endswith("own.tar.gz")

    @pytest.mark.parametrize("valid,expected", [(True, "success"), (False, "danger")])
    def test_verify_result(self, auth_client, backup_permitted, valid, expected):
        with (
            patch("services.backup_service.BackupService.sanitize_filename", return_value="own.tar.gz"),
            patch("services.backup_service.BackupService.user_may_access_backup", return_value=True),
            patch("services.backup_service.BackupService.verify_backup", return_value={"valid": valid}),
            patch("routes.tenant_backups.flash") as flash,
        ):
            resp = auth_client.post("/backups/verify/own.tar.gz", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert flash.call_args.args[1] == expected

    @pytest.mark.parametrize("deleted,expected", [(True, "success"), (False, "danger")])
    def test_delete_result(self, auth_client, backup_permitted, deleted, expected):
        with (
            patch("services.backup_service.BackupService.sanitize_filename", return_value="own.tar.gz"),
            patch("services.backup_service.BackupService.user_may_access_backup", return_value=True),
            patch("services.backup_service.BackupService.delete_backup", return_value=deleted),
            patch("routes.tenant_backups.flash") as flash,
        ):
            resp = auth_client.post("/backups/delete/own.tar.gz", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert flash.call_args.args[1] == expected
