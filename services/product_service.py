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

    @staticmethod
    def get_tenant_product(product_id, tenant_id):
        """Fetch a product scoped to tenant; returns None when absent."""
        from models import Product

        return Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()

    @staticmethod
    def search_active_products(query_text, tid, limit=20):
        """Active-product search across name/name_ar/sku/barcode, tenant-scoped."""
        from sqlalchemy import or_

        from models import Product

        q = Product.query.filter(
            Product.is_active,
            or_(
                Product.name.ilike(f"%{query_text}%"),
                Product.name_ar.ilike(f"%{query_text}%"),
                Product.sku.ilike(f"%{query_text}%"),
                Product.barcode.ilike(f"%{query_text}%"),
            ),
        )
        if tid:
            q = q.filter(Product.tenant_id == tid)
        return q.limit(limit).all()

    @staticmethod
    def get_active_category(category_id, tenant_id):
        """Fetch an active category by id within a tenant; returns None when absent."""
        from models import ProductCategory

        return ProductCategory.query.filter_by(
            id=int(category_id),
            tenant_id=int(tenant_id),
            is_active=True,
        ).first()

    @staticmethod
    def category_name_taken(tenant_id, name, exclude_id=None):
        """True when another category in the tenant already uses *name* (case-insensitive)."""
        from models import ProductCategory

        q = ProductCategory.query.filter(
            ProductCategory.tenant_id == tenant_id,
            db.func.lower(ProductCategory.name) == name.lower(),
        )
        if exclude_id:
            q = q.filter(ProductCategory.id != int(exclude_id))
        return q.first() is not None

    @staticmethod
    def find_category_name_conflict(tenant_id, name, exclude_id=None):
        """Return the conflicting category for *name* (case-insensitive), if any."""
        from models import ProductCategory

        q = ProductCategory.query.filter(
            ProductCategory.tenant_id == tenant_id,
            db.func.lower(ProductCategory.name) == name.lower(),
        )
        if exclude_id:
            q = q.filter(ProductCategory.id != int(exclude_id))
        return q.first()

    @staticmethod
    def count_products_in_category(tenant_id, category_id):
        """Number of products assigned to a category within a tenant."""
        from models import Product

        return Product.query.filter_by(
            tenant_id=tenant_id,
            category_id=category_id,
        ).count()

    @staticmethod
    def list_active_categories(tenant_id, ordered=False):
        """Active categories for a tenant, optionally ordered by name."""
        from models import ProductCategory

        query = ProductCategory.query.filter_by(is_active=True, tenant_id=tenant_id)
        if ordered:
            return query.order_by(ProductCategory.name).all()
        return query.all()

    @staticmethod
    def find_category_by_name(tenant_id, name):
        """Case-insensitive exact-name category lookup within a tenant."""
        from models import ProductCategory

        return ProductCategory.query.filter_by(tenant_id=tenant_id).filter(ProductCategory.name.ilike(name)).first()

    @staticmethod
    def get_default_warehouse(tenant_id):
        """Main active warehouse for a tenant; falls back to any tenant warehouse."""
        from models import Warehouse

        warehouse = Warehouse.query.filter_by(is_active=True, is_main=True, tenant_id=tenant_id).first()
        if not warehouse:
            warehouse = Warehouse.query.filter_by(tenant_id=tenant_id).first()
        return warehouse

    @staticmethod
    def find_duplicate_product(sku, barcode, tenant_id):
        """Find an existing product sharing the SKU or barcode, optionally tenant-scoped."""
        from models import Product

        dup_q = Product.query.filter((Product.sku == sku) | (Product.barcode == barcode))
        if tenant_id is not None:
            dup_q = dup_q.filter(Product.tenant_id == tenant_id)
        return dup_q.first()

    @staticmethod
    def transaction_counts(product_id, tenant_id):
        """Count sale/purchase lines tied to a product (for delete guards)."""
        from models import PurchaseLine, SaleLine

        sales_query = SaleLine.query.filter_by(product_id=product_id)
        purchases_query = PurchaseLine.query.filter_by(product_id=product_id)
        if tenant_id is not None:
            sales_query = sales_query.filter(SaleLine.tenant_id == tenant_id)
            purchases_query = purchases_query.filter(PurchaseLine.tenant_id == tenant_id)
        return sales_query.count(), purchases_query.count()

    @staticmethod
    def get_price_tier(product_id, tier_code):
        """Fetch a product's price tier by tier code; returns None when absent."""
        from models import ProductPriceTier

        return ProductPriceTier.query.filter_by(
            product_id=product_id,
            tier_code=tier_code,
        ).first()

    @staticmethod
    def find_customer_in_tenant(customer_id, tenant_id):
        """Fetch a customer by id within a tenant; returns None when absent."""
        from models import Customer

        return Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).first()

    @staticmethod
    def annotate_branch_and_warehouse_info(products, warehouse_ids):
        """
        For all-branches views, annotate each product with visible warehouse names
        and branch names based on accessible stock movements.
        """
        if not products:
            return products

        from models import Branch, StockMovement, Warehouse

        for product in products:
            product.visible_warehouse_names = []
            product.visible_branch_names = []

        if not warehouse_ids:
            return products

        product_ids = [p.id for p in products]
        rows = (
            db.session.query(
                StockMovement.product_id,
                Warehouse.name,
                Warehouse.name_ar,
                Branch.name,
                Branch.code,
            )
            .join(Warehouse, Warehouse.id == StockMovement.warehouse_id)
            .outerjoin(Branch, Branch.id == Warehouse.branch_id)
            .filter(StockMovement.product_id.in_(product_ids))
            .filter(StockMovement.warehouse_id.in_(warehouse_ids))
            .all()
        )

        by_product = {}
        for product_id, wh_name, wh_name_ar, branch_name, branch_code in rows:
            bucket = by_product.setdefault(product_id, {"warehouses": set(), "branches": set()})
            if wh_name_ar or wh_name:
                bucket["warehouses"].add((wh_name_ar or wh_name).strip())
            if branch_name:
                branch_label = f"{branch_name} ({branch_code})" if branch_code else branch_name
                bucket["branches"].add(branch_label.strip())

        for product in products:
            info = by_product.get(product.id, {"warehouses": set(), "branches": set()})
            product.visible_warehouse_names = sorted(info["warehouses"])
            product.visible_branch_names = sorted(info["branches"])

        return products

    @staticmethod
    def tenant_business_type(tenant_id):
        """Normalized business type for a tenant; None when unset."""
        from models import Tenant

        tenant = db.session.get(Tenant, int(tenant_id))
        if tenant and tenant.business_type:
            return (tenant.business_type or "general").strip().lower()
        return None

    @staticmethod
    def scoped_customers_query(customer_type=None, branch_scope_id=None):
        """Tenant-scoped active-customer query, optionally narrowed to customers
        with sales/payments/receipts inside the branch scope."""
        from sqlalchemy import select

        from models import Customer, Payment, Sale
        from models.receipt import Receipt
        from utils.tenanting import tenant_query

        query = tenant_query(Customer).filter(Customer.is_active)
        if customer_type:
            query = query.filter(Customer.customer_type == customer_type)

        if branch_scope_id is None:
            return query

        sale_ids = select(Sale.customer_id).where(
            Sale.customer_id.isnot(None),
            Sale.branch_id == branch_scope_id,
        )
        payment_ids = select(Payment.customer_id).where(
            Payment.customer_id.isnot(None),
            Payment.branch_id == branch_scope_id,
        )
        receipt_ids = select(Receipt.customer_id).where(
            Receipt.customer_id.isnot(None),
            Receipt.branch_id == branch_scope_id,
        )
        return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))

    @staticmethod
    def scoped_customers(customer_type, branch_scope_id=None):
        """Scoped active customers of *customer_type*, ordered by name."""
        from models import Customer

        return (
            ProductService.scoped_customers_query(customer_type, branch_scope_id=branch_scope_id)
            .order_by(Customer.name)
            .all()
        )

    @staticmethod
    def find_scoped_customer(customer_id, customer_type, branch_scope_id=None):
        """Scoped active-customer lookup by id; None when absent or out of scope."""
        from models import Customer

        return (
            ProductService.scoped_customers_query(customer_type, branch_scope_id=branch_scope_id)
            .filter(Customer.id == customer_id)
            .first()
        )
