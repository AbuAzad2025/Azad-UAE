"""Tests for API balance isolation - cross-tenant customer/supplier balance returns 0.0"""

from unittest.mock import MagicMock, patch
from models import Customer, Supplier, Tenant


class TestAPIBalanceIsolation:
    """Test that API balance helpers enforce tenant isolation."""

    @staticmethod
    def _make_tenant(db_session, name="Test Tenant"):
        import uuid

        unique = str(uuid.uuid4())[:8]
        tenant = Tenant(
            name=f"{name} {unique}",
            name_ar="Ø´Ø±ÙƒØ© ØªØ¬Ø±Ø¨Ø©",
            slug=f"test-{unique}",
            email=f"test-{unique}@example.com",
            phone_1="0500000000",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(tenant)
        db_session.flush()
        return tenant

    @staticmethod
    def _make_customer(db_session, tenant_id, name="Test Customer"):
        import uuid

        unique = str(uuid.uuid4())[:8]
        customer = Customer(
            tenant_id=tenant_id,
            name=f"{name} {unique}",
            phone="0500000000",
            email=f"customer-{unique}@example.com",
            is_active=True,
            customer_type="regular",
        )
        db_session.add(customer)
        db_session.flush()
        return customer

    @staticmethod
    def _make_supplier(db_session, tenant_id, name="Test Supplier"):
        import uuid

        unique = str(uuid.uuid4())[:8]
        supplier = Supplier(
            tenant_id=tenant_id,
            name=f"{name} {unique}",
            phone="0500000000",
            email=f"supplier-{unique}@example.com",
            is_active=True,
        )
        db_session.add(supplier)
        db_session.flush()
        return supplier

    def test_customer_balance_cross_tenant_returns_zero(self, app, db_session):
        """Tenant A user requesting tenant B customer balance returns 0.0 without branch scope."""
        tenant_a = self._make_tenant(db_session, "Tenant A")
        tenant_b = self._make_tenant(db_session, "Tenant B")

        customer_a = self._make_customer(db_session, tenant_a.id, "Customer A")
        customer_b = self._make_customer(db_session, tenant_b.id, "Customer B")
        db_session.commit()

        # Mock user from tenant A
        user_a = MagicMock()
        user_a.id = 1
        user_a.tenant_id = tenant_a.id
        user_a.is_authenticated = True
        user_a.is_owner = False

        with app.test_request_context():
            with patch("routes.api.current_user", user_a):
                with patch("routes.api.branch_scope_id", return_value=None):
                    from routes.api import _customer_balance

                    # Request tenant B's customer from tenant A context - should return 0.0
                    result = _customer_balance(customer_b.id)
                    assert result == 0.0, (
                        "Cross-tenant customer balance must return 0.0"
                    )

                    # Request tenant A's own customer - should return balance
                    result = _customer_balance(customer_a.id)
                    assert result == 0.0, (
                        "Own tenant customer returns 0.0 (no transactions yet)"
                    )

    def test_supplier_balance_cross_tenant_returns_zero(self, app, db_session):
        """Tenant A user requesting tenant B supplier balance returns 0.0 without branch scope."""
        tenant_a = self._make_tenant(db_session, "Tenant A")
        tenant_b = self._make_tenant(db_session, "Tenant B")

        supplier_a = self._make_supplier(db_session, tenant_a.id, "Supplier A")
        supplier_b = self._make_supplier(db_session, tenant_b.id, "Supplier B")
        db_session.commit()

        # Mock user from tenant A
        user_a = MagicMock()
        user_a.id = 1
        user_a.tenant_id = tenant_a.id
        user_a.is_authenticated = True
        user_a.is_owner = False

        with app.test_request_context():
            with patch("routes.api.current_user", user_a):
                with patch("routes.api.branch_scope_id", return_value=None):
                    from routes.api import _supplier_balance

                    # Request tenant B's supplier from tenant A context - should return 0.0
                    result = _supplier_balance(supplier_b.id)
                    assert result == 0.0, (
                        "Cross-tenant supplier balance must return 0.0"
                    )

                    # Request tenant A's own supplier - should return balance
                    result = _supplier_balance(supplier_a.id)
                    assert result == 0.0, (
                        "Own tenant supplier returns 0.0 (no transactions yet)"
                    )

    def test_missing_customer_balance_returns_zero(self, app, db_session):
        """Non-existent customer ID returns 0.0 (same as cross-tenant)."""
        tenant_a = self._make_tenant(db_session, "Tenant A")
        user_a = MagicMock()
        user_a.id = 1
        user_a.tenant_id = tenant_a.id
        user_a.is_authenticated = True
        user_a.is_owner = False

        with app.test_request_context():
            with patch("routes.api.current_user", user_a):
                with patch("routes.api.branch_scope_id", return_value=None):
                    from routes.api import _customer_balance

                    result = _customer_balance(999999)
                    assert result == 0.0, "Missing customer ID must return 0.0"

    def test_missing_supplier_balance_returns_zero(self, app, db_session):
        """Non-existent supplier ID returns 0.0 (same as cross-tenant)."""
        tenant_a = self._make_tenant(db_session, "Tenant A")
        user_a = MagicMock()
        user_a.id = 1
        user_a.tenant_id = tenant_a.id
        user_a.is_authenticated = True
        user_a.is_owner = False

        with app.test_request_context():
            with patch("routes.api.current_user", user_a):
                with patch("routes.api.branch_scope_id", return_value=None):
                    from routes.api import _supplier_balance

                    result = _supplier_balance(999999)
                    assert result == 0.0, "Missing supplier ID must return 0.0"
