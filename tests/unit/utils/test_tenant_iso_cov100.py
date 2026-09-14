"""Gap100 for utils/tenant_limits.py, tenant_orm.py, tenant_security.py,
tenanting.py — exception fallbacks, filter-less counts, guard arcs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestTenantLimitsFallbacks:
    def test_error_link_resolution_failure(self, app):
        from utils.tenant_limits import TenantLimitError

        saved = TenantLimitError.wa_upgrade_link
        TenantLimitError.wa_upgrade_link = ""
        app.config["DEVELOPER_WHATSAPP"] = ""
        try:
            with (
                app.test_request_context("/"),
                patch(
                    "models.system_settings.SystemSettings.get_current",
                    side_effect=RuntimeError("settings down"),
                ),
            ):
                err = TenantLimitError("users", 1, 2)
        finally:
            TenantLimitError.wa_upgrade_link = saved
        assert "users" in str(err)

    def test_monthly_count_without_extra_filter(self):
        import utils.tenant_limits as tl

        class _Comparable:
            def __eq__(self, other):
                return True

            def __ge__(self, other):
                return True

            def __hash__(self):
                return 1

        model = SimpleNamespace(tenant_id=_Comparable(), sale_date=_Comparable())
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 7
        sess = MagicMock()
        sess.query.return_value = q
        with patch.object(tl.db, "session", sess):
            assert tl._monthly_count(model, 1, "sale_date") == 7

    def test_enforce_feature_enabled_returns_none(self):
        import utils.tenant_limits as tl

        tenant = SimpleNamespace(id=1, my_flag=True)
        with patch.object(tl, "_active_tenant", return_value=tenant):
            assert tl.enforce_feature("my_flag", "ميزة") is None

    def test_active_tenant_no_tid_returns_none(self):
        import utils.tenant_limits as tl

        with patch.object(tl, "get_active_tenant_id", return_value=None):
            assert tl._active_tenant() is None


class TestTenantOrmFallbacks:
    def test_active_tenant_for_orm_no_context(self):
        from utils.tenant_orm import _active_tenant_for_orm

        class _BoomG:
            def __getattr__(self, name):
                raise RuntimeError("g unavailable")

        with patch("flask.g", _BoomG()):
            assert _active_tenant_for_orm() is None

    def test_inject_criteria_already_applied(self):
        import utils.tenant_orm as to

        state = MagicMock()
        state.is_select = True
        state.execution_options = {"tenant_criteria_applied": True}
        statement = MagicMock()
        state.statement = statement
        with patch.object(to, "tenant_scope_enabled", return_value=True):
            to._inject_tenant_criteria(state)
        assert state.statement is statement

    def test_inject_criteria_skips_exempt_model(self):
        import utils.tenant_orm as to

        exempt = MagicMock()
        exempt.__name__ = "User"
        state = MagicMock()
        state.is_select = True
        state.execution_options = {}
        state.statement = MagicMock()
        with (
            patch.object(to, "tenant_scope_enabled", return_value=True),
            patch.object(to, "_active_tenant_for_orm", return_value=1),
            patch.object(to, "_get_criteria", return_value=lambda m: True),
            patch.object(to, "_discover_tenant_models", return_value=[exempt]),
        ):
            to._inject_tenant_criteria(state)
        state.statement.options.assert_not_called()

    def _guard_session(self, new=None, dirty=None, deleted=None):
        session = MagicMock()
        session.new = new or []
        session.dirty = dirty or []
        session.deleted = deleted or []
        return session

    def _fake_model_obj(self, cls):
        obj = MagicMock()
        obj.__class__ = cls
        return obj

    def test_write_guard_insert_unmapped_skipped(self, app):
        import utils.tenant_orm as to

        class _Ghost:
            pass

        with (
            app.test_request_context("/"),
            patch.object(to, "has_request_context", return_value=True),
            patch.object(to, "_active_tenant_for_orm", return_value=1),
            patch.object(to, "_discover_tenant_models", return_value=[_Ghost]),
            patch.object(to, "sa_inspect", return_value=None),
        ):
            to._inject_tenant_write_guard(self._guard_session(new=[self._fake_model_obj(_Ghost)]), None, None)

    def test_write_guard_update_unmapped_skipped(self, app):
        import utils.tenant_orm as to

        class _Ghost:
            pass

        with (
            app.test_request_context("/"),
            patch.object(to, "has_request_context", return_value=True),
            patch.object(to, "_active_tenant_for_orm", return_value=1),
            patch.object(to, "_discover_tenant_models", return_value=[_Ghost]),
            patch.object(to, "sa_inspect", return_value=None),
        ):
            to._inject_tenant_write_guard(self._guard_session(dirty=[self._fake_model_obj(_Ghost)]), None, None)

    def test_write_guard_delete_unmapped_skipped(self, app):
        import utils.tenant_orm as to

        class _Ghost:
            pass

        with (
            app.test_request_context("/"),
            patch.object(to, "has_request_context", return_value=True),
            patch.object(to, "_active_tenant_for_orm", return_value=1),
            patch.object(to, "_discover_tenant_models", return_value=[_Ghost]),
            patch.object(to, "sa_inspect", return_value=None),
        ):
            to._inject_tenant_write_guard(self._guard_session(deleted=[self._fake_model_obj(_Ghost)]), None, None)

    def test_write_guard_delete_null_tenant_skipped(self, app):
        import utils.tenant_orm as to

        class _Ghost:
            pass

        obj = self._fake_model_obj(_Ghost)
        obj.tenant_id = None
        mapper = MagicMock()
        mapper.columns = {"tenant_id": MagicMock()}
        with (
            app.test_request_context("/"),
            patch.object(to, "has_request_context", return_value=True),
            patch.object(to, "_active_tenant_for_orm", return_value=1),
            patch.object(to, "_discover_tenant_models", return_value=[_Ghost]),
            patch.object(to, "sa_inspect", return_value=mapper),
        ):
            to._inject_tenant_write_guard(self._guard_session(deleted=[obj]), None, None)


class TestTenantSecurityOwnerPassthrough:
    def test_owner_without_tenant_context_proceeds(self, app):
        from types import SimpleNamespace as _SN

        from utils.tenant_security import validate_tenant_ownership

        with app.test_request_context("/"):
            from flask import g

            if hasattr(g, "active_tenant_id"):
                delattr(g, "active_tenant_id")

            @validate_tenant_ownership(MagicMock(__name__="Product"))
            def _view(product_id=None):
                return "ok"

            import flask_login

            with (
                patch.object(
                    flask_login,
                    "current_user",
                    _SN(is_authenticated=True, is_owner=True),
                ),
                patch("utils.tenanting.is_platform_owner", return_value=True),
                patch("utils.tenant_security.db") as mdb,
            ):
                mdb.session.get.return_value = _SN(tenant_id=5)
                assert _view(product_id=1) == "ok"


class TestTenantingFallbacks:
    def test_g_lookup_exception_returns_none(self):
        import utils.tenanting as tg

        class _BoomG:
            def __getattr__(self, name):
                raise RuntimeError("g unavailable")

        with (
            patch.object(tg, "has_request_context", return_value=True),
            patch("flask.g", _BoomG()),
        ):
            assert tg.get_active_tenant_id(None) is None

    def test_platform_owner_without_request_context(self):
        import utils.tenanting as tg

        user = MagicMock(is_authenticated=True, is_owner=True, tenant_id=5)
        with (
            patch.object(tg, "is_platform_owner", return_value=True),
            patch.object(tg, "has_request_context", return_value=False),
        ):
            assert tg.get_active_tenant_id(user) == 5
