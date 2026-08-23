"""Read-only lookups extracted from routes/ai_routes/actions.py.

Every method reproduces, verbatim, the filters/ordering/limits/scoping of the
inline wizard query it replaced. Model imports stay local to each method and
mirror the import path of the original call site (``models.customer.Customer``
for interactive wizard steps, the ``models`` package for the quick
colon-command lookups) so patch seams keep resolving identically.
"""


class AiActionsQueryService:
    # ── customers ────────────────────────────────────────────────────────────

    @staticmethod
    def active_customers(tid, limit=None):
        """Active customers of the tenant, optionally capped."""
        from models.customer import Customer

        query = Customer.query.filter_by(tenant_id=tid, is_active=True)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    @staticmethod
    def find_customer_by_name(tid, name):
        """Active customer by exact name (wizard steps)."""
        from models.customer import Customer

        return Customer.query.filter_by(tenant_id=tid, name=name, is_active=True).first()

    @staticmethod
    def customer_by_id(customer_id, tid):
        """Customer by id within the tenant, active or not (post-payment refresh)."""
        from models.customer import Customer

        return Customer.query.filter_by(id=customer_id, tenant_id=tid).first()

    # ── products / suppliers / warehouses ────────────────────────────────────

    @staticmethod
    def active_products(tid, limit=None):
        from models.product import Product

        query = Product.query.filter_by(tenant_id=tid, is_active=True)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    @staticmethod
    def find_product_by_name(tid, name):
        from models.product import Product

        return Product.query.filter_by(tenant_id=tid, name=name, is_active=True).first()

    @staticmethod
    def find_supplier_by_name(tid, name):
        from models.supplier import Supplier

        return Supplier.query.filter_by(name=name, is_active=True, tenant_id=tid).first()

    @staticmethod
    def active_suppliers(tid):
        from models.supplier import Supplier

        return Supplier.query.filter_by(is_active=True, tenant_id=tid).all()

    @staticmethod
    def active_warehouses(tid):
        from models import Warehouse

        return Warehouse.query.filter_by(is_active=True, tenant_id=tid).all()

    # ── ledgers / stock listing ──────────────────────────────────────────────

    @staticmethod
    def recent_gl_entries(tid, limit=20):
        from models.gl import GLJournalEntry

        return (
            GLJournalEntry.query.filter_by(is_active=True, tenant_id=tid)
            .order_by(GLJournalEntry.entry_date.desc())
            .limit(limit)
            .all()
        )

    # ── option-2 full lists (legacy unscoped behaviour preserved) ────────────

    @staticmethod
    def all_active_sales():
        from models.sale import Sale

        return Sale.query.filter_by(is_active=True).all()

    @staticmethod
    def all_active_expenses():
        from models.expense import Expense

        return Expense.query.filter_by(is_active=True).all()

    @staticmethod
    def all_active_purchases():
        from models.purchase import Purchase

        return Purchase.query.filter_by(is_active=True).all()

    @staticmethod
    def all_active_cheques():
        from models.cheque import Cheque

        return Cheque.query.filter_by(is_active=True).all()

    @staticmethod
    def active_users():
        from utils.tenanting import scoped_user_query

        return scoped_user_query(active_only=True).all()

    # ── quick colon-command lookups (``models`` package seam) ────────────────

    @staticmethod
    def resolve_customer_by_name(tid, name):
        from models import Customer

        return Customer.query.filter_by(tenant_id=tid, name=name, is_active=True).first()

    @staticmethod
    def resolve_product_by_name(tid, name):
        from models import Product

        return Product.query.filter_by(tenant_id=tid, name=name, is_active=True).first()

    @staticmethod
    def recent_customer_payments(customer_id, limit=5):
        from models import Payment

        return Payment.query.filter_by(customer_id=customer_id).order_by(Payment.payment_date.desc()).limit(limit).all()
