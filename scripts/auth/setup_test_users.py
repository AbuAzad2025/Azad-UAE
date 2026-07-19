"""Seed test user accounts for multi-role Playwright / Schemathesis auth.

Usage:
    python scripts/auth/setup_test_users.py

Creates one user per role (super_admin, tenant_owner, store_manager, cashier)
in an isolated test tenant. Exports storage-state JSON files to scripts/auth/
for Playwright context injection.
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

STORAGE_DIR = os.path.join(os.path.dirname(__file__))
BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:5000")
ADMIN_EMAIL = "test-super@azad.test"
ADMIN_PASSWORD = "TestSuper@123456"


def _setup():
    # Skip startup maintenance that queries raw tables before schema exists
    os.environ["SKIP_SYSTEM_INTEGRITY"] = "1"

    from app.factory import create_app
    from config import TestConfig
    from extensions import db

    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
    return app, db


def _seed(db):
    from models import Tenant, Branch, Warehouse, Role, User

    uid = uuid.uuid4().hex[:8]

    tenant = Tenant(
        name=f"AuthTest {uid}",
        slug=f"authtest-{uid}",
        default_currency="AED",
        base_currency="AED",
        enable_tax=True,
        default_tax_rate=Decimal("5.00"),
        enable_pos=True,
        is_active=True,
        is_suspended=False,
        subscription_plan="pro",
        subscription_plan_duration="monthly",
        subscription_end=datetime.now(timezone.utc) + timedelta(days=30),
        max_users=50,
        max_branches=5,
    )
    db.session.add(tenant)
    db.session.flush()

    branch = Branch(
        tenant_id=tenant.id,
        name=f"Main {uid}",
        name_ar=f"الرئيسي {uid}",
        is_active=True,
    )
    db.session.add(branch)
    db.session.flush()

    warehouse = Warehouse(
        tenant_id=tenant.id,
        name=f"Main WH {uid}",
        is_active=True,
    )
    db.session.add(warehouse)
    db.session.flush()

    role_map = {}
    for slug, label in [
        ("super_admin", "Super Admin"),
        ("tenant_owner", "Tenant Owner"),
        ("store_manager", "Store Manager"),
        ("cashier", "Cashier"),
    ]:
        role = Role.query.filter_by(slug=slug).first()
        if not role:
            role = Role(
                name=label,
                name_ar=label,
                slug=slug,
                description=f"Automated test role: {slug}",
                is_system=True,
            )
            db.session.add(role)
            db.session.flush()
        role_map[slug] = role

    users = []
    for slug, email_slug in [
        ("super_admin", "super"),
        ("tenant_owner", "owner"),
        ("store_manager", "manager"),
        ("cashier", "cashier"),
    ]:
        email = f"test-{email_slug}-{uid}@azad.test"
        password = f"Test{slug.title().replace('_', '')}@123!"
        user = User(
            tenant_id=tenant.id,
            email=email,
            username=f"{email_slug}-{uid}",
            name=slug.replace("_", " ").title(),
            role_id=role_map[slug].id,
            branch_id=branch.id,
            is_active=True,
            is_verified=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        users.append(
            {"slug": slug, "email": email, "password": password, "user_id": user.id}
        )

    db.session.commit()
    return tenant, branch, warehouse, users


def _export_state(app, users, tenant):
    """Export storage-state JSON for each user role."""
    from flask import session as flask_session
    from flask_login import login_user

    state_dir = os.path.join(STORAGE_DIR)
    os.makedirs(state_dir, exist_ok=True)

    with app.app_context():
        for u in users:
            from models import User as UserModel

            user = UserModel.query.get(u["user_id"])
            with app.test_request_context():
                login_user(user)
                flask_session["tenant_id"] = tenant.id
                flask_session["role"] = u["slug"]
                flask_session["language"] = "ar"
                state = {
                    "cookies": {
                        "session": flask_session.sid or "",
                    },
                    "session": dict(flask_session),
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "tenant_id": tenant.id,
                        "role_slug": u["slug"],
                    },
                    "meta": {
                        "base_url": BASE_URL,
                        "tenant_slug": tenant.slug,
                    },
                }
                path = os.path.join(state_dir, f"{u['slug']}_state.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2, default=str)
                print(f"  [OK] Exported {path}")


def main():
    print("=== Auth Test Users Setup ===\n")
    app, db = _setup()
    with app.app_context():
        tenant, branch, warehouse, users = _seed(db)
        print(f"  Tenant: {tenant.slug} (id={tenant.id})")
        for u in users:
            print(f"  User: {u['slug']:20s} email={u['email']}")
        _export_state(app, users, tenant)
    print("\nDone. Run: cp scripts/auth/*_state.json tests/e2e/tours/")


if __name__ == "__main__":
    main()
