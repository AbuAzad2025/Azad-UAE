"""Sovereign Migration for Demo Tenant Provisioning

Revision ID: 9999_provision_demo_sovereign
Revises: edf0e540a237
"""
from alembic import op
import sqlalchemy as sa

revision = "9999_provision_demo_sovereign"
down_revision = "edf0e540a237"
branch_labels = None
depends_on = None

from app import create_app
from extensions import db
from models.tenant import Tenant
from models.branch import Branch
from models.warehouse import Warehouse
from models.cash_box import CashBox
from models.user import User, Role
from services.gl_provisioning_service import GLProvisioningService
from services.document_sequence_service import DocumentSequenceService

SEQUENCE_CODES = [
    'sale', 'purchase', 'payment', 'receipt', 'gl_entry',
    'cheque', 'invoice', 'return', 'expense',
]


def upgrade():
    app = create_app()
    with app.app_context():
        # 1. Check if demo exists to ensure Idempotency
        if Tenant.query.filter_by(slug='demo').first():
            print("Demo tenant already exists, skipping.")
            return

        # 2. Provisioning Logic (Demo Tenant)
        demo_tenant = Tenant(
            name="Demo",
            name_ar="ديمو",
            slug="demo",
            business_type="general",
            is_active=True,
        )
        db.session.add(demo_tenant)
        db.session.flush()  # Ensure tenant ID is available

        # 3. Provision Core Organizational Units
        branch = Branch(
            name="الفرع الرئيسي",
            code="MAIN",
            tenant_id=demo_tenant.id,
            is_main=True,
        )
        db.session.add(branch)
        db.session.flush()

        warehouse = Warehouse(
            name="المستودع الرئيسي",
            tenant_id=demo_tenant.id,
            branch_id=branch.id,
            warehouse_type="general",
            is_main=True,
        )
        db.session.add(warehouse)

        cashbox = CashBox(
            name_ar="الصندوق الرئيسي",
            code="MAIN",
            tenant_id=demo_tenant.id,
            branch_id=branch.id,
            box_type="cash",
            currency="ILS",
            current_balance=0,
            is_active=True,
            is_default=True,
        )
        db.session.add(cashbox)

        # 4. Provision Financial Core
        GLProvisioningService.provision_tenant(demo_tenant.id)

        # 5. Provision Document Sequences
        for code in SEQUENCE_CODES:
            DocumentSequenceService.get_or_create(demo_tenant.id, code)

        # 6. Setup Demo Admin (Role is global, not tenant-scoped)
        role = Role.query.filter_by(slug='admin').first()
        if not role:
            role = Role(name='Admin', slug='admin')
            db.session.add(role)
            db.session.flush()

        demo_admin = User(
            username='demo_admin',
            email='demo@azad.com',
            tenant_id=demo_tenant.id,
            role_id=role.id,
            is_active=True,
            is_owner=False,
        )
        demo_admin.set_password('Demo@2026')
        db.session.add(demo_admin)

        db.session.commit()
        print("Demo tenant provisioned successfully with all core components.")


def downgrade():
    app = create_app()
    with app.app_context():
        demo_tenant = Tenant.query.filter_by(slug='demo').first()
        if demo_tenant:
            db.session.delete(demo_tenant)
            db.session.commit()
