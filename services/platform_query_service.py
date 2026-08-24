"""Platform-level DB lookups extracted from routes/auth.py, routes/api.py and
routes/ai_routes/assistant.py.

Model imports are performed locally inside each method so this module stays
import-safe during app bootstrap (no model → service import cycles).
"""

from extensions import db


class PlatformQueryService:
    # ── payment identity (auth) ──────────────────────────────────────────────

    @staticmethod
    def payment_id_known_locally(payment_id) -> bool:
        """True when payment_id matches a known Donation / PackagePurchase / Sale reference."""
        from models import Donation, PackagePurchase, Sale

        pid = str(payment_id).strip()
        if not pid:
            return False
        if Donation.query.filter((Donation.gateway_transaction_id == pid) | (Donation.transaction_hash == pid)).first():
            return True
        if PackagePurchase.query.filter_by(transaction_id=pid).first():
            return True
        return bool(Sale.query.filter_by(checkout_gateway_ref=pid).first())

    # ── login page context (auth) ────────────────────────────────────────────

    @staticmethod
    def first_active_tenant():
        from models.tenant import Tenant

        return Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()

    @staticmethod
    def active_login_branches() -> list:
        from models import Branch

        return Branch.query.filter_by(is_active=True).order_by(Branch.is_main.desc(), Branch.code, Branch.name).all()

    @staticmethod
    def active_support_packages() -> list:
        from models import Package

        return Package.query.filter_by(is_active=True).order_by(Package.sort_order.asc()).all()

    # ── credentials & login flow lookups (auth) ──────────────────────────────

    @staticmethod
    def find_user_by_username(username):
        from models import User

        return User.query.filter(User.username.ilike(username)).first()

    @staticmethod
    def get_branch_safe(raw_branch_id):
        """Branch by id; None when the id is malformed or the row is missing."""
        from models import Branch

        try:
            return db.session.get(Branch, int(raw_branch_id or 0))
        except Exception:
            return None

    @staticmethod
    def get_tenant(tenant_id):
        from models.tenant import Tenant

        return db.session.get(Tenant, tenant_id)

    # ── unified search (api) ─────────────────────────────────────────────────

    @staticmethod
    def scoped_customers_query(user):
        """Customer query scoped by active tenant and branch-visible activity."""
        from sqlalchemy import select

        from models import Customer, Payment, Sale
        from models.receipt import Receipt
        from utils.branching import branch_scope_id
        from utils.tenanting import get_active_tenant_id

        query = Customer.query
        tid = get_active_tenant_id(user)
        if tid is not None:
            query = query.filter(Customer.tenant_id == tid)
        scoped_branch_id = branch_scope_id()
        if scoped_branch_id is None:
            return query

        sale_ids = select(Sale.customer_id).where(Sale.customer_id.isnot(None), Sale.branch_id == scoped_branch_id)
        payment_ids = select(Payment.customer_id).where(
            Payment.customer_id.isnot(None), Payment.branch_id == scoped_branch_id
        )
        receipt_ids = select(Receipt.customer_id).where(
            Receipt.customer_id.isnot(None), Receipt.branch_id == scoped_branch_id
        )
        return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))

    @staticmethod
    def scoped_suppliers_query(user):
        """Supplier query scoped by active tenant and branch-visible activity."""
        from sqlalchemy import select

        from models import Payment, Purchase, Supplier
        from utils.branching import branch_scope_id
        from utils.tenanting import get_active_tenant_id

        query = Supplier.query
        tid = get_active_tenant_id(user)
        if tid is not None:
            query = query.filter(Supplier.tenant_id == tid)
        scoped_branch_id = branch_scope_id()
        if scoped_branch_id is None:
            return query

        purchase_ids = select(Purchase.supplier_id).where(
            Purchase.supplier_id.isnot(None), Purchase.branch_id == scoped_branch_id
        )
        payment_ids = select(Payment.supplier_id).where(
            Payment.supplier_id.isnot(None), Payment.branch_id == scoped_branch_id
        )
        return query.filter(Supplier.id.in_(purchase_ids.union(payment_ids)))

    @staticmethod
    def customer_balance_unscoped(customer_id, user) -> float:
        """Balance via the tenant-scoped customer when no branch scope applies."""
        from models import Customer

        customer = PlatformQueryService.scoped_customers_query(user).filter(Customer.id == customer_id).first()
        return float(customer.get_balance_aed()) if customer else 0.0

    @staticmethod
    def supplier_balance_unscoped(supplier_id, user) -> float:
        """Balance via the tenant-scoped supplier when no branch scope applies."""
        from models import Supplier

        supplier = PlatformQueryService.scoped_suppliers_query(user).filter(Supplier.id == supplier_id).first()
        return float(supplier.get_balance_aed()) if supplier else 0.0

    @staticmethod
    def products_base_query(user, purpose=""):
        """Base product query for the unified search endpoint."""
        from models import Product
        from services.stock_service import StockService
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        if purpose == "purchase":
            return Product.query.filter(Product.is_active, Product.tenant_id == tid)
        return StockService.get_visible_products_query(user)

    # ── username availability (api) ──────────────────────────────────────────

    @staticmethod
    def find_existing_username(username, user):
        from models import User
        from utils.tenanting import get_active_tenant_id

        existing = User.query.filter_by(username=username)
        tid = get_active_tenant_id(user)
        if tid is not None:
            existing = existing.filter(User.tenant_id == tid)
        return existing.first()

    # ── display exchange rates (api) ─────────────────────────────────────────

    @staticmethod
    def tenant_base_currency(tenant_id, default):
        from models import Tenant

        tenant = Tenant.query.get(tenant_id) if tenant_id else None
        return tenant.get_base_currency if tenant else default

    # ── product lookups (api) ────────────────────────────────────────────────

    @staticmethod
    def product_for_info(product_id, user):
        """Product by id visible to the user's active tenant, else None."""
        from models import Product
        from utils.tenanting import get_active_tenant_id

        product = db.session.get(Product, int(product_id))
        if not product:
            return None
        tid = get_active_tenant_id(user)
        if tid is not None and product.tenant_id != tid:
            return None
        return product

    @staticmethod
    def find_product_by_barcode(code, user):
        from models import Product
        from utils.tenanting import get_active_tenant_id

        query = Product.query.filter(Product.barcode == code)
        tid = get_active_tenant_id(user)
        if tid is not None:
            query = query.filter(Product.tenant_id == tid)
        return query.first()

    # ── Excel import (ai assistant) ──────────────────────────────────────────

    @staticmethod
    def main_import_warehouse(tid):
        """Main active warehouse of the tenant, falling back to any active one."""
        from models import Warehouse

        warehouse = Warehouse.query.filter_by(is_active=True, is_main=True, tenant_id=tid).first()
        if not warehouse:
            warehouse = Warehouse.query.filter_by(is_active=True, tenant_id=tid).first()
        return warehouse

    @staticmethod
    def warehouse_in_tenant(warehouse_id, tid):
        from models import Warehouse

        return Warehouse.query.filter_by(id=warehouse_id, tenant_id=tid).first()

    @staticmethod
    def first_active_warehouse(tid):
        from models import Warehouse

        return Warehouse.query.filter_by(tenant_id=tid, is_active=True).first()

    @staticmethod
    def product_by_part_number(part_number, tid):
        from models import Product

        return Product.query.filter_by(part_number=part_number, tenant_id=tid).first()

    # ── analytics endpoints (api_analytics) ──────────────────────────────────

    @staticmethod
    def _analytics_branch_scope(query, model, user):
        """Branch-level scoping when the user is branch-restricted."""
        from utils.branching import branch_scope_id_for

        scoped_branch_id = branch_scope_id_for(user)
        if scoped_branch_id is not None:
            branch_col = getattr(model, "branch_id", None)
            if branch_col is not None:
                query = query.filter(branch_col == scoped_branch_id)
        return query

    @staticmethod
    def analytics_overdue_customer_candidates(user):
        """Active customers (tenant + branch scoped) for overdue scanning."""
        from models import Customer
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        customers = Customer.query.filter_by(is_active=True)
        if tid:
            customers = customers.filter(Customer.tenant_id == tid)
        customers = PlatformQueryService._analytics_branch_scope(customers, Customer, user)
        return customers.all()

    @staticmethod
    def analytics_today_sales(user, day):
        """Confirmed sales dated ``day`` (tenant + branch scoped)."""
        from extensions import db
        from models import Sale
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        today_sales = Sale.query.filter(db.func.date(Sale.sale_date) == day, Sale.status == "confirmed")
        if tid:
            today_sales = today_sales.filter(Sale.tenant_id == tid)
        today_sales = PlatformQueryService._analytics_branch_scope(today_sales, Sale, user)
        return today_sales.all()

    @staticmethod
    def analytics_today_payments(user, day):
        """Payments dated ``day`` (tenant + branch scoped)."""
        from extensions import db
        from models import Payment
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        today_payments = Payment.query.filter(db.func.date(Payment.payment_date) == day)
        if tid:
            today_payments = today_payments.filter(Payment.tenant_id == tid)
        today_payments = PlatformQueryService._analytics_branch_scope(today_payments, Payment, user)
        return today_payments.all()

    @staticmethod
    def analytics_top_customers(user, limit):
        """Active customers ordered by lifetime purchases."""
        from models import Customer
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        customers = Customer.query.filter_by(is_active=True)
        if tid:
            customers = customers.filter(Customer.tenant_id == tid)
        customers = PlatformQueryService._analytics_branch_scope(customers, Customer, user)
        return customers.order_by(Customer.total_purchases.desc()).limit(limit).all()

    @staticmethod
    def analytics_low_stock_products(user):
        """Active products at or below their alert threshold."""
        from models import Product
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        products = Product.query.filter(Product.is_active, Product.current_stock <= Product.min_stock_alert)
        if tid:
            products = products.filter(Product.tenant_id == tid)
        products = PlatformQueryService._analytics_branch_scope(products, Product, user)
        return products.all()

    @staticmethod
    def analytics_revenue_trend_rows(user, since):
        """Daily confirmed revenue since ``since`` (tenant + branch scoped)."""
        from sqlalchemy import func

        from extensions import db
        from models import Sale
        from utils.tenanting import get_active_tenant_id

        tid = get_active_tenant_id(user)
        daily_revenue = db.session.query(
            func.date(Sale.sale_date).label("date"),
            func.sum(Sale.amount_aed).label("total"),
        ).filter(Sale.sale_date >= since, Sale.status == "confirmed")
        if tid:
            daily_revenue = daily_revenue.filter(Sale.tenant_id == tid)
        daily_revenue = PlatformQueryService._analytics_branch_scope(daily_revenue, Sale, user)
        return daily_revenue.group_by(func.date(Sale.sale_date)).all()
