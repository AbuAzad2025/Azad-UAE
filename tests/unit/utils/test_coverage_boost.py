"""Coverage boost — edge cases for utils helpers/tenanting/tenant_orm/branching."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

class TestHelpersCoverageBoost:
    def test_sanitize_masks_internal_pattern(self, app):
        from utils.helpers import sanitize_error_message

        with app.app_context():
            msg = sanitize_error_message(Exception('column "foo" does not exist'))
            assert "internal database" in msg.lower()

    def test_sanitize_masks_syntax_error(self, app):
        from utils.helpers import sanitize_error_message

        with app.app_context():
            msg = sanitize_error_message(Exception("syntax error at position 1"))
            assert "internal database" in msg.lower()

    def test_sanitize_masks_psycopg2(self, app):
        from utils.helpers import sanitize_error_message

        with app.app_context():
            msg = sanitize_error_message(Exception("psycopg2.OperationalError: FATAL:  too many"))
            assert "internal database" in msg.lower()

    def test_sanitize_masks_long_message(self, app):
        from utils.helpers import sanitize_error_message

        long_msg = "x" * 250
        with app.app_context():
            msg = sanitize_error_message(Exception(long_msg))
            assert "internal error" in msg.lower()

    def test_sanitize_returns_short_safe_message(self, app):
        from utils.helpers import sanitize_error_message

        with app.app_context():
            assert sanitize_error_message(Exception("unique violation")) == "unique violation"

    def test_normalize_branch_code_edge(self):
        from utils.helpers import _normalize_branch_code

        assert _normalize_branch_code(0) is None
        assert _normalize_branch_code("  ") is None  # only stripped symbols -> empty -> None
        assert _normalize_branch_code("a-b 2") == "AB2"

    def test_resolve_branch_code_no_branch_id_returns_none(self):
        from utils.helpers import _resolve_branch_code

        assert _resolve_branch_code(branch_code=None, branch_id=None) is None
        assert _resolve_branch_code(branch_code="", branch_id=0) is None

    def test_resolve_branch_code_branch_without_code_fallback(self, app):
        from utils.helpers import _resolve_branch_code

        branch = MagicMock(code=None)
        with patch("utils.helpers.db.session.get", return_value=branch):
            assert _resolve_branch_code(branch_id=5) == "BR05"

    def test_build_number_pattern_both_branches(self):
        from utils.helpers import _build_number_pattern

        assert _build_number_pattern("INV", "BR01", "2026") == "INV-BR01-2026-%"
        assert _build_number_pattern("INV", None, "2026") == "INV-2026-%"

    def test_parse_sequence_suffix(self):
        from utils.helpers import _parse_sequence_suffix

        assert _parse_sequence_suffix("INV-2026-0007") == 7
        assert _parse_sequence_suffix("bad") is None
        assert _parse_sequence_suffix(None) is None
        assert _parse_sequence_suffix(123) == 123

    def test_format_time_and_datetime_and_date_and_number(self):
        from utils.helpers import format_date, format_datetime, format_number, format_time

        assert format_time(None) == ""
        assert format_datetime(None) == ""
        assert format_date(None) == ""
        assert format_number(None) == "0"
        dt = datetime(2026, 1, 2, 3, 4)
        assert format_time(dt) == "03:04"
        assert format_datetime(dt) == "2026-01-02 03:04"
        assert format_date(dt) == "2026-01-02"
        assert format_time("already") == "already"
        assert format_datetime(12345) == "12345"
        assert format_number("bad") == "bad"
        assert format_number(Decimal("1234.5"), decimals=1) == "1,234.5"

    def test_generate_sku_and_barcode(self):
        from utils.helpers import generate_barcode, generate_sku

        assert generate_sku().startswith("SKU-")
        assert len(generate_barcode()) >= 14

    def test_allowed_file_no_dot(self, app):
        from utils.helpers import allowed_file

        with app.app_context():
            assert allowed_file("noextension", allowed_extensions={".png"}) is False
            assert allowed_file(None) is False
            assert allowed_file("photo.JPG", allowed_extensions={".png", ".jpg"}) is True

    def test_save_uploaded_file_elf_rejected(self, app):
        from utils.helpers import save_uploaded_file

        f = MagicMock()
        f.filename = "evil.png"
        f.tell.side_effect = [100, 0]
        f.read.return_value = b"\x7fELF" + b"\x00" * 508
        with app.app_context(), pytest.raises(ValueError, match="Executable"):
            save_uploaded_file(f, allowed_extensions={".png"})

    def test_convert_currency_same_and_default(self, app):
        from utils.helpers import convert_currency

        assert convert_currency(50, "AED", "AED") == 50
        tenant = MagicMock(default_currency="SAR")
        with (
            patch("models.Tenant.get_current", return_value=tenant),
            patch("services.currency_service.CurrencyService.get_exchange_rate", return_value=Decimal("1.5")),
        ):
            assert convert_currency(10, "AED") == Decimal("15.0")

    def test_format_currency_fallback_exception(self):
        from utils import helpers as h

        class Bad:
            def __format__(self, spec):
                raise RuntimeError("boom")
            def __str__(self):
                return "bad-obj"
        assert h.format_currency(Bad()) == "bad-obj"


# ── tenanting ────────────────────────────────────────────────────────────────

class TestTenantingCoverageBoost:
    def test_get_active_tenant_resolves_from_g(self, app):
        from utils.tenanting import get_active_tenant_id

        user = MagicMock(is_authenticated=True, is_owner=True, tenant_id=None)
        with app.test_request_context("/"):
            from flask import g

            g.active_tenant_id = 55
            # g path taken when user is unauthenticated — fallback still uses g
            anon = MagicMock(is_authenticated=False)
            assert get_active_tenant_id(anon) == 55

    def test_get_active_tenant_company_user_none_returns_none(self):
        from utils.tenanting import get_active_tenant_id

        user = MagicMock(is_authenticated=True, is_owner=False, tenant_id=None)
        assert get_active_tenant_id(user) is None

    def test_apply_tenant_scope_no_tenant_field(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=5)
        from utils.tenanting import apply_tenant_scope

        q = MagicMock()
        # model without tenant_id attr -> return unchanged
        assert apply_tenant_scope(q, object()) is q
        q.filter.assert_not_called()

    def test_apply_tenant_scope_owner_no_selection(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        from utils.tenanting import apply_tenant_scope

        class M:
            tenant_id = MagicMock()
            tenant_id.__lt__ = lambda self, other: "lt"
        q = MagicMock()
        q.filter.return_value = "filtered"
        result = apply_tenant_scope(q, M, MagicMock(is_owner=True))
        q.filter.assert_called_once()
        assert result == "filtered"

    def test_without_tenant_scope_outside_request(self, mocker):
        mocker.patch("utils.tenanting.has_request_context", return_value=False)
        from utils.tenanting import without_tenant_scope

        # should not raise even outside request context
        with without_tenant_scope():
            pass

    def test_get_tenant_status_suspended_no_reason(self, mocker):
        tenant = MagicMock(is_active=False, is_suspended=False, suspension_reason=None)
        mocker.patch("utils.tenanting.db.session.get", return_value=tenant)
        from utils.tenanting import get_tenant_status

        status = get_tenant_status(9)
        assert status["suspended"] is True
        assert status["reason"] == "Tenant suspended"

    def test_scoped_user_query_non_owner_no_tenant(self, mocker):
        from utils.tenanting import scoped_user_query

        class _Col:
            def __lt__(self, other):
                return "lt"
        user_model = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        user_model.query = q
        user_model.is_owner = MagicMock()
        user_model.is_active = MagicMock()
        user_model.tenant_id = _Col()
        mocker.patch("models.user.User", user_model, create=True)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        result = scoped_user_query(MagicMock(is_authenticated=True, is_owner=False, tenant_id=None))
        q.filter.assert_called()

    def test_tenant_get_or_404_success_via_tid_match(self, app, mocker):
        mocker.patch("utils.tenanting.db.session.get", return_value=MagicMock(tenant_id=3, id=1))
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=3)
        from utils.tenanting import tenant_get_or_404

        with app.test_request_context():
            obj = tenant_get_or_404(MagicMock, 1)
            assert obj.tenant_id == 3


# ── tenant_orm ───────────────────────────────────────────────────────────────

class TestTenantOrmCoverageBoost:
    def test_criteria_for_model_platform_owner_shows_all(self, mocker):
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        from utils.tenant_orm import _criteria_for_model
        from sqlalchemy import true as sql_true

        crit = _criteria_for_model(None)
        class M:
            pass
        # platform owner with tid None => sql_true
        assert crit(M) is not None

    def test_criteria_for_model_non_owner_hides_all(self, mocker):
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        from utils.tenant_orm import _criteria_for_model

        crit = _criteria_for_model(None)
        class M:
            tenant_id = MagicMock()
            tenant_id.__lt__ = lambda self, o: "hidden"
        assert crit(M) == "hidden"

    def test_get_criteria_cached_and_fallback(self, app, mocker):
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        from utils.tenant_orm import _get_criteria

        with app.test_request_context("/"):
            from flask import g
            # ensure clean cache
            if hasattr(g, "_tenant_criteria_cache"):
                delattr(g, "_tenant_criteria_cache")
            c1 = _get_criteria(5)
            c2 = _get_criteria(5)
            assert c1 is c2
        # outside request context fallback builds uncached
        mocker.patch("utils.tenant_orm.has_request_context", return_value=False)
        # patch g access to raise RuntimeError to trigger outer fallback? but _get_criteria handles RuntimeError
        fallback = _get_criteria(None)
        assert callable(fallback)

    def test_validate_instance_tenant_none_rec_tid_platform_owner(self, mocker):
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=5)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        mapper = MagicMock(columns={"tenant_id": object()})
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mapper)
        from utils.tenant_orm import _validate_instance_tenant

        class Sale:
            __name__ = "Sale"
        obj = Sale()
        obj.tenant_id = None
        assert _validate_instance_tenant(obj) is True

    def test_validate_instance_tenant_tid_none_returns_false(self, mocker):
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=None)
        mapper = MagicMock(columns={"tenant_id": object()})
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mapper)
        from utils.tenant_orm import _validate_instance_tenant

        class Sale:
            __name__ = "Sale"
        obj = Sale()
        obj.tenant_id = 5
        assert _validate_instance_tenant(obj) is False

    def test_active_tenant_for_orm_prefers_g(self, app):
        from utils.tenant_orm import _active_tenant_for_orm

        with app.test_request_context("/"):
            from flask import g
            g.active_tenant_id = 77
            assert _active_tenant_for_orm() == 77

    def test_active_tenant_for_orm_g_exception_fallback(self, mocker):
        # force getattr(g, ...) to raise by patching flask.g
        mocker.patch("utils.tenant_orm.has_request_context", return_value=True)
        # simulate exception during g access by making g raise
        import utils.tenant_orm as torm
        orig_g = torm.g
        fake_g = MagicMock()
        type(fake_g).active_tenant_id = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        mocker.patch.object(torm, "g", fake_g)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=9)
        from utils.tenant_orm import _active_tenant_for_orm
        # should not raise, fallback to tenanting
        assert _active_tenant_for_orm() == 9

    def test_write_guard_auto_stamps_and_cross_tenant(self, app, mocker):
        from utils.tenant_orm import TenantIsolationError, _inject_tenant_write_guard

        # need request context
        with app.test_request_context("/"):
            mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=10)
            # tenant model discovery
            class FakeModel:
                __name__ = "Sale"
            FakeModel.__tablename__ = "sales"
            mocker.patch("utils.tenant_orm._discover_tenant_models", return_value=[FakeModel])
            mocker.patch("utils.tenant_orm.sa_inspect", return_value=MagicMock(columns={"tenant_id": object()}))
            # INSERT auto-stamp when tenant_id None
            obj_new = FakeModel()
            obj_new.tenant_id = None
            session = MagicMock()
            session.new = [obj_new]
            session.dirty = []
            session.deleted = []
            _inject_tenant_write_guard(session, None, None)
            assert obj_new.tenant_id == 10

            # cross-tenant INSERT raises
            obj_bad = FakeModel()
            obj_bad.tenant_id = 99
            session.new = [obj_bad]
            with pytest.raises(TenantIsolationError):
                _inject_tenant_write_guard(session, None, None)

            # UPDATE guard
            obj_dirty = FakeModel()
            obj_dirty.tenant_id = 99
            session.new = []
            session.dirty = [obj_dirty]
            with pytest.raises(TenantIsolationError):
                _inject_tenant_write_guard(session, None, None)

            # DELETE guard
            session.dirty = []
            session.deleted = [obj_dirty]
            with pytest.raises(TenantIsolationError):
                _inject_tenant_write_guard(session, None, None)

            # skip when g.skip_tenant_scope
            from flask import g
            g.skip_tenant_scope = True
            session.deleted = []
            _inject_tenant_write_guard(session, None, None)  # no raise
            g.skip_tenant_scope = False

    def test_log_cross_tenant_warning_handles_exception(self, mocker):
        mocker.patch("flask.current_app.logger.warning", side_effect=RuntimeError("log fail"))
        from utils.tenant_orm import _log_cross_tenant_warning
        # should not raise
        _log_cross_tenant_warning("Sale", 1, 2)

    def test_discover_returns_empty_without_cache(self, mocker):
        import utils.tenant_orm as torm
        torm._TENANT_MODELS = None
        # registry has no tenant-bearing models
        registry = MagicMock()
        registry.mappers = []
        mocker.patch.object(torm.db.Model, "registry", registry, create=True)
        result = torm._discover_tenant_models()
        assert result == []
        assert torm._TENANT_MODELS is None  # not cached when empty
        torm._TENANT_MODELS = None


# ── branching ────────────────────────────────────────────────────────────────

class TestBranchingCoverageBoost:
    def test_is_global_user_non_callable_super_admin(self):
        from utils.branching import is_global_user

        user = MagicMock(is_authenticated=True, is_owner=False, is_super_admin="not-callable")
        user.role = MagicMock(slug="cashier")
        assert is_global_user(user) is False

    def test_is_global_user_owner_true(self):
        from utils.branching import is_global_user

        user = MagicMock(is_authenticated=True, is_owner=True, role=MagicMock(slug="cashier"))
        assert is_global_user(user) is True

    def test_get_active_branch_id_global_invalid_session_clears(self, app, mocker):
        from utils.branching import ACTIVE_BRANCH_MODE_SESSION_KEY, ACTIVE_BRANCH_SESSION_KEY, get_active_branch_id

        mocker.patch("utils.branching.is_global_user", return_value=True)
        mocker.patch("utils.branching.get_active_branch_mode", return_value="single")
        mocker.patch("utils.branching.user_can_access_branch", return_value=False)
        user = MagicMock(is_authenticated=True, is_owner=False, tenant_id=1, branch_id=2, role=MagicMock(slug="super_admin"))
        user.is_super_admin.return_value = True
        with app.test_request_context("/"):
            from flask import session
            session[ACTIVE_BRANCH_SESSION_KEY] = 999
            assert get_active_branch_id(user) is None
            assert ACTIVE_BRANCH_SESSION_KEY not in session
            assert session[ACTIVE_BRANCH_MODE_SESSION_KEY] == "single"

    def test_get_warehouse_stock_map(self, mocker):
        from utils.branching import get_warehouse_stock_map, get_branch_stock_map

        assert get_branch_stock_map(warehouse_ids=None) == {}
        assert get_warehouse_stock_map(warehouse_ids=[]) == {}
        q = MagicMock()
        q.filter.return_value = q
        q.group_by.return_value.all.return_value = [(1, 10, Decimal("3")), (2, 10, None)]
        mocker.patch("utils.branching.db.session.query", return_value=q)
        result = get_warehouse_stock_map(product_ids=[1], warehouse_ids=[10])
        assert result[(1, 10)] == Decimal("3")
        assert result[(2, 10)] == Decimal("0")

    def test_get_accessible_warehouses_query_scoped(self, mocker):
        from utils.branching import get_accessible_warehouses_query

        wh = MagicMock()
        q = MagicMock()
        q.filter_by.return_value = q
        q.filter.return_value = q
        wh.query = q
        mocker.patch("models.Warehouse", wh, create=True)
        mocker.patch("utils.branching.get_active_tenant_id", return_value=1)
        mocker.patch("utils.branching.branch_scope_id_for", return_value=5)
        result = get_accessible_warehouses_query(MagicMock(is_authenticated=True, tenant_id=1))
        assert result is q.filter.return_value

    def test_user_can_access_branch_none_is_global(self, mocker):
        mocker.patch("utils.branching.is_global_user", return_value=True)
        from utils.branching import user_can_access_branch
        assert user_can_access_branch(None, MagicMock()) is True
        assert user_can_access_branch("all", MagicMock()) is True

    def test_get_active_branch_mode_no_context(self, mocker):
        mocker.patch("utils.branching.has_request_context", return_value=False)
        from utils.branching import get_active_branch_mode
        assert get_active_branch_mode() == "single"

    def test_role_requires_branch(self):
        from utils.branching import role_requires_branch
        assert role_requires_branch(is_owner=True) is False
        assert role_requires_branch(role=MagicMock(slug=None), is_owner=False) is True
