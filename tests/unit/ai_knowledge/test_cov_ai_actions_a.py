"""Coverage for routes/ai_routes/actions.py wizard fallthrough/help branches (part A).

Targets early guards plus the balance/customer/product/invoice/receive/give/
expense/supplier/purchase wizard residual lines and arcs.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from routes.ai_routes.actions import _process_user_action


@pytest.fixture
def cov_user():
    user = MagicMock()
    user.is_authenticated = True
    user.is_owner = False
    user.id = 42
    user.tenant_id = 1
    user.branch_id = None
    user.has_permission.return_value = True
    return user


@contextmanager
def _wizard_env(ctx, tid=1):
    with (
        patch("routes.ai_routes.actions._conversation_ctx", return_value=ctx),
        patch("routes.ai_routes.actions.get_active_tenant_id", return_value=tid),
        patch("routes.ai_routes.actions.train_local_ai"),
    ):
        yield


def _run(message, user, ctx, tid=1):
    with _wizard_env(ctx, tid):
        return _process_user_action(message, user)


def test_no_active_tenant(cov_user):
    """Line 74: get_active_tenant_id returns None."""
    result = _run("رصيد", cov_user, {}, tid=None)
    assert "تينانت" in result


def test_wizard_rbac_deny(cov_user):
    """Lines 97-98: wizard context without the required permission."""
    cov_user.has_permission.return_value = False
    result = _run("hello", cov_user, {"last_action": "رصيد"})
    assert "صلاحية" in result


def test_balance_step_mismatch_falls_through(cov_user):
    """Arc 196->235: balance wizard option=1 with step not in (1, 2)."""
    ctx = {"last_action": "رصيد", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_customer_help_unknown_step(cov_user):
    """Arc 553->556: customer help text with step outside 1/2/3."""
    ctx = {"last_action": "عميل", "option": "1", "step": 99, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "99" in result


def test_customer_step_mismatch_falls_through(cov_user):
    """Arc 596->649: customer wizard option=1 with step not in (1, 2, 3)."""
    ctx = {"last_action": "عميل", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_product_step_mismatch_falls_through(cov_user):
    """Arc 744->803: product wizard option=1 with step not in (1, 2, 3, 4)."""
    ctx = {"last_action": "منتج", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_product_zero_quantity_skips_opening_stock(cov_user):
    """Arc 758->764: product wizard step 4 with quantity 0 skips stock move."""
    ctx = {
        "last_action": "منتج",
        "option": "1",
        "step": 4,
        "data": {"name": "N", "part_number": "PN", "price": 10.0},
    }
    product = MagicMock(id=77)
    with (
        patch(
            "services.product_service.ProductService.create_product",
            return_value=product,
        ),
        patch("routes.ai_routes.actions.StockService.add_opening_stock") as add_stock,
    ):
        result = _run("0", cov_user, ctx)
    assert "تم إنشاء المنتج" in result
    add_stock.assert_not_called()


def test_invoice_help_side(cov_user):
    """Arc 822->824: invoice wizard listener help side (no ctx delete)."""
    ctx = {"last_action": "فاتورة", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_invoice_step_mismatch_falls_through(cov_user):
    """Arc 944->993: invoice wizard option=1 with step not in (1, 2, 3)."""
    ctx = {"last_action": "فاتورة", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_receive_help_side(cov_user):
    """Arc 1012->1014: receive-payment wizard listener help side."""
    ctx = {"last_action": "استلام", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_receive_step_mismatch_falls_through(cov_user):
    """Arc 1062->1116: receive wizard option=1 with step not in (1, 2, 3)."""
    ctx = {"last_action": "استلام", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_give_help_side(cov_user):
    """Arc 1135->1137: give-payment wizard listener help side."""
    ctx = {"last_action": "إعطاء", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_give_step_mismatch_falls_through(cov_user):
    """Arc 1185->1256: give wizard option=1 with step not in (1, 2, 3)."""
    ctx = {"last_action": "إعطاء", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_expense_help_side(cov_user):
    """Arc 1275->1277: expense wizard listener help side."""
    ctx = {"last_action": "مصروف", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_expense_step_mismatch_falls_through(cov_user):
    """Arc 1314->1365: expense wizard option=1 with step not in (1, 2, 3)."""
    ctx = {"last_action": "مصروف", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_supplier_help_side(cov_user):
    """Arc 1386->1388: supplier wizard listener help side."""
    ctx = {"last_action": "مورد", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_supplier_step_mismatch_falls_through(cov_user):
    """Arc 1458->1517: supplier wizard option=1 with step not in (1..5)."""
    ctx = {"last_action": "مورد", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_purchase_help_side(cov_user):
    """Arc 1536->1538: purchase wizard listener help side."""
    ctx = {"last_action": "مشتريات", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_purchase_step_mismatch_falls_through(cov_user):
    """Arc 1604->1656: purchase wizard option=1 with step not in (1..4)."""
    ctx = {"last_action": "مشتريات", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_purchase_step_four_success(cov_user):
    """Lines 1620-1628: purchase wizard step 4 happy path."""
    ctx = {
        "last_action": "مشتريات",
        "option": "1",
        "step": 4,
        "data": {
            "supplier_id": 1,
            "supplier_name": "S",
            "product_id": 2,
            "product_name": "P",
            "quantity": 5.0,
        },
    }
    purchase = MagicMock(id=88)
    with patch(
        "services.purchase_service.PurchaseService.create_quick_purchase",
        return_value=purchase,
    ):
        result = _run("40", cov_user, ctx)
    assert "تم إنشاء المشتريات" in result
