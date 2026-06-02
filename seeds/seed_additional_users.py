"""Seed additional users for Alhazem and Nasrallah tenants."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "postgresql+psycopg2://postgres:123@localhost:5432/azad_uae"
os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

from app import create_app
from extensions import db
from models import User, Role, Branch, Tenant
from werkzeug.security import generate_password_hash

app = create_app()


def get_tenant_ids():
    t1 = Tenant.query.filter_by(slug="alhazem").first()
    t2 = Tenant.query.filter_by(slug="nasrallah").first()
    return (t1.id if t1 else 8, t2.id if t2 else 2)


def seed():
    with app.app_context():
        alhazem_id, nasrallah_id = get_tenant_ids()
        print(f"Tenant IDs: alhazem={alhazem_id}, nasrallah={nasrallah_id}")
        
        for tid, prefix in [(alhazem_id, "AHZ"), (nasrallah_id, "NSR")]:
            branch = Branch.query.filter_by(tenant_id=tid).first()
            if not branch:
                print(f"Skip {prefix}: no branch found")
                continue
            
            # Get roles
            admin_role = Role.query.filter_by(name="admin").first()
            sales_role = Role.query.filter_by(name="sales").first()
            warehouse_role = Role.query.filter_by(name="warehouse").first()
            
            # If roles don't exist, create default role
            if not admin_role:
                admin_role = Role(name="admin", slug="admin", description="Administrator")
                db.session.add(admin_role); db.session.flush()
            if not sales_role:
                sales_role = Role(name="sales", slug="sales", description="Sales User")
                db.session.add(sales_role); db.session.flush()
            if not warehouse_role:
                warehouse_role = Role(name="warehouse", slug="warehouse", description="Warehouse User")
                db.session.add(warehouse_role); db.session.flush()
            
            count = 0
            # Additional users
            users_data = [
                (f"{prefix}_manager", "Manager User", "manager", admin_role),
                (f"{prefix}_sales1", "Sales User 1", "sales", sales_role),
                (f"{prefix}_sales2", "Sales User 2", "sales", sales_role),
                (f"{prefix}_warehouse", "Warehouse User", "warehouse", warehouse_role),
                (f"{prefix}_accountant", "Accountant User", "accountant", admin_role),
            ]
            
            for username, full_name, dept, role in users_data:
                if User.query.filter_by(username=username).first():
                    continue
                u = User(
                    tenant_id=tid,
                    username=username,
                    email=f"{username}@example.com",
                    password_hash=generate_password_hash("password123"),
                    full_name=full_name,
                    role_id=role.id if role else None,
                    branch_id=branch.id,
                    is_active=True
                )
                db.session.add(u); count += 1
            db.session.commit()
            print(f"{prefix} additional users added: {count}")
        print("✅ Additional users seeded successfully")


if __name__ == "__main__":
    seed()
