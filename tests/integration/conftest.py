"""Integration-test fixtures built from factory_boy factories.

These fixtures complement tests/conftest.py by providing records created through
factories, guaranteeing unique slugs/emails/codes per test run.
"""

from __future__ import annotations

import pytest

from services.gl_service import GLService
from services.stock_service import StockService
from tests.factories import (
    BranchFactory,
    CustomerFactory,
    ProductFactory,
    RoleFactory,
    SupplierFactory,
    TenantFactory,
    UserFactory,
    WarehouseFactory,
)


@pytest.fixture
def demo_tenant(db_session):
    """A fresh tenant created through the factory."""
    tenant = TenantFactory()
    db_session.commit()
    return tenant


@pytest.fixture
def demo_branch(db_session, demo_tenant):
    """A main branch for the demo tenant."""
    branch = BranchFactory(tenant=demo_tenant)
    db_session.commit()
    return branch


@pytest.fixture
def demo_warehouse(db_session, demo_tenant, demo_branch):
    """A warehouse linked to the demo branch."""
    warehouse = WarehouseFactory(tenant=demo_tenant, branch=demo_branch)
    db_session.commit()
    return warehouse


@pytest.fixture
def demo_role(db_session):
    """A unique role for demo users."""
    role = RoleFactory()
    db_session.commit()
    return role


@pytest.fixture
def demo_user(db_session, demo_tenant, demo_role):
    """An active user linked to the demo tenant."""
    user = UserFactory(tenant=demo_tenant, role=demo_role)
    db_session.commit()
    return user


@pytest.fixture
def demo_customer(db_session, demo_tenant):
    """A customer linked to the demo tenant."""
    customer = CustomerFactory(tenant=demo_tenant)
    db_session.commit()
    return customer


@pytest.fixture
def demo_supplier(db_session, demo_tenant):
    """A supplier linked to the demo tenant."""
    supplier = SupplierFactory(tenant=demo_tenant)
    db_session.commit()
    return supplier


@pytest.fixture
def demo_product(db_session, demo_tenant):
    """A product linked to the demo tenant with zero stock."""
    product = ProductFactory(tenant=demo_tenant)
    db_session.commit()
    return product


@pytest.fixture
def demo_product_in_stock(db_session, demo_tenant, demo_warehouse):
    """A product with initial stock in the demo warehouse."""
    product = ProductFactory(tenant=demo_tenant)
    StockService.add_stock(product.id, 100, warehouse_id=demo_warehouse.id)
    db_session.commit()
    db_session.refresh(product)
    return product


@pytest.fixture
def demo_gl_accounts(db_session, demo_tenant, app):
    """Ensure core chart of accounts exists for the demo tenant."""
    with app.app_context():
        GLService.ensure_core_accounts(tenant_id=demo_tenant.id)
        if app.config.get("ENABLE_DYNAMIC_GL_MAPPING"):
            from services.gl_accounting_setup import GLAccountingSetupService

            GLAccountingSetupService.execute(tenant_id=demo_tenant.id, dry_run=False)
        db_session.commit()
    return demo_tenant
