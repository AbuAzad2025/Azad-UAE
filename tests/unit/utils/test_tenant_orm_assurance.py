"""Tenant ORM scoping — criteria injection, session.get guard, scope gates."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestTenantScopeEnabled:
    def test_false_without_request_context(self):
        from utils.tenant_orm import tenant_scope_enabled

        assert tenant_scope_enabled() is False

    def test_false_when_skip_flag_on_g(self, app):
        from flask import g
        from utils.tenant_orm import tenant_scope_enabled

        with app.test_request_context("/"):
            g.skip_tenant_scope = True
            assert tenant_scope_enabled() is False

    def test_false_for_static_endpoint(self, app, mocker):
        mocker.patch("flask_login.utils._get_user")
        from utils.tenant_orm import tenant_scope_enabled

        with app.test_request_context("/"):
            mocker.patch("utils.tenant_orm.request").endpoint = "static"
            assert tenant_scope_enabled() is False

    def test_false_for_skip_blueprint(self, app, mocker):
        mocker.patch("utils.tenant_orm.has_request_context", return_value=True)
        req = mocker.patch("utils.tenant_orm.request")
        req.endpoint = "auth.login"
        req.blueprint = "auth"
        mocker.patch("flask_login.utils._get_user")
        from utils.tenant_orm import tenant_scope_enabled

        assert tenant_scope_enabled() is False

    def test_false_for_unauthenticated_user(self, app, mocker):
        user = MagicMock(is_authenticated=False)
        mocker.patch("flask_login.utils._get_user", return_value=user)
        from utils.tenant_orm import tenant_scope_enabled

        with app.test_request_context("/"):
            mocker.patch("utils.tenant_orm.request").endpoint = "sales.index"
            mocker.patch("utils.tenant_orm.request").blueprint = "sales"
            assert tenant_scope_enabled() is False

    def test_true_for_authenticated_tenant_user(self, app, mocker):
        user = MagicMock(is_authenticated=True)
        mocker.patch("flask_login.utils._get_user", return_value=user)
        from utils.tenant_orm import tenant_scope_enabled

        with app.test_request_context("/"):
            mocker.patch("utils.tenant_orm.request").endpoint = "sales.index"
            mocker.patch("utils.tenant_orm.request").blueprint = "sales"
            assert tenant_scope_enabled() is True


class TestActiveTenantShim:
    def test_active_tenant_for_orm(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=42)
        from utils.tenant_orm import _active_tenant_for_orm

        assert _active_tenant_for_orm() == 42


class TestCriteriaAndValidation:
    def test_criteria_none_tenant_impossible_match(self):
        from utils.tenant_orm import _criteria_for_model

        class _Col:
            def __lt__(self, other):
                return self

        class M:
            tenant_id = _Col()

        crit = _criteria_for_model(None)
        assert crit(M) is M.tenant_id

    def test_criteria_matches_active_tenant(self):
        from utils.tenant_orm import _criteria_for_model

        class M:
            tenant_id = 7

        crit = _criteria_for_model(7)
        assert crit(M) == (M.tenant_id == 7)


class TestOrmExecuteListener:
    def test_skips_non_select(self):
        from utils.tenant_orm import _inject_tenant_criteria

        state = MagicMock(is_select=False)
        _inject_tenant_criteria(state)
        state.statement.options.assert_not_called()

    def test_skips_when_scope_disabled(self, mocker):
        from utils.tenant_orm import _inject_tenant_criteria

        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=False)
        state = MagicMock(is_select=True)
        _inject_tenant_criteria(state)
        state.statement.options.assert_not_called()

    def test_skips_with_execution_option(self, mocker):
        from utils.tenant_orm import _inject_tenant_criteria

        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        state = MagicMock(is_select=True, execution_options={"skip_tenant_scope": True})
        _inject_tenant_criteria(state)
        state.statement.options.assert_not_called()

    def test_injects_criteria_when_enabled(self, mocker):
        from utils.tenant_orm import _inject_tenant_criteria

        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=3)
        mocker.patch(
            "utils.tenant_orm._discover_tenant_models", return_value=[MagicMock()]
        )
        stmt = MagicMock()
        stmt.options.return_value = "patched"
        state = MagicMock(is_select=True, statement=stmt, execution_options={})
        _inject_tenant_criteria(state)
        assert state.statement == "patched"


class TestDiscoveryAndRegistration:
    def test_discover_caches_models(self, mocker):
        import utils.tenant_orm as torm

        torm._TENANT_MODELS = None
        mapper = MagicMock()
        mapper.class_.__tablename__ = "sales"
        mapper.class_.__name__ = "Sale"
        mapper.columns = {"tenant_id": object()}
        registry = MagicMock()
        registry.mappers = [mapper]
        mocker.patch.object(torm.db.Model, "registry", registry, create=True)
        models = torm._discover_tenant_models()
        assert models == [mapper.class_]
        assert torm._discover_tenant_models() is models

    def test_discover_swallows_registry_errors(self, mocker):
        import utils.tenant_orm as torm

        torm._TENANT_MODELS = None

        class _BrokenRegistry:
            @property
            def mappers(self):
                raise RuntimeError("registry unavailable")

        mocker.patch.object(torm.db.Model, "registry", _BrokenRegistry(), create=True)
        assert torm._discover_tenant_models() == []

    def test_register_discovers_models(self, app, mocker):
        import utils.tenant_orm as torm

        torm._TENANT_MODELS = None
        spy = mocker.patch.object(torm, "_discover_tenant_models", return_value=[])
        torm.register_tenant_orm_scoping(app)
        assert spy.called

    def test_shims_delegate(self, mocker):
        mocker.patch("utils.tenanting.tenant_query", return_value="q")
        mocker.patch("utils.tenanting.model_has_tenant", return_value=True)
        from utils.tenant_orm import tenant_query, model_has_tenant

        assert tenant_query("Model") == "q"
        assert model_has_tenant("Model") is True

    def test_discover_skips_tenants_and_exempt_models(self, mocker):
        import utils.tenant_orm as torm

        torm._TENANT_MODELS = None
        tenant_mapper = MagicMock()
        tenant_mapper.class_.__tablename__ = "tenants"
        tenant_mapper.class_.__name__ = "Tenant"
        user_mapper = MagicMock()
        user_mapper.class_.__tablename__ = "users"
        user_mapper.class_.__name__ = "User"
        user_mapper.columns = {"tenant_id": object()}
        sale_mapper = MagicMock()
        sale_mapper.class_.__tablename__ = "sales"
        sale_mapper.class_.__name__ = "Sale"
        sale_mapper.columns = {"tenant_id": object()}
        registry = MagicMock()
        registry.mappers = [tenant_mapper, user_mapper, sale_mapper]
        mocker.patch.object(torm.db.Model, "registry", registry, create=True)
        assert torm._discover_tenant_models() == [sale_mapper.class_]

    def test_criteria_model_without_tenant_id(self):
        from utils.tenant_orm import _criteria_for_model

        class Plain:
            pass

        crit = _criteria_for_model(1)
        assert crit(Plain) is not None


class TestValidateInstanceTenant:
    def test_none_returns_true(self):
        from utils.tenant_orm import _validate_instance_tenant

        assert _validate_instance_tenant(None) is True

    def test_exempt_model_returns_true(self):
        from utils.tenant_orm import _validate_instance_tenant

        class User:
            __name__ = "User"

        assert _validate_instance_tenant(User()) is True

    def test_model_no_tenant_id_returns_true(self):
        from utils.tenant_orm import _validate_instance_tenant

        class Plain:
            pass

        assert _validate_instance_tenant(Plain()) is True

    def test_tenant_id_matches_active(self, mocker):
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=5)
        mock_mapper = mocker.MagicMock()
        mock_mapper.columns = {"tenant_id": object()}
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mock_mapper)
        from utils.tenant_orm import _validate_instance_tenant

        class M:
            __name__ = "Sale"

        m = M()
        m.tenant_id = 5
        assert _validate_instance_tenant(m) is True

    def test_tenant_id_mismatch_returns_false(self, mocker):
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=5)
        mock_mapper = mocker.MagicMock()
        mock_mapper.columns = {"tenant_id": object()}
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mock_mapper)
        from utils.tenant_orm import _validate_instance_tenant

        class M:
            __name__ = "Sale"

        m = M()
        m.tenant_id = 99
        assert _validate_instance_tenant(m) is False


class TestPatchSessionGet:
    def test_patches_session_get(self):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        torm._patch_session_get()
        assert torm._SESSION_GET_PATCHED is True
        # Second call should be a no-op
        torm._patch_session_get()
        assert torm._SESSION_GET_PATCHED is True

    def test_get_with_tenant_exempt_model(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        mock_obj = mocker.Mock(__name__="User")
        orig_get = mocker.Mock(return_value=mock_obj)
        mocker.patch.object(torm.Session, "get", orig_get)
        torm._patch_session_get()

        entity = mocker.Mock(__name__="User")
        result = torm.Session.get(mocker.Mock(), entity, 1)
        assert result is mock_obj

    def test_get_with_tenant_skip_scope_option(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        mock_obj = mocker.Mock(__name__="Branch")
        mock_obj.tenant_id = 5
        orig_get = mocker.Mock(return_value=mock_obj)
        mocker.patch.object(torm.Session, "get", orig_get)
        torm._patch_session_get()

        entity = mocker.Mock(__name__="Branch")
        result = torm.Session.get(
            mocker.Mock(), entity, 1, execution_options={"skip_tenant_scope": True}
        )
        assert result is mock_obj

    def test_get_with_tenant_validated_ok(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        mock_obj = mocker.Mock(__name__="Branch")
        mock_obj.tenant_id = 5
        orig_get = mocker.Mock(return_value=mock_obj)
        mocker.patch.object(torm.Session, "get", orig_get)
        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        mocker.patch("utils.tenant_orm._validate_instance_tenant", return_value=True)
        torm._patch_session_get()

        entity = mocker.Mock(__name__="Branch")
        result = torm.Session.get(mocker.Mock(), entity, 1)
        assert result is mock_obj

    def test_get_with_tenant_validated_rejected(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        mock_obj = mocker.Mock(__name__="Branch")
        mock_obj.tenant_id = 99
        orig_get = mocker.Mock(return_value=mock_obj)
        mocker.patch.object(torm.Session, "get", orig_get)
        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        mocker.patch("utils.tenant_orm._validate_instance_tenant", return_value=False)
        torm._patch_session_get()

        entity = mocker.Mock(__name__="Branch")
        result = torm.Session.get(mocker.Mock(), entity, 1)
        assert result is None

    def test_login_import_failure_in_scope(self, mocker):
        mocker.patch("utils.tenant_orm.has_request_context", return_value=True)
        req = mocker.patch("utils.tenant_orm.request")
        req.endpoint = "sales.index"
        req.blueprint = "sales"
        mocker.patch(
            "utils.tenant_orm.getattr",
            side_effect=lambda obj, name, default=False: default,
        )
        mocker.patch.dict("sys.modules", {"flask_login": None})
        from utils.tenant_orm import tenant_scope_enabled

        assert tenant_scope_enabled() is False
