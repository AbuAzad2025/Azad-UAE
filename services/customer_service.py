"""Customer service — balance operations and customer management."""

from __future__ import annotations

import logging

from extensions import db
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)


class CustomerService:
    """Pure business logic for customer operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_customer(name: str, phone: str | None = None, address: str | None = None, tenant_id: int | None = None):
        """Create a new customer. Returns the created customer (not yet committed)."""
        from models.customer import Customer

        customer = Customer(name=name, phone=phone or "", address=address or "", balance=0)
        if tenant_id is not None:
            customer.tenant_id = tenant_id
        db.session.add(customer)
        return customer

    @staticmethod
    def set_balance(customer_id: int, new_balance_aed, tenant_id: int):
        """Set a customer's balance directly (correction/admin operations)."""
        from models.customer import Customer

        customer = tenant_query(Customer).filter_by(id=customer_id, tenant_id=tenant_id).first()
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found in tenant {tenant_id}")
        customer.set_balance(new_balance_aed)
        db.session.flush()
        return customer.balance

    @staticmethod
    def adjust_balance(customer_id: int, delta_aed, tenant_id: int):
        """Adjust a customer's balance by delta (positive = credit, negative = debit)."""
        from models.customer import Customer

        customer = tenant_query(Customer).filter_by(id=customer_id, tenant_id=tenant_id).first()
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found in tenant {tenant_id}")
        customer.adjust_balance(delta_aed)
        db.session.flush()
        return customer.balance
