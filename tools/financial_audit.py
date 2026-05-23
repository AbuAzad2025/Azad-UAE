import os
import sys
from decimal import Decimal


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _q(v: Decimal) -> str:
    return f"{v.quantize(Decimal('0.001')):,}"


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
        Customer,
        Expense,
        GLJournalEntry,
        PartnerCommissionEntry,
        Sale,
        SaleLine,
    )

    app = create_app()
    with app.app_context():
        sales = Sale.query.filter_by(status="confirmed", is_active=True).all()
        sale_ids = [s.id for s in sales]
        revenue = _d(sum((_d(s.amount_aed) for s in sales), Decimal("0")))

        lines = SaleLine.query.filter(SaleLine.sale_id.in_(sale_ids)).all() if sale_ids else []
        cogs = _d(sum((_d(l.cost_price) * _d(l.quantity) for l in lines), Decimal("0")))
        gross_profit = revenue - cogs

        expenses = Expense.query.filter_by(status="confirmed", is_active=True).all()
        total_expenses = _d(sum((_d(e.amount_aed) for e in expenses), Decimal("0")))

        partner_entries = PartnerCommissionEntry.query.all()
        total_partner_commission = _d(
            sum((_d(e.commission_amount_aed) for e in partner_entries), Decimal("0"))
        )

        mismatches = 0
        for e in partner_entries:
            expected = (_d(e.base_amount_aed) * (_d(e.percentage) / Decimal("100"))).quantize(Decimal("0.001"))
            actual = _d(e.commission_amount_aed).quantize(Decimal("0.001"))
            if abs(expected - actual) > Decimal("0.001"):
                mismatches += 1

        partner_totals = {}
        for e in partner_entries:
            partner_totals[e.partner_customer_id] = partner_totals.get(e.partner_customer_id, Decimal("0")) + _d(
                e.commission_amount_aed
            )

        partner_rows = []
        for partner_id, amount in sorted(partner_totals.items(), key=lambda x: x[1], reverse=True):
            partner = Customer.query.get(partner_id)
            partner_rows.append((partner.name if partner else str(partner_id), amount))

        entries = GLJournalEntry.query.filter_by(is_posted=True).all()
        unbalanced = [e for e in entries if not e.is_balanced()]

        net_profit_before_partner = gross_profit - total_expenses
        net_profit_after_partner = net_profit_before_partner - total_partner_commission

        print("FIN_AUDIT_OK")
        print(f"SALES_COUNT={len(sales)} SALES_LINES={len(lines)}")
        print(f"REVENUE_AED={_q(revenue)}")
        print(f"COGS_AED={_q(cogs)}")
        print(f"GROSS_PROFIT_AED={_q(gross_profit)}")
        print(f"EXPENSES_AED={_q(total_expenses)}")
        print(f"NET_BEFORE_PARTNER_AED={_q(net_profit_before_partner)}")
        print(f"PARTNER_COMMISSION_AED={_q(total_partner_commission)}")
        print(f"NET_AFTER_PARTNER_AED={_q(net_profit_after_partner)}")
        print(f"PARTNER_ENTRIES={len(partner_entries)} MISMATCH_ENTRIES={mismatches}")
        print(f"GL_ENTRIES={len(entries)} GL_UNBALANCED={len(unbalanced)}")
        print("TOP_PARTNERS:")
        for name, amount in partner_rows[:10]:
            print(f"- {name}: {_q(amount)}")


if __name__ == "__main__":
    main()
