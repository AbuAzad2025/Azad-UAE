"""Coverage for routes/ai_routes/actions.py quick-colon cascade (part B).

Targets the cheque/user wizard residual arcs plus every quick-create
``if match`` / ``if len(parts)`` fallback side in the colon-command cascade.
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


def test_cheque_help_side(cov_user):
    """Arc 1675->1677: cheque wizard listener help side."""
    ctx = {"last_action": "شيك", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_cheque_step_mismatch_falls_through(cov_user):
    """Arc 1738->1789: cheque wizard option=1 with step not in (1..4)."""
    ctx = {"last_action": "شيك", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_cheque_step_four_success(cov_user):
    """Lines 1758-1762: cheque wizard step 4 happy path."""
    ctx = {
        "last_action": "شيك",
        "option": "1",
        "step": 4,
        "data": {"cheque_number": "123456", "amount": 5000.0, "cheque_type": "incoming"},
    }
    cheque = MagicMock(id=99)
    with patch(
        "services.cheque_service.ChequeService.create_cheque",
        return_value=cheque,
    ):
        result = _run("2025-12-31", cov_user, ctx)
    assert "تم إنشاء الشيك" in result


def test_user_help_side(cov_user):
    """Arc 1864->1866: user wizard listener help side."""
    ctx = {"last_action": "مستخدم", "option": "1", "step": 1, "data": {}}
    result = _run("مساعدة", cov_user, ctx)
    assert "مساعدة" in result


def test_user_step_mismatch_falls_through(cov_user):
    """Arc 1920->1970: user wizard option=1 with step not in (1..4)."""
    ctx = {"last_action": "مستخدم", "option": "1", "step": 99, "data": {}}
    assert _run("hello world", cov_user, ctx) is None


def test_colon_regex_nomatch_cascade(cov_user):
    """Arcs 2346->2378, 2380->2423, 2425->2460, 2462->2506, 2508->2539,
    2541->2577, 2589->2618, 2623->2662, 2674->2702, 2715->2772:
    every quick-create ``if match`` fallback side.
    """
    message = "عميل منتج مورد فاتورة مصروف دفعة رصيد استلام إعطاء عرض رصيد: x"
    with patch("re.search", return_value=None):
        assert _run(message, cov_user, {}) is None


def test_colon_customer_too_few_parts(cov_user):
    """Arc 2351->2378: customer quick-create with fewer than 2 parts."""
    assert _run("عميل: فقط", cov_user, {}) is None


def test_colon_product_too_few_parts(cov_user):
    """Arc 2385->2423: product quick-create with fewer than 3 parts."""
    assert _run("منتج: اسم فقط", cov_user, {}) is None


def test_colon_supplier_too_few_parts(cov_user):
    """Arc 2430->2460: supplier quick-create with fewer than 2 parts."""
    assert _run("مورد: اسم فقط", cov_user, {}) is None


def test_colon_sale_too_few_parts(cov_user):
    """Arc 2467->2506: sale quick-create with fewer than 3 parts."""
    assert _run("فاتورة: اسم فقط", cov_user, {}) is None


def test_colon_expense_too_few_parts(cov_user):
    """Arc 2513->2539: expense quick-create with fewer than 2 parts."""
    assert _run("مصروف: وصف فقط", cov_user, {}) is None


def test_colon_payment_too_few_parts(cov_user):
    """Arc 2546->2577: payment quick-create with fewer than 3 parts."""
    assert _run("دفعة: اسم فقط", cov_user, {}) is None


def test_colon_receive_too_few_parts(cov_user):
    """Arc 2628->2662: receive quick-create with fewer than 3 parts."""
    assert _run("استلام: اسم فقط", cov_user, {}) is None


def test_colon_give_too_few_parts(cov_user):
    """Arc 2720->2772: give quick-create with fewer than 3 parts."""
    assert _run("إعطاء: اسم فقط", cov_user, {}) is None


def test_colon_product_zero_quantity_skips_stock(cov_user):
    """Arc 2404->2410: product quick-create without quantity skips stock move."""
    product = MagicMock(id=78)
    with (
        patch(
            "services.product_service.ProductService.create_product",
            return_value=product,
        ),
        patch("routes.ai_routes.actions.StockService.add_opening_stock") as add_stock,
    ):
        result = _run("منتج: فلتر, PN1, 100", cov_user, {})
    assert "تم إنشاء المنتج" in result
    add_stock.assert_not_called()
