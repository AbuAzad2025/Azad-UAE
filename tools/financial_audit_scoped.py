import os
import sys
from collections import defaultdict
from decimal import Decimal


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _q(v: Decimal) -> str:
    return f"{_d(v).quantize(Decimal('0.001')):,}"


def _sum(values) -> Decimal:
    total = Decimal("0")
    for v in values:
        total += _d(v)
    return total


def _check_amount_aed(amount, exchange_rate, amount_aed) -> bool:
    ex = _d(exchange_rate or 0)
    if ex <= 0:
        return False
    expected = (_d(amount) * ex).quantize(Decimal("0.001"))
    actual = _d(amount_aed).quantize(Decimal("0.001"))
    return abs(expected - actual) <= Decimal("0.01")


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
        GLJournalEntry,
        PartnerCommissionEntry,
        Payment,
        Purchase,
        PurchaseLine,
        Receipt,
        Sale,
        SaleLine,
        StockMovement,
        Tenant,
        Warehouse,
    )

    app = create_app()
    with app.app_context():
        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).all()
        if not tenants:
            raise RuntimeError("No tenants found")

        gl_null_tenant = GLJournalEntry.query.filter(GLJournalEntry.tenant_id.is_(None)).count()
        stock_null_tenant = StockMovement.query.filter(StockMovement.tenant_id.is_(None)).count()
        cheque_null_tenant = Cheque.query.filter(Cheque.tenant_id.is_(None)).count()
        expense_null_tenant = Expense.query.filter(Expense.tenant_id.is_(None)).count()
        payment_null_tenant = Payment.query.filter(Payment.tenant_id.is_(None)).count()
        receipt_null_tenant = Receipt.query.filter(Receipt.tenant_id.is_(None)).count()

        cross_tenant_gl = 0
        for e in GLJournalEntry.query.filter(GLJournalEntry.branch_id.isnot(None)).all():
            b = Branch.query.get(e.branch_id)
            if not b:
                continue
            if e.tenant_id is not None and b.tenant_id is not None and int(e.tenant_id) != int(b.tenant_id):
                cross_tenant_gl += 1

        negative_stock_rows = []
        stock_sums = (
            db.session.query(StockMovement.warehouse_id, StockMovement.product_id, db.func.sum(StockMovement.quantity))
            .group_by(StockMovement.warehouse_id, StockMovement.product_id)
            .all()
        )
        for wh_id, product_id, qty_sum in stock_sums:
            if _d(qty_sum) < Decimal("0"):
                negative_stock_rows.append((wh_id, product_id, _d(qty_sum)))

        per_tenant = []
        for t in tenants:
            tid = int(t.id)
            branches = Branch.query.filter_by(tenant_id=tid, is_active=True).order_by(Branch.id.asc()).all()
            if not branches:
                branches = Branch.query.filter_by(is_active=True).order_by(Branch.id.asc()).all()

            tenant_sales = Sale.query.filter_by(tenant_id=tid, status="confirmed", is_active=True).all()
            sale_ids = [s.id for s in tenant_sales]
            tenant_lines = (
                SaleLine.query.filter(SaleLine.tenant_id == tid, SaleLine.sale_id.in_(sale_ids)).all() if sale_ids else []
            )
            revenue = _sum(s.amount_aed for s in tenant_sales)
            cogs = _sum((_d(l.cost_price) * _d(l.quantity) for l in tenant_lines))
            gross_profit = revenue - cogs

            tenant_purchases = Purchase.query.filter_by(tenant_id=tid, status="confirmed").all()
            purchase_ids = [p.id for p in tenant_purchases]
            purchase_lines = (
                PurchaseLine.query.filter(PurchaseLine.tenant_id == tid, PurchaseLine.purchase_id.in_(purchase_ids)).all()
                if purchase_ids
                else []
            )
            purchases_total = _sum(p.amount_aed for p in tenant_purchases)

            tenant_expenses = Expense.query.filter_by(tenant_id=tid, status="confirmed", is_active=True).all()
            expenses_total = _sum(e.amount_aed for e in tenant_expenses)

            tenant_comm = PartnerCommissionEntry.query.filter_by(tenant_id=tid).all()
            comm_total = _sum(e.commission_amount_aed for e in tenant_comm)

            tenant_entries = GLJournalEntry.query.filter_by(tenant_id=tid, is_posted=True).all()
            unbalanced = [e for e in tenant_entries if not e.is_balanced()]

            bad_fx = 0
            for s in tenant_sales:
                if not _check_amount_aed(s.total_amount, s.exchange_rate, s.amount_aed):
                    bad_fx += 1
            for p in tenant_purchases:
                if not _check_amount_aed(p.total_amount, p.exchange_rate, p.amount_aed):
                    bad_fx += 1
            for e in tenant_expenses:
                if not _check_amount_aed(e.amount, e.exchange_rate, e.amount_aed):
                    bad_fx += 1

            per_branch = []
            for b in branches:
                bid = int(b.id)
                b_sales = [s for s in tenant_sales if int(s.branch_id or 0) == bid]
                b_sale_ids = [s.id for s in b_sales]
                b_lines = [l for l in tenant_lines if l.sale_id in b_sale_ids]

                b_revenue = _sum(s.amount_aed for s in b_sales)
                b_cogs = _sum((_d(l.cost_price) * _d(l.quantity) for l in b_lines))
                b_exp = _sum(e.amount_aed for e in tenant_expenses if int(e.branch_id or 0) == bid)
                b_entries = [e for e in tenant_entries if int(e.branch_id or 0) == bid]
                b_unbalanced = [e for e in b_entries if not e.is_balanced()]

                per_branch.append(
                    {
                        "branch": b.code,
                        "sales": len(b_sales),
                        "revenue": b_revenue,
                        "cogs": b_cogs,
                        "gross": b_revenue - b_cogs,
                        "expenses": b_exp,
                        "gl_entries": len(b_entries),
                        "gl_unbalanced": len(b_unbalanced),
                    }
                )

            net_before_comm = gross_profit - expenses_total
            net_after_comm = net_before_comm - comm_total

            per_tenant.append(
                {
                    "tenant": t.slug,
                    "currency": (t.default_currency or "AED").upper(),
                    "branches": per_branch,
                    "sales": len(tenant_sales),
                    "revenue": revenue,
                    "cogs": cogs,
                    "gross": gross_profit,
                    "purchases": purchases_total,
                    "expenses": expenses_total,
                    "commission": comm_total,
                    "net_before_comm": net_before_comm,
                    "net_after_comm": net_after_comm,
                    "gl_entries": len(tenant_entries),
                    "gl_unbalanced": len(unbalanced),
                    "fx_mismatch": bad_fx,
                }
            )

        print("FIN_AUDIT_SCOPED_OK")
        print(f"TENANTS={len(tenants)}")
        print(f"GL_NULL_TENANT={gl_null_tenant} STOCK_NULL_TENANT={stock_null_tenant} CHEQUE_NULL_TENANT={cheque_null_tenant}")
        print(f"EXPENSE_NULL_TENANT={expense_null_tenant} PAYMENT_NULL_TENANT={payment_null_tenant} RECEIPT_NULL_TENANT={receipt_null_tenant}")
        print(f"GL_CROSS_TENANT_BRANCH_MISMATCH={cross_tenant_gl}")
        print(f"NEGATIVE_STOCK_ROWS={len(negative_stock_rows)}")
        for wh_id, product_id, qty_sum in negative_stock_rows[:10]:
            wh = Warehouse.query.get(wh_id)
            wh_code = wh.code if wh else str(wh_id)
            print(f"- NEG_STOCK wh={wh_code} product_id={product_id} qty={_q(qty_sum)}")

        for row in per_tenant:
            print(f"TENANT {row['tenant']} ({row['currency']}): SALES={row['sales']} GL={row['gl_entries']} UNBAL={row['gl_unbalanced']} FX_MISMATCH={row['fx_mismatch']}")
            print(f"- REVENUE_AED={_q(row['revenue'])} COGS_AED={_q(row['cogs'])} GROSS_AED={_q(row['gross'])}")
            print(f"- EXP_AED={_q(row['expenses'])} COMM_AED={_q(row['commission'])} NET_AED={_q(row['net_after_comm'])}")
            for b in row["branches"]:
                print(
                    f"  BRANCH {b['branch']}: SALES={b['sales']} REV={_q(b['revenue'])} COGS={_q(b['cogs'])} EXP={_q(b['expenses'])} GL={b['gl_entries']} UNBAL={b['gl_unbalanced']}"
                )


if __name__ == "__main__":
    main()

