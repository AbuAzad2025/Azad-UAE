"""Multi-currency aggregation regression tests (P4).

Guards the P1 fix: analytics and financial KPIs must aggregate BASE-currency
amounts (amount_aed), never original-currency totals, so a tenant selling in
mixed currencies never sees cross-currency sums.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from services.analytics_service import AnalyticsService


def _make_sale(db_session, tenant, customer, seller, *, currency, total, rate, base_total):
    from models import Sale

    sale = Sale(
        tenant_id=tenant.id,
        sale_number=f"FX-{uuid.uuid4().hex[:8]}",
        customer_id=customer.id,
        seller_id=seller.id,
        status="confirmed",
        sale_date=datetime.now(timezone.utc),
        subtotal=Decimal(str(total)),
        total_amount=Decimal(str(total)),
        amount=Decimal(str(total)),
        currency=currency,
        exchange_rate=Decimal(str(rate)),
        amount_aed=Decimal(str(base_total)),
    )
    db_session.add(sale)
    db_session.flush()
    return sale


@pytest.fixture
def fx_sales(db_session, sample_tenant, sample_customer, sample_user):
    """Two confirmed sales in different currencies for one tenant/customer.

    100 USD @ 3.67 -> 367 base (tenant base is AED in sample_tenant)
    100 ILS @ 1.00 -> 100 base
    Unsafe original-currency sum would be 200; correct base sum is 467.
    """
    _make_sale(
        db_session,
        sample_tenant,
        sample_customer,
        sample_user,
        currency="USD",
        total="100",
        rate="3.67",
        base_total="367",
    )
    _make_sale(
        db_session,
        sample_tenant,
        sample_customer,
        sample_user,
        currency="ILS",
        total="100",
        rate="1.0",
        base_total="100",
    )
    db_session.commit()
    return sample_tenant, sample_customer


class TestMultiCurrencyAggregation:
    def test_customer_lifetime_value_uses_base_currency(self, app, fx_sales):
        tenant, customer = fx_sales
        with app.app_context():
            insights = AnalyticsService.get_customer_insights(tenant.id)
        row = next(r for r in insights if r["name"] == customer.name)
        assert row["lifetime_value"] == pytest.approx(467.0)
        assert row["lifetime_value"] != pytest.approx(200.0)

    def test_daily_sales_trend_uses_base_currency(self, app, fx_sales):
        tenant, _ = fx_sales
        with app.app_context():
            insights = AnalyticsService.get_sales_insights(tenant.id)
        today = datetime.now().date().isoformat()
        today_rows = [d for d in insights["daily_sales"] if d["date"] == today]
        assert today_rows, "expected at least one daily-sales row for today"
        assert sum(d["total"] for d in today_rows) == pytest.approx(467.0)
