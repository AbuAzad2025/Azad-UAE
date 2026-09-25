"""Unit tests for routes/tenant_backups.py — tenant self-service backup surface.

Guards: anonymous redirected to login, missing permission 403s, download of
foreign files denied, happy paths redirect with flashes.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def backup_permitted(db_session, sample_role):
    """Grant manage_backups to the shared test role (auth_client's user)."""
    from models import Permission

    perm = db_session.query(Permission).filter_by(code="manage_backups").first()
    if perm is None:
        perm = Permission(code="manage_backups", name="Backups", name_ar="نسخ", category="test")
        db_session.add(perm)
    if perm not in sample_role.permissions:
        sample_role.permissions.append(perm)
    db_session.commit()
    return sample_role


class TestTenantBackupsGuard:
    def test_anonymous_redirects_to_login(self, client):
        resp = client.get("/backups/", follow_redirects=False)
        assert resp.status_code in (301, 302, 303)

    def test_without_permission_403(self, auth_client):
        assert auth_client.get("/backups/").status_code == 403


class TestTenantBackupsIndex:
    def test_renders_with_tenant(self, auth_client, backup_permitted, sample_tenant):
        with (
            patch(
                "services.backup_service.BackupService.list_backups_for_user",
                return_value=[],
            ),
            patch("routes.tenant_backups.render_template", return_value="ok"),
        ):
            resp = auth_client.get("/backups/")
        assert resp.status_code == 200


class TestTenantBackupsCreate:
    def test_success_redirects(self, auth_client, backup_permitted):
        with patch(
            "services.backup_service.BackupService.create_tenant_manual_backup",
            return_value={"ok": True, "filename": "f.tar.gz"},
        ):
            resp = auth_client.post("/backups/create", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_rate_limited_redirects(self, auth_client, backup_permitted):
        with patch(
            "services.backup_service.BackupService.create_tenant_manual_backup",
            return_value={"ok": False, "error": "rate_limited", "retry_after_minutes": 55},
        ):
            resp = auth_client.post("/backups/create", follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestTenantBackupsDownload:
    def test_foreign_file_denied(self, auth_client, backup_permitted):
        with patch(
            "services.backup_service.BackupService.user_may_access_backup",
            return_value=False,
        ):
            resp = auth_client.get("/backups/download/azad_backup_tenant_other.tar.gz", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_unknown_file_denied(self, auth_client, backup_permitted):
        with patch(
            "services.backup_service.BackupService.user_may_access_backup",
            return_value=False,
        ):
            resp = auth_client.post("/backups/verify/nope.tar.gz", follow_redirects=False)
        assert resp.status_code in (302, 303)
