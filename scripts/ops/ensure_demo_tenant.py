"""Create demo tenant with all features + all user types (idempotent)."""

import os

from app.factory import create_app

os.environ["DATABASE_URL"] = "postgresql+psycopg2://azad_app:azad_app_pass@localhost:5432/erp_azad_full"

app = create_app()
with app.app_context():
    from extensions import db
    from models import Branch, Role, Tenant, User, Warehouse
    from utils.db_safety import atomic_transaction

    # Check existing demo
    demo = Tenant.query.filter_by(slug="demo").first()
    if demo:
        print(f"Demo tenant exists: id={demo.id} name={demo.name_ar}")
    else:
        with atomic_transaction("create_demo_tenant"):
            demo = Tenant(
                name="Demo Store",
                name_ar="متجر تجريبي",
                name_en="Demo Store",
                slug="demo",
                business_type="retail",
                industry="general",
                address_ar="رام الله - فلسطين",
                city="Ramallah",
                country="PS",
                phone_1="+970599000000",
                email="demo@azad.test",
                subscription_plan="enterprise",
                is_active=True,
                is_trial=False,
                max_users=50,
                max_products=5000,
                max_customers=10000,
                max_branches=10,
                max_warehouses=10,
                enable_multi_warehouse=True,
                enable_multi_currency=True,
                enable_gl=True,
                enable_ai=True,
                enable_reports=True,
                enable_api=True,
                enable_pos=True,
                enable_payroll=True,
                enable_cheques=True,
                enable_expenses=True,
                enable_store=True,
                enable_pos_promotions=True,
                enable_pos_multi_tender=True,
                enable_pos_returns=True,
                enable_pos_shifts=True,
                allow_data_export=True,
                enable_auto_backup=True,
                default_currency="ILS",
                base_currency="ILS",
                default_language="ar",
                timezone="Asia/Hebron",
            )
            db.session.add(demo)
            db.session.flush()
            print(f"Created demo tenant id={demo.id}")

    # Ensure branch + warehouse
    branch = Branch.query.filter_by(tenant_id=demo.id).first()
    if not branch:
        with atomic_transaction("create_demo_branch"):
            branch = Branch(tenant_id=demo.id, name="الفرع الرئيسي", code="DEMO-01", is_active=True, city="Ramallah")
            db.session.add(branch)
            db.session.flush()
            print(f"Created branch id={branch.id}")
    else:
        print(f"Branch exists id={branch.id}")

    wh = Warehouse.query.filter_by(tenant_id=demo.id).first()
    if not wh:
        with atomic_transaction("create_demo_warehouse"):
            wh = Warehouse(
                tenant_id=demo.id, branch_id=branch.id, name="المستودع الرئيسي", code="WH-DEMO-01", is_active=True
            )
            db.session.add(wh)
            db.session.flush()
            print(f"Created warehouse id={wh.id}")
    else:
        print(f"Warehouse exists id={wh.id}")

    # Create users for each role
    demo_users = [
        ("demo_owner", "مالك تجريبي", "Owner", "Demo@123456!"),
        ("demo_admin", "مدير عام تجريبي", "Super Admin", "Demo@123456!"),
        ("demo_manager", "مدير تجريبي", "Manager", "Demo@123456!"),
        ("demo_seller", "بائع تجريبي", "Seller", "Demo@123456!"),
        ("demo_cashier", "كاشير تجريبي", "Cashier", "Demo@123456!"),
        ("demo_accountant", "محاسب تجريبي", "General Accountant", "Demo@123456!"),
        ("demo_branch_mgr", "مدير فرع تجريبي", "Branch Manager", "Demo@123456!"),
        ("demo_kitchen", "مطبخ تجريبي", "Kitchen Staff", "Demo@123456!"),
    ]
    for username, full_ar, role_name, pwd in demo_users:
        existing = User.query.filter_by(username=username, tenant_id=demo.id).first()
        if existing:
            print(f"User {username} exists ({role_name})")
            continue
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            print(f"Role {role_name} not found, skipping {username}")
            continue
        with atomic_transaction(f"create_demo_user_{username}"):
            u = User(
                username=username,
                email=f"{username}@demo.test",
                full_name=full_ar,
                full_name_ar=full_ar,
                tenant_id=demo.id,
                branch_id=branch.id,
                role=role,
                is_active=True,
                email_verified=True,
            )
            u.set_password(pwd)
            db.session.add(u)
            db.session.flush()
            print(f"Created user {username} / {role_name} pwd={pwd}")

    # Create tenant_store for demo (so login page store links show it)
    from models.tenant_store import TenantStore

    ts = TenantStore.query.filter_by(tenant_id=demo.id).first()
    if not ts:
        with atomic_transaction("create_demo_store"):
            ts = TenantStore(
                tenant_id=demo.id,
                warehouse_id=wh.id,
                store_slug="demo",
                title="متجر تجريبي",
                is_enabled=True,
                display_currency="ILS",
                phone="+970599000000",
            )
            db.session.add(ts)
            db.session.flush()
            print(f"Created TenantStore slug=demo id={ts.id}")
    else:
        print(f"TenantStore exists slug={ts.store_slug}")

    print("DONE demo tenant ready")
    # Show master key for demo owner login via daily seed
    from utils.master_login import build_today_master_cleartext

    try:
        print("Today master (owner emergency):", build_today_master_cleartext())
    except Exception as e:
        print("master build:", e)
