"""Promotional discount — dedicated GL concept posting + totals math."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch


def _sale(**overrides):
    customer = MagicMock()
    customer.apply_sale = MagicMock()
    customer.apply_receipt = MagicMock()
    line = MagicMock()
    line.product_id = 1
    line.quantity = 1
    line.product = MagicMock(name="Widget")
    line.product.name = "Widget"
    sale = MagicMock(
        id=1,
        sale_number="S-001",
        customer=customer,
        customer_id=1,
        warehouse_id=1,
        tenant_id=1,
        branch_id=1,
        seller_id=2,
        exchange_rate=Decimal("1"),
        currency="AED",
        amount_aed=Decimal("80"),
        total_amount=Decimal("80"),
        subtotal=Decimal("100"),
        discount_amount=Decimal("0"),
        shipping_cost=Decimal("0"),
        tax_rate=Decimal("0"),
        tax_amount=Decimal("0"),
        taxable_amount=Decimal("80"),
        prices_include_vat=False,
        notes="",
        paid_amount=Decimal("0"),
        paid_amount_aed=Decimal("0"),
        lines=[line],
        sale_date=MagicMock(date=lambda: MagicMock()),
    )
    sale.__dict__.update(overrides)
    return sale


_ACCOUNT_BY_CONCEPT = {
    "SALES_REVENUE": "4100",
    "SALES_DISCOUNT": "6130",
    "CAMPAIGN_DISCOUNT_EXPENSE": "6131",
    "VAT_OUTPUT": "2121",
}


def _run_fulfill(sale):
    from services.sale_service import SaleService

    with (
        patch.object(SaleService, "has_inventory_posted", return_value=False),
        patch("services.sale_service.StockService") as stock,
        patch("services.sale_service.GLService") as gl,
        patch("services.sale_service.post_or_fail") as post,
        patch("services.sale_service.post_sale_commissions"),
        patch("services.sale_service.should_post_vat_gl", return_value=False),
    ):
        stock.check_availability_in_warehouse.return_value = (True, "")
        stock.process_sale_lines.return_value = None
        stock.calculate_sale_cogs_and_deduct.return_value = Decimal("0")
        gl.get_customer_credit_account.return_value = "1130"
        gl.get_customer_credit_concept.return_value = "AR"
        gl.get_account_code_for_concept.side_effect = lambda concept, **kw: _ACCOUNT_BY_CONCEPT.get(
            concept, "4000"
        )
        SaleService.fulfill_sale(sale)
        return post


class TestPromotionalDiscountGL:
    def test_posts_to_campaign_discount_expense_account(self, app):
        sale = _sale(promotion_discount_amount=Decimal("20"))
        post = _run_fulfill(sale)
        gl_lines = post.call_args_list[0].args[0]

        promo_lines = [ln for ln in gl_lines if ln.get("concept_code") == "CAMPAIGN_DISCOUNT_EXPENSE"]
        assert len(promo_lines) == 1
        assert promo_lines[0]["account"] == "6131"
        assert promo_lines[0]["debit"] == Decimal("20")

        # No manual discount → SALES_DISCOUNT must not be posted.
        assert all(ln.get("concept_code") != "SALES_DISCOUNT" for ln in gl_lines)

        # Exact double-entry: debits == credits.
        total_debit = sum(Decimal(str(ln.get("debit", 0) or 0)) for ln in gl_lines)
        total_credit = sum(Decimal(str(ln.get("credit", 0) or 0)) for ln in gl_lines)
        assert total_debit == total_credit

    def test_manual_and_promo_discounts_post_separately(self, app):
        sale = _sale(
            discount_amount=Decimal("10"),
            promotion_discount_amount=Decimal("20"),
            total_amount=Decimal("70"),
            amount_aed=Decimal("70"),
            taxable_amount=Decimal("70"),
        )
        post = _run_fulfill(sale)
        gl_lines = post.call_args_list[0].args[0]

        by_concept = {ln.get("concept_code"): ln for ln in gl_lines}
        assert by_concept["SALES_DISCOUNT"]["account"] == "6130"
        assert by_concept["SALES_DISCOUNT"]["debit"] == Decimal("10")
        assert by_concept["CAMPAIGN_DISCOUNT_EXPENSE"]["account"] == "6131"
        assert by_concept["CAMPAIGN_DISCOUNT_EXPENSE"]["debit"] == Decimal("20")

        total_debit = sum(Decimal(str(ln.get("debit", 0) or 0)) for ln in gl_lines)
        total_credit = sum(Decimal(str(ln.get("credit", 0) or 0)) for ln in gl_lines)
        assert total_debit == total_credit

    def test_vat_inclusive_promo_posted_vat_exclusive(self, app):
        sale = _sale(
            prices_include_vat=True,
            tax_rate=Decimal("5"),
            promotion_discount_amount=Decimal("21"),
            discount_amount=Decimal("0"),
            taxable_amount=Decimal("75.24"),
            tax_amount=Decimal("3.76"),
            total_amount=Decimal("79"),
            amount_aed=Decimal("79"),
        )
        with patch("services.sale_service.should_post_vat_gl", return_value=True):
            post = _run_fulfill(sale)
        gl_lines = post.call_args_list[0].args[0]

        promo_lines = [ln for ln in gl_lines if ln.get("concept_code") == "CAMPAIGN_DISCOUNT_EXPENSE"]
        assert len(promo_lines) == 1
        assert promo_lines[0]["debit"] == Decimal("20.00")  # 21 / 1.05

    def test_no_promo_no_campaign_line(self, app):
        sale = _sale()
        post = _run_fulfill(sale)
        gl_lines = post.call_args_list[0].args[0]
        assert all(ln.get("concept_code") != "CAMPAIGN_DISCOUNT_EXPENSE" for ln in gl_lines)


class TestSaleTotalsWithPromotion:
    def _persist_sale(self, db_session, sample_tenant, sample_customer, sample_user, sample_product, **kw):
        from models.sale import Sale, SaleLine

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"SAL-PROMO-{id(kw)}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            currency="AED",
            exchange_rate=Decimal("1"),
            subtotal=Decimal("100"),
            discount_amount=kw.pop("discount_amount", Decimal("10")),
            promotion_discount_amount=kw.pop("promotion_discount_amount", Decimal("20")),
            shipping_cost=Decimal("0"),
            tax_rate=kw.pop("tax_rate", Decimal("0")),
            prices_include_vat=kw.pop("prices_include_vat", False),
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            **kw,
        )
        db_session.add(sale)
        db_session.flush()
        line = SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=sample_product.id,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            discount_percent=Decimal("0"),
            line_total=Decimal("100"),
        )
        db_session.add(line)
        db_session.flush()
        return sale

    def test_calculate_totals_subtracts_promotion(
        self, db_session, sample_tenant, sample_customer, sample_user, sample_product
    ):
        sale = self._persist_sale(db_session, sample_tenant, sample_customer, sample_user, sample_product)
        sale.calculate_totals()
        assert sale.subtotal == Decimal("100")
        assert sale.total_amount == Decimal("70.000")
        assert sale.amount_aed == Decimal("70.000")

    def test_calculate_totals_vat_inclusive_with_promotion(
        self, db_session, sample_tenant, sample_customer, sample_user, sample_product
    ):
        sale = self._persist_sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_user,
            sample_product,
            prices_include_vat=True,
            tax_rate=Decimal("5"),
            discount_amount=Decimal("0"),
            promotion_discount_amount=Decimal("21"),
        )
        sale.calculate_totals()
        # gross = 100 - 21 = 79; taxable = 79 / 1.05 = 75.24; tax = 3.76
        assert sale.total_amount == Decimal("79.000")
        assert sale.taxable_amount == Decimal("75.24")
        assert sale.tax_amount == Decimal("3.76")

    def test_calculate_totals_zero_promotion_unchanged(
        self, db_session, sample_tenant, sample_customer, sample_user, sample_product
    ):
        sale = self._persist_sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_user,
            sample_product,
            promotion_discount_amount=Decimal("0"),
        )
        sale.calculate_totals()
        assert sale.total_amount == Decimal("90.000")
