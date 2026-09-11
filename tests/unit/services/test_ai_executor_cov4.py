"""Cov4: ai_executor — guards + CRUD/list/summary/number/factory arcs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.ai_executor import AIExecutor, AIExecutorError, get_ai_executor


def _executor(tid, user=None):
    user = user or SimpleNamespace(id=7, tenant_id=tid, branch_id=None)
    with patch("services.ai_executor.get_active_tenant_id", return_value=tid):
        return AIExecutor(user=user)


def test_init_and_guards(sample_tenant):
    ex = _executor(sample_tenant.id)
    assert ex._require_tenant() == sample_tenant.id
    assert ex._current_user_id() == 7
    assert ex._require_user_id() == 7
    assert ex._current_branch_id() is None
    with patch("services.ai_executor.get_active_tenant_id", return_value=None):
        ex2 = AIExecutor(user=SimpleNamespace(id=1))
        with pytest.raises(AIExecutorError):
            ex2._require_tenant()
    ex3 = AIExecutor(user=SimpleNamespace())
    with pytest.raises(AIExecutorError):
        ex3._require_user_id()


def test_customer_crud(db_session, sample_tenant):
    ex = _executor(sample_tenant.id)
    with pytest.raises(AIExecutorError):
        ex.create_customer("")
    out = ex.create_customer("Cov4 Customer", phone="0501", email="c@x.y")
    assert out["success"] is True
    listed = ex.list_customers()
    assert listed["count"] >= 1
    listed2 = ex.list_customers(search="Cov4 Customer")
    assert listed2["count"] >= 1
    assert ex.list_customers(search="no-such-name-zzz")["count"] == 0
    bal = ex.get_customer_balance("Cov4 Customer")
    assert bal["balance"] == 0.0
    with pytest.raises(AIExecutorError):
        ex.get_customer_balance("Ghost Customer")


def test_product_crud_and_stock(db_session, sample_tenant):
    ex = _executor(sample_tenant.id)
    with pytest.raises(AIExecutorError):
        ex.create_product("")
    with pytest.raises(AIExecutorError):
        ex.create_product("P", regular_price=0)
    out = ex.create_product("Cov4 Widget", sku="COV4-W", regular_price=50,
                            cost_price=20, current_stock=3, min_stock_alert=10)
    assert out["success"] is True
    assert ex.list_products(search="Cov4 Widget")["count"] >= 1
    stock = ex.check_stock()
    assert stock["success"] is True
    assert any(r["name"] == "Cov4 Widget" for r in stock["low_stock"])


def test_create_sale_validation_branches(db_session, sample_tenant, sample_customer):
    ex = _executor(sample_tenant.id)
    with pytest.raises(AIExecutorError):
        ex.create_sale("Ghost", [{"name": "X", "quantity": 1}])
    with pytest.raises(AIExecutorError):
        ex.create_sale(sample_customer.name, [{"name": "Ghost Product", "quantity": 1}])


def test_receive_payment_branches(db_session, sample_tenant, sample_customer):
    ex = _executor(sample_tenant.id)
    with pytest.raises(AIExecutorError):
        ex.receive_payment("Ghost", 10)
    with pytest.raises(AIExecutorError):
        ex.receive_payment(sample_customer.name, 0)
    out = ex.receive_payment(sample_customer.name, 25, method="cash")
    assert out["success"] is True
    assert out["payment_number"].startswith("PAY")


def test_expense_supplier_employee_branches(db_session, sample_tenant):
    ex = _executor(sample_tenant.id)
    with pytest.raises(AIExecutorError):
        ex.add_expense("", 10)
    with pytest.raises(AIExecutorError):
        ex.add_expense("desc", 0)
    with pytest.raises(AIExecutorError):
        ex.add_expense("desc", 10)  # no category branch
    from models import ExpenseCategory

    cat = ExpenseCategory(tenant_id=sample_tenant.id, name="Cov4Cat")
    db_session.add(cat)
    db_session.flush()
    out = ex.add_expense("Cov4 expense", 12.5, category_id=cat.id)
    assert out["success"] is True
    with pytest.raises(AIExecutorError):
        ex.create_supplier("")
    assert ex.create_supplier("Cov4 Supplier")["success"] is True
    with pytest.raises(AIExecutorError):
        ex.create_employee("")
    assert ex.create_employee("Cov4 Emp", basic_salary=1000)["success"] is True


def test_purchase_branches(db_session, sample_tenant):
    from models import Supplier

    ex = _executor(sample_tenant.id)
    with pytest.raises(AIExecutorError):
        ex.create_purchase("Ghost Supplier", [])
    sup = Supplier(tenant_id=sample_tenant.id, name="Cov4 PS", is_active=True)
    db_session.add(sup)
    db_session.flush()
    with pytest.raises(AIExecutorError):
        ex.create_purchase("Cov4 PS", [])  # no warehouse branch
    with pytest.raises(AIExecutorError):
        ex.create_purchase("Cov4 PS", [{"name": "Ghost P"}])


def test_summaries_and_numbers_and_factory(db_session, sample_tenant):
    ex = _executor(sample_tenant.id)
    s = ex.sales_summary()
    assert s["success"] is True and s["count"] >= 0
    p = ex.profit_summary()
    assert p["success"] is True
    assert p["margin_percent"] == 0
    n = AIExecutor._generate_number("PAY", MagicMock())
    assert isinstance(n, str) and n
    with patch("utils.helpers.generate_number", side_effect=RuntimeError("x")):
        n2 = AIExecutor._generate_number("PAY", MagicMock())
        assert n2.startswith("PAY-")
    u = SimpleNamespace(id=424242)
    a = get_ai_executor(user=u)
    b = get_ai_executor(user=u)
    assert a is b  # cache-hit arc
    c = get_ai_executor(user=SimpleNamespace())
    assert isinstance(c, AIExecutor)  # no-id arc
