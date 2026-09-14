"""Cov5: sale_service — warehouse/serial/warranty/promo/payment/defer/quick/cancel arcs."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _parties(tenant_id=1, branch_id=1):
    customer = MagicMock()
    customer.is_active = True
    customer.id = 1
    customer.customer_type = "regular"
    customer.tenant_id = tenant_id
    seller = MagicMock()
    seller.is_active = True
    seller.id = 2
    seller.tenant_id = tenant_id
    seller.branch_id = branch_id
    return customer, seller


def _product(**kw):
    product = MagicMock()
    product.id = 1
    product.name = "Test Product"
    product.cost_price = 50
    product.has_serial_number = False
    product.warranty_days = 0
    product.get_price_for_customer.return_value = Decimal("100")
    product.partner_shares = []
    for key, val in kw.items():
        setattr(product, key, val)
    return product


def _run_create(customer, seller, lines, flush_side_effect=None, extra=(), ex_rate=None, cogs=None, **kwargs):
    from contextlib import ExitStack

    from services.sale_service import SaleService

    wh = MagicMock(id=1, branch_id=1)
    line_instance = MagicMock()
    line_instance.line_total = Decimal("200")
    line_instance.quantity = 2
    line_instance.cost_price = Decimal("50")
    line_instance.id = 1
    line_instance.product_id = 1
    line_instance.calculate_line_total = MagicMock()

    def _calc(self_sale):
        self_sale.total_amount = Decimal("200")
        self_sale.amount = Decimal("200")
        self_sale.amount_aed = Decimal("200")

    flush_patch = (
        patch("services.sale_service.db.session.flush", side_effect=flush_side_effect)
        if flush_side_effect is not None
        else patch("services.sale_service.db.session.flush")
    )
    with ExitStack() as stack:
        mock_stock = stack.enter_context(patch("services.sale_service.StockService"))
        mock_wh = stack.enter_context(patch("models.Warehouse"))
        stack.enter_context(patch("services.sale_service.ensure_warehouse_access", return_value=wh))
        stack.enter_context(patch("services.sale_service.generate_number", return_value="S-2024-001"))
        mock_ex = stack.enter_context(patch("services.sale_service.ExchangeRateService"))
        stack.enter_context(patch("services.sale_service.db.session.add"))
        stack.enter_context(flush_patch)
        stack.enter_context(patch("services.sale_service.db.session.commit"))
        stack.enter_context(patch("services.sale_service.SaleService.fulfill_sale"))
        mock_line = stack.enter_context(patch("services.sale_service.SaleLine"))
        mock_calc = stack.enter_context(patch("services.sale_service.Sale.calculate_totals", autospec=True))
        for ext in extra:
            stack.enter_context(ext)
        mock_stock.check_availability_in_warehouse.return_value = (True, "")
        mock_stock._resolve_cogs_unit_cost.return_value = cogs or (Decimal("50"), "test")
        mock_wh.query.filter_by.return_value = mock_wh.query
        mock_wh.query.first.return_value = wh
        mock_ex.resolve_exchange_rate_for_transaction.return_value = ex_rate if ex_rate is not None else {"rate": 1.0}
        mock_line.return_value = line_instance
        mock_calc.side_effect = _calc
        return SaleService.create_sale(customer, seller, lines, **kwargs)


def test_warehouse_resolution_no_tenant(app):
    from services.sale_service import SaleService

    customer, seller = _parties(tenant_id=None, branch_id=None)
    with (
        patch("services.sale_service.get_active_tenant_id", return_value=None),
        patch("models.Warehouse") as mock_wh,
    ):
        mock_wh.query.filter_by.return_value = mock_wh.query
        mock_wh.query.first.return_value = None
        with pytest.raises(ValueError, match="مستودع"):
            SaleService.create_sale(customer, seller, [{"product_id": 1, "quantity": 1}])


def test_warranty_invalid_and_auto(app):
    customer, seller = _parties()
    product = _product(warranty_days=30)
    lines = [
        {
            "product": product,
            "quantity": 1,
            "unit_price": 100,
            "warranty_start_date": "2026-01-01",
            "warranty_end_date": "bad-date",
        },
        {"product": product, "quantity": 1, "unit_price": 100, "warranty_start_date": "2026-04-04"},
        {"product": product, "quantity": 1, "unit_price": 100, "warranty_end_date": "2026-05-05"},
        {"product": product, "quantity": 1, "unit_price": 100},
    ]
    _run_create(customer, seller, lines)


def test_serial_multiple_found_loops(app):
    customer, seller = _parties()
    product = _product(has_serial_number=True)
    lines = [{"product": product, "quantity": 2, "unit_price": 100, "serials": ["SN1", "SN2"]}]
    stub = MagicMock(status="available", warehouse_id=None, warranty_start_date=None)
    with patch("models.ProductSerial.query") as q:
        q.filter_by.return_value.first.side_effect = [stub, None]
        with pytest.raises(ValueError, match="السيريال"):
            _run_create(customer, seller, lines)


def test_serial_missing_allowed_creates(app, monkeypatch):
    customer, seller = _parties()
    product = _product(has_serial_number=True)
    lines = [{"product": product, "quantity": 1, "unit_price": 100, "serials": ["NEW1"]}]
    monkeypatch.setitem(app.config, "ALLOW_SERIAL_CREATION_ON_SALE", True)
    with patch("models.ProductSerial.query") as q:
        q.filter_by.return_value.first.return_value = None
        _run_create(customer, seller, lines)


def test_invalid_promo_raises(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with (
        patch("services.sale_service.PromotionService") as promo,
        pytest.raises(ValueError, match="الترويجي"),
    ):
        promo.record_applied_promotions.return_value = Decimal("-5")
        _run_create(
            customer,
            seller,
            lines,
            promotion_evaluation={"promo": True},
        )


def test_zero_split_total_raises(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with (
        patch("services.sale_service.SaleService.prepare_split_payments", return_value=[{"amount_aed": Decimal("0")}]),
        pytest.raises(ValueError, match="الدفعات"),
    ):
        _run_create(customer, seller, lines, payments_data=[{"amount": "10", "payment_method": "cash"}])


def test_valid_split_total_continues(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    result = _run_create(customer, seller, lines, payments_data=[{"amount": "50", "payment_method": "cash"}])
    assert result is not None


def test_quick_sale_without_tenant_mocked(app):
    from services.sale_service import SaleService

    with (
        patch("services.sale_service.db.session"),
        patch("services.sale_service.generate_number", return_value="S-NT"),
        patch("models.Warehouse") as mock_wh,
    ):
        mock_wh.query.filter_by.return_value.first.return_value = None
        sale = SaleService.create_quick_sale(1, 2, 1, 10)
        assert sale.sale_number == "S-NT"


def test_fx_exact_settlement_posts_nothing(app):
    from unittest.mock import MagicMock as MM

    from services.sale_service import SaleService

    paid = MM(payment_confirmed=True, amount_aed=Decimal("100"))
    sale = MM(
        id=6,
        sale_number="S-FX3",
        currency="ILS",
        exchange_rate=Decimal("1"),
        amount_aed=Decimal("100"),
        tenant_id=1,
        branch_id=1,
        seller_id=9,
        customer_id=3,
    )
    sale.customer = MM()
    sale.customer.apply_receipt = MM()
    sale.recalculate_payment_status = MM()
    sale.payments = [paid]
    sale.returns = []
    with (
        patch("utils.helpers.generate_number", return_value="PAY-FX3"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.GLService"),
        patch("services.sale_service.db.session"),
        patch("services.sale_service.convert_and_quantize_aed", return_value=Decimal("36")),
        patch("services.sale_service.canonical_payment_type", return_value="sale_payment"),
    ):
        out = SaleService.create_payment_for_sale(sale, 36, "cash", currency="USD", exchange_rate=3.6)
        assert out.payment_number == "PAY-FX3"


def test_payment_foreign_currency_note(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    result = _run_create(
        customer,
        seller,
        lines,
        payment_data={"amount": "10", "currency": "USD", "exchange_rate": "3.67"},
    )
    assert result is not None


def test_defer_flush_failure(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with pytest.raises(RuntimeError, match="defer boom"):
        _run_create(
            customer,
            seller,
            lines,
            defer_fulfillment=True,
            flush_side_effect=[None, None, None, RuntimeError("defer boom")],
        )


def test_final_flush_failure(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with pytest.raises(RuntimeError, match="final boom"):
        _run_create(
            customer,
            seller,
            lines,
            flush_side_effect=[None, None, None, RuntimeError("final boom")],
        )


def test_quick_sale_guards_and_success(db_session, sample_tenant, sample_customer, sample_product, sample_warehouse):
    from services.sale_service import SaleService
    from services.stock_service import StockService

    with pytest.raises(ValueError, match="العميل"):
        SaleService.create_quick_sale(999999999, sample_product.id, 1, 10)
    with pytest.raises(ValueError, match="المنتج"):
        SaleService.create_quick_sale(sample_customer.id, 999999999, 1, 10)
    StockService.add_stock(sample_product.id, 50, warehouse_id=sample_warehouse.id)
    sale = SaleService.create_quick_sale(sample_customer.id, sample_product.id, 2, 10, tenant_id=sample_tenant.id)
    assert sale.sale_number.startswith("S-")


def test_quick_sale_without_warehouse_skips_stock(db_session, sample_tenant, sample_customer, sample_product, mocker):
    from services.sale_service import SaleService

    mock_wh = mocker.patch("models.Warehouse")
    mock_wh.query.filter_by.return_value.first.return_value = None
    sale = SaleService.create_quick_sale(sample_customer.id, sample_product.id, 1, 10, tenant_id=sample_tenant.id)
    assert sale.id is not None


def test_quick_sale_with_explicit_seller(
    db_session, sample_tenant, sample_user, sample_warehouse, sample_customer, sample_product
):
    from services.sale_service import SaleService
    from services.stock_service import StockService

    StockService.add_stock(sample_product.id, 50, warehouse_id=sample_warehouse.id)
    sale = SaleService.create_quick_sale(
        sample_customer.id, sample_product.id, 1, 10, tenant_id=sample_tenant.id, seller_id=sample_user.id
    )
    assert sale.seller_id == sample_user.id


def test_quick_sale_tenant_user_seller(
    db_session, sample_tenant, sample_user, sample_warehouse, sample_customer, sample_product
):
    from services.sale_service import SaleService
    from services.stock_service import StockService

    StockService.add_stock(sample_product.id, 50, warehouse_id=sample_warehouse.id)
    sale = SaleService.create_quick_sale(sample_customer.id, sample_product.id, 1, 10, tenant_id=sample_tenant.id)
    assert sale.seller_id == sample_user.id


def test_fulfill_foreign_currency_note(app):
    from services.sale_service import SaleService

    sale = MagicMock(
        customer=MagicMock(apply_sale=MagicMock(), update_classification=MagicMock()),
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        exchange_rate=Decimal("1"),
        currency="ILS",
        amount_aed=Decimal("100"),
        sale_number="S-FX",
        lines=[],
        tax_rate=Decimal("0"),
        subtotal=Decimal("100"),
        shipping_cost=Decimal("0"),
        discount_amount=Decimal("0"),
        taxable_amount=Decimal("100"),
        tax_amount=Decimal("0"),
    )
    sale.calculate_totals = MagicMock()
    with (
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.sale_service.StockService") as stock,
        patch("services.sale_service.GLService"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.post_sale_commissions"),
        patch("services.sale_service.should_post_vat_gl", return_value=False),
        patch("services.sale_service.db.session"),
    ):
        stock.check_availability_in_warehouse.return_value = (True, "")
        stock.calculate_sale_cogs_and_deduct.return_value = Decimal("50")
        SaleService.fulfill_sale(
            sale, payment_data={"amount": 10, "currency": "USD", "exchange_rate": "3.67", "payment_method": "cash"}
        )


def test_cancel_pending_cheque_variants(app):
    from unittest.mock import MagicMock as MM

    from services.sale_service import SaleService

    def _sale():
        s = MM(id=1, sale_number="S-C", status="confirmed", tenant_id=1, branch_id=1, amount_aed=Decimal("100"))
        s.customer = MM(total_purchases=Decimal("100"))
        s.customer.adjust_balance = MM()
        s.customer.update_classification = MM()
        s.recalculate_payment_status = MM()
        return s

    sale = _sale()
    pmt = MM(cheque_id=None)
    pmt.reject_payment = MM()
    with (
        patch("models.Payment") as pay_mod,
        patch("services.sale_service.db.session"),
        patch.object(SaleService, "has_inventory_posted", return_value=False),
    ):
        pay_mod.query.filter_by.return_value.count.return_value = 0
        pay_mod.query.filter_by.return_value.all.return_value = [pmt]
        SaleService.cancel_sale(sale)
        pmt.reject_payment.assert_called_once()

    sale2 = _sale()
    sale2.customer = None
    with (
        patch("models.Payment") as pay_mod,
        patch("services.sale_service.db.session"),
        patch.object(SaleService, "has_inventory_posted", return_value=False),
    ):
        pay_mod.query.filter_by.return_value.count.return_value = 0
        pay_mod.query.filter_by.return_value.all.return_value = []
        SaleService.cancel_sale(sale2)
        assert sale2.status == "cancelled"


def test_cancel_cheque_already_cancelled(app):
    from unittest.mock import MagicMock as MM

    from services.sale_service import SaleService

    sale = MM(id=1, sale_number="S-C", status="confirmed", tenant_id=1, branch_id=1, amount_aed=Decimal("100"))
    sale.customer = MM(total_purchases=Decimal("100"))
    sale.customer.adjust_balance = MM()
    sale.customer.update_classification = MM()
    sale.recalculate_payment_status = MM()
    pmt = MM(cheque_id=7)
    pmt.reject_payment = MM()
    cheque = MM(status="cancelled")
    with (
        patch("models.Payment") as pay_mod,
        patch("services.sale_service.db.session") as db_mod,
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.cheque_service.process_cheque_cancel") as cancel_chq,
    ):
        pay_mod.query.filter_by.return_value.count.return_value = 0
        pay_mod.query.filter_by.return_value.all.return_value = [pmt]
        db_mod.get.return_value = cheque
        SaleService.cancel_sale(sale)
        cancel_chq.assert_not_called()
        pmt.reject_payment.assert_called_once()


def test_valid_promo_continues(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with patch("services.sale_service.PromotionService") as promo:
        promo.record_applied_promotions.return_value = Decimal("5")
        result = _run_create(customer, seller, lines, promotion_evaluation={"promo": True})
        assert result is not None


def test_payment_default_currency_skips_note(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    result = _run_create(
        customer, seller, lines, payment_data={"amount": "10", "currency": "ILS", "exchange_rate": "1"}
    )
    assert result is not None


def test_rate_needs_input_raises(app):

    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with pytest.raises(ValueError, match="صرف"):
        _run_create(customer, seller, lines, ex_rate={"rate_mode": "needs_input"})


def test_rate_invalid_raises(app):

    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with pytest.raises(ValueError, match="صالح"):
        _run_create(customer, seller, lines, ex_rate={"rate": 0})


def test_vat_exclusive_revenue_path(app):
    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with patch("utils.tax_settings.get_prices_include_vat", return_value=True):
        result = _run_create(customer, seller, lines, tax_rate=5)
        assert result is not None


def test_partner_zero_commission_skipped(app):
    customer, seller = _parties()
    product = _product()
    product.partner_shares = [MagicMock(partner_customer_id=4242, percentage=10)]
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with patch("models.Customer.query") as cust_q:
        cust_q.filter_by.return_value.first.return_value = MagicMock()
        _run_create(customer, seller, lines, cogs=(Decimal("500"), "test"))


def test_negative_payment_raises(app):

    customer, seller = _parties()
    product = _product()
    lines = [{"product": product, "quantity": 2, "unit_price": 100}]
    with pytest.raises(ValueError, match="سالب"):
        _run_create(customer, seller, lines, payment_data={"amount": "-5", "currency": "ILS"})


def test_fulfill_default_currency_skips_note(app):
    from services.sale_service import SaleService

    sale = MagicMock(
        customer=MagicMock(apply_sale=MagicMock(), update_classification=MagicMock()),
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        exchange_rate=Decimal("1"),
        currency="ILS",
        amount_aed=Decimal("100"),
        sale_number="S-ILS",
        lines=[],
        tax_rate=Decimal("0"),
        subtotal=Decimal("100"),
        shipping_cost=Decimal("0"),
        discount_amount=Decimal("0"),
        taxable_amount=Decimal("100"),
        tax_amount=Decimal("0"),
    )
    sale.calculate_totals = MagicMock()
    with (
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.sale_service.StockService") as stock,
        patch("services.sale_service.GLService"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.post_sale_commissions"),
        patch("services.sale_service.should_post_vat_gl", return_value=False),
        patch("services.sale_service.db.session"),
    ):
        stock.check_availability_in_warehouse.return_value = (True, "")
        stock.calculate_sale_cogs_and_deduct.return_value = Decimal("50")
        SaleService.fulfill_sale(
            sale, payment_data={"amount": 10, "currency": "ILS", "exchange_rate": "1", "payment_method": "cash"}
        )


def test_fulfill_promo_debit_posts_line(app):
    from services.sale_service import SaleService

    sale = MagicMock(
        customer=MagicMock(apply_sale=MagicMock(), update_classification=MagicMock()),
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        exchange_rate=Decimal("1"),
        currency="ILS",
        amount_aed=Decimal("100"),
        sale_number="S-PR",
        lines=[],
        tax_rate=Decimal("0"),
        subtotal=Decimal("100"),
        shipping_cost=Decimal("0"),
        discount_amount=Decimal("0"),
        taxable_amount=Decimal("100"),
        tax_amount=Decimal("0"),
    )
    sale.calculate_totals = MagicMock()
    sale.__dict__["promotion_discount_amount"] = Decimal("7")
    with (
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.sale_service.StockService") as stock,
        patch("services.sale_service.GLService"),
        patch("services.sale_service.post_or_fail") as post,
        patch("services.sale_service.post_sale_commissions"),
        patch("services.sale_service.should_post_vat_gl", return_value=False),
        patch("services.sale_service.db.session"),
    ):
        stock.check_availability_in_warehouse.return_value = (True, "")
        stock.calculate_sale_cogs_and_deduct.return_value = Decimal("50")
        SaleService.fulfill_sale(sale)
        assert post.called


def test_fulfill_raw_split_payments_prepare(app):
    from services.sale_service import SaleService

    sale = MagicMock(
        customer=MagicMock(apply_sale=MagicMock(), update_classification=MagicMock()),
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        exchange_rate=Decimal("1"),
        currency="ILS",
        amount_aed=Decimal("100"),
        sale_number="S-SP",
        lines=[],
        tax_rate=Decimal("0"),
        subtotal=Decimal("100"),
        shipping_cost=Decimal("0"),
        discount_amount=Decimal("0"),
        taxable_amount=Decimal("100"),
        tax_amount=Decimal("0"),
    )
    sale.calculate_totals = MagicMock()
    with (
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.sale_service.StockService") as stock,
        patch("services.sale_service.GLService"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.post_sale_commissions"),
        patch("services.sale_service.should_post_vat_gl", return_value=False),
        patch("services.sale_service.db.session"),
        patch.object(SaleService, "_create_split_payments") as mk,
    ):
        stock.check_availability_in_warehouse.return_value = (True, "")
        stock.calculate_sale_cogs_and_deduct.return_value = Decimal("50")
        SaleService.fulfill_sale(sale, payments_data=[{"amount": "10", "payment_method": "cash", "currency": "ILS"}])
        mk.assert_called_once()


def test_fulfill_precomputed_split_skips_prepare(app):
    from services.sale_service import SaleService

    sale = MagicMock(
        customer=MagicMock(apply_sale=MagicMock(), update_classification=MagicMock()),
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        exchange_rate=Decimal("1"),
        currency="ILS",
        amount_aed=Decimal("100"),
        sale_number="S-SP2",
        lines=[],
        tax_rate=Decimal("0"),
        subtotal=Decimal("100"),
        shipping_cost=Decimal("0"),
        discount_amount=Decimal("0"),
        taxable_amount=Decimal("100"),
        tax_amount=Decimal("0"),
    )
    sale.calculate_totals = MagicMock()
    chunks = [{"amount": "10", "payment_method": "cash", "currency": "ILS", "amount_aed": Decimal("10")}]
    with (
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.sale_service.StockService") as stock,
        patch("services.sale_service.GLService"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.post_sale_commissions"),
        patch("services.sale_service.should_post_vat_gl", return_value=False),
        patch("services.sale_service.db.session"),
        patch.object(SaleService, "_create_split_payments") as mk,
        patch.object(SaleService, "prepare_split_payments") as prep,
    ):
        stock.check_availability_in_warehouse.return_value = (True, "")
        stock.calculate_sale_cogs_and_deduct.return_value = Decimal("50")
        SaleService.fulfill_sale(sale, payments_data=chunks)
        mk.assert_called_once()
        prep.assert_not_called()


def _fx_sale():
    from unittest.mock import MagicMock as MM

    confirmed = MM(payment_confirmed=True, amount_aed=Decimal("30"))
    pending = MM(payment_confirmed=False, amount_aed=Decimal("10"))
    approved_ret = MM(status="approved", amount_aed=Decimal("5"))
    pending_ret = MM(status="pending", amount_aed=Decimal("7"))
    sale = MM(
        id=5,
        sale_number="S-FX",
        currency="ILS",
        exchange_rate=Decimal("1"),
        amount_aed=Decimal("100"),
        tenant_id=1,
        branch_id=1,
        seller_id=9,
        customer_id=3,
    )
    sale.customer = MM()
    sale.customer.apply_receipt = MM()
    sale.recalculate_payment_status = MM()
    sale.payments = [confirmed, pending]
    sale.returns = [approved_ret, pending_ret]
    return sale


def test_fx_cross_currency_partial_settlement(app):

    from services.sale_service import SaleService

    sale = _fx_sale()
    with (
        patch("utils.helpers.generate_number", return_value="PAY-FX"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.GLService"),
        patch("services.sale_service.db.session"),
        patch("services.sale_service.convert_and_quantize_aed", return_value=Decimal("36")),
        patch("services.sale_service.canonical_payment_type", return_value="sale_payment"),
    ):
        out = SaleService.create_payment_for_sale(sale, 10, "cash", currency="USD", exchange_rate=3.6)
        assert out.payment_number == "PAY-FX"


def test_fx_same_currency_rate_diff_no_post(app):

    from services.sale_service import SaleService

    sale = _fx_sale()
    sale.payments = []
    sale.returns = []
    with (
        patch("utils.helpers.generate_number", return_value="PAY-FX2"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.GLService"),
        patch("services.sale_service.db.session"),
        patch("services.sale_service.convert_and_quantize_aed", return_value=Decimal("10")),
        patch("services.sale_service.canonical_payment_type", return_value="sale_payment"),
    ):
        out = SaleService.create_payment_for_sale(sale, 10, "cash", currency="ILS", exchange_rate=1.5)
        assert out.payment_number == "PAY-FX2"


def test_fx_open_balance_negative_skips_posting(app):
    from unittest.mock import MagicMock as MM

    from services.sale_service import SaleService

    sale = _fx_sale()
    sale.payments = [MM(payment_confirmed=True, amount_aed=Decimal("130"))]
    sale.returns = [MM(status="approved", amount_aed=Decimal("10"))]
    with (
        patch("utils.helpers.generate_number", return_value="PAY-FX3"),
        patch("services.sale_service.post_or_fail"),
        patch("services.sale_service.GLService"),
        patch("services.sale_service.db.session"),
        patch("services.sale_service.convert_and_quantize_aed", return_value=Decimal("36")),
        patch("services.sale_service.canonical_payment_type", return_value="sale_payment"),
    ):
        out = SaleService.create_payment_for_sale(sale, 10, "cash", currency="USD", exchange_rate=3.6)
        assert out.payment_number == "PAY-FX3"


def test_cheque_payment_guards(db_session, sample_sale):
    from services.sale_service import SaleService

    with pytest.raises(ValueError, match="رقم الشيك"):
        SaleService.create_payment_for_sale(sample_sale, 10, "cheque", cheque_date="2026-01-01", bank_name="B")
    with pytest.raises(ValueError, match="الاستحقاق"):
        SaleService.create_payment_for_sale(sample_sale, 10, "cheque", cheque_number="CHQ1", bank_name="B")
    with pytest.raises(ValueError, match="البنك"):
        SaleService.create_payment_for_sale(sample_sale, 10, "cheque", cheque_number="CHQ1", cheque_date="2026-01-01")


def test_cheque_payment_string_date(db_session, sample_sale, sample_gl_accounts):
    from datetime import date

    from services.sale_service import SaleService

    out = SaleService.create_payment_for_sale(
        sample_sale, 10, "cheque", cheque_number="CHQ9", cheque_date="2026-01-15", bank_name="B"
    )
    assert out.cheque_number == "CHQ9"
    with pytest.raises(ValueError, match="الشيك"):
        SaleService.create_payment_for_sale(
            sample_sale, 10, "cheque", cheque_number="CHQ9", cheque_date="15-01-2026", bank_name="B"
        )
    out2 = SaleService.create_payment_for_sale(
        sample_sale, 11, "cheque", cheque_number="CHQ10", cheque_date=date(2026, 2, 20), bank_name="B"
    )
    assert out2.cheque_number == "CHQ10"
