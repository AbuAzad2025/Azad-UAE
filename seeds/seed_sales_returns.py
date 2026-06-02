"""Seed product returns for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import ProductReturn, ProductReturnLine, Sale, SaleLine, Product, User, Branch, Customer, Tenant
from datetime import datetime, timezone
from decimal import Decimal

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        for tid, prefix, curr in [(alhazem_id, "RET-AHZ", "AED"), (nasrallah_id, "RET-NSR", "ILS")]:
            sales = Sale.query.filter_by(tenant_id=tid, status="confirmed").limit(8).all()
            user = User.query.filter_by(tenant_id=tid).first()
            branch = Branch.query.filter_by(tenant_id=tid).first()
            
            if not (sales and user and branch):
                print(f"Skip {prefix}: missing data")
                continue
            
            count = 0
            for i, sale in enumerate(sales):
                if ProductReturn.query.filter_by(tenant_id=tid, sale_id=sale.id).first():
                    continue
                
                # Get 1-2 lines from the sale to return
                sale_lines = SaleLine.query.filter_by(sale_id=sale.id).limit(random.randint(1, 2)).all()
                if not sale_lines:
                    continue
                
                total = Decimal("0")
                lines_data = []
                for sl in sale_lines:
                    qty = random.randint(1, min(2, int(sl.quantity)))
                    line_total = Decimal(str(qty)) * sl.unit_price
                    lines_data.append((sl.product_id, sl.id, qty, sl.unit_price, line_total))
                    total += line_total
                
                ret = ProductReturn(
                    tenant_id=tid,
                    return_number=f"{prefix}-{20260001+i}",
                    sale_id=sale.id,
                    customer_id=sale.customer_id,
                    branch_id=branch.id,
                    total_amount=total,
                    refund_amount=total,
                    currency=curr,
                    exchange_rate=Decimal("1"),
                    amount_aed=total,
                    return_reason=random.choice(["Defective", "Wrong item", "Customer request", "Damaged"]),
                    status="approved",
                    processed_by=user.id,
                    return_date=datetime(2026, random.randint(1,5), random.randint(1,28), random.randint(9,17), tzinfo=timezone.utc)
                )
                db.session.add(ret); db.session.flush()
                
                for pid, sl_id, qty, price, ltotal in lines_data:
                    line = ProductReturnLine(
                        tenant_id=tid,
                        return_id=ret.id,
                        sale_line_id=sl_id,
                        product_id=pid,
                        quantity=Decimal(str(qty)),
                        unit_price=price,
                        line_total=ltotal
                    )
                    db.session.add(line)
                count += 1
            db.session.commit()
            print(f"{prefix} returns added: {count}")
        print("✅ Sales returns seeded successfully")


if __name__ == "__main__":
    seed()
