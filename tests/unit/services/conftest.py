from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal


import pytest

from models import Cheque, TenantStore, Warehouse


@pytest.fixture(autouse=True)
def _app_context(app):
    with app.app_context():
        yield


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    yield
    db_session.rollback()


@pytest.fixture
def incoming_cheque(db_session, sample_tenant):
    ch = Cheque(
        tenant_id=sample_tenant.id,
        cheque_number=f"IN-{uuid.uuid4().hex[:6]}",
        cheque_bank_number=f"BNK-{uuid.uuid4().hex[:4]}",
        cheque_type="incoming",
        bank_name="Test Bank",
        amount=Decimal("1000.00"),
        amount_aed=Decimal("1000.00"),
        currency="AED",
        issue_date=date.today(),
        due_date=date.today(),
        status="pending",
    )
    db_session.add(ch)
    db_session.flush()
    return ch


@pytest.fixture
def outgoing_cheque(db_session, sample_tenant):
    ch = Cheque(
        tenant_id=sample_tenant.id,
        cheque_number=f"OUT-{uuid.uuid4().hex[:6]}",
        cheque_bank_number=f"BNK-{uuid.uuid4().hex[:4]}",
        cheque_type="outgoing",
        bank_name="Test Bank",
        amount=Decimal("500.00"),
        amount_aed=Decimal("500.00"),
        currency="AED",
        issue_date=date.today(),
        due_date=date.today(),
        status="pending",
    )
    db_session.add(ch)
    db_session.flush()
    return ch


@pytest.fixture
def online_warehouse(db_session, sample_tenant, sample_branch):
    wh = Warehouse(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        name=f"Online WH {uuid.uuid4().hex[:4]}",
        name_ar="مستودع أونلاين",
        code=f"ONL-{uuid.uuid4().hex[:4].upper()}",
        warehouse_type=Warehouse.TYPE_ONLINE,
        is_active=True,
    )
    db_session.add(wh)
    db_session.flush()
    return wh


@pytest.fixture
def tenant_store(db_session, sample_tenant, online_warehouse):
    slug = f"store-{uuid.uuid4().hex[:8]}"
    store = TenantStore(
        tenant_id=sample_tenant.id,
        warehouse_id=online_warehouse.id,
        store_slug=slug,
        subdomain=slug,
        title="Test Store",
        is_enabled=True,
    )
    db_session.add(store)
    db_session.flush()
    return store


@pytest.fixture
def online_sale(db_session, sample_tenant, sample_customer, sample_user, online_warehouse):
    from models import Sale

    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number=f"WEB-{uuid.uuid4().hex[:6]}",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        warehouse_id=online_warehouse.id,
        source="online_store",
        status="pending",
        payment_status="unpaid",
        subtotal=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        checkout_payment_method="cod",
    )
    db_session.add(sale)
    db_session.flush()
    return sale
