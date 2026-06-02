"""Seed store coupons for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import StoreCoupon, Tenant
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
        
        # Alhazem Coupons
        data = [
            ("WELCOME10", "Welcome discount", Decimal("10"), None, Decimal("100"), 100),
            ("SUMMER20", "Summer sale", Decimal("20"), None, Decimal("200"), 50),
            ("BATTERY5", "Battery special", Decimal("5"), None, Decimal("50"), 200),
            ("VIP15", "VIP customer", Decimal("15"), None, Decimal("500"), 30),
            ("FLASH25", "Flash sale", Decimal("25"), None, Decimal("300"), 20),
        ]
        count = 0
        for code, desc, pct, amt, min_amt, max_uses in data:
            if StoreCoupon.query.filter_by(tenant_id=alhazem_id, code=code).first(): continue
            c = StoreCoupon(
                tenant_id=alhazem_id,
                code=code,
                description=desc,
                discount_percent=pct,
                discount_amount=amt,
                min_order_amount=min_amt,
                max_uses=max_uses,
                used_count=random.randint(0, max_uses // 2),
                is_active=True,
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 12, 31, tzinfo=timezone.utc)
            )
            db.session.add(c); count += 1
        db.session.commit()
        print(f"Alhazem coupons added: {count}")
        
        # Nasrallah Coupons
        data = [
            ("NEW10", "New customer", Decimal("10"), None, Decimal("50"), 100),
            ("ELECTRO15", "Electronics", Decimal("15"), None, Decimal("100"), 50),
            ("TOOLS20", "Tools discount", Decimal("20"), None, Decimal("150"), 40),
            ("PAINT5", "Paint special", Decimal("5"), None, Decimal("30"), 80),
            ("WEEKEND30", "Weekend sale", Decimal("30"), None, Decimal("200"), 15),
        ]
        count = 0
        for code, desc, pct, amt, min_amt, max_uses in data:
            if StoreCoupon.query.filter_by(tenant_id=nasrallah_id, code=code).first(): continue
            c = StoreCoupon(
                tenant_id=nasrallah_id,
                code=code,
                description=desc,
                discount_percent=pct,
                discount_amount=amt,
                min_order_amount=min_amt,
                max_uses=max_uses,
                used_count=random.randint(0, max_uses // 2),
                is_active=True,
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 12, 31, tzinfo=timezone.utc)
            )
            db.session.add(c); count += 1
        db.session.commit()
        print(f"Nasrallah coupons added: {count}")
        print("✅ Coupons seeded successfully")


if __name__ == "__main__":
    seed()
