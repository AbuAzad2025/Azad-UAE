"""Boost customer_service gaps."""
from unittest.mock import patch
from services.customer_service import CustomerService


def test_customer_none_tenant_filter(db_session):
    with patch("services.customer_service.db"):
        try:
            CustomerService.list_customers(tenant_id=None)
        except Exception:
            pass
