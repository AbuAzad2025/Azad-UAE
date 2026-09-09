"""Coverage tests for data_analyzer arcs 140->139, 224->221, 286->289."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from ai_knowledge.analytics.data_analyzer import DataAnalyzer


class _Col:
    def __lt__(self, other):
        return MagicMock()

    def __le__(self, other):
        return MagicMock()

    def __gt__(self, other):
        return MagicMock()

    def __ge__(self, other):
        return MagicMock()

    def __eq__(self, other):
        return MagicMock()


def _sale(total, customer_name_or_none, day=1):
    sale = MagicMock()
    sale.total_amount = Decimal(str(total))
    sale.created_at = datetime(2024, 5, day, 12, 0, 0)
    if customer_name_or_none is None:
        sale.customer = None
    else:
        sale.customer = MagicMock()
        sale.customer.name = customer_name_or_none
    return sale


def test_cov_da_sales_skips_customer_none_arc():
    """Arc 140->139: sale.customer falsy loops back to for header."""
    sales = [_sale(100, None, day=1), _sale(200, "Ali", day=2)]
    with patch("models.Sale") as sale_cls:
        sale_cls.created_at = _Col()
        sale_cls.query.filter.return_value.all.return_value = sales
        result = DataAnalyzer.analyze_sales_performance(period_days=30)
    assert result["success"] is True
    assert result["analysis"]["total_sales"] == 2
    names = [c["name"] for c in result["analysis"]["top_customers"]]
    assert names == ["Ali"]


def test_cov_da_sales_all_customers_none():
    """Arc 140->139 only-false side: every sale lacks a customer."""
    sales = [_sale(50, None, day=1), _sale(70, None, day=1)]
    with patch("models.Sale") as sale_cls:
        sale_cls.created_at = _Col()
        sale_cls.query.filter.return_value.all.return_value = sales
        result = DataAnalyzer.analyze_sales_performance(period_days=30)
    assert result["success"] is True
    assert result["analysis"]["top_customers"] == []


def _product(pid, pname, sku, stock):
    prod = MagicMock()
    prod.id = pid
    prod.name = pname
    prod.sku = sku
    prod.current_stock = stock
    return prod


def test_cov_da_all_products_skips_product_without_lines():
    """Arc 224->221: product with no sales lines is skipped."""
    prod_a = _product(1, "A", "A1", 4)
    prod_b = _product(2, "B", "B1", 9)
    line = MagicMock(quantity=2, line_total=Decimal("30"))
    with patch("models.Product") as product_cls, patch("models.SaleLine") as sl_cls:
        product_cls.query.all.return_value = [prod_a, prod_b]
        sl_cls.query.filter.return_value.all.side_effect = [[line], []]
        result = DataAnalyzer.analyze_product_performance()
    assert result["success"] is True
    assert result["total_products"] == 2
    assert result["analyzed_products"] == 1
    assert result["top_products"][0]["name"] == "A"


def test_cov_da_payment_repeated_method_hits_else_arc():
    """Arc 286->289: second payment reuses method (not-not-in dict)."""
    pay1 = MagicMock(payment_method="cash", amount=Decimal("100"))
    pay2 = MagicMock(payment_method="cash", amount=Decimal("50"))
    with patch("models.Payment") as payment_cls:
        payment_cls.query.all.return_value = [pay1, pay2]
        result = DataAnalyzer.analyze_payment_patterns()
    assert result["success"] is True
    assert result["analysis"]["total_payments"] == 2
    assert len(result["analysis"]["payment_methods"]) == 1
    assert result["analysis"]["payment_methods"][0]["count"] == 2
    assert result["analysis"]["payment_methods"][0]["total_amount"] == 150.0


def test_cov_da_payment_mixed_methods_covers_both_sides():
    """Both sides of 286: new method creates entry, repeat hits 289."""
    pay1 = MagicMock(payment_method="cash", amount=Decimal("100"))
    pay2 = MagicMock(payment_method="card", amount=Decimal("200"))
    pay3 = MagicMock(payment_method="cash", amount=Decimal("50"))
    with patch("models.Payment") as payment_cls:
        payment_cls.query.all.return_value = [pay1, pay2, pay3]
        result = DataAnalyzer.analyze_payment_patterns()
    assert result["success"] is True
    assert result["analysis"]["total_payments"] == 3
    assert len(result["analysis"]["payment_methods"]) == 2
