"""POS Phase 4 — ReturnService promotional-discount reversal + original-rate parity.

MagicMock-at-boundary style per tests/unit/services/test_return_service_assurance.py.
Covers: proportional promo reversal (bundle scenario), exact GL parity
(CAMPAIGN_DISCOUNT_EXPENSE credited back), customer refund reduced by the
promo share, tax reversal on the post-promo base, and foreign-currency sales
reversed at the ORIGINAL exchange rate.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from tests.unit.services.test_return_service_assurance import (
    _product,
    _sale,
    _sale_line,
    _user,
)


def _patch_common(mocker, sale, lines, product):
    """Mirror of the assurance-suite fixture, extended for multi-line sales."""
    session = mocker.patch("services.return_service.db.session")
    by_id = {sale.id: sale}
    by_id.update({line.id: line for line in lines})
    by_id[lines[0].product_id] = product
    session.get.side_effect = lambda model, pk: by_id.get(pk)
    session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal(
        "0"
    )
    mocker.patch("services.return_service.generate_number", return_value="R-900")
    mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
    mocker.patch("services.return_service.is_platform_owner", return_value=False)
    mocker.patch("services.return_service.branch_scope_id_for", return_value=None)
    mocker.patch("services.return_service.should_post_vat_gl", return_value=True)
    mocker.patch("services.return_service.StockService.create_movement")
    mocker.patch("services.return_service.GLService.get_account_code_for_concept", return_value="6131")
    mocker.patch("services.return_service.GLService.get_customer_credit_account", return_value="1130")
    mocker.patch("services.return_service.GLService.get_customer_credit_concept", return_value="AR")
    mocker.patch("services.return_service.GLService.ensure_core_accounts")
    post_mock = mocker.patch("services.return_service.post_or_fail")
    for line in lines:
        line.product = product
    return session, post_mock


def _gl_calls(post_mock):
    return [call.kwargs["lines"] for call in post_mock.call_args_list]


class TestPromoReversal:
    def test_promo_share_reduces_refund_and_reverses_expense(self, app, mocker):
        """Sale 100 with promo 10: returning the full line refunds 90 + tax on 90."""
        sale = _sale(subtotal=Decimal("100"), tax_rate=Decimal("0"))
        sale.promotion_discount_amount = Decimal("10")
        line = _sale_line(line_total=Decimal("100"), quantity=Decimal("1"))
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [line], product)
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line.id, "quantity": 1, "condition": "damaged"}],
                user=_user(),
            )

        assert Decimal(str(result.refund_amount)) == Decimal("90.000")
        revenue_lines = _gl_calls(post_mock)[0]
        promo_leg = [l for l in revenue_lines if l["concept_code"] == "CAMPAIGN_DISCOUNT_REVERSAL"]
        assert len(promo_leg) == 1
        assert promo_leg[0]["credit"] == Decimal("10.000")
        revenue_leg = [l for l in revenue_lines if l["concept_code"] == "SALES_RETURNS"][0]
        customer_leg = [l for l in revenue_lines if l.get("credit") and l["concept_code"] == "AR"][0]
        # GL parity: Dr revenue(100) == Cr customer(90) + Cr promo reversal(10)
        assert revenue_leg["debit"] == Decimal("100.000")
        assert customer_leg["credit"] == Decimal("90.000")
        assert revenue_leg["debit"] == customer_leg["credit"] + promo_leg[0]["credit"]

    def test_bundle_partial_return_proportional_and_exact(self, app, mocker):
        """Bundle: two lines 60/40, promo 10 → return the 60 line reverses exactly 6."""
        sale = _sale(subtotal=Decimal("100"), tax_rate=Decimal("5"))
        sale.promotion_discount_amount = Decimal("10")
        line_a = _sale_line(id=201, line_total=Decimal("60"), quantity=Decimal("2"))
        line_b = _sale_line(id=202, line_total=Decimal("40"), quantity=Decimal("1"))
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [line_a, line_b], product)
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line_a.id, "quantity": 2, "condition": "damaged"}],
                user=_user(),
            )

        # promo share = 60/100 * 10 = 6; customer net = 60 - 6 = 54; tax 5% = 2.7
        assert Decimal(str(result.refund_amount)) == Decimal("56.700")
        revenue_lines = _gl_calls(post_mock)[0]
        promo_leg = [l for l in revenue_lines if l["concept_code"] == "CAMPAIGN_DISCOUNT_REVERSAL"][0]
        assert promo_leg["credit"] == Decimal("6.000")
        tax_leg = [l for l in revenue_lines if l["concept_code"] == "VAT_OUTPUT"][0]
        assert tax_leg["debit"] == Decimal("2.700")
        debit_total = sum(Decimal(str(l.get("debit", 0) or 0)) for l in revenue_lines)
        credit_total = sum(Decimal(str(l.get("credit", 0) or 0)) for l in revenue_lines)
        assert debit_total == credit_total

    def test_no_promo_behaves_as_before(self, app, mocker):
        """No promotion_discount_amount on the sale → legacy totals, no promo leg."""
        sale = _sale(subtotal=Decimal("100"), tax_rate=Decimal("0"))
        line = _sale_line(line_total=Decimal("100"), quantity=Decimal("1"))
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [line], product)
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line.id, "quantity": 1, "condition": "damaged"}],
                user=_user(),
            )

        assert Decimal(str(result.refund_amount)) == Decimal("100.000")
        revenue_lines = _gl_calls(post_mock)[0]
        assert all(l["concept_code"] != "CAMPAIGN_DISCOUNT_REVERSAL" for l in revenue_lines)


class TestOriginalExchangeRate:
    def test_foreign_currency_return_uses_original_rate(self, app, mocker):
        """Sale made at rate 3.0; today's rate moved — the reversal must use 3.0."""
        sale = _sale(subtotal=Decimal("100"), tax_rate=Decimal("0"))
        sale.currency = "USD"
        sale.exchange_rate = Decimal("3.0")
        line = _sale_line(line_total=Decimal("100"), quantity=Decimal("1"))
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [line], product)
        mocker.patch(
            "utils.currency_utils.convert_and_quantize_aed",
            side_effect=lambda amount, currency, rate, **kw: (
                Decimal(str(amount)) * Decimal(str(rate))
            ).quantize(Decimal("0.001")),
        )
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line.id, "quantity": 1, "condition": "damaged"}],
                user=_user(),
            )

        assert Decimal(str(result.exchange_rate)) == Decimal("3.0")
        assert Decimal(str(result.amount_aed)) == Decimal("300.000")
        revenue_kwargs = post_mock.call_args_list[0].kwargs
        assert Decimal(str(revenue_kwargs["exchange_rate"])) == Decimal("3.0")
        assert revenue_kwargs["currency"] == "USD"


class TestSellerRestriction:
    def test_pos_return_permission_bypasses_own_sales_rule(self, mocker):
        mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
        mocker.patch("services.return_service.is_platform_owner", return_value=False)
        mocker.patch("services.return_service.branch_scope_id_for", return_value=None)
        from services.return_service import ReturnService

        user = _user(seller=True)
        user.has_permission = MagicMock(return_value=True)
        ReturnService._validate_sale_access(_sale(seller_id=99), user)

    def test_seller_without_permission_still_blocked(self, mocker):
        mocker.patch("services.return_service.get_active_tenant_id", return_value=1)
        mocker.patch("services.return_service.is_platform_owner", return_value=False)
        mocker.patch("services.return_service.branch_scope_id_for", return_value=None)
        from services.return_service import ReturnService

        user = _user(seller=True)
        user.has_permission = MagicMock(return_value=False)
        user.is_owner = False
        import pytest

        with pytest.raises(ValueError, match="Seller cannot"):
            ReturnService._validate_sale_access(_sale(seller_id=99), user)
