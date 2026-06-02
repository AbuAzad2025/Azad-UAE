"""Seed fixed assets for Alhazem and Nasrallah tenants."""
import os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import FixedAsset, Tenant, GLAccount
from datetime import date
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
        
        # Fixed assets data
        assets = [
            ("Delivery Truck", "شحنة التوصيل", "vehicle", Decimal("50000"), 5),
            ("Office Equipment", "معدات المكتب", "equipment", Decimal("15000"), 3),
            ("Computers", "أجهزة الكمبيوتر", "equipment", Decimal("20000"), 3),
            ("Furniture", "الأثاث", "furniture", Decimal("10000"), 5),
            ("POS System", "نظام نقاط البيع", "equipment", Decimal("8000"), 3),
            ("Storage Racks", "رفوف التخزين", "furniture", Decimal("12000"), 5),
            ("Generator", "مولد كهربائي", "equipment", Decimal("25000"), 5),
            ("Air Conditioning", "تكييف", "equipment", Decimal("18000"), 5),
        ]
        
        for tid, prefix in [(alhazem_id, "AHZ"), (nasrallah_id, "NSR")]:
            # Get asset account
            asset_account = GLAccount.query.filter_by(tenant_id=tid, type="asset").first()
            if not asset_account:
                print(f"Skip {prefix}: no asset account found")
                continue
            
            count = 0
            for name_en, name_ar, asset_type, cost, useful_life in assets:
                if FixedAsset.query.filter_by(tenant_id=tid, asset_number=f"{prefix}-FA-{count+1:03d}").first():
                    continue
                asset = FixedAsset(
                    tenant_id=tid,
                    asset_number=f"{prefix}-FA-{count+1:03d}",
                    name_ar=name_ar,
                    name_en=name_en,
                    category=asset_type,
                    purchase_date=date(2025, random.randint(1, 12), random.randint(1, 28)),
                    purchase_price=cost,
                    salvage_value=cost * Decimal("0.1"),
                    useful_life_years=useful_life,
                    depreciation_method="straight_line",
                    status="active",
                    location="Main Branch",
                    asset_account_id=asset_account.id
                )
                db.session.add(asset); count += 1
            db.session.commit()
            print(f"{prefix} fixed assets added: {count}")
        print("✅ Fixed assets seeded successfully")


if __name__ == "__main__":
    seed()
