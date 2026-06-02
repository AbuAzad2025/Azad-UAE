"""Seed cost centers for Alhazem and Nasrallah tenants."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import CostCenter, Tenant

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        # Cost centers data per tenant
        cost_centers = [
            # Alhazem cost centers
            (alhazem_id, "AHZ-RETAIL", "المتجر الرئيسي", "Main Store", "retail"),
            (alhazem_id, "AHZ-SERVICE", "مركز الخدمة", "Service Center", "service"),
            (alhazem_id, "AHZ-WAREHOUSE", "المخزن", "Warehouse", "warehouse"),
            (alhazem_id, "AHZ-ADMIN", "الإدارة", "Administration", "admin"),
            (alhazem_id, "AHZ-SALES", "قسم المبيعات", "Sales Department", "sales"),
            (alhazem_id, "AHZ-MARKETING", "التسويق", "Marketing", "marketing"),
            # Nasrallah cost centers
            (nasrallah_id, "NSR-RETAIL", "المتجر الرئيسي", "Main Store", "retail"),
            (nasrallah_id, "NSR-SERVICE", "مركز الخدمة", "Service Center", "service"),
            (nasrallah_id, "NSR-WAREHOUSE", "المخزن", "Warehouse", "warehouse"),
            (nasrallah_id, "NSR-ADMIN", "الإدارة", "Administration", "admin"),
            (nasrallah_id, "NSR-SALES", "قسم المبيعات", "Sales Department", "sales"),
            (nasrallah_id, "NSR-MARKETING", "التسويق", "Marketing", "marketing"),
        ]
        
        count = 0
        for tid, code, name_ar, name_en, dept in cost_centers:
            if CostCenter.query.filter_by(tenant_id=tid, code=code).first():
                continue
            cc = CostCenter(
                tenant_id=tid,
                code=code,
                name_ar=name_ar,
                name_en=name_en,
                center_type=dept,
                is_active=True
            )
            db.session.add(cc); count += 1
        db.session.commit()
        print(f"Cost centers added: {count}")
        print("✅ Cost centers seeded successfully")


if __name__ == "__main__":
    seed()
