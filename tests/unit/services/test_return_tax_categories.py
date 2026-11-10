"""Return VAT follows each returned line's tax category, not the sale rate alone.

Golden scenarios (independently computed): a sale at 10% with one standard
line (100) and one zero-rated line (100) refunds 210 — the zero line
contributes no VAT. Under the old single-rate math this refunded 220.
"""

from __future__ import annotations

from decimal import Decimal

from tests.unit.services.test_return_promo_reversal import _gl_calls, _patch_common
from tests.unit.services.test_return_service_assurance import _product, _sale, _sale_line, _user


class TestReturnTaxByCategory:
    def test_zero_rated_line_contributes_no_vat(self, app, mocker):
        sale = _sale(subtotal=Decimal("200"), tax_rate=Decimal("10"))
        standard = _sale_line(id=201, line_total=Decimal("100"), quantity=Decimal("1"))
        standard.tax_category = "standard"
        zero = _sale_line(id=202, line_total=Decimal("100"), quantity=Decimal("1"))
        zero.tax_category = "zero"
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [standard, zero], product)
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [
                    {"sale_line_id": standard.id, "quantity": 1, "condition": "damaged"},
                    {"sale_line_id": zero.id, "quantity": 1, "condition": "damaged"},
                ],
                user=_user(),
            )

        # Net 200; VAT only on the standard line: 100 * 10% = 10.
        assert Decimal(str(result.refund_amount)) == Decimal("210.000")
        revenue_lines = _gl_calls(post_mock)[0]
        tax_leg = [gl_line for gl_line in revenue_lines if gl_line["concept_code"] == "VAT_OUTPUT"][0]
        assert tax_leg["debit"] == Decimal("10.000")
        debit_total = sum(Decimal(str(gl_line.get("debit", 0) or 0)) for gl_line in revenue_lines)
        credit_total = sum(Decimal(str(gl_line.get("credit", 0) or 0)) for gl_line in revenue_lines)
        assert debit_total == credit_total

    def test_exempt_line_contributes_no_vat(self, app, mocker):
        sale = _sale(subtotal=Decimal("100"), tax_rate=Decimal("10"))
        line = _sale_line(line_total=Decimal("100"), quantity=Decimal("1"))
        line.tax_category = "exempt"
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
        assert all(gl_line["concept_code"] != "VAT_OUTPUT" for gl_line in revenue_lines)

    def test_standard_lines_keep_sale_rate_parity(self, app, mocker):
        sale = _sale(subtotal=Decimal("100"), tax_rate=Decimal("10"))
        line = _sale_line(line_total=Decimal("100"), quantity=Decimal("1"))
        line.tax_category = "standard"
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [line], product)
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line.id, "quantity": 1, "condition": "damaged"}],
                user=_user(),
            )

        assert Decimal(str(result.refund_amount)) == Decimal("110.000")

    def test_vat_inclusive_prices_refund_exactly_what_was_paid(self, app, mocker):
        # Customer paid 110 gross (100 + 10% VAT). Refund must be 110 —
        # not 110 + tax on top — split as revenue 100 / VAT 10.
        sale = _sale(subtotal=Decimal("110"), tax_rate=Decimal("10"))
        sale.prices_include_vat = True
        line = _sale_line(line_total=Decimal("110"), quantity=Decimal("1"))
        line.tax_category = "standard"
        product = _product()
        _, post_mock = _patch_common(mocker, sale, [line], product)
        from services.return_service import ReturnService

        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line.id, "quantity": 1, "condition": "damaged"}],
                user=_user(),
            )

        assert Decimal(str(result.refund_amount)) == Decimal("110.000")
        revenue_lines = _gl_calls(post_mock)[0]
        tax_leg = [gl_line for gl_line in revenue_lines if gl_line["concept_code"] == "VAT_OUTPUT"][0]
        assert tax_leg["debit"] == Decimal("10.000")
        revenue_leg = [gl_line for gl_line in revenue_lines if gl_line["concept_code"] == "SALES_RETURNS"][0]
        assert revenue_leg["debit"] == Decimal("100.000")
        debit_total = sum(Decimal(str(gl_line.get("debit", 0) or 0)) for gl_line in revenue_lines)
        credit_total = sum(Decimal(str(gl_line.get("credit", 0) or 0)) for gl_line in revenue_lines)
        assert debit_total == credit_total
