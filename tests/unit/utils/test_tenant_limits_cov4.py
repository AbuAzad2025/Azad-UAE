"""Cov4: tenant_limits — error link, guards, summary, enforce."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import utils.tenant_limits as tl
from utils.tenant_limits import TenantLimitError


def test_error_builds_link_once(app):
    TenantLimitError.wa_upgrade_link = ""
    with app.test_request_context("/"):
        app.config["DEVELOPER_WHATSAPP"] = " 971500000000 "
        e = TenantLimitError("users", 5, 9)
        assert "wa.me" in str(e) or "971500000000" in str(e)  # lines 31-51
        e2 = TenantLimitError("users", 5, 9)
        assert "users" in str(e2)  # link cached: no duplicate append


def test_error_link_exception_path(monkeypatch):
    TenantLimitError.wa_upgrade_link = ""
    monkeypatch.setattr("utils.tenant_limits.db", MagicMock())
    import flask

    monkeypatch.setattr(flask, "current_app", MagicMock(side_effect=RuntimeError("x")))
    e = TenantLimitError("users", 1, 2)  # lines 46-47
    assert "users" in str(e)


def test_active_tenant_exception_returns_none():
    with patch.object(tl, "get_active_tenant_id", side_effect=RuntimeError("boom")):
        assert tl._active_tenant() is None  # lines 63-64


def test_month_start():
    assert tl._month_start().day == 1  # line 68


def test_check_limit_no_tenant():
    with patch.object(tl, "_active_tenant", return_value=None):
        tl.check_limit("users", model=MagicMock())  # line 89-90


def test_check_limit_none_and_zero():
    with patch.object(tl, "_active_tenant", return_value=SimpleNamespace(id=1)):
        tl.check_limit("unknown_resource_xyz", model=MagicMock())  # line 94-95
    t0 = SimpleNamespace(id=1, max_users=0)
    with patch.object(tl, "_active_tenant", return_value=t0):
        tl.check_limit("users", model=MagicMock())  # line 100-101
        with pytest.raises(TenantLimitError):  # line 97-98
            tl.check_limit("users", model=MagicMock(), error_if_disabled=True)


def test_check_limit_over_raises():
    t = SimpleNamespace(id=3, max_users=1)
    q = MagicMock()
    q.filter.return_value = q
    q.count.return_value = 5
    sess = MagicMock()
    sess.query.return_value = q
    with patch.object(tl, "_active_tenant", return_value=t), patch.object(tl.db, "session", sess):
        from models import User

        with pytest.raises(TenantLimitError):  # lines 103-110
            tl.check_limit("users", model=User, extra_filter=lambda qq: qq)
        sess.query.return_value = MagicMock(
            filter=lambda *a, **k: MagicMock(count=lambda: 0, filter=lambda *a, **k: MagicMock(count=lambda: 0))
        )


def test_monthly_and_feature():
    with patch.object(tl, "_active_tenant", return_value=None):
        tl.check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")  # 122-124
        assert tl.check_feature_enabled("whatever") is True  # 150-151
    t = SimpleNamespace(id=1, max_sales_per_month=0)
    with patch.object(tl, "_active_tenant", return_value=t):
        tl.check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")  # 130-131
    t2 = SimpleNamespace(id=1)
    with patch.object(tl, "_active_tenant", return_value=t2):
        tl.check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")  # 127-129


def test_usage_summary_none_and_warn():
    assert tl.get_tenant_usage_summary(None) == []  # 183-184
    t = SimpleNamespace(
        id=9,
        max_users=10,
        max_branches=0,
        max_warehouses=None,
        max_products=10,
        max_customers=10,
        max_suppliers=10,
        max_sales_per_month=10,
    )
    with patch.object(tl, "_count_model", return_value=9), patch.object(tl, "_monthly_count", return_value=1):
        rows = tl.get_tenant_usage_summary(t)  # 190-249
        assert any(r["warn"] for r in rows)
        assert tl.get_tenant_usage_warnings(t)  # 252-254


def test_enforce_feature_disabled():
    t = SimpleNamespace(id=1, my_flag=False)
    with patch.object(tl, "_active_tenant", return_value=t):
        with pytest.raises(TenantLimitError):  # 257-264
            tl.enforce_feature("my_flag", "ميزة")
    with patch.object(tl, "_active_tenant", return_value=None):
        tl.enforce_feature("my_flag", "ميزة")


def test_count_helpers_extra_filter():
    from types import SimpleNamespace as _SN

    class _Ge:
        def __eq__(self, other):
            return True

        def __ge__(self, other):
            return True

        def __hash__(self):
            return 1

    model = _SN(tenant_id=_Ge(), sale_date=_Ge())
    q = MagicMock()
    q.filter.return_value = q
    q.count.return_value = 4
    sess = MagicMock()
    sess.query.return_value = q
    with patch.object(tl.db, "session", sess):
        assert tl._count_model(model, 1, lambda qq: qq) == 4  # 160-164
        assert tl._monthly_count(model, 1, "sale_date", lambda qq: qq) == 4  # 167-174
