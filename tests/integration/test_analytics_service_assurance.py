"""Integration tests for AnalyticsService — real DB queries."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest


@pytest.mark.integration
class TestCustomerInsightsIntegration:
    """get_customer_insights — LTV sorting and cap against real PostgreSQL."""

    def test_sorts_by_lifetime_value_desc_and_caps_fifty(
        self, app, db_session, sample_tenant, sample_user,
    ):
        from extensions import db
        from models import Customer, Sale
        from services.analytics_service import AnalyticsService

        now = datetime.now(timezone.utc)
        with app.app_context():
            for i in range(55):
                customer = Customer(
                    tenant_id=sample_tenant.id,
                    name=f'C{i}',
                    email=f'ltv-{i}-{uuid.uuid4().hex[:6]}@test.local',
                    phone=f'055{i:07d}',
                    is_active=True,
                )
                db_session.add(customer)
                db_session.flush()
                amount = Decimal(str(1000 - i))
                db_session.add(Sale(
                    tenant_id=sample_tenant.id,
                    sale_number=f'LTV-{i}-{uuid.uuid4().hex[:6]}',
                    customer_id=customer.id,
                    seller_id=sample_user.id,
                    sale_date=now,
                    created_at=now,
                    subtotal=amount,
                    total_amount=amount,
                    amount=amount,
                    amount_aed=amount,
                    status='confirmed',
                ))
            db_session.commit()

            seeded = db.session.query(Customer).filter_by(
                tenant_id=sample_tenant.id, is_active=True,
            ).count()
            assert seeded >= 55, (
                f'expected >=55 customers for tenant {sample_tenant.id}, got {seeded}'
            )

            result = AnalyticsService.get_customer_insights(tenant_id=sample_tenant.id)

        assert len(result) == 50
        assert result[0]['lifetime_value'] >= result[1]['lifetime_value']
        assert result[0]['lifetime_value'] == pytest.approx(1000.0)
        assert result[-1]['lifetime_value'] == pytest.approx(951.0)
