"""Seed additional tenants for the system."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import Tenant, User, Role, Branch, Warehouse, GLPeriod, InvoiceSettings
from services.gl_tree_builder import GLTreeBuilder
from werkzeug.security import generate_password_hash
from decimal import Decimal

app = create_app()


def seed():
    with app.app_context():
        # Additional tenants data
        tenants_data = [
            {
                "name": "Dubai Electronics",
                "name_ar": "دبي إلكترونيات",
                "slug": "dubai_electronics",
                "business_type": "retail",
                "city": "Dubai",
                "country": "UAE",
                "currency": "AED",
                "phone": "+97141234567",
                "email": "info@dubaielectronics.ae"
            },
            {
                "name": "Abu Dhabi Construction",
                "name_ar": "أبوظبي للإنشاءات",
                "slug": "abudhabi_construction",
                "business_type": "construction",
                "city": "Abu Dhabi",
                "country": "UAE",
                "currency": "AED",
                "phone": "+971507654321",
                "email": "info@abudhabiconstruction.ae"
            },
            {
                "name": "Sharjah Trading",
                "name_ar": "الشارقة للتجارة",
                "slug": "sharjah_trading",
                "business_type": "trading",
                "city": "Sharjah",
                "country": "UAE",
                "currency": "AED",
                "phone": "+971509876543",
                "email": "info@sharjahtrading.ae"
            },
        ]
        
        count = 0
        for t_data in tenants_data:
            if Tenant.query.filter_by(slug=t_data["slug"]).first():
                continue
            
            tenant = Tenant(
                name=t_data["name"],
                name_ar=t_data["name_ar"],
                slug=t_data["slug"],
                business_type=t_data["business_type"],
                city=t_data["city"],
                country=t_data["country"],
                default_currency=t_data["currency"],
                phone_1=t_data["phone"],
                email=t_data["email"],
                is_active=True
            )
            db.session.add(tenant); db.session.flush()
            print(f"Created tenant: {tenant.name} (ID: {tenant.id})")
            
            # Create admin user
            admin_role = Role.query.filter_by(name="admin").first()
            user = User(
                tenant_id=tenant.id,
                username=f"{t_data['slug']}_admin",
                email=f"admin@{t_data['slug']}.ae",
                password_hash=generate_password_hash("password123"),
                full_name=f"{t_data['name']} Admin",
                role_id=admin_role.id if admin_role else None,
                is_active=True
            )
            db.session.add(user); db.session.flush()
            
            # Create branch
            branch = Branch(
                tenant_id=tenant.id,
                name="Main Branch",
                code="MAIN",
                address=t_data["city"],
                is_active=True,
                is_main=True
            )
            db.session.add(branch); db.session.flush()
            
            # Create warehouse
            warehouse = Warehouse(
                tenant_id=tenant.id,
                name="Main Warehouse",
                name_ar="المخزن الرئيسي",
                code="WH01",
                warehouse_type="main",
                branch_id=branch.id,
                is_active=True
            )
            db.session.add(warehouse); db.session.flush()
            
            # Create complete GL tree using GLTreeBuilder
            audit_report = GLTreeBuilder.build(tenant.id)
            print(f"  GL Tree built: {len(audit_report['created'])} accounts created, {len(audit_report['updated'])} updated")
            db.session.flush()
            
            # Create GL period
            period = GLPeriod(
                tenant_id=tenant.id,
                year=2026,
                month=1,
                is_closed=False
            )
            db.session.add(period)
            
            # Create invoice settings
            inv_settings = InvoiceSettings(
                tenant_id=tenant.id,
                company_name_ar=t_data["name_ar"],
                company_name_en=t_data["name"],
                address_ar=t_data["city"],
                phone_1=t_data["phone"],
                email=t_data["email"]
            )
            db.session.add(inv_settings)
            
            count += 1
        db.session.commit()
        print(f"Additional tenants added: {count}")
        print("✅ Additional tenants seeded successfully")


if __name__ == "__main__":
    seed()
