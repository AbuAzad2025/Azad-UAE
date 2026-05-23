import os
import sys
from decimal import Decimal


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DEBUG", "1")
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

    from app import create_app
    from extensions import db
    from models import (
        Branch,
        Cheque,
        Customer,
        Expense,
        ExpenseCategory,
        GLAccount,
        GLJournalEntry,
        GLJournalLine,
        Payment,
        Purchase,
        PurchaseLine,
        Receipt,
        Sale,
        SaleLine,
        StockMovement,
        Supplier,
        Tenant,
        User,
        Warehouse,
    )
    from services.stock_service import StockService

    app = create_app()
    with app.app_context():
        default_tenant = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
        if not default_tenant:
            default_tenant = Tenant.get_current()
        default_tenant_id = int(default_tenant.id)

        def _tenant_from_branch(branch_id):
            if not branch_id:
                return None
            b = Branch.query.get(branch_id)
            return int(b.tenant_id) if b and b.tenant_id else None

        def _tenant_from_warehouse(warehouse_id):
            if not warehouse_id:
                return None
            wh = Warehouse.query.get(warehouse_id)
            return int(wh.tenant_id) if wh and wh.tenant_id else None

        def _tenant_from_user(user_id):
            if not user_id:
                return None
            u = User.query.get(user_id)
            return int(u.tenant_id) if u and u.tenant_id else None

        def _set_if_null(model, rows, resolve_tid):
            updated = 0
            for r in rows:
                if getattr(r, "tenant_id", None) is not None:
                    continue
                tid = resolve_tid(r) or default_tenant_id
                r.tenant_id = tid
                updated += 1
            return updated

        updated_counts = {}

        updated_counts["branches"] = _set_if_null(Branch, Branch.query.filter(Branch.tenant_id.is_(None)).all(), lambda r: default_tenant_id)
        updated_counts["warehouses"] = _set_if_null(
            Warehouse,
            Warehouse.query.filter(Warehouse.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)),
        )
        updated_counts["users"] = _set_if_null(
            User,
            User.query.filter(User.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)),
        )
        updated_counts["customers"] = _set_if_null(Customer, Customer.query.filter(Customer.tenant_id.is_(None)).all(), lambda r: default_tenant_id)
        updated_counts["suppliers"] = _set_if_null(Supplier, Supplier.query.filter(Supplier.tenant_id.is_(None)).all(), lambda r: default_tenant_id)
        updated_counts["expense_categories"] = _set_if_null(
            ExpenseCategory, ExpenseCategory.query.filter(ExpenseCategory.tenant_id.is_(None)).all(), lambda r: default_tenant_id
        )
        updated_counts["expenses"] = _set_if_null(
            Expense,
            Expense.query.filter(Expense.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "user_id", None)),
        )
        updated_counts["cheques"] = _set_if_null(
            Cheque,
            Cheque.query.filter(Cheque.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "user_id", None)),
        )

        updated_counts["sales"] = _set_if_null(
            Sale,
            Sale.query.filter(Sale.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "seller_id", None)),
        )
        updated_counts["sale_lines"] = _set_if_null(
            SaleLine,
            SaleLine.query.filter(SaleLine.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(Sale.query.get(r.sale_id).branch_id if Sale.query.get(r.sale_id) else None),
        )

        updated_counts["purchases"] = _set_if_null(
            Purchase,
            Purchase.query.filter(Purchase.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "user_id", None)) or _tenant_from_warehouse(getattr(r, "warehouse_id", None)),
        )
        updated_counts["purchase_lines"] = _set_if_null(
            PurchaseLine,
            PurchaseLine.query.filter(PurchaseLine.tenant_id.is_(None)).all(),
            lambda r: int(Purchase.query.get(r.purchase_id).tenant_id) if Purchase.query.get(r.purchase_id) and Purchase.query.get(r.purchase_id).tenant_id else None,
        )

        updated_counts["payments"] = _set_if_null(
            Payment,
            Payment.query.filter(Payment.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "user_id", None)),
        )
        updated_counts["receipts"] = _set_if_null(
            Receipt,
            Receipt.query.filter(Receipt.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "user_id", None)),
        )

        updated_counts["stock_movements"] = _set_if_null(
            StockMovement,
            StockMovement.query.filter(StockMovement.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_warehouse(getattr(r, "warehouse_id", None)) or _tenant_from_user(getattr(r, "user_id", None)),
        )

        updated_counts["gl_accounts"] = _set_if_null(GLAccount, GLAccount.query.filter(GLAccount.tenant_id.is_(None)).all(), lambda r: default_tenant_id)
        updated_counts["gl_entries"] = _set_if_null(
            GLJournalEntry,
            GLJournalEntry.query.filter(GLJournalEntry.tenant_id.is_(None)).all(),
            lambda r: _tenant_from_branch(getattr(r, "branch_id", None)) or _tenant_from_user(getattr(r, "created_by", None)),
        )
        updated_counts["gl_lines"] = _set_if_null(
            GLJournalLine,
            GLJournalLine.query.filter(GLJournalLine.tenant_id.is_(None)).all(),
            lambda r: int(GLJournalEntry.query.get(r.entry_id).tenant_id)
            if GLJournalEntry.query.get(r.entry_id) and GLJournalEntry.query.get(r.entry_id).tenant_id
            else None,
        )

        db.session.commit()

        stock_sums = (
            db.session.query(StockMovement.warehouse_id, StockMovement.product_id, db.func.sum(StockMovement.quantity))
            .group_by(StockMovement.warehouse_id, StockMovement.product_id)
            .all()
        )
        neg = [(wh_id, product_id, _d(qty_sum)) for wh_id, product_id, qty_sum in stock_sums if _d(qty_sum) < Decimal("0")]

        fixed_stock = 0
        for wh_id, product_id, qty_sum in neg:
            try:
                StockService.adjust_stock(
                    product_id=product_id,
                    quantity=abs(qty_sum),
                    notes="Repair negative stock",
                    warehouse_id=wh_id,
                )
                fixed_stock += 1
                db.session.commit()
            except Exception:
                db.session.rollback()

        print("TENANT_REPAIR_OK")
        for k in sorted(updated_counts.keys()):
            print(f"UPDATED_{k.upper()}={updated_counts[k]}")
        print(f"NEG_STOCK_FIXED={fixed_stock} NEG_STOCK_FOUND={len(neg)}")


if __name__ == "__main__":
    main()

