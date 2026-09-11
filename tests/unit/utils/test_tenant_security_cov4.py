"""Cov4: tenant_security decorators + decorators module gates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from utils.tenant_security import require_tenant_context, validate_tenant_ownership


def _app_ctx(app, tid=5):
    from flask import g

    g.active_tenant_id = tid


def test_validate_missing_id(app):
    with app.test_request_context("/"):
        _app_ctx(app, 5)

        @validate_tenant_ownership(MagicMock(__name__="Product"))
        def _view(product_id=None):
            return "ok"

        with pytest.raises(Exception):  # 65-66 400
            _view()


def test_validate_no_tenant_non_owner(app):
    with app.test_request_context("/"):
        from flask import g

        if hasattr(g, "active_tenant_id"):
            delattr(g, "active_tenant_id")

        @validate_tenant_ownership(MagicMock(__name__="Product"))
        def _view(product_id=None):
            return "ok"

        import flask_login

        with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=False, is_owner=False)):
            with patch("utils.tenanting.is_platform_owner", return_value=False):
                with pytest.raises(Exception):  # 74-75 404
                    _view(product_id=1)


def test_validate_resource_flows(app):
    with app.test_request_context("/"):
        _app_ctx(app, 5)
        model = SimpleNamespace(__name__="Product")

        @validate_tenant_ownership(model)
        def _view(product_id=None):
            return "ok"

        with patch("utils.tenant_security.db") as mdb:
            mdb.session.get.return_value = None
            with pytest.raises(Exception):  # 79-80 not found
                _view(product_id=1)
            mdb.session.get.return_value = SimpleNamespace(tenant_id=None)
            with patch("utils.tenanting.is_platform_owner", return_value=False):
                import flask_login

                with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=True)):
                    with pytest.raises(Exception):  # 88-89 no-tenant non-owner
                        _view(product_id=1)
            mdb.session.get.return_value = SimpleNamespace(tenant_id=6)
            with pytest.raises(Exception):  # 92-93 mismatch
                _view(product_id=1)
            mdb.session.get.return_value = SimpleNamespace(tenant_id=5)
            assert _view(product_id=1) == "ok"  # 96 happy


def test_validate_first_param_fallback(app):
    with app.test_request_context("/"):
        _app_ctx(app, 5)

        @validate_tenant_ownership(SimpleNamespace(__name__="X"))
        def _view(thing=None):
            return "ok"

        with patch("utils.tenant_security.db") as mdb:
            mdb.session.get.return_value = SimpleNamespace(tenant_id=5)
            assert _view(thing=9) == "ok"  # 61-63 fallback


def test_require_context(app):
    with app.test_request_context("/"):
        from flask import g

        g.active_tenant_id = 5

        @require_tenant_context
        def _v():
            return "ok"

        assert _v() == "ok"  # happy
        delattr(g, "active_tenant_id")

        @require_tenant_context
        def _v2():
            return "ok"

        import flask_login

        with patch.object(flask_login, "current_user", SimpleNamespace(is_authenticated=False)):
            with patch("utils.tenanting.is_platform_owner", return_value=True):
                assert _v2() == "ok"  # owner bypass 122-123
            with patch("utils.tenanting.is_platform_owner", return_value=False):
                with pytest.raises(Exception):  # 124-125 403
                    _v2()
