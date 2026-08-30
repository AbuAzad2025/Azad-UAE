"""Coverage boost 2 — remaining services to reach 99%+."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.payment_service import PaymentService
from services.reports_query_service import ReportsQueryService


class TestPaymentServiceCoverage:
    def test_create_receipt_manual_sale_id_none(self):
        with (
            patch("services.payment_service.db.session", MagicMock()),
            patch("services.payment_service.convert_and_quantize_aed", return_value=Decimal("10")),
            patch("services.payment_service.resolve_tenant_base_currency", return_value="AED"),
        ):
            from models import Customer

            cust = MagicMock(spec=Customer)
            cust.id = 1
            cust.tenant_id = 1
            with patch("services.payment_service.current_user", MagicMock(is_authenticated=False)):
                r = PaymentService.create_receipt(
                    {
                        "tenant_id": 1,
                        "customer_id": 1,
                        "amount": "10",
                        "currency": "AED",
                        "payment_method": "cash",
                        "source_type": "manual",
                        "source_id": None,
                    },
                    customer=cust,
                    receipt_number="REC-TEST-1",
                )
                assert r.sale_id is None
                assert r.source_type == "manual"

    def test_create_receipt_sale_sets_sale_id(self):
        with (
            patch("services.payment_service.db.session", MagicMock()),
            patch("services.payment_service.convert_and_quantize_aed", return_value=Decimal("20")),
            patch("services.payment_service.resolve_tenant_base_currency", return_value="AED"),
        ):
            cust = MagicMock()
            cust.id = 2
            cust.tenant_id = 1
            with patch("services.payment_service.current_user", MagicMock(is_authenticated=True, id=5)):
                r = PaymentService.create_receipt(
                    {
                        "tenant_id": 1,
                        "customer_id": 2,
                        "amount": "20",
                        "currency": "AED",
                        "payment_method": "cash",
                        "source_type": "sale",
                        "source_id": 99,
                    },
                    customer=cust,
                    receipt_number="REC-TEST-2",
                )
                assert r.sale_id == 99
                assert r.source_id == 99


class TestReportsQueryCoverage:
    def test_dashboard_stats_empty_tenant(self):
        with patch("services.reports_query_service.tenant_query") as mock_tq:
            mock_q = MagicMock()
            mock_q.count.return_value = 0
            mock_q.scalar.return_value = Decimal("0")
            mock_tq.return_value = mock_q
            result = ReportsQueryService.dashboard_stats(tenant_id=999)
            assert isinstance(result, dict)

    def test_sales_by_period_no_data(self):
        with patch("services.reports_query_service.tenant_query") as mock_tq:
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.all.return_value = []
            mock_tq.return_value = mock_q
            result = ReportsQueryService.sales_by_period(tenant_id=1, period="monthly")
            assert result == []


class TestSaleServiceCoverage:
    def test_calculate_totals_vat_inclusive(self):
        from models.sale import Sale, SaleLine

        sale = Sale(
            tenant_id=1,
            sale_number="S-1",
            customer_id=1,
            seller_id=1,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        line = SaleLine(
            tenant_id=1,
            sale_id=1,
            product_id=1,
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            line_total=Decimal("200"),
        )
        sale.lines = [line]
        sale.subtotal = Decimal("200")
        sale.discount_amount = Decimal("10")
        sale.promotion_discount_amount = Decimal("5")
        sale.shipping_cost = Decimal("5")
        sale.tax_rate = Decimal("5")
        sale.prices_include_vat = True
        sale.calculate_totals()
        assert sale.total_amount > Decimal("0")

    def test_calculate_totals_vat_exclusive(self):
        from models.sale import Sale, SaleLine

        sale = Sale(
            tenant_id=1,
            sale_number="S-2",
            customer_id=1,
            seller_id=1,
            total_amount=Decimal("0"),
            amount=Decimal("0"),
            amount_aed=Decimal("0"),
            currency="AED",
            exchange_rate=Decimal("1"),
        )
        line = SaleLine(
            tenant_id=1,
            sale_id=1,
            product_id=1,
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            line_total=Decimal("100"),
        )
        sale.lines = [line]
        sale.subtotal = Decimal("100")
        sale.discount_amount = Decimal("0")
        sale.promotion_discount_amount = Decimal("0")
        sale.shipping_cost = Decimal("0")
        sale.tax_rate = Decimal("5")
        sale.prices_include_vat = False
        sale.calculate_totals()
        assert sale.tax_amount == Decimal("5.00")


class TestProductServiceExtra:
    def test_stock_transfer_same_warehouse_raises(self):
        from services.stock_service import StockService

        with patch("extensions.db.session.get", return_value=MagicMock(tenant_id=1)):
            wh = MagicMock()
            wh.id = 1
            q = MagicMock()
            q.filter_by.return_value = q
            q.first.return_value = wh
            with patch("models.Warehouse.query", q):
                with pytest.raises(ValueError, match="نفس المستودع"):
                    StockService.transfer_stock(product_id=1, from_warehouse_id=1, to_warehouse_id=1, quantity=5)
