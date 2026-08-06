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
        cost_price=None,
        sku: str = "",
        barcode: str = "",
        part_number: str = "",
        current_stock: float = 0,
        unit: str = "قطعة",
        category_id: int | None = None,
        warranty_days: int = 0,
        tenant_id: int | None = None,
    ):
        """Create a new product. Returns the created product (not yet committed)."""
        from models import Product

        product = Product(
            name=name,
            sku=sku,
            barcode=barcode,
            regular_price=regular_price,
            cost_price=cost_price,
            part_number=part_number,
            current_stock=current_stock,
            unit=unit,
            category_id=category_id,
            warranty_days=warranty_days,
        )
        if tenant_id is not None:
            product.tenant_id = tenant_id
        db.session.add(product)
        return product

    @staticmethod
    def create_category(name: str, name_ar: str = "", description: str = "", tenant_id: int | None = None):
        """Create a new product category. Returns the created category (not yet committed)."""
        from models.product import ProductCategory

        category = ProductCategory(
            name=name,
            name_ar=name_ar or name,
            description=description,
            is_active=True,
        )
        if tenant_id is not None:
            category.tenant_id = tenant_id
        db.session.add(category)
        return category

    @staticmethod
    def delete_product(product, has_sales: bool = False, has_purchases: bool = False):
        """Soft-delete (deactivate) if product has transactions, otherwise hard-delete."""
        if has_sales or has_purchases:
            product.is_active = False
        else:
            db.session.delete(product)

    @staticmethod
    def create_price_tier(product_id: int, tier_code: str, price, currency: str = "AED", tenant_id: int | None = None):
        """Create a price tier for a product. Returns the tier (not yet committed)."""
        from models import ProductPriceTier

        tier = ProductPriceTier(
            product_id=product_id,
            tier_code=tier_code,
            price=price,
            currency=currency,
        )
        if tenant_id is not None:
            tier.tenant_id = tenant_id
        db.session.add(tier)
        return tier
