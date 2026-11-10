"""FX accounting reconciliation — multi-currency sales post to base consistently.

Each sale's ``amount_aed`` is the single source the scope P&L reads, so the
revenue recognized in base currency must equal amount × rate exactly, in
every currency/rate combination.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from models import Sale, SaleLine
from services.partner_service import PartnerService
from utils.currency_utils import convert_and_quantize_aed

JAN = (date(2026, 1, 1), date(2026, 1, 31))


class TestMultiCurrencyRevenue:
    @pytest.mark.parametrize(
        "amount,rate,currency",
        [
            ("100", "3.65", "USD"), ("200", "3.65", "USD"), ("50", "4.00", "EUR"),
            ("1000", "0.98", "SAR"), ("75", "11.95", "KWD"), ("300", "0.95", "ILS"),
        ],
    )
    def test_revenue_in_base_currency(
        self, db_session, sample_tenant, sample_warehouse, sample_user, sample_customer,
        sample_product, amount, rate, currency,
    ):
        expected = convert_and_quantize_aed(Decimal(amount), currency, Decimal(rate), base_currency="AED")
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"FX-{currency}-{amount}-{rate}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            sale_date=datetime(2026, 1, 10, tzinfo=UTC),
            status="confirmed",
            subtotal=Decimal(amount),
            total_amount=Decimal(amount),
            amount=Decimal(amount),
            amount_aed=expected,
            tax_amount=Decimal("0"),
            currency=currency,
            exchange_rate=Decimal(rate),
        )
        db_session.add(sale)
        db_session.flush()
        db_session.add(
            SaleLine(
                tenant_id=sample_tenant.id, sale_id=sale.id, product_id=sample_product.id,
                quantity=Decimal("1"), unit_price=Decimal(amount), line_total=Decimal(amount),
                cost_price=Decimal("0"),
            )
        )
        db_session.flush()
        revenue = PartnerService.get_scope_revenue(sample_tenant.id, *JAN, "company")
        assert Decimal(str(revenue)) == expected
