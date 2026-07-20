"""Unit tests for routes/owner/backups.py — owner backup endpoints.

tests/unit/routes/test_owner_routes.py already exercises these endpoints with
a fully mocked auth stack (is_global_owner_user is patched there). This file
deliberately uses REAL logins so the owner_required guard itself is tested,
with BackupService mocked only at the service boundary — no real pg_dump, no
filesystem writes outside pytest tmp paths.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_client(client, db_session):
    """Real platform owner (is_owner + tenant_id=None) via real login."""
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = db_session.query(Role).filter_by(slug="owner").first()
    if not role:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.flush()
    user = User(
        username=f"powner-{unique}",
        email=f"powner-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture(autouse=True)
def _audit(mocker):
    return mocker.patch("routes.owner.backups._audit_owner_db_action")


@pytest.fixture
def backup_svc(mocker):
    """Boundary mock for BackupService class methods used by the routes."""

    class _Svc:
        pass

    svc = _Svc()
    for name in (
        "create_backup",
        "get_list_backups_context",
        "sanitize_filename",
        "user_may_access_backup",
        "get_backup_info",
        "verify_backup",
        "prepare_restore",
        "restore_backup_to_target_db",
        "restore_scoped_backup_to_target_db",
        "list_backups_for_user",
        "delete_backup",
        "list_backups",
        "get_backup_stats",
        "get_schedule_settings",
        "get_schedule_state",
        "save_schedule_settings",
    ):
        setattr(
            svc, name, mocker.patch(f"services.backup_service.BackupService.{name}")
        )
    return svc


class TestOwnerGuardContract:
    """The real guard: anonymous and tenant admins get 404, owner gets in."""

    def test_anonymous_gets_404(self, client):
        assert client.get("/owner/backups/list").status_code == 404

    def test_tenant_admin_gets_404(self, auth_client):
        assert auth_client.get("/owner/backups/list").status_code == 404

    def test_platform_owner_gets_through(
        self, platform_owner_client, backup_svc, mocker
    ):
        mocker.patch("routes.owner.backups.render_template", return_value="ok")
        backup_svc.get_list_backups_context.return_value = {
            "backups": [],
            "stats": {},
            "schedule_settings": {},
            "schedule_state": {},
            "backup_dir": "/tmp",
            "pg_tools": {},
            "tenants": [],
            "branches": [],
            "stores": [],
            "is_platform_owner": True,
            "now": None,
        }
        resp = platform_owner_client.get("/owner/backups/list")
        assert resp.status_code == 200
        backup_svc.get_list_backups_context.assert_called_once()


class TestBackupNow:
    def test_json_success(self, platform_owner_client, backup_svc):
        backup_svc.create_backup.return_value = {
            "filename": "b.sql.gz",
            "size_mb": 2,
        }
        resp = platform_owner_client.post("/owner/backup-now", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["filename"] == "b.sql.gz"
        assert backup_svc.create_backup.call_args.kwargs["scope"] == "system"
        assert backup_svc.create_backup.call_args.kwargs["manual"] is True

    def test_json_failure_returns_400(self, platform_owner_client, backup_svc):
        backup_svc.create_backup.return_value = None
        resp = platform_owner_client.post("/owner/backup-now", json={})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_form_post_redirects(self, platform_owner_client, backup_svc):
        backup_svc.create_backup.return_value = {
            "filename": "b.sql.gz",
            "size_mb": 2,
        }
        resp = platform_owner_client.post("/owner/backup-now", data={})
        assert resp.status_code == 302


class TestCreateScopedBackup:
    def test_system_scope_created(self, platform_owner_client, backup_svc):
        backup_svc.create_backup.return_value = {"filename": "sys.sql.gz"}
        resp = platform_owner_client.post(
            "/owner/backups/create", data={"scope": "system"}
        )
        assert resp.status_code == 302
        assert backup_svc.create_backup.call_args.kwargs["scope"] == "system"

    def test_unsupported_scope_rejected(self, platform_owner_client, backup_svc):
        resp = platform_owner_client.post(
            "/owner/backups/create", data={"scope": "galaxy"}
        )
        assert resp.status_code == 302
        backup_svc.create_backup.assert_not_called()

    def test_tenant_scope_requires_tenant_id(self, platform_owner_client, backup_svc):
        resp = platform_owner_client.post(
            "/owner/backups/create", data={"scope": "tenant"}
        )
        assert resp.status_code == 302
        backup_svc.create_backup.assert_not_called()

    def test_tenant_scope_with_tenant_created(self, platform_owner_client, backup_svc):
        backup_svc.create_backup.return_value = {"filename": "t.sql.gz"}
        resp = platform_owner_client.post(
            "/owner/backups/create", data={"scope": "tenant", "tenant_id": "7"}
        )
        assert resp.status_code == 302
        kwargs = backup_svc.create_backup.call_args.kwargs
        assert kwargs["scope"] == "tenant"
        assert kwargs["tenant_id"] == 7


class TestBackupInfoAndVerify:
    def test_info_invalid_filename_400(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = None
        resp = platform_owner_client.get("/owner/backups/info/...evil...")
        assert resp.status_code == 400

    def test_info_missing_backup_404(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.get_backup_info.return_value = None
        resp = platform_owner_client.get("/owner/backups/info/b.sql.gz")
        assert resp.status_code == 404

    def test_info_success(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.get_backup_info.return_value = {"size_mb": 3}
        resp = platform_owner_client.get("/owner/backups/info/b.sql.gz")
        assert resp.status_code == 200
        assert resp.get_json()["info"] == {"size_mb": 3}

    def test_verify_access_denied_403(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = False
        resp = platform_owner_client.post("/owner/backups/verify/b.sql.gz")
        assert resp.status_code == 403

    def test_verify_valid_result(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.verify_backup.return_value = {"valid": True, "format": "pg"}
        resp = platform_owner_client.post("/owner/backups/verify/b.sql.gz")
        assert resp.status_code == 200
        assert resp.get_json()["verified"] is True

    def test_verify_invalid_result_still_200(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.verify_backup.return_value = {"valid": False}
        resp = platform_owner_client.post("/owner/backups/verify/b.sql.gz")
        assert resp.status_code == 200
        assert resp.get_json()["verified"] is False


class TestDownloadAndDelete:
    def test_download_serves_real_file(
        self, platform_owner_client, backup_svc, tmp_path, mocker
    ):
        backup_file = tmp_path / "b.sql.gz"
        backup_file.write_bytes(b"backup-bytes")
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        mocker.patch("services.backup_service.BackupService.BACKUP_DIR", str(tmp_path))
        resp = platform_owner_client.get("/owner/backups/download/b.sql.gz")
        assert resp.status_code == 200
        assert resp.data == b"backup-bytes"

    def test_download_missing_file_redirects(
        self, platform_owner_client, backup_svc, tmp_path, mocker
    ):
        backup_svc.sanitize_filename.return_value = "gone.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        mocker.patch("services.backup_service.BackupService.BACKUP_DIR", str(tmp_path))
        resp = platform_owner_client.get("/owner/backups/download/gone.sql.gz")
        assert resp.status_code == 302

    def test_delete_not_listed_redirects_without_delete(
        self, platform_owner_client, backup_svc
    ):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.list_backups_for_user.return_value = []
        resp = platform_owner_client.post(
            "/owner/backups/delete", data={"filename": "b.sql.gz"}
        )
        assert resp.status_code == 302
        backup_svc.delete_backup.assert_not_called()

    def test_delete_existing_calls_service(self, platform_owner_client, backup_svc):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.list_backups_for_user.return_value = [{"filename": "b.sql.gz"}]
        backup_svc.delete_backup.return_value = True
        resp = platform_owner_client.post(
            "/owner/backups/delete", data={"filename": "b.sql.gz"}
        )
        assert resp.status_code == 302
        backup_svc.delete_backup.assert_called_once_with("b.sql.gz")


class TestRestoreFlows:
    def test_prepare_restore_post_returns_payload(
        self, platform_owner_client, backup_svc
    ):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.user_may_access_backup.return_value = True
        backup_svc.prepare_restore.return_value = {"ok": True, "commands": ["psql"]}
        resp = platform_owner_client.post("/owner/backups/prepare-restore/b.sql.gz")
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True, "commands": ["psql"]}

    def test_restore_target_without_url_redirects(
        self, platform_owner_client, backup_svc, monkeypatch
    ):
        monkeypatch.delenv("TARGET_TEST_DATABASE_URL", raising=False)
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.get_backup_info.return_value = {"manifest": {}}
        resp = platform_owner_client.post(
            "/owner/backups/restore-target/b.sql.gz", data={}
        )
        assert resp.status_code == 302
        backup_svc.restore_backup_to_target_db.assert_not_called()

    def test_restore_target_with_url_calls_service(
        self, platform_owner_client, backup_svc
    ):
        backup_svc.sanitize_filename.return_value = "b.sql.gz"
        backup_svc.get_backup_info.return_value = {"manifest": {}}
        backup_svc.restore_backup_to_target_db.return_value = {
            "ok": True,
            "target_db": "copy_db",
        }
        resp = platform_owner_client.post(
            "/owner/backups/restore-target/b.sql.gz",
            data={
                "target_database_url": "postgresql://u:p@localhost/copy_db",
                "restore_confirm": "RESTORE",
            },
        )
        assert resp.status_code == 302
        backup_svc.restore_backup_to_target_db.assert_called_once()


class TestScheduledBackups:
    def test_get_renders_with_context(self, platform_owner_client, backup_svc, mocker):
        render = mocker.patch(
            "routes.owner.backups.render_template", return_value="rendered"
        )
        backup_svc.get_schedule_settings.return_value = {"enabled": True}
        backup_svc.get_schedule_state.return_value = {"last_run": None}
        backup_svc.list_backups.return_value = []
        backup_svc.get_backup_stats.return_value = {"total": 0}
        resp = platform_owner_client.get("/owner/scheduled-backups")
        assert resp.status_code == 200
        render.assert_called_once()

    def test_post_saves_settings(self, platform_owner_client, backup_svc):
        resp = platform_owner_client.post(
            "/owner/scheduled-backups",
            data={
                "enabled": "on",
                "frequency": "daily",
                "backup_time": "03:00",
                "keep_count": "7",
            },
        )
        assert resp.status_code == 302
        backup_svc.save_schedule_settings.assert_called_once_with(
            {
                "enabled": True,
                "frequency": "daily",
                "backup_time": "03:00",
                "keep_count": 7,
            }
        )
