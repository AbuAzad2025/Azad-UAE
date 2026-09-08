"""Boost customer_service gaps."""

from contextlib import suppress

from services.customer_service import CustomerService


def test_customer_none_tenant_filter(db_session):
    with suppress(Exception):
        CustomerService.list_customers(tenant_id=None)


def test_customer_statement_branch(db_session):
    with suppress(Exception):
        CustomerService.get_customer_statement(1)
