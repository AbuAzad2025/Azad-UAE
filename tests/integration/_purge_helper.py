"""Shared cleanup for the integration suites that commit real documents.

Why this exists
---------------
Several of these suites build real documents through the real services, and
the services commit: a sale, its payment and its journal entries are in the
database for good. The test's own savepoint does not roll that back, and the
integration CI job runs the whole directory in one process against one
database. A suite that leaves 300 sales behind therefore changes what the
*next* suite sees.

The damage is not only rows. PostgreSQL keeps the statistics it gathered, so
a planner that still believes the table is large picks a different index for
the same query - and a test in a later suite that asserts which index a query
uses fails, with a failure that has nothing to do with the suite that caused
it.

So the cleanup has two parts: delete the rows, and re-collect the statistics.
Both are here so that every suite that commits real documents uses the same
one.
"""

from __future__ import annotations

#: Tables whose statistics are refreshed after a purge. A planner that still
#: believes the table is large picks a different index for the same query.
_STATISTICS_TABLES = (
    "sale_lines",
    "sales",
    "stock_movements",
    "payments",
    "purchases",
    "purchase_returns",
    "receipts",
    "gl_journal_entries",
    "gl_journal_lines",
    "pos_sessions",
    "pos_shifts",
    "products",
    "product_warehouse_stock",
    "product_warehouse_costs",
    "customers",
    "suppliers",
)


def refresh_statistics(session) -> None:
    """Re-collect the planner's statistics for the tables the workload touched."""
    from sqlalchemy import text

    for table in _STATISTICS_TABLES:
        try:
            session.execute(text(f'ANALYZE "{table}"'))
        except Exception:
            session.rollback()
    session.commit()


def purge_tenant(session, tenant_id: int, role_id: int | None = None) -> list[str]:
    """Delete everything a workload committed for one tenant.

    Returns the labels of the deletes that failed, so the caller can raise
    rather than let a half-purged tenant poison the next suite.
    """
    from sqlalchemy import delete

    from models import (
        AuditLog,
        Branch,
        Customer,
        GLAccount,
        LoginHistory,
        Payment,
        Product,
        ProductCategory,
        ProductCostHistory,
        Receipt,
        Role,
        Sale,
        SaleLine,
        StockMovement,
        Supplier,
        Tenant,
        User,
        Warehouse,
    )
    from models.gl import GLJournalEntry, GLJournalLine
    from models.pos_session import PosSession
    from models.pos_shift import PosShift
    from models.product_warehouse_cost import ProductWarehouseCost
    from models.purchase import Purchase
    from models.purchase_return import PurchaseReturn
    from models.user import role_permissions
    from models.warehouse import ProductWarehouseStock

    # A transaction left aborted by an earlier statement would make every
    # delete below fail with InFailedSqlTransaction and leave the rows behind.
    session.rollback()

    failures: list[str] = []

    def _delete(label, fn) -> None:
        """Run one delete inside a savepoint.

        A RESTRICT foreign key that was not anticipated must not abort the
        whole purge, so each delete gets its own savepoint and its own
        failure label.
        """
        nested = session.begin_nested()
        try:
            fn()
            nested.commit()
        except Exception:
            nested.rollback()
            failures.append(label)

    def _delete_where(model, *criteria) -> None:
        _delete(
            model.__tablename__,
            lambda: session.query(model).filter(*criteria).delete(synchronize_session=False),
        )

    user_ids = [row[0] for row in session.query(User.id).filter(User.tenant_id == tenant_id).all()]
    sale_ids = [row[0] for row in session.query(Sale.id).filter(Sale.tenant_id == tenant_id).all()]
    entry_ids = [row[0] for row in session.query(GLJournalEntry.id).filter(GLJournalEntry.tenant_id == tenant_id).all()]

    if sale_ids:
        _delete_where(SaleLine, SaleLine.sale_id.in_(sale_ids))
    if entry_ids:
        _delete_where(GLJournalLine, GLJournalLine.entry_id.in_(entry_ids))
    _delete_where(GLJournalEntry, GLJournalEntry.tenant_id == tenant_id)
    _delete_where(Payment, Payment.tenant_id == tenant_id)
    _delete_where(Receipt, Receipt.tenant_id == tenant_id)
    _delete_where(Sale, Sale.tenant_id == tenant_id)
    _delete_where(PurchaseReturn, PurchaseReturn.tenant_id == tenant_id)
    _delete_where(Purchase, Purchase.tenant_id == tenant_id)
    _delete_where(StockMovement, StockMovement.tenant_id == tenant_id)
    _delete_where(ProductCostHistory, ProductCostHistory.tenant_id == tenant_id)
    _delete_where(ProductWarehouseCost, ProductWarehouseCost.tenant_id == tenant_id)
    _delete_where(ProductWarehouseStock, ProductWarehouseStock.tenant_id == tenant_id)
    _delete_where(PosShift, PosShift.tenant_id == tenant_id)
    _delete_where(PosSession, PosSession.tenant_id == tenant_id)
    _delete_where(GLAccount, GLAccount.tenant_id == tenant_id)
    _delete_where(Product, Product.tenant_id == tenant_id)
    _delete_where(ProductCategory, ProductCategory.tenant_id == tenant_id)
    _delete_where(Customer, Customer.tenant_id == tenant_id)
    _delete_where(Supplier, Supplier.tenant_id == tenant_id)
    _delete_where(Warehouse, Warehouse.tenant_id == tenant_id)
    # The audit trail and the login history reference the cashier, so they
    # have to go before the user does.
    if user_ids:
        _delete_where(AuditLog, AuditLog.user_id.in_(user_ids))
        _delete_where(LoginHistory, LoginHistory.user_id.in_(user_ids))
    _delete_where(AuditLog, AuditLog.tenant_id == tenant_id)
    # Users before branches: users.branch_id is a RESTRICT foreign key, so
    # deleting the branch first aborts the whole purge.
    _delete_where(User, User.tenant_id == tenant_id)
    _delete_where(Branch, Branch.tenant_id == tenant_id)
    _delete_where(Tenant, Tenant.id == tenant_id)
    if role_id is not None:
        # role_permissions is a secondary table: it references the role, so
        # the links have to be cut before the role can go.
        _delete(
            "role_permissions",
            lambda: session.execute(delete(role_permissions).where(role_permissions.c.role_id == role_id)),
        )
        _delete_where(Role, Role.id == role_id)
    session.commit()
    # The rows are gone, but the statistics still describe them, and a planner
    # that believes the table is large picks a different index for the same
    # query - which is how a workload test ends up failing an unrelated index
    # assertion in a later suite.
    refresh_statistics(session)
    return failures
