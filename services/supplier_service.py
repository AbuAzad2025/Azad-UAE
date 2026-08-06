"""Supplier service — supplier creation and management."""

from __future__ import annotations

import logging

from extensions import db

logger = logging.getLogger(__name__)


class SupplierService:
    """Pure business logic for supplier operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_supplier(
        name: str,
        phone: str = "",
        email: str = "",
        address: str = "",
        tenant_id: int | None = None,
    ):
        """Create a new supplier. Returns the created supplier (not yet committed)."""
        from models import Supplier

        supplier = Supplier(name=name, phone=phone, email=email, address=address, is_active=True)
        if tenant_id is not None:
            supplier.tenant_id = tenant_id
        db.session.add(supplier)
        return supplier
