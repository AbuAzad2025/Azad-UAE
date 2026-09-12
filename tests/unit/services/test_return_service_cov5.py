"""Cov5: return_service — validation guards, MWAC error, flush failure, scoped/search arcs."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError


def _user(tenant_id=1, seller=False, authenticated=True):
    u = MagicMock()
    u.is_authenticated = authenticated
    u.id = 10
    u.tenant_id = tenant_id
    u.is_seller = MagicMock(return_value=seller)
    return u


def _sale(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", 100)
    s.tenant_id = kwargs.get("tenant_id", 1)
    s.branch_id = kwargs.get("branch_id", 2)
    s.warehouse_id = kwargs.get("warehouse_id", 3)
    s.status = kwargs.get("status", "confirmed")
    s.customer_id = kwargs.get("customer_id", 5)
    s.customer = kwargs.get("customer", MagicMock())
    s.currency = "AED"
    s.exchange_rate = Decimal("1")
    s.sale_number = "S-001"
    s.subtotal = kwargs.get("subtotal", Decimal("100"))
    s.discount_amount = kwargs.get("discount_amount", Decimal("0"))
    s.shipping_cost = kwargs.get("shipping_cost", Decimal("0"))
    s.tax_rate = kwargs.get("tax_rate", Decimal("5"))
    s.seller_id = kwargs.get("seller_id", 10)
    s.recalculate_payment_status = MagicMock()
    return s


def _sale_line(**kwargs):
    sl = MagicMock()
    sl.id = kwargs.get("id", 200)
    sl.sale_id = kwargs.get("sale_id", 100)
    sl.tenant_id = kwargs.get("tenant_id", 1)
    sl.product_id = kwargs.get("product_id", 50)
    sl.quantity = kwargs.get("quantity", Decimal("1"))
    sl.line_total = kwargs.get("line_total", Decimal("100"))
    sl.cost_price = kwargs.get("cost_price", Decimal("40"))
    sl.product = kwargs.get("product")
    return sl


def _product(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 50)
    p.name = kwargs.get("name", "Widget")
    p.has_serial_number = kwargs.get("has_serial_number", False)
    p.cost_price = kwargs.get("cost_price", Decimal("30"))
    return p


def _patch_common(mocker, sale, sale_line, product):
    session = mocker.patch("services.return_service.db.session")
    session.get.side_effect = lambda model, pk: {sale.id: sale, sale_line.id: sale_line}.get(pk)
    session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal(
        "0"
    )
    mocker.patch("services.return_service.generate_number", return_value="R-001")
    mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
    mocker.patch("services.return_service.is_platform_owner", return_value=False)
    mocker.patch("services.return_service.branch_scope_id_for", return_value=None)
    mocker.patch("services.return_service.should_post_vat_gl", return_value=True)
    mocker.patch("services.return_service.StockService.create_movement")
    mocker.patch(
        "services.return_service.GLService.get_account_code_for_concept",
        return_value="4100",
    )
    mocker.patch(
        "services.return_service.GLService.get_customer_credit_account",
        return_value="1130",
    )
    mocker.patch(
        "services.return_service.GLService.get_customer_credit_concept",
        return_value="AR",
    )
    mocker.patch("services.return_service.GLService.ensure_core_accounts")
    mocker.patch("services.return_service.post_or_fail")
    sale_line.product = product
    return session


def _approve(mocker, sale, line, product, app):
    _patch_common(mocker, sale, line, product)
    from services.return_service import ReturnService

    with app.app_context():
        return ReturnService.create_return(
            sale.id, [{"sale_line_id": line.id, "quantity": 1, "condition": "good"}], user=_user()
        )


def test_product_not_found(app, mocker):
    sale = _sale()
    line = _sale_line(product=None)
    session = _patch_common(mocker, sale, line, None)
    session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(ValueError, match="not found"):
        ReturnService.create_return(sale.id, [{"sale_line_id": line.id, "quantity": 1}], user=_user())


def test_serial_fractional_quantity_raises(app, mocker):
    sale = _sale()
    product = _product(has_serial_number=True)
    line = _sale_line(product=product)
    _patch_common(mocker, sale, line, product)
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(ValueError, match="whole-number"):
        ReturnService.create_return(
            sale.id, [{"sale_line_id": line.id, "quantity": "0.5", "serials": ["S1"]}], user=_user()
        )


def test_serial_unlinked_raises(app, mocker):
    sale = _sale()
    product = _product(has_serial_number=True)
    line = _sale_line(product=product)
    _patch_common(mocker, sale, line, product)
    mocker.patch("utils.serial_helpers.validate_serials")
    mocker.patch("services.return_service.ProductSerial.query").filter_by.return_value.first.return_value = None
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(ValueError, match="not linked"):
        ReturnService.create_return(
            sale.id, [{"sale_line_id": line.id, "quantity": 1, "serials": ["S1"]}], user=_user()
        )


def test_serial_not_sold_raises(app, mocker):
    sale = _sale()
    product = _product(has_serial_number=True)
    line = _sale_line(product=product)
    _patch_common(mocker, sale, line, product)
    mocker.patch("utils.serial_helpers.validate_serials")
    mocker.patch(
        "services.return_service.ProductSerial.query"
    ).filter_by.return_value.first.return_value = MagicMock(status="available")
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(ValueError, match="not sold"):
        ReturnService.create_return(
            sale.id, [{"sale_line_id": line.id, "quantity": 1, "serials": ["S1"]}], user=_user()
        )


def test_zero_sold_qty_raises(app, mocker):
    sale = _sale()
    line = _sale_line()
    product = _product()
    line.product = product
    _patch_common(mocker, sale, line, product)
    mocker.patch("services.return_service.ReturnService._sale_line_sold_qty", return_value=Decimal("0"))
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(ValueError, match="Invalid sale line quantity"):
        ReturnService.create_return(sale.id, [{"sale_line_id": line.id, "quantity": 1}], user=_user())


def test_mwac_operational_error_reraises(app, mocker):
    sale = _sale()
    line = _sale_line(cost_price=Decimal("40"))
    product = _product()
    line.product = product
    _patch_common(mocker, sale, line, product)
    mocker.patch("services.return_service.current_app.config.get", return_value=True)
    pwc = MagicMock(
        total_quantity=Decimal("10"),
        total_value=Decimal("400"),
        average_cost=Decimal("40"),
    )
    pwc_q = MagicMock()
    pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = pwc
    mocker.patch("models.ProductWarehouseCost.query", pwc_q)
    mocker.patch("models.ProductCostHistory")
    mocker.patch(
        "services.return_service.StockService._mwac_calc",
        side_effect=OperationalError("stmt", {}, Exception("lock")),
    )
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(OperationalError):
        ReturnService.create_return(
            sale.id, [{"sale_line_id": line.id, "quantity": 1, "condition": "good"}], user=_user()
        )


def test_final_flush_failure_reraises(app, mocker):
    sale = _sale()
    line = _sale_line()
    product = _product()
    line.product = product
    session = _patch_common(mocker, sale, line, product)
    session.flush.side_effect = [None, RuntimeError("late flush")]
    from services.return_service import ReturnService

    with app.app_context(), pytest.raises(RuntimeError, match="late flush"):
        ReturnService.create_return(
            sale.id, [{"sale_line_id": line.id, "quantity": 1, "condition": "good"}], user=_user()
        )


def test_scoped_query_owner_no_tenant(mocker):
    mocker.patch("services.return_service.get_active_tenant_id", return_value=None)
    mocker.patch("services.return_service.is_platform_owner", return_value=True)
    from services.return_service import ReturnService

    q = ReturnService.get_scoped_returns_query(MagicMock())
    assert q is not None


def test_scoped_query_seller_and_branch(mocker):
    mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
    mocker.patch("services.return_service.is_platform_owner", return_value=False)
    from services.return_service import ReturnService

    user = _user(seller=True)
    q = ReturnService.get_scoped_returns_query(user, scoped_branch_id=99)
    assert q is not None


def test_search_non_digit_query(mocker):
    fq = MagicMock()
    fq.filter.return_value.order_by.return_value.paginate.return_value.items = []
    mocker.patch("utils.tenanting.tenant_query", return_value=fq)
    from services.return_service import ReturnService

    items, _ = ReturnService.search_sales_for_return("ABC", 1, 10, MagicMock())
    assert items == []
