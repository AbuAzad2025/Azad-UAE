from __future__ import annotations

from flask import current_app
from sqlalchemy import inspect, text

from extensions import db


def _ensure_column(table_name: str, column_name: str, ddl: str) -> bool:
    inspector = inspect(db.engine)
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing:
        return False
    with db.engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))
    return True


def _ensure_index(index_name: str, table_name: str, column_name: str) -> None:
    with db.engine.begin() as connection:
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})"))


def _first_non_null(*values):
    for value in values:
        if value is not None:
            return value
    return None


def ensure_branch_isolation_schema_and_data():
    from models import Branch, Cheque, Expense, GLJournalEntry, Payment, Receipt, Purchase, Sale, User, Warehouse, Tenant
    from utils.branching import GLOBAL_ROLE_SLUGS

    schema_changes = 0
    for table_name in ("payments", "receipts", "cheques"):
        if _ensure_column(table_name, "branch_id", "branch_id INTEGER"):
            schema_changes += 1
        _ensure_index(f"ix_{table_name}_branch_id", table_name, "branch_id")

    main_branch = Branch.query.filter_by(is_active=True, is_main=True).order_by(Branch.id.asc()).first()
    if not main_branch:
        # Resolve first active tenant to set tenant_id (required by PostgreSQL NOT NULL)
        first_tenant = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
        tenant_id = first_tenant.id if first_tenant else None
        # If no tenant exists, there is nothing to backfill — skip branch creation
        if tenant_id is None:
            current_app.logger.info(
                "BranchRepair: No active tenant found — skipping Main Branch creation."
            )
            return {
                "schema_changes": schema_changes,
                "main_branch_id": None,
                "users": 0,
                "sales": 0,
                "purchases": 0,
                "expenses": 0,
                "payments": 0,
                "receipts": 0,
                "cheques": 0,
                "gl_entries": 0,
                "skipped_no_tenant": True,
            }
        main_branch = Branch(
            name="Main Branch", code="MAIN", is_main=True, is_active=True,
            tenant_id=tenant_id,
        )
        db.session.add(main_branch)
        db.session.flush()

    for warehouse in Warehouse.query.filter(Warehouse.branch_id.is_(None)).all():
        warehouse.branch_id = main_branch.id

    user_backfills = 0
    for user in User.query.all():
        role_slug = getattr(getattr(user, "role", None), "slug", None)
        requires_branch = not getattr(user, "is_owner", False) and role_slug not in GLOBAL_ROLE_SLUGS
        if requires_branch and user.branch_id is None:
            user.branch_id = main_branch.id
            user_backfills += 1

    sale_backfills = 0
    for sale in Sale.query.filter(Sale.branch_id.is_(None)).all():
        sale.branch_id = _first_non_null(
            getattr(getattr(sale, "warehouse", None), "branch_id", None),
            getattr(getattr(sale, "seller", None), "branch_id", None),
            main_branch.id,
        )
        sale_backfills += 1

    purchase_backfills = 0
    for purchase in Purchase.query.filter(Purchase.branch_id.is_(None)).all():
        purchase.branch_id = _first_non_null(
            getattr(getattr(purchase, "warehouse", None), "branch_id", None),
            getattr(getattr(purchase, "user", None), "branch_id", None),
            main_branch.id,
        )
        purchase_backfills += 1

    expense_backfills = 0
    for expense in Expense.query.filter(Expense.branch_id.is_(None)).all():
        expense.branch_id = _first_non_null(
            getattr(getattr(expense, "user", None), "branch_id", None),
            main_branch.id,
        )
        expense_backfills += 1

    payment_backfills = 0
    for payment in Payment.query.filter(Payment.branch_id.is_(None)).all():
        payment.branch_id = _first_non_null(
            getattr(getattr(payment, "sale", None), "branch_id", None),
            getattr(getattr(payment, "user", None), "branch_id", None),
            main_branch.id,
        )
        payment_backfills += 1

    receipt_backfills = 0
    for receipt in Receipt.query.filter(Receipt.branch_id.is_(None)).all():
        source_sale = db.session.get(Sale, receipt.source_id) if receipt.source_type == "sale" and receipt.source_id else None
        receipt.branch_id = _first_non_null(
            getattr(source_sale, "branch_id", None),
            getattr(getattr(receipt, "user", None), "branch_id", None),
            main_branch.id,
        )
        receipt_backfills += 1

    cheque_backfills = 0
    for cheque in Cheque.query.filter(Cheque.branch_id.is_(None)).all():
        cheque.branch_id = _first_non_null(
            getattr(getattr(cheque, "payment_record", None), "branch_id", None),
            getattr(getattr(cheque, "receipt_record", None), "branch_id", None),
            getattr(getattr(cheque, "expense", None), "branch_id", None),
            main_branch.id,
        )
        cheque_backfills += 1

    gl_backfills = 0
    for entry in GLJournalEntry.query.filter(GLJournalEntry.branch_id.is_(None)).all():
        linked_branch_id = None
        if entry.reference_type == "Payment":
            linked = db.session.get(Payment, entry.reference_id)
            linked_branch_id = getattr(linked, "branch_id", None)
        elif entry.reference_type == "Receipt":
            linked = db.session.get(Receipt, entry.reference_id)
            linked_branch_id = getattr(linked, "branch_id", None)
        elif entry.reference_type == "Expense":
            linked = db.session.get(Expense, entry.reference_id)
            linked_branch_id = getattr(linked, "branch_id", None)
        elif entry.reference_type in {"sale", "sale_cogs"}:
            linked = db.session.get(Sale, entry.reference_id)
            linked_branch_id = getattr(linked, "branch_id", None)
        elif entry.reference_type == "purchase":
            linked = db.session.get(Purchase, entry.reference_id)
            linked_branch_id = getattr(linked, "branch_id", None)
        elif entry.reference_type and entry.reference_type.startswith("cheque_"):
            linked = db.session.get(Cheque, entry.reference_id)
            linked_branch_id = getattr(linked, "branch_id", None)

        entry.branch_id = _first_non_null(
            linked_branch_id,
            getattr(getattr(entry, "user", None), "branch_id", None),
            main_branch.id,
        )
        gl_backfills += 1

    db.session.commit()

    current_app.logger.info(
        "BranchRepair: schema_changes=%s users=%s sales=%s purchases=%s expenses=%s payments=%s receipts=%s cheques=%s gl=%s main_branch=%s",
        schema_changes,
        user_backfills,
        sale_backfills,
        purchase_backfills,
        expense_backfills,
        payment_backfills,
        receipt_backfills,
        cheque_backfills,
        gl_backfills,
        main_branch.id,
    )

    return {
        "schema_changes": schema_changes,
        "main_branch_id": main_branch.id,
        "users": user_backfills,
        "sales": sale_backfills,
        "purchases": purchase_backfills,
        "expenses": expense_backfills,
        "payments": payment_backfills,
        "receipts": receipt_backfills,
        "cheques": cheque_backfills,
        "gl_entries": gl_backfills,
    }
