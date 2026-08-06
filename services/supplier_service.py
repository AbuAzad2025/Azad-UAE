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
        name_en: str = "",
        company_name: str = "",
        phone2: str = "",
        website: str = "",
        city: str = "",
        country: str = "PS",
        tax_number: str = "",
        commercial_registration: str = "",
        supplier_type: str = "individual",
        rating=None,
        credit_limit: float = 0,
        payment_terms_days: int = 30,
        preferred_currency: str = "AED",
        total_purchases_aed=None,
        total_paid_aed=None,
        notes: str = "",
        tags: str = "",
        is_verified: bool = False,
        tenant_id: int | None = None,
        created_by: int | None = None,
    ):
        """Create a new supplier. Returns the created supplier (not yet committed)."""
        from models import Supplier

        supplier = Supplier(
            name=name,
            name_en=name_en,
            company_name=company_name,
            phone=phone,
            phone2=phone2,
            email=email,
            website=website,
            address=address,
            city=city,
            country=country,
            tax_number=tax_number,
            commercial_registration=commercial_registration,
            supplier_type=supplier_type,
            rating=rating,
            credit_limit=credit_limit,
            payment_terms_days=payment_terms_days,
            preferred_currency=preferred_currency,
            total_purchases_aed=total_purchases_aed or 0,
            total_paid_aed=total_paid_aed or 0,
            notes=notes,
            tags=tags,
            is_verified=is_verified,
            is_active=True,
            created_by=created_by,
        )
        if tenant_id is not None:
            supplier.tenant_id = tenant_id
        db.session.add(supplier)
        return supplier
