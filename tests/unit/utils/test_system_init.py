from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from utils import system_init as system_init_module


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config.update(
        OWNER_USERNAME="owner",
        OWNER_EMAIL="owner@example.com",
        OWNER_PASSWORD="secret",
        MAIL_USERNAME="mailer",
        MAIL_PASSWORD="pass",
    )
    app.logger = MagicMock()
    return app


@contextmanager
def _tenant_scope():
    yield


def _query(value=None, all_values=None):
    query = MagicMock()
    query.filter.return_value = query
    query.filter_by.return_value = query
    query.order_by.return_value = query
    query.first.return_value = value
    query.all.return_value = all_values if all_values is not None else []
    return query


class TestEnsureSystemIntegrity:
    def test_ensure_system_integrity_wraps_inner_call(self, flask_app):
        with (
            patch("utils.system_init._ensure_system_integrity_inner") as inner,
            patch("utils.tenanting.without_tenant_scope", return_value=_tenant_scope()),
        ):
            system_init_module.ensure_system_integrity(flask_app)
        inner.assert_called_once_with(flask_app)

    def test_inner_runs_bootstrap_pipeline(self, flask_app):
        owner_role = MagicMock()
        owner_user = MagicMock(id=1, username="owner")
        with (
            flask_app.app_context(),
            patch("utils.system_init.db.create_all"),
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=owner_role),
            patch("utils.system_init._ensure_owner_user", return_value=(owner_user, False)),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_core_data"),
            patch("app.runtime.branch_repair.ensure_branch_isolation_schema_and_data"),
            patch("utils.system_init._ensure_tenant_gl_trees"),
            patch("app.runtime.accounting_repair.repair_accounting_data"),
            patch("utils.telemetry.start_telemetry"),
            patch.dict("os.environ", {"DISABLE_TELEMETRY": "false"}, clear=False),
        ):
            system_init_module._ensure_system_integrity_inner(flask_app)
        flask_app.logger.info.assert_called()

    def test_inner_logs_telemetry_disabled_message(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.system_init.db.create_all"),
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=MagicMock()),
            patch(
                "utils.system_init._ensure_owner_user",
                return_value=(MagicMock(), False),
            ),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_core_data"),
            patch("app.runtime.branch_repair.ensure_branch_isolation_schema_and_data"),
            patch("utils.system_init._ensure_tenant_gl_trees"),
            patch("app.runtime.accounting_repair.repair_accounting_data"),
            patch.dict("os.environ", {"DISABLE_TELEMETRY": "true"}, clear=False),
        ):
            system_init_module._ensure_system_integrity_inner(flask_app)
        flask_app.logger.info.assert_any_call("SystemInit: Telemetry disabled via environment variable.")

    def test_inner_starts_telemetry_when_enabled(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.system_init.db.create_all"),
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=MagicMock()),
            patch(
                "utils.system_init._ensure_owner_user",
                return_value=(MagicMock(), False),
            ),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_core_data"),
            patch("app.runtime.branch_repair.ensure_branch_isolation_schema_and_data"),
            patch("utils.system_init._ensure_tenant_gl_trees"),
            patch("app.runtime.accounting_repair.repair_accounting_data"),
            patch("utils.telemetry.start_telemetry") as start_telemetry,
            patch.dict("os.environ", {}, clear=False),
        ):
            __import__("os").environ.pop("DISABLE_TELEMETRY", None)
            system_init_module._ensure_system_integrity_inner(flask_app)
        start_telemetry.assert_called_once()

    def test_inner_swallows_telemetry_logging_failure(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.system_init.db.create_all"),
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=MagicMock()),
            patch(
                "utils.system_init._ensure_owner_user",
                return_value=(MagicMock(), False),
            ),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_core_data"),
            patch("app.runtime.branch_repair.ensure_branch_isolation_schema_and_data"),
            patch("utils.system_init._ensure_tenant_gl_trees"),
            patch("app.runtime.accounting_repair.repair_accounting_data"),
            patch("utils.telemetry.start_telemetry", side_effect=RuntimeError("telemetry")),
            patch(
                "services.logging_core.LoggingCore.log_error",
                side_effect=RuntimeError("log fail"),
            ),
        ):
            __import__("os").environ.pop("DISABLE_TELEMETRY", None)
            system_init_module._ensure_system_integrity_inner(flask_app)

    def test_inner_handles_repair_and_telemetry_failures(self, flask_app):
        with (
            flask_app.app_context(),
            patch("utils.system_init.db.create_all"),
            patch("utils.system_init._ensure_permissions"),
            patch("utils.system_init._ensure_owner_role", return_value=MagicMock()),
            patch(
                "utils.system_init._ensure_owner_user",
                return_value=(MagicMock(), False),
            ),
            patch("utils.system_init._record_server_activation"),
            patch("utils.system_init._ensure_super_admin_role"),
            patch("utils.system_init._ensure_developer_role"),
            patch("utils.system_init._ensure_functional_roles"),
            patch("utils.system_init._ensure_core_data"),
            patch(
                "app.runtime.branch_repair.ensure_branch_isolation_schema_and_data",
                side_effect=RuntimeError("branch"),
            ),
            patch("services.logging_core.LoggingCore.log_error"),
            patch(
                "utils.system_init._ensure_tenant_gl_trees",
                side_effect=RuntimeError("gl"),
            ),
            patch(
                "app.runtime.accounting_repair.repair_accounting_data",
                side_effect=RuntimeError("acct"),
            ),
            patch("utils.telemetry.start_telemetry", side_effect=RuntimeError("telemetry")),
            patch("services.logging_core.LoggingCore.log_error"),
            patch.dict("os.environ", {}, clear=False),
        ):
            __import__("os").environ.pop("DISABLE_TELEMETRY", None)
            system_init_module._ensure_system_integrity_inner(flask_app)


