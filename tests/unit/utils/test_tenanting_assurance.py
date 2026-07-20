"""Tenant isolation — active tenant resolution, scoping, status."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from werkzeug.exceptions import Forbidden, NotFound


def _user(**kwargs):
    user = MagicMock()
    user.is_authenticated = kwargs.get("is_authenticated", True)
    user.is_owner = kwargs.get("is_owner", False)
    user.tenant_id = kwargs.get("tenant_id", 7)
    return user


class TestTenantResolution:
    def test_platform_owner_detection(self):
        from utils.tenanting import is_platform_owner, is_global_tenant_user

        assert is_platform_owner(_user(is_owner=True)) is True
        assert is_global_tenant_user(_user(is_owner=True)) is True
        assert is_platform_owner(_user(is_owner=False)) is False

    def test_company_user_locked_to_tenant(self):
        from utils.tenanting import get_active_tenant_id

        assert get_active_tenant_id(_user(tenant_id=9)) == 9

    def test_unauthenticated_returns_none(self):
        from utils.tenanting import get_active_tenant_id

        assert get_active_tenant_id(_user(is_authenticated=False)) is None

    def test_owner_session_tenant(self, app, mocker):
        from utils.tenanting import get_active_tenant_id, ACTIVE_TENANT_SESSION_KEY

        with app.test_request_context():
            from flask import session

            session[ACTIVE_TENANT_SESSION_KEY] = "12"
            assert get_active_tenant_id(_user(is_owner=True, tenant_id=None)) == 12

    def test_owner_invalid_session_falls_back(self, app):
        from utils.tenanting import get_active_tenant_id, ACTIVE_TENANT_SESSION_KEY

        with app.test_request_context():
            from flask import session

            session[ACTIVE_TENANT_SESSION_KEY] = "bad"
            assert get_active_tenant_id(_user(is_owner=True, tenant_id=5)) == 5

    def test_require_active_tenant_id_aborts(self, app):
        from utils.tenanting import require_active_tenant_id

        with app.test_request_context():
            with pytest.raises(Forbidden):
                require_active_tenant_id(_user(is_authenticated=False))


class _Col:
    def __eq__(self, other):
        return self

    def __lt__(self, other):
        return self


class TestTenantScope:
    def test_apply_tenant_scope_filters(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=3)
        model = MagicMock()
        model.tenant_id = MagicMock()
        query = MagicMock()
        from utils.tenanting import apply_tenant_scope

        apply_tenant_scope(query, model, _user())
        query.filter.assert_called_once()

    def test_owner_without_tenant_empty_scope(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        model = MagicMock()
        model.tenant_id = _Col()
        query = MagicMock()
        from utils.tenanting import apply_tenant_scope

        apply_tenant_scope(query, model, _user(is_owner=True))
        query.filter.assert_called_once_with(model.tenant_id < 0)

    def test_tenant_query_delegates(self, mocker):
        mocker.patch("utils.tenanting.apply_tenant_scope", return_value="scoped")
        model = MagicMock()
        model.query = "base"
        from utils.tenanting import tenant_query

        assert tenant_query(model) == "scoped"

    def test_model_has_tenant(self):
        from utils.tenanting import model_has_tenant

        assert model_has_tenant(type("M", (), {"tenant_id": 1})()) is True
        assert model_has_tenant(object()) is False


class TestTenantRecordGuards:
    def test_assert_none_or_404(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            with pytest.raises(NotFound):
                assert_tenant_record(None)

    def test_assert_cross_tenant_404(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        record = MagicMock(tenant_id=2)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            with pytest.raises(NotFound):
                assert_tenant_record(record)

    def test_assert_owner_no_tenant_on_record(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            assert assert_tenant_record(MagicMock(tenant_id=None), or_404=False) is True

    def test_tenant_get_or_404(self, app, mocker):
        record = MagicMock(tenant_id=1)
        mocker.patch("utils.tenanting.db.session.get", return_value=record)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from utils.tenanting import tenant_get_or_404

        with app.test_request_context():
            assert tenant_get_or_404(MagicMock, 5) is record

    def test_assign_tenant_id(self, app, mocker):
        mocker.patch("utils.tenanting.require_active_tenant_id", return_value=4)
        record = MagicMock(tenant_id=None)
        from utils.tenanting import assign_tenant_id

        with app.test_request_context():
            assign_tenant_id(record)
        assert record.tenant_id == 4


class TestScopedUserQuery:
    def test_scoped_user_query_tenant(self, mocker):
        user_model = MagicMock()
        user_model.query = MagicMock()
        user_model.is_owner = MagicMock()
        user_model.is_active = MagicMock()
        user_model.tenant_id = MagicMock()
        mocker.patch("models.user.User", user_model)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=2)
        from utils.tenanting import scoped_user_query

        scoped_user_query(_user(), active_only=True, exclude_owners=True)
        user_model.query.filter.assert_called()


class TestSetActiveTenant:
    def test_clear_active_tenant(self, app):
        from utils.tenanting import set_active_tenant, ACTIVE_TENANT_SESSION_KEY

        with app.test_request_context():
            from flask import session

            session[ACTIVE_TENANT_SESSION_KEY] = 1
            set_active_tenant(None, _user(is_owner=True))
            assert ACTIVE_TENANT_SESSION_KEY not in session

    def test_unauthenticated_rejected(self, app):
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="Unauthenticated"):
                set_active_tenant(1, _user(is_authenticated=False))

    def test_normal_user_wrong_tenant(self, app):
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="own tenant"):
                set_active_tenant(99, _user(tenant_id=1))

    def test_owner_sets_active_tenant(self, app, mocker):
        tenant = MagicMock(is_active=True, is_suspended=False)
        mocker.patch("utils.tenanting.db.session.get", return_value=tenant)
        from utils.tenanting import set_active_tenant, ACTIVE_TENANT_SESSION_KEY

        with app.test_request_context():
            from flask import session

            set_active_tenant(8, _user(is_owner=True))
            assert session[ACTIVE_TENANT_SESSION_KEY] == 8

    def test_inactive_tenant_rejected(self, app, mocker):
        mocker.patch("utils.tenanting.db.session.get", return_value=MagicMock(is_active=False))
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="not active"):
                set_active_tenant(1, _user(is_owner=True))

    def test_without_tenant_scope_flag(self, app):
        from utils.tenanting import without_tenant_scope

        with app.test_request_context():
            from flask import g

            g.skip_tenant_scope = False
            with without_tenant_scope():
                assert g.skip_tenant_scope is True
            assert g.skip_tenant_scope is False


class TestTenantStatus:
    def test_none_tenant_ok(self):
        from utils.tenanting import get_tenant_status

        assert get_tenant_status(None)["ok"] is True

    def test_missing_tenant(self, mocker):
        mocker.patch("utils.tenanting.db.session.get", return_value=None)
        from utils.tenanting import get_tenant_status

        status = get_tenant_status(1)
        assert status["ok"] is False
        assert status["suspended"] is True

    def test_suspended_tenant(self, mocker):
        tenant = MagicMock(is_active=True, is_suspended=True, suspension_reason="billing")
        mocker.patch("utils.tenanting.db.session.get", return_value=tenant)
        from utils.tenanting import get_tenant_status

        status = get_tenant_status(2)
        assert status["ok"] is False
        assert status["reason"] == "billing"


class TestTenantingExtended:
    def test_apply_tenant_scope_no_tenant_field(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        query = MagicMock()
        from utils.tenanting import apply_tenant_scope

        assert apply_tenant_scope(query, object()) is query

    def test_assert_tenant_record_or_404_false(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            assert assert_tenant_record(None, or_404=False) is False

    def test_assert_record_no_tenant_not_owner(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            with pytest.raises(NotFound):
                assert_tenant_record(MagicMock(tenant_id=None))

    def test_assert_no_active_tenant_owner(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            with pytest.raises(Forbidden):
                assert_tenant_record(MagicMock(tenant_id=1))

    def test_assert_cross_tenant_or_404_false(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            assert assert_tenant_record(MagicMock(tenant_id=2), or_404=False) is False

    def test_tenant_get_missing_or_404_false(self, app, mocker):
        mocker.patch("utils.tenanting.db.session.get", return_value=None)
        from utils.tenanting import tenant_get

        with app.test_request_context():
            assert tenant_get(MagicMock, 1, or_404=False) is None

    def test_assign_tenant_id_already_set(self, app):
        from utils.tenanting import assign_tenant_id

        record = MagicMock(tenant_id=9)
        with app.test_request_context():
            assert assign_tenant_id(record) is record

    def test_scoped_user_query_owner_no_tenant(self, mocker):
        user_model = MagicMock()
        user_model.query = MagicMock()
        mocker.patch("models.user.User", user_model)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        from utils.tenanting import scoped_user_query

        scoped_user_query(_user(is_owner=True))
        user_model.query.filter.assert_not_called()

    def test_require_report_tenant_id(self, app, mocker):
        mocker.patch("utils.tenanting.require_active_tenant_id", return_value=3)
        from utils.tenanting import require_report_tenant_id

        with app.test_request_context():
            assert require_report_tenant_id() == 3

    def test_set_active_tenant_invalid_id(self, app):
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="Invalid"):
                set_active_tenant("bad", _user(is_owner=True))

    def test_set_active_tenant_invalid_user_tenant_id(self, app):
        user = _user(tenant_id="bad")
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="valid integer"):
                set_active_tenant(1, user)

    def test_clear_active_tenant_helper(self, app):
        from utils.tenanting import clear_active_tenant, ACTIVE_TENANT_SESSION_KEY

        with app.test_request_context():
            from flask import session

            session[ACTIVE_TENANT_SESSION_KEY] = 5
            clear_active_tenant()
            assert ACTIVE_TENANT_SESSION_KEY not in session

    def test_resolve_user_current_user_failure(self, app):
        from unittest.mock import MagicMock, patch
        import utils.tenanting as tenanting

        proxy = MagicMock()
        proxy._get_current_object.side_effect = RuntimeError("no ctx")
        with app.test_request_context(), patch.object(tenanting, "current_user", proxy):
            assert tenanting._resolve_user() is None

    def test_resolve_user_anonymous_returns_none(self, app):
        from utils.tenanting import _resolve_user

        with app.test_request_context():
            assert _resolve_user() is None

    def test_require_active_tenant_id_success(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=5)
        from utils.tenanting import require_active_tenant_id

        assert require_active_tenant_id() == 5

    def test_assert_record_no_tenant_or_404_false(self, app, mocker):
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=1)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            assert assert_tenant_record(MagicMock(tenant_id=None), or_404=False) is False

    def test_assert_no_active_tenant_or_404_false(self, app, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        from utils.tenanting import assert_tenant_record

        with app.test_request_context():
            assert assert_tenant_record(MagicMock(tenant_id=1), or_404=False) is False

    def test_tenant_get_missing_aborts(self, app, mocker):
        mocker.patch("utils.tenanting.db.session.get", return_value=None)
        from utils.tenanting import tenant_get_or_404

        with app.test_request_context():
            with pytest.raises(NotFound):
                tenant_get_or_404(MagicMock, 1)

    def test_scoped_user_query_no_tenant_non_owner(self, mocker):
        user_model = MagicMock()
        user_model.query = MagicMock()
        user_model.tenant_id = _Col()
        mocker.patch("models.user.User", user_model)
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=False)
        from utils.tenanting import scoped_user_query

        result = scoped_user_query(_user(tenant_id=None))
        user_model.query.filter.assert_called_with(user_model.tenant_id < 0)
        assert result is user_model.query.filter.return_value

    def test_set_active_tenant_missing_user_tenant_id(self, app):
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="must have a tenant_id"):
                set_active_tenant(1, _user(tenant_id=None))

    def test_set_active_tenant_not_found(self, app, mocker):
        mocker.patch("utils.tenanting.db.session.get", return_value=None)
        from utils.tenanting import set_active_tenant

        with app.test_request_context():
            with pytest.raises(ValueError, match="not found"):
                set_active_tenant(1, _user(is_owner=True))

    def test_get_tenant_status_active(self, mocker):
        tenant = MagicMock(is_active=True, is_suspended=False)
        mocker.patch("utils.tenanting.db.session.get", return_value=tenant)
        from utils.tenanting import get_tenant_status

        status = get_tenant_status(3)
        assert status["ok"] is True
        assert status["suspended"] is False
