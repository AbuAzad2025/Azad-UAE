"""Tenant ORM scoping — criteria injection, session.get guard, scope gates."""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.orm import Session


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

    def test_validate_none_is_ok(self):
        from utils.tenant_orm import _validate_instance_tenant

        assert _validate_instance_tenant(None) is True

    def test_validate_exempt_user_model(self):
        from utils.tenant_orm import _validate_instance_tenant

        user = MagicMock()
        user.__class__.__name__ = "User"
        assert _validate_instance_tenant(user) is True

    def test_validate_no_tenant_column(self, mocker):
        from utils.tenant_orm import _validate_instance_tenant

        obj = MagicMock()
        obj.__class__.__name__ = "Plain"
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=None)
        assert _validate_instance_tenant(obj) is True

    def test_validate_platform_owner_null_tenant_record(self, mocker):
        from utils.tenant_orm import _validate_instance_tenant

        obj = MagicMock(tenant_id=None)
        obj.__class__.__name__ = "Sale"
        mapper = MagicMock()
        mapper.columns = {"tenant_id": object()}
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mapper)
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=1)
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)
        assert _validate_instance_tenant(obj) is True

    def test_validate_mismatch_returns_false(self, mocker):
        from utils.tenant_orm import _validate_instance_tenant

        obj = MagicMock(tenant_id=2)
        obj.__class__.__name__ = "Sale"
        mapper = MagicMock()
        mapper.columns = {"tenant_id": object()}
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mapper)
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=1)
        assert _validate_instance_tenant(obj) is False

    def test_validate_no_active_tenant(self, mocker):
        from utils.tenant_orm import _validate_instance_tenant

        obj = MagicMock(tenant_id=1)
        obj.__class__.__name__ = "Sale"
        mapper = MagicMock()
        mapper.columns = {"tenant_id": object()}
        mocker.patch("utils.tenant_orm.sa_inspect", return_value=mapper)
        mocker.patch("utils.tenant_orm._active_tenant_for_orm", return_value=None)
        assert _validate_instance_tenant(obj) is False


class TestSessionGetPatch:
    def test_cross_tenant_get_returns_none(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        obj = MagicMock(tenant_id=99)
        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        mocker.patch("utils.tenant_orm._validate_instance_tenant", return_value=False)
        mocker.patch.object(Session, "get", return_value=obj)
        torm._patch_session_get()
        session = object.__new__(Session)
        assert session.get("Sale", 1) is None
        torm._SESSION_GET_PATCHED = False

    def test_skip_scope_execution_option(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        obj = MagicMock()
        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        mocker.patch("utils.tenant_orm._validate_instance_tenant", return_value=False)
        mocker.patch.object(Session, "get", return_value=obj)
        torm._patch_session_get()
        session = object.__new__(Session)
        result = session.get("Sale", 1, execution_options={"skip_tenant_scope": True})
        assert result is obj
        torm._SESSION_GET_PATCHED = False


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

    def test_register_logs_and_patches(self, app, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        torm._TENANT_MODELS = []
        mocker.patch.object(torm, "_discover_tenant_models", return_value=[])
        mocker.patch.object(torm, "_patch_session_get")
        torm.register_tenant_orm_scoping(app)
        torm._patch_session_get.assert_called_once()

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

    def test_session_get_returns_obj_when_scope_disabled(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        obj = MagicMock()
        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=False)
        mocker.patch.object(Session, "get", return_value=obj)
        torm._patch_session_get()
        session = object.__new__(Session)
        assert session.get("Sale", 1) is obj
        torm._SESSION_GET_PATCHED = False

    def test_session_get_returns_obj_when_valid(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = False
        obj = MagicMock()
        mocker.patch("utils.tenant_orm.tenant_scope_enabled", return_value=True)
        mocker.patch("utils.tenant_orm._validate_instance_tenant", return_value=True)
        mocker.patch.object(Session, "get", return_value=obj)
        torm._patch_session_get()
        session = object.__new__(Session)
        assert session.get("Sale", 1) is obj
        torm._SESSION_GET_PATCHED = False

    def test_patch_session_get_idempotent(self, mocker):
        import utils.tenant_orm as torm

        torm._SESSION_GET_PATCHED = True
        mocker.patch.object(Session, "get")
        torm._patch_session_get()
        torm._SESSION_GET_PATCHED = False

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
