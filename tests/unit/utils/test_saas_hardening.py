"""SaaS isolation & limits verification — write-path guard, subscription
expiry (402), resource-limit enforcement (403)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from extensions import db


class TestCrossTenantWriteBlock:
    """Verify the before_flush guard blocks cross-tenant INSERT/UPDATE."""

    @staticmethod
    def _active_tenant_context(app, tenant_id):
        """Return a request context with a mocked active tenant."""
        ctx = app.test_request_context()
        ctx.push()
        with patch("utils.tenant_orm._active_tenant_for_orm", return_value=tenant_id):
            yield
        ctx.pop()

    def test_cross_tenant_insert_raises_isolation_error(self, app, db_session, sample_tenant):
        from models import Product
        from models.tenant import Tenant
        from utils.tenant_orm import TenantIsolationError
        import uuid

        other = Tenant(
            name=f"Other {uuid.uuid4().hex[:8]}",
            name_ar="أخرى",
            slug=f"other-{uuid.uuid4().hex[:8]}",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        with app.test_request_context():
            with patch("utils.tenant_orm._active_tenant_for_orm", return_value=sample_tenant.id):
                product = Product(
                    name="Cross-tenant",
                    sku=f"X-{uuid.uuid4().hex[:8]}",
                    tenant_id=other.id,
                    regular_price=Decimal("100.00"),
                )
                db_session.add(product)
                with pytest.raises(TenantIsolationError, match="Cross-tenant INSERT"):
                    db_session.flush()
                db_session.rollback()

    def test_cross_tenant_update_raises_isolation_error(self, app, db_session, sample_tenant, sample_product):
        from models.tenant import Tenant
        from utils.tenant_orm import TenantIsolationError
        import uuid

        other = Tenant(
            name=f"Other {uuid.uuid4().hex[:8]}",
            name_ar="أخرى",
            slug=f"other-{uuid.uuid4().hex[:8]}",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        sample_product.tenant_id = other.id
        db_session.commit()

        with app.test_request_context():
            with patch("utils.tenant_orm._active_tenant_for_orm", return_value=sample_tenant.id):
                sample_product.name = "Hacked name"
                db_session.add(sample_product)
                with pytest.raises(TenantIsolationError, match="Cross-tenant UPDATE"):
                    db_session.flush()
                db_session.rollback()


class TestSubscriptionExpiryEnforcement:
    """Verify expired subscription returns HTTP 402."""

    def test_expired_subscription_blocks_request(self, app, client, sample_tenant, sample_user):
        sample_tenant.subscription_end = datetime.now(timezone.utc) - timedelta(days=1)
        sample_tenant.subscription_plan_duration = "monthly"
        db.session.flush()

        resp = client.post(
            "/auth/login",
            data={
                "username": sample_user.username,
                "password": "password123",
            },
            follow_redirects=True,
        )

        resp = client.get("/sales/", follow_redirects=False)
        assert resp.status_code == 402

    def test_lifetime_tenants_bypass_402(self, app, client, sample_tenant, sample_user):
        sample_tenant.subscription_end = datetime.now(timezone.utc) - timedelta(days=1)
        sample_tenant.subscription_plan_duration = "lifetime"
        db.session.flush()

        client.post(
            "/auth/login",
            data={
                "username": sample_user.username,
                "password": "password123",
            },
            follow_redirects=True,
        )

        resp = client.get("/sales/", follow_redirects=False)
        assert resp.status_code != 402


class TestDynamicResourceLimits:
    """Verify max_sales_per_month enforcement via the route-level decorator."""

    def test_monthly_sales_limit_blocks_at_cap(
        self,
        app,
        db_session,
        sample_tenant,
        sample_customer,
        sample_user,
        sample_product_with_stock,
        sample_warehouse,
        sample_gl_accounts,
    ):
        from datetime import datetime, timezone
        from decimal import Decimal
        from models import Sale

        sample_tenant.max_sales_per_month = 2
        db_session.flush()

        def _create_confirmed_sale():
            import uuid

            s = Sale(
                tenant_id=sample_tenant.id,
                sale_number=f"SLS-{uuid.uuid4().hex[:8]}",
                customer_id=sample_customer.id,
                seller_id=sample_user.id,
                sale_date=datetime.now(timezone.utc),
                subtotal=Decimal("100.000"),
                total_amount=Decimal("105.000"),
                amount=Decimal("105.000"),
                amount_aed=Decimal("105.000"),
                status="confirmed",
                currency="AED",
            )
            db_session.add(s)
            db_session.commit()
            return s

        _create_confirmed_sale()
        _create_confirmed_sale()

        with app.test_request_context():
            with (
                patch(
                    "utils.tenant_limits.get_active_tenant_id",
                    return_value=sample_tenant.id,
                ),
                patch("utils.tenant_limits.current_user") as mock_user,
            ):
                mock_user.is_authenticated = True

                from utils.tenant_limits import (
                    check_sales_monthly_limit,
                    TenantLimitError,
                )

                with pytest.raises(TenantLimitError):
                    check_sales_monthly_limit()

    def test_enforce_resource_limit_decorator_returns_403(self, app, db_session, sample_tenant, sample_user):
        from datetime import datetime, timezone
        from decimal import Decimal
        from models import Sale
        from utils.decorators import enforce_resource_limit

        sample_tenant.max_sales_per_month = 2
        db_session.flush()

        import uuid

        for _ in range(2):
            s = Sale(
                tenant_id=sample_tenant.id,
                sale_number=f"SLS-{uuid.uuid4().hex[:8]}",
                customer_id=1,
                seller_id=sample_user.id,
                sale_date=datetime.now(timezone.utc),
                subtotal=Decimal("100.000"),
                total_amount=Decimal("105.000"),
                amount=Decimal("105.000"),
                amount_aed=Decimal("105.000"),
                status="confirmed",
                currency="AED",
            )
            db_session.add(s)
        db_session.commit()

        @enforce_resource_limit("sales_monthly")
        def _dummy():
            return "ok"

        with app.test_request_context():
            with (
                patch(
                    "utils.tenant_limits.get_active_tenant_id",
                    return_value=sample_tenant.id,
                ),
                patch("utils.tenant_limits.current_user") as mock_user,
            ):
                mock_user.is_authenticated = True
                from werkzeug.exceptions import Forbidden

                with pytest.raises(Forbidden):
                    _dummy()
