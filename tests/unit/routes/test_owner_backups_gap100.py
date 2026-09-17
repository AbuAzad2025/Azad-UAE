"""Gap coverage for routes/owner/backups.py lines 123->129 and surrounding branches."""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def platform_owner_client_gap(client, db_session):
    from models import Role, User

    unique = str(uuid.uuid4())[:8]
    role = db_session.query(Role).filter_by(slug="owner").first()
    if not role:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.flush()
    user = User(
        username=f"powner-gap-{unique}",
        email=f"powner-gap-{unique}@example.com",
        full_name="Platform Owner Gap",
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
def _audit_gap(mocker):
    return mocker.patch("routes.owner.backups._audit_owner_db_action")


@pytest.fixture
def backup_svc_gap(mocker):
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
        setattr(svc, name, mocker.patch(f"services.backup_service.BackupService.{name}"))
    return svc


def _make_tenant_branch_user(db_session):
    from models import Branch, Role, Tenant, User

    unique = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"Gap Tenant {unique}",
        name_ar="شركة فجوة",
        slug=f"gap-tenant-{unique}",
        email=f"gap-{unique}@example.com",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(tenant)
    db_session.flush()
    branch = Branch(
        tenant_id=tenant.id,
        name=f"Gap Branch {unique}",
        code=f"GB{unique[:4].upper()}",
        is_active=True,
        is_main=True,
    )
    db_session.add(branch)
    db_session.flush()
    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if not role:
        role = Role(name="Super Admin", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.flush()
    user = User(
        username=f"gap-user-{unique}",
        email=f"gap-user-{unique}@example.com",
        full_name="Gap User",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id,
        is_owner=False,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return tenant, branch, user


class TestCreateScopedBackupGapBranches:
    def test_branch_scope_missing_branch_id_redirects_global(self, platform_owner_client_gap, backup_svc_gap):
        backup_svc_gap.create_backup.return_value = {"filename": "x.sql.gz"}
        resp = platform_owner_client_gap.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": "1"},
        )
        assert resp.status_code == 302
        backup_svc_gap.create_backup.assert_not_called()

    def test_branch_scope_global_owner_with_branch_creates(self, platform_owner_client_gap, backup_svc_gap):
        backup_svc_gap.create_backup.return_value = {"filename": "b.sql.gz"}
        resp = platform_owner_client_gap.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": "1", "branch_id": "5"},
        )
        assert resp.status_code == 302
        assert backup_svc_gap.create_backup.call_args.kwargs["scope"] == "branch"
        assert backup_svc_gap.create_backup.call_args.kwargs["branch_id"] == 5

    def test_branch_scope_global_store_missing_store_id_redirects(self, platform_owner_client_gap, backup_svc_gap):
        resp = platform_owner_client_gap.post(
            "/owner/backups/create",
            data={"scope": "store", "tenant_id": "1"},
        )
        assert resp.status_code == 302
        backup_svc_gap.create_backup.assert_not_called()

    def test_branch_scope_global_store_with_store_creates(self, platform_owner_client_gap, backup_svc_gap):
        backup_svc_gap.create_backup.return_value = {"filename": "s.sql.gz"}
        resp = platform_owner_client_gap.post(
            "/owner/backups/create",
            data={"scope": "store", "tenant_id": "1", "store_id": "9"},
        )
        assert resp.status_code == 302
        assert backup_svc_gap.create_backup.call_args.kwargs["scope"] == "store"
        assert backup_svc_gap.create_backup.call_args.kwargs["store_id"] == 9

    def test_branch_scope_non_global_match_proceeds(self, client, db_session, backup_svc_gap, mocker):
        tenant, branch, user = _make_tenant_branch_user(db_session)
        client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
            follow_redirects=False,
        )
        mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=tenant.id)
        backup_svc_gap.create_backup.return_value = {"filename": "branch-ok.sql.gz"}
        resp = client.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": str(tenant.id), "branch_id": str(branch.id)},
        )
        assert resp.status_code == 302
        backup_svc_gap.create_backup.assert_called_once()
        assert backup_svc_gap.create_backup.call_args.kwargs["branch_id"] == branch.id

    def test_branch_scope_non_global_mismatch_aborts_403(self, client, db_session, backup_svc_gap, mocker):
        tenant, branch, user = _make_tenant_branch_user(db_session)
        client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
            follow_redirects=False,
        )
        mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=tenant.id)
        other_branch_id = branch.id + 9999
        resp = client.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": str(tenant.id), "branch_id": str(other_branch_id)},
        )
        assert resp.status_code == 403
        backup_svc_gap.create_backup.assert_not_called()

    def test_branch_scope_non_global_missing_branch_id_redirects(self, client, db_session, backup_svc_gap, mocker):
        tenant, branch, user = _make_tenant_branch_user(db_session)
        client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
            follow_redirects=False,
        )
        mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=tenant.id)
        resp = client.post(
            "/owner/backups/create",
            data={"scope": "branch", "tenant_id": str(tenant.id)},
        )
        assert resp.status_code == 302
        backup_svc_gap.create_backup.assert_not_called()

    def test_tenant_scope_non_global_mismatch_aborts(self, client, db_session, backup_svc_gap, mocker):
        tenant, branch, user = _make_tenant_branch_user(db_session)
        client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
            follow_redirects=False,
        )
        mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=tenant.id)
        resp = client.post(
            "/owner/backups/create",
            data={"scope": "tenant", "tenant_id": str(tenant.id + 9999)},
        )
        assert resp.status_code == 403
        backup_svc_gap.create_backup.assert_not_called()

    def test_tenant_scope_non_global_no_active_tid_aborts(self, client, db_session, backup_svc_gap, mocker):
        _tenant, _branch, user = _make_tenant_branch_user(db_session)
        client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
            follow_redirects=False,
        )
        mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        resp = client.post(
            "/owner/backups/create",
            data={"scope": "tenant", "tenant_id": "1"},
        )
        assert resp.status_code == 403
        backup_svc_gap.create_backup.assert_not_called()

    def test_system_scope_non_global_denied(self, client, db_session, backup_svc_gap, mocker):
        _tenant, _branch, user = _make_tenant_branch_user(db_session)
        client.post(
            "/auth/login",
            data={"username": user.username, "password": "password123"},
            follow_redirects=False,
        )
        mocker.patch("utils.decorators.is_global_owner_user", return_value=True)
        mocker.patch("utils.auth_helpers.is_global_owner_user", return_value=False)
        resp = client.post("/owner/backups/create", data={"scope": "system"})
        assert resp.status_code == 403
        backup_svc_gap.create_backup.assert_not_called()
