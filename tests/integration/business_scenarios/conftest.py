"""Fixtures and assertions for the business-scenario suite.

Two things every scenario needs and none of the existing fixtures provide:

1. A way to ask the ledger a question. The integration suite so far asserts on
   service return values; a business scenario has to ask what the accounts now
   say, which is the only way to catch a posting that hit the wrong account.
2. A signed-in client for each actor a scenario involves - platform owner,
   company admin, cashier - because the permission boundary is part of the
   behaviour under test.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


@pytest.fixture
def scenario_owner(db_session, client):
    """Platform owner, signed in over real HTTP.

    tenant_id is None, which is what @owner_required checks for, so this is the
    only actor that can reach /owner/tenants/create.
    """
    import uuid

    from models import Role, Tenant, User

    unique = str(uuid.uuid4())[:8]
    tenant = Tenant(
        name=f"Scenario Platform {unique}",
        name_ar="منصة السيناريو",
        slug=f"scenario-plat-{unique}",
        email=f"plat-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()

    role = db_session.query(Role).filter_by(slug="owner").first()
    if role is None:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.commit()

    user = User(
        username=f"plat-owner-{unique}",
        email=f"plat-{unique}@example.com",
        full_name="Platform Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )
    # Log out on teardown. A platform owner leaves tenant_id=None active in the
    # session, and the next test's fixtures create branches and customers for
    # their own tenant - which the ORM write guard then rejects as a cross-tenant
    # insert. Without this the suite fails depending on test order, which is
    # exactly the kind of nondeterminism these scenarios exist to rule out.
    yield user
    client.get("/auth/logout", follow_redirects=True)


@pytest.fixture
def pos_subfeatures_on(db_session, demo_tenant):
    """Turn the POS sub-features the scenarios need on for the demo tenant.

    Split tenders are a paid sub-feature: utils/pos_features.pos_feature_enabled
    reads the tenant's ``enable_pos_multi_tender`` column first and otherwise
    falls back to the plan default, which for a bare test tenant is the basic
    tier, so checkout is refused with 403 before any money is handled.

    Set through the columns rather than by faking a subscription, because these
    scenarios are about the split-tender accounting, not about plan resolution -
    plan defaulting has its own coverage.
    """
    demo_tenant.enable_pos_multi_tender = True
    demo_tenant.enable_pos_promotions = True
    db_session.flush()
    return demo_tenant


@pytest.fixture
def ledger(db_session):
    """Read-only view of what the ledger says, for verification.

    Deliberately queries posted journal lines rather than trusting a service's
    return value. If a posting is written to the wrong account, only a query
    against the journal will show it.
    """

    class Ledger:
        def balance(self, account_code: str, tenant_id: int) -> float:
            from sqlalchemy import func, select

            from models import GLAccount, GLJournalEntry, GLJournalLine

            stmt = (
                select(
                    func.coalesce(func.sum(GLJournalLine.debit), 0),
                    func.coalesce(func.sum(GLJournalLine.credit), 0),
                )
                .select_from(GLJournalLine)
                .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
                .join(GLAccount, GLAccount.id == GLJournalLine.account_id)
                .where(
                    GLAccount.code == str(account_code),
                    GLEntry_tenant_filter(tenant_id),
                    GLJournalEntry.status == "posted",
                )
            )
            debit, credit = db_session.execute(stmt).one()
            return float(debit or 0) - float(credit or 0)

        def entries(self, tenant_id: int) -> list:
            """Every posted entry for the tenant, newest first."""
            from models import GLJournalEntry

            return (
                db_session.query(GLJournalEntry)
                .filter(GLEntry_tenant_filter(tenant_id))
                .filter_by(status="posted")
                .order_by(GLJournalEntry.id.desc())
                .all()
            )

        def lines_for(self, entry_id: int):
            from models import GLJournalLine

            return db_session.query(GLJournalLine).filter_by(entry_id=entry_id).all()

        def codes_for(self, entry_id: int) -> list[str]:
            from models import GLAccount

            return [db_session.query(GLAccount).get(line.account_id).code for line in self.lines_for(entry_id)]

    def GLEntry_tenant_filter(tenant_id):  # noqa: N802 - local predicate helper
        from models import GLJournalEntry

        return GLJournalEntry.tenant_id == tenant_id

    return Ledger()


# ── Shared sale-surface fixtures ────────────────────────────────────────
# Used by more than one wave: wave 1 exercises the revenue path, wave 2 settles
# it by cheque and reverses it by return. They live here rather than in either
# test module so a second wave can reuse them without importing fixtures across
# test modules, which pytest treats as an error.
@pytest.fixture
def pos_cashier(client, db_session, demo_tenant, demo_branch):
    """A signed-in cashier who is actually allowed to ring up a sale.

    demo_tenant rather than sample_tenant on purpose: the products, the customer
    and the till session in this wave all live under demo_tenant, and a cashier
    belonging to a different tenant cannot open a session against them.

    The permissions are attached explicitly rather than via RoleFactory, because
    /pos/api/checkout is guarded by @permission_required(MANAGE_SALES) and a
    factory role carries none.
    """
    from models import Permission, Role, User

    unique = str(uuid.uuid4())[:8]
    role = Role(
        name=f"POS Cashier {unique}",
        slug=f"pos-cashier-{unique}",
        is_active=True,
    )
    role.permissions = Permission.query.filter(
        Permission.code.in_(
            [
                "manage_sales",
                "manage_products",
                "view_products",
                "view_inventory",
                # scenario_customer creates a customer over HTTP, and
                # routes/customers.py:/create is guarded by manage_customers.
                "manage_customers",
                "view_customers",
                # Wave 2 settles by cheque and reverses by return: every
                # routes/cheques.py action is behind manage_payments, and
                # routes/returns.py sits behind its own guard.
                "manage_payments",
                "view_payments",
                "manage_returns",
                "view_returns",
                "manage_accounting",
                "view_reports",
                # Wave 3's store admin routes - settings, orders, confirm and
                # cancel - are all behind manage_store.
                "manage_store",
                "view_store",
                # Wave 4 is the cost side: buying from suppliers and moving
                # stock between warehouses.
                "manage_purchases",
                "view_purchases",
                "manage_warehouse",
                "view_warehouse",
            ]
        )
    ).all()
    db_session.add(role)
    # The role's identity is only assigned on flush, and users.role_id is NOT NULL,
    # so the insert has to wait for it.
    db_session.flush()

    user = User(
        username=f"pos-{unique}",
        email=f"pos-{unique}@example.com",
        full_name="POS Cashier",
        tenant_id=demo_tenant.id,
        role_id=role.id,
        branch_id=demo_branch.id,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )
    return user


@pytest.fixture
def till_open(db_session, pos_cashier, demo_tenant, demo_branch, pos_subfeatures_on):
    """An open POS session owned by the cashier who is actually signed in.

    Without this, /pos/api/checkout refuses to ring up: the route resolves the
    session for the current user and a branch, so a session belonging to anyone
    else is simply not found.

    No terminal_id, deliberately: routes/pos.py:_require_session_token returns
    early for a session with no terminal, so no HMAC token is demanded. Binding a
    terminal is exercised in the multi-tender scenarios instead.
    """
    from models import PosSession

    session = PosSession(
        session_number=f"POS-TEST-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=demo_tenant.id,
        branch_id=demo_branch.id,
        user_id=pos_cashier.id,
        opening_balance_cash=Decimal("0"),
        status="open",
    )
    db_session.add(session)
    db_session.commit()
    return session


@pytest.fixture
def stocked_product(db_session, demo_tenant, demo_branch, demo_warehouse, ledger):
    """A product with real opening stock, created under the scenario tenant.

    Built through ProductService + StockService rather than the HTML form: what
    this wave asserts is that a barcode resolves and that a sale moves stock and
    posts the right journal, and the create form's field validation is already
    covered elsewhere. Opening stock goes through add_opening_stock so it posts
    Dr 1140 / Cr 3130, not a purchase.
    """
    from decimal import Decimal as D

    from services.product_service import ProductService
    from services.stock_service import StockService

    unique = str(uuid.uuid4())[:8]
    product = ProductService.create_product(
        tenant_id=demo_tenant.id,
        name=f"Canned Beans {unique}",
        sku=f"SKU-{unique}",
        barcode=f"BC{unique}",
        regular_price=D("25"),
        cost_price=D("10"),
    )
    db_session.flush()
    StockService.add_opening_stock(
        product.id,
        D("100"),
        warehouse_id=demo_warehouse.id,
    )
    db_session.flush()

    qty = StockService.get_product_stock(product.id, warehouse_id=demo_warehouse.id)
    assert D(str(qty)) == D("100"), f"opening stock not applied ({qty})"

    # Opening stock is not a purchase: it posts Dr 1140 / Cr 3130, bypassing AP.
    # Asserted here so every later scenario in this wave starts from a ledger
    # that is known to be balanced, rather than assuming it.
    inv = ledger.balance("1140", demo_tenant.id)
    equity = ledger.balance("3130", demo_tenant.id)
    assert inv == D("1000"), f"expected 100 x cost 10 in 1140, got {inv}"
    assert equity == D("-1000"), f"expected the offset in 3130, got {equity}"

    return {"product": product, "warehouse": demo_warehouse, "sku": f"SKU-{unique}"}


@pytest.fixture
def scenario_customer(client, db_session, demo_tenant):
    """A customer created over HTTP, not through a factory.

    Creating it through the form rather than a factory is the point: the sale
    scenarios should be able to attribute a sale to a customer the tenant
    actually created, and the response is asserted rather than assumed.
    """
    from models import Customer

    unique = str(uuid.uuid4())[:8]
    name = f"Walk In Customer {unique}"
    resp = client.post(
        "/customers/create",
        data={
            "name": name,
            "customer_type": "regular",
            # Digits only: normalize_phone_optional rejects letters, and a uuid
            # slice is hex, so "050" + uuid[:7] fails about half the time.
            "phone": "050" + "".join(ch for ch in unique if ch.isdigit())[:7].ljust(7, "0"),
            "email": f"cust-{unique}@example.com",
        },
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:300]

    # Read back inside without_tenant_scope: this fixture runs outside a request,
    # so the ORM's automatic scoping has no active tenant to scope to and would
    # filter the row away. The sale path reads it from inside the request, which
    # is why the create has to have gone through HTTP rather than a factory.
    from utils.tenanting import without_tenant_scope

    with without_tenant_scope():
        customer = db_session.query(Customer).filter_by(tenant_id=demo_tenant.id, name=name).one()

    # Created customers land inactive, and SaleService.create_sale refuses an
    # inactive customer outright ("العميل غير صالح أو غير نشط"). Activating is
    # done here rather than by patching the service, so the sale is exercised
    # through the same validation every real sale goes through.
    if not customer.is_active:
        customer.is_active = True
        db_session.flush()
    return customer
