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


@pytest.fixture(scope="session", autouse=True)
def _seed_permissions(app):
    """Make the real permission table available to integration tests.

    tests/conftest.py creates the app with SKIP_SYSTEM_INTEGRITY=1, which is
    right for speed but leaves the permissions table empty. That is invisible
    until a test hits a route behind ``@permission_required``: the guard denies
    it and the failure looks like a product bug rather than a missing fixture
    row - a 403 on /pos/api/checkout because ``manage_sales`` was never created.

    The seeder is the same one production boot uses, sourced from
    utils.constants, and it is idempotent. It runs per session, outside any
    per-test savepoint, because permissions are reference data rather than test
    state.
    """
    from models import Permission
    from utils.system_init import _ensure_permissions

    with app.app_context():
        # Seeded when any of the required codes is missing, rather than only when
        # the table is empty.
        #
        # Guarding on "table is empty" is what let budget:create and
        # budget:approve stay absent from the test database even after being added
        # to utils/constants.py: a database that already held permissions skipped
        # the seeder entirely.
        #
        # The condition is per-code for the same reason, and deliberately not an
        # unconditional _ensure_permissions() - that runs inside atomic_transaction
        # and commits, which escapes the per-test savepoint and broke the
        # isolation wave 1 depends on.
        required = ("manage_sales", "budget:create", "budget:approve")
        if any(Permission.query.filter_by(code=code).first() is None for code in required):
            _ensure_permissions()
        for code in required:
            assert Permission.query.filter_by(code=code).first() is not None, (
                f"permission seeding did not produce {code}"
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
    """Ensure core chart of accounts exists for the demo tenant.

    GLService.ensure_core_accounts does both halves of the job: it runs
    GLTreeBuilder.build for the accounts and, when dynamic GL mapping is
    enabled, GLService.ensure_gl_mappings for the concept rows. It previously
    also called GLAccountingSetupService.execute, which was redundant double
    seeding off the same GL_MODULE_DEFINITIONS source - and, because the two
    allocate branch liquidity codes differently (``1120-B{branch.id}`` versus a
    ``1120-B{allocation-counter}``), a latent collision on
    ``uq_gl_accounts_tenant_code``.
    """
    with app.app_context():
        GLService.ensure_core_accounts(tenant_id=demo_tenant.id)
        db_session.commit()
    return demo_tenant
