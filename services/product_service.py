"""Product service — product creation and management."""

from __future__ import annotations

import logging

from extensions import db

logger = logging.getLogger(__name__)


class ProductService:
    """Pure business logic for product operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_product(
        name: str,
        regular_price,
        part_number: str = "",
        current_stock: float = 0,
        unit: str = "قطعة",
        tenant_id: int | None = None,
    ):
        """Create a new product. Returns the created product (not yet committed)."""
        from models import Product

        product = Product(
            name=name,
            part_number=part_number,
            regular_price=regular_price,
            current_stock=current_stock,
            unit=unit,
        )
        if tenant_id is not None:
            product.tenant_id = tenant_id
        db.session.add(product)
        return product
