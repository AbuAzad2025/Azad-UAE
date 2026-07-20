"""Integration tests for AnalyticsService — real DB only (no session mocks)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest


def _add_customer(db_session, tenant_id, *, name, email_suffix):
    from models import Customer

    customer = Customer(
        tenant_id=tenant_id,
        name=name,
        email=f"{email_suffix}-{uuid.uuid4().hex[:6]}@analytics.test",
        phone=f"05{uuid.uuid4().int % 10**8:08d}",
        is_active=True,
    )
    db_session.add(customer)
    db_session.flush()
    return customer


def _add_sale(
    db_session,
    *,
    tenant_id,
    customer_id,
    seller_id,
    amount,
    branch_id=None,
    sale_date=None,
):
    from models import Sale

    when = sale_date or datetime.now(timezone.utc)
    amt = Decimal(str(amount))
    sale = Sale(
        tenant_id=tenant_id,
        sale_number=f"S-{uuid.uuid4().hex[:8]}",
        customer_id=customer_id,
        seller_id=seller_id,
        branch_id=branch_id,
        sale_date=when,
        created_at=when,
        subtotal=amt,
        total_amount=amt,
        amount=amt,
        amount_aed=amt,
        status="confirmed",
    )
    db_session.add(sale)
    db_session.flush()
    return sale


def _add_sale_line(db_session, *, tenant_id, sale_id, product_id, qty, unit_price, cost_price):
    from models import SaleLine

    qty_d = Decimal(str(qty))
    unit_d = Decimal(str(unit_price))
    line = SaleLine(
        tenant_id=tenant_id,
        sale_id=sale_id,
        product_id=product_id,
        quantity=qty_d,
        unit_price=unit_d,
        line_total=unit_d * qty_d,
        cost_price=Decimal(str(cost_price)),
    )
    db_session.add(line)
    db_session.flush()
    return line


@pytest.mark.integration
class TestCustomerInsightsIntegration:
    def test_sorts_by_lifetime_value_desc_and_caps_fifty(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
    ):
        from models import Customer
        from services.analytics_service import AnalyticsService

        now = datetime.now(timezone.utc)
        with app.app_context():
            for i in range(55):
                customer = _add_customer(
                    db_session,
                    sample_tenant.id,
                    name=f"C{i}",
                    email_suffix=f"ltv{i}",
                )
                _add_sale(
                    db_session,
                    tenant_id=sample_tenant.id,
                    customer_id=customer.id,
                    seller_id=sample_user.id,
                    amount=1000 - i,
                    sale_date=now,
                )
            db_session.commit()

            seeded = (
                db_session.query(Customer)
                .filter_by(
                    tenant_id=sample_tenant.id,
                    is_active=True,
                )
                .count()
            )
            assert seeded >= 55

            result = AnalyticsService.get_customer_insights(tenant_id=sample_tenant.id)

        assert len(result) == 50
        assert result[0]["lifetime_value"] >= result[1]["lifetime_value"]
        assert result[0]["lifetime_value"] == pytest.approx(1000.0)
        assert result[-1]["lifetime_value"] == pytest.approx(951.0)

    def test_branch_filter_scopes_to_branch_sales(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
        sample_branch,
    ):
        from models import Branch
        from services.analytics_service import AnalyticsService

        with app.app_context():
            other_branch = Branch(
                tenant_id=sample_tenant.id,
                name=f"Other {uuid.uuid4().hex[:4]}",
                code=f"OB{uuid.uuid4().hex[:3].upper()}",
                is_active=True,
            )
            db_session.add(other_branch)
            db_session.flush()

            main_customer = _add_customer(
                db_session,
                sample_tenant.id,
                name="Main Branch Cust",
                email_suffix="main",
            )
            other_customer = _add_customer(
                db_session,
                sample_tenant.id,
                name="Other Branch Cust",
                email_suffix="other",
            )
            _add_sale(
                db_session,
                tenant_id=sample_tenant.id,
                customer_id=main_customer.id,
                seller_id=sample_user.id,
                amount=500,
                branch_id=sample_branch.id,
            )
            _add_sale(
                db_session,
                tenant_id=sample_tenant.id,
                customer_id=other_customer.id,
                seller_id=sample_user.id,
                amount=900,
                branch_id=other_branch.id,
            )
            db_session.commit()

            result = AnalyticsService.get_customer_insights(
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
            )

        assert len(result) == 1
        assert result[0]["name"] == "Main Branch Cust"
        assert result[0]["lifetime_value"] == pytest.approx(500.0)


@pytest.mark.integration
class TestSalesInsightsIntegration:
    def test_daily_sales_and_top_products_shape(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
        sample_product,
        sample_branch,
    ):
        from services.analytics_service import AnalyticsService

        now = datetime.now(timezone.utc)
        with app.app_context():
            sale = _add_sale(
                db_session,
                tenant_id=sample_tenant.id,
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                amount=2500,
                branch_id=sample_branch.id,
                sale_date=now,
            )
            _add_sale_line(
                db_session,
                tenant_id=sample_tenant.id,
                sale_id=sale.id,
                product_id=sample_product.id,
                qty=10,
                unit_price=90,
                cost_price=30,
            )
            db_session.commit()

            insights = AnalyticsService.get_sales_insights(
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
            )

        assert insights["daily_sales"]
        assert insights["daily_sales"][0]["total"] == pytest.approx(2500.0)
        assert insights["top_products"]
        assert insights["top_products"][0]["revenue"] == pytest.approx(900.0)

    def test_branch_filter_excludes_other_branch_sales(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
        sample_product,
        sample_branch,
    ):
        from models import Branch
        from services.analytics_service import AnalyticsService

        with app.app_context():
            other_branch = Branch(
                tenant_id=sample_tenant.id,
                name=f"Alt {uuid.uuid4().hex[:4]}",
                code=f"AL{uuid.uuid4().hex[:3].upper()}",
                is_active=True,
            )
            db_session.add(other_branch)
            db_session.flush()

            sale_here = _add_sale(
                db_session,
                tenant_id=sample_tenant.id,
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                amount=100,
                branch_id=sample_branch.id,
            )
            _add_sale_line(
                db_session,
                tenant_id=sample_tenant.id,
                sale_id=sale_here.id,
                product_id=sample_product.id,
                qty=1,
                unit_price=100,
                cost_price=10,
            )
            sale_there = _add_sale(
                db_session,
                tenant_id=sample_tenant.id,
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                amount=9999,
                branch_id=other_branch.id,
            )
            _add_sale_line(
                db_session,
                tenant_id=sample_tenant.id,
                sale_id=sale_there.id,
                product_id=sample_product.id,
                qty=1,
                unit_price=9999,
                cost_price=10,
            )
            db_session.commit()

            insights = AnalyticsService.get_sales_insights(
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
            )

        assert insights["top_products"][0]["revenue"] == pytest.approx(100.0)


@pytest.mark.integration
class TestProductPerformanceIntegration:
    def test_high_volume_sorted_by_revenue(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
        sample_warehouse,
    ):
        from models import Product
        from services.analytics_service import AnalyticsService

        now = datetime.now(timezone.utc)
        with app.app_context():
            low = Product(
                tenant_id=sample_tenant.id,
                name="Low Vol",
                sku=f"L-{uuid.uuid4().hex[:6]}",
                cost_price=Decimal("10"),
                regular_price=Decimal("20"),
                is_active=True,
            )
            high = Product(
                tenant_id=sample_tenant.id,
                name="High Vol",
                sku=f"H-{uuid.uuid4().hex[:6]}",
                cost_price=Decimal("20"),
                regular_price=Decimal("40"),
                is_active=True,
            )
            db_session.add_all([low, high])
            db_session.flush()

            for product, qty, price, cost in (
                (low, 5, 20, 10),
                (high, 50, 100, 20),
            ):
                sale = _add_sale(
                    db_session,
                    tenant_id=sample_tenant.id,
                    customer_id=sample_customer.id,
                    seller_id=sample_user.id,
                    amount=qty * price,
                    sale_date=now,
                )
                _add_sale_line(
                    db_session,
                    tenant_id=sample_tenant.id,
                    sale_id=sale.id,
                    product_id=product.id,
                    qty=qty,
                    unit_price=price,
                    cost_price=cost,
                )
            db_session.commit()

            perf = AnalyticsService.get_product_performance(tenant_id=sample_tenant.id)

        assert perf[0]["name"] == "High Vol"
        assert perf[0]["status"] == "ممتاز"
        assert perf[0]["margin"] == pytest.approx(4000.0)
        assert perf[0]["margin_percent"] == pytest.approx(80.0)

    def test_branch_filter_limits_performance_rows(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
        sample_product,
        sample_branch,
    ):
        from models import Branch
        from services.analytics_service import AnalyticsService

        now = datetime.now(timezone.utc)
        with app.app_context():
            empty_branch = Branch(
                tenant_id=sample_tenant.id,
                name=f"Empty {uuid.uuid4().hex[:4]}",
                code=f"EM{uuid.uuid4().hex[:3].upper()}",
                is_active=True,
            )
            db_session.add(empty_branch)
            db_session.flush()

            sale = _add_sale(
                db_session,
                tenant_id=sample_tenant.id,
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                amount=200,
                branch_id=sample_branch.id,
                sale_date=now,
            )
            _add_sale_line(
                db_session,
                tenant_id=sample_tenant.id,
                sale_id=sale.id,
                product_id=sample_product.id,
                qty=2,
                unit_price=100,
                cost_price=40,
            )
            db_session.commit()

            assert (
                AnalyticsService.get_product_performance(
                    tenant_id=sample_tenant.id,
                    branch_id=empty_branch.id,
                )
                == []
            )


@pytest.mark.integration
class TestForecastingAndPackagesIntegration:
    def test_forecast_returns_twelve_months_and_confidence_label(
        self,
        app,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
    ):
        from services.analytics_service import AnalyticsService

        base = datetime.now(timezone.utc).replace(day=15)
        with app.app_context():
            for month_offset, revenue in enumerate(
                [100, 500, 50, 400, 80, 450, 60, 420, 70, 410, 90, 430],
            ):
                when = base - timedelta(days=30 * month_offset)
                _add_sale(
                    db_session,
                    tenant_id=sample_tenant.id,
                    customer_id=sample_customer.id,
                    seller_id=sample_user.id,
                    amount=revenue,
                    sale_date=when,
                )
            db_session.commit()

            historical, forecast = AnalyticsService.get_forecasting_data(
                tenant_id=sample_tenant.id,
            )

        assert len(historical) == 12
        assert forecast["confidence"] in ("عالية", "متوسطة", "منخفضة")

    def test_package_performance_completed_vs_pending(self, app, db_session):
        from models import Package, PackagePurchase
        from services.analytics_service import AnalyticsService

        slug = f"gold-{uuid.uuid4().hex[:8]}"
        with app.app_context():
            package = Package(
                name_ar="Gold",
                name_en="Gold",
                slug=slug,
                price=100.0,
                is_active=True,
            )
            db_session.add(package)
            db_session.flush()
            db_session.add_all(
                [
                    PackagePurchase(
                        package_id=package.id,
                        customer_name="A",
                        customer_email=f"a-{uuid.uuid4().hex[:6]}@t.com",
                        payment_method="card",
                        payment_status="completed",
                        amount_paid=100.0,
                    ),
                    PackagePurchase(
                        package_id=package.id,
                        customer_name="B",
                        customer_email=f"b-{uuid.uuid4().hex[:6]}@t.com",
                        payment_method="card",
                        payment_status="pending",
                        amount_paid=0.0,
                    ),
                ]
            )
            db_session.commit()

            result = AnalyticsService.get_package_performance(tenant_id=None)

        row = next(r for r in result if r["package_name"] == "Gold")
        assert row["completed"] == 1
        assert row["pending"] == 1
        assert row["revenue"] == pytest.approx(100.0)


@pytest.mark.integration
class TestDonationAnalyticsIntegration:
    def test_payment_method_aggregation(self, app, db_session, sample_tenant):
        from models import Donation
        from services.analytics_service import AnalyticsService

        with app.app_context():
            db_session.add_all(
                [
                    Donation(
                        tenant_id=sample_tenant.id,
                        amount_usd=Decimal("50"),
                        payment_method="card",
                        status="completed",
                    ),
                    Donation(
                        tenant_id=sample_tenant.id,
                        amount_usd=Decimal("30"),
                        payment_method="card",
                        status="completed",
                    ),
                    Donation(
                        tenant_id=sample_tenant.id,
                        amount_usd=Decimal("10"),
                        payment_method="bank",
                        status="completed",
                    ),
                ]
            )
            db_session.commit()

            stats = AnalyticsService.get_payment_method_stats(tenant_id=sample_tenant.id)

        assert "card" in stats["methods"]
        assert "bank" in stats["methods"]
        assert sum(stats["totals"]) == pytest.approx(90.0)

    def test_predict_revenue_growth_projection(self):
        from services.analytics_service import AnalyticsService

        with patch.object(
            AnalyticsService,
            "get_revenue_by_period",
            return_value={"total_revenue": 600, "purchases": [], "donations": []},
        ):
            pred = AnalyticsService.predict_revenue(months=2, tenant_id=1)

        assert pred["historical_avg"] == pytest.approx(100.0)
        assert len(pred["predictions"]) == 2
        assert pred["growth_rate"] == 0.05