class TestRoleAndPermissionBootstrap:
    def test_ensure_permissions_creates_missing_codes(self, flask_app):
        query = MagicMock()
        query.filter_by.return_value.first.return_value = None
        with (
            flask_app.app_context(),
            patch.object(system_init_module.Permission, "query", query),
            patch("utils.system_init.db.session") as session,
            patch("utils.constants.PERMISSION_CODES", ["manage_sales"]),
            patch(
                "utils.constants.PERMISSIONS",
                {"manage_sales": {"en": "Sales", "ar": "مبيعات"}},
            ),
        ):
            system_init_module._ensure_permissions()
        session.add.assert_called()

    def test_ensure_owner_role_creates_and_assigns_permissions(self, flask_app):
        _role = MagicMock(slug="owner", permissions=[])
        perms = [MagicMock(code="admin")]
        role_query = MagicMock()
        role_query.filter_by.return_value.first.return_value = None
        perm_query = MagicMock()
        perm_query.all.return_value = perms
        with (
            flask_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            result = system_init_module._ensure_owner_role()
        session.add.assert_called()
        assert result.permissions == perms

    def test_ensure_super_admin_and_developer_roles_sync_permissions(self, flask_app):
        super_role = MagicMock(slug="super_admin", permissions=[])
        dev_role = MagicMock(slug="developer", permissions=[])
        perms = [MagicMock(code="admin"), MagicMock(code="manage_sales")]

        def filter_by(**_kwargs):
            query = MagicMock()
            slug = _kwargs.get("slug")
            query.first.return_value = super_role if slug == "super_admin" else dev_role
            return query

        role_query = MagicMock()
        role_query.filter_by.side_effect = filter_by
        perm_query = MagicMock()
        perm_query.all.return_value = perms
        with (
            flask_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            system_init_module._ensure_super_admin_role()
            system_init_module._ensure_developer_role()
        assert session.commit.call_count >= 2

    def test_ensure_super_admin_role_creates_missing_role(self, flask_app):
        perms = [MagicMock(code="admin")]

        def filter_by(**_kwargs):
            query = MagicMock()
            query.first.return_value = None
            return query

        role_query = MagicMock()
        role_query.filter_by.side_effect = filter_by
        perm_query = MagicMock()
        perm_query.all.return_value = perms
        with (
            flask_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            system_init_module._ensure_super_admin_role()
        session.add.assert_called()

    def test_ensure_developer_role_creates_missing_role(self, flask_app):
        perms = [MagicMock(code="admin")]

        def filter_by(**_kwargs):
            query = MagicMock()
            query.first.return_value = None
            return query

        role_query = MagicMock()
        role_query.filter_by.side_effect = filter_by
        perm_query = MagicMock()
        perm_query.all.return_value = perms
        with (
            flask_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session") as session,
        ):
            system_init_module._ensure_developer_role()
        session.add.assert_called()

    def test_ensure_functional_roles_creates_and_assigns(self, flask_app):
        manager = MagicMock(slug="manager", permissions=[])
        seller = MagicMock(slug="seller", permissions=[])
        branch = MagicMock(slug="branch_manager", permissions=[])
        accountant = MagicMock(slug="accountant", permissions=[])
        perm = MagicMock(code="manage_sales")

        def filter_by_side_effect(**kwargs):
            slug = kwargs.get("slug")
            mapping = {
                "manager": manager,
                "seller": seller,
                "branch_manager": branch,
                "accountant": accountant,
            }
            result = MagicMock()
            result.first.return_value = mapping.get(slug)
            return result

        role_query = MagicMock()
        role_query.filter.return_value.first.return_value = None
        role_query.filter_by.side_effect = filter_by_side_effect
        perm_query = MagicMock()
        perm_query.all.return_value = [perm]

        with (
            flask_app.app_context(),
            patch.object(system_init_module.Role, "query", role_query),
            patch.object(system_init_module.Permission, "query", perm_query),
            patch("utils.system_init.db.session"),
        ):
            system_init_module._ensure_functional_roles()
        assert manager.permissions == [perm]


class TestCoreDataBootstrap:
    def test_ensure_core_data_seeds_platform_reference_data(self, flask_app):
        from models import Currency, SystemSettings

        settings = MagicMock(system_name="Azad Garage System")
        currency_query = MagicMock()
        currency_query.filter_by.return_value.first.return_value = None

        with (
            flask_app.app_context(),
            patch.object(SystemSettings, "get_current", return_value=settings),
            patch.object(Currency, "query", currency_query),
            patch("utils.system_init.db.session") as session,
            patch("services.store_payment_method_service.StorePaymentMethodService.ensure_defaults") as store_defaults,
            patch("utils.seed_industry_fields.seed_industry_fields") as seed_fields,
        ):
            system_init_module._ensure_core_data()
        session.flush.assert_called()
        settings.system_name = "Azad ERP System"
        store_defaults.assert_called_once()
        seed_fields.assert_called_once()

    def test_ensure_core_data_handles_optional_seed_failures(self, flask_app):
        from models import Currency, SystemSettings

        settings = MagicMock(system_name="Azad ERP System")
        currency_query = MagicMock()
        currency_query.filter_by.return_value.first.return_value = MagicMock()
        with (
            flask_app.app_context(),
            patch.object(SystemSettings, "get_current", return_value=settings),
            patch.object(Currency, "query", currency_query),
            patch("utils.system_init.db.session"),
            patch(
                "services.store_payment_method_service.StorePaymentMethodService.ensure_defaults",
                side_effect=RuntimeError("store"),
            ),
            patch(
                "utils.seed_industry_fields.seed_industry_fields",
                side_effect=RuntimeError("seed"),
            ),
        ):
            system_init_module._ensure_core_data()

    def test_ensure_core_data_creates_missing_currencies(self, flask_app):
        from models import Currency, SystemSettings

        settings = MagicMock(system_name="Azad ERP System")
        currency_query = MagicMock()
        currency_query.filter_by.return_value.first.return_value = None

        with (
            flask_app.app_context(),
            patch.object(SystemSettings, "get_current", return_value=settings),
            patch.object(Currency, "query", currency_query),
            patch("utils.system_init.db.session") as session,
            patch("services.store_payment_method_service.StorePaymentMethodService.ensure_defaults"),
            patch("utils.seed_industry_fields.seed_industry_fields"),
        ):
            system_init_module._ensure_core_data()
        assert session.add.call_count >= 1


class TestOwnerUserBootstrap:
    def test_creates_new_owner_user(self, flask_app):
        role = MagicMock()
        new_user = MagicMock()
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = None
        user_cls = MagicMock(return_value=new_user)
        user_cls.query = user_query
        with (
            flask_app.app_context(),
            patch("utils.system_init.User", user_cls),
            patch("utils.system_init.db.session") as session,
        ):
            _user, created = system_init_module._ensure_owner_user(role)
        assert created is True
        session.add.assert_called_once_with(new_user)
        new_user.set_password.assert_called_once_with("secret")

    def test_marks_legacy_username_as_owner(self, flask_app):
        role = MagicMock()
        legacy = MagicMock(username="owner", is_owner=False, role=None)
        responses = iter([None, legacy])

        def filter_by(**_kwargs):
            query = MagicMock()
            query.first.return_value = next(responses)
            return query

        user_query = MagicMock()
        user_query.filter_by.side_effect = filter_by
        with (
            flask_app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session"),
        ):
            user, created = system_init_module._ensure_owner_user(role)
        assert created is False
        assert user.is_owner is True

    def test_updates_owner_email_when_available(self, flask_app):
        role = MagicMock()
        owner = MagicMock(username="owner", is_owner=True, role=role, email="old@system.local", id=1)
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = owner
        user_query.filter.return_value.first.return_value = None
        with (
            flask_app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session"),
        ):
            user, created = system_init_module._ensure_owner_user(role)
        assert created is False
        assert user.email == "owner@example.com"

    def test_skips_conflicting_owner_email(self, flask_app):
        role = MagicMock()
        owner = MagicMock(username="owner", is_owner=True, role=role, email="old@system.local", id=1)
        conflict = MagicMock(username="other", id=2)
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = owner
        user_query.filter.return_value.first.return_value = conflict
        with (
            flask_app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session"),
        ):
            user, _ = system_init_module._ensure_owner_user(role)
        assert user.email == "old@system.local"

    def test_updates_owner_role_linkage(self, flask_app):
        role = MagicMock()
        other_role = MagicMock()
        owner = MagicMock(
            username="owner",
            is_owner=True,
            role=other_role,
            email="owner@system.local",
            id=1,
        )
        user_query = MagicMock()
        user_query.filter_by.return_value.first.return_value = owner
        with (
            flask_app.app_context(),
            patch.object(system_init_module.User, "query", user_query),
            patch("utils.system_init.db.session") as _session,
        ):
            user, created = system_init_module._ensure_owner_user(role)
        assert created is False
        assert user.role == role


class TestTenantGlTrees:
    def test_ensure_tenant_gl_trees_provisions_accounts(self, flask_app):
        from models.tenant import Tenant

        tenant = MagicMock(id=3, is_active=True)
        tenant_query = MagicMock()
        tenant_query.filter_by.return_value.order_by.return_value.all.return_value = [tenant]
        with (
            flask_app.app_context(),
            patch.object(Tenant, "query", tenant_query),
            patch("services.gl_service.GLService.ensure_core_accounts") as ensure,
        ):
            system_init_module._ensure_tenant_gl_trees()
        ensure.assert_called_once_with(tenant_id=3, cleanup_extra=False)


class TestRecordServerActivation:
    def test_records_first_activation_alert(self, flask_app):
        settings = MagicMock()
        settings.get_custom_setting.return_value = None
        owner = MagicMock(id=5, username="owner", email="owner@example.com")
        with (
            flask_app.app_context(),
            patch("models.SystemSettings.get_current", return_value=settings),
            patch("utils.telemetry.get_machine_signature", return_value="sig-1"),
            patch("socket.gethostname", return_value="host"),
            patch("platform.system", return_value="Windows"),
            patch("platform.release", return_value="11"),
            patch("platform.machine", return_value="AMD64"),
            patch("platform.processor", return_value="cpu"),
            patch("utils.system_init.db.session") as session,
            patch.dict("os.environ", {"DISABLE_TELEMETRY": "false"}, clear=False),
            patch("extensions.mail.send"),
        ):
            system_init_module._record_server_activation(owner, True)
        session.add.assert_called_once()

    def test_records_server_changed_alert(self, flask_app):
        settings = MagicMock()
        settings.get_custom_setting.return_value = "old-sig"
        owner = MagicMock(id=5, username="owner", email="owner@system.local")
        with (
            flask_app.app_context(),
            patch("models.SystemSettings.get_current", return_value=settings),
            patch("utils.telemetry.get_machine_signature", return_value="new-sig"),
            patch("socket.gethostname", return_value="host"),
            patch("platform.system", return_value="Linux"),
            patch("platform.release", return_value="6"),
            patch("platform.machine", return_value="x86"),
            patch("platform.processor", return_value="cpu"),
            patch("utils.system_init.db.session"),
        ):
            system_init_module._record_server_activation(owner, False)

    def test_skips_when_signature_unchanged(self, flask_app):
        settings = MagicMock()
        settings.get_custom_setting.return_value = "same-sig"
        with (
            flask_app.app_context(),
            patch("models.SystemSettings.get_current", return_value=settings),
            patch("utils.telemetry.get_machine_signature", return_value="same-sig"),
            patch("utils.system_init.db.session") as session,
        ):
            system_init_module._record_server_activation(MagicMock(), False)
        session.add.assert_not_called()

    def test_sends_activation_email_when_mail_configured(self, flask_app, monkeypatch):
        settings = MagicMock()
        settings.get_custom_setting.return_value = None
        owner = MagicMock(id=5, username="owner", email="owner@example.com")
        monkeypatch.delenv("DISABLE_TELEMETRY", raising=False)
        with (
            flask_app.app_context(),
            patch("models.SystemSettings.get_current", return_value=settings),
            patch("utils.telemetry.get_machine_signature", return_value="sig-mail"),
            patch("socket.gethostname", return_value="host"),
            patch("platform.system", return_value="Windows"),
            patch("platform.release", return_value="11"),
            patch("platform.machine", return_value="AMD64"),
            patch("platform.processor", return_value="cpu"),
            patch("utils.system_init.db.session"),
            patch("flask_mail.Message"),
            patch("extensions.mail.send") as send_mail,
        ):
            system_init_module._record_server_activation(owner, True)
        send_mail.assert_called_once()

    def test_skips_mail_when_telemetry_disabled(self, flask_app, monkeypatch):
        settings = MagicMock()
        settings.get_custom_setting.return_value = None
        owner = MagicMock(id=5, username="owner", email="owner@example.com")
        monkeypatch.setenv("DISABLE_TELEMETRY", "true")
        with (
            flask_app.app_context(),
            patch("models.SystemSettings.get_current", return_value=settings),
            patch("utils.telemetry.get_machine_signature", return_value="sig-skip"),
            patch("socket.gethostname", return_value="host"),
            patch("platform.system", return_value="Windows"),
            patch("platform.release", return_value="11"),
            patch("platform.machine", return_value="AMD64"),
            patch("platform.processor", return_value="cpu"),
            patch("utils.system_init.db.session"),
            patch("extensions.mail.send") as send_mail,
        ):
            system_init_module._record_server_activation(owner, True)
        send_mail.assert_not_called()
        flask_app.logger.info.assert_called_with("SystemInit: Mail sending skipped (DISABLE_TELEMETRY).")

    def test_returns_before_mail_when_smtp_not_configured(self, flask_app, monkeypatch):
        settings = MagicMock()
        settings.get_custom_setting.return_value = None
        owner = MagicMock(id=5, username="owner", email="owner@example.com")
        flask_app.config["MAIL_USERNAME"] = None
        monkeypatch.delenv("DISABLE_TELEMETRY", raising=False)
        with (
            flask_app.app_context(),
            patch("models.SystemSettings.get_current", return_value=settings),
            patch("utils.telemetry.get_machine_signature", return_value="sig-no-mail"),
            patch("socket.gethostname", return_value="host"),
            patch("platform.system", return_value="Windows"),
            patch("platform.release", return_value="11"),
            patch("platform.machine", return_value="AMD64"),
            patch("platform.processor", return_value="cpu"),
            patch("utils.system_init.db.session"),
            patch("extensions.mail.send") as send_mail,
        ):
            system_init_module._record_server_activation(owner, True)
        send_mail.assert_not_called()

    def test_record_activation_failure_rolls_back(self, flask_app):
        with (
            flask_app.app_context(),
            patch(
                "models.SystemSettings.get_current",
                side_effect=RuntimeError("settings down"),
            ),
            patch("services.logging_core.LoggingCore.log_error"),
            patch(
                "utils.system_init.db.session.rollback",
                side_effect=RuntimeError("rollback fail"),
            ),
        ):
            system_init_module._record_server_activation(MagicMock(), False)

    def test_record_activation_logging_failure_is_swallowed(self, flask_app):
        with (
            flask_app.app_context(),
            patch(
                "models.SystemSettings.get_current",
                side_effect=RuntimeError("settings down"),
            ),
            patch(
                "services.logging_core.LoggingCore.log_error",
                side_effect=RuntimeError("log fail"),
            ),
            patch("utils.system_init.db.session.rollback"),
        ):
            system_init_module._record_server_activation(MagicMock(), False)
