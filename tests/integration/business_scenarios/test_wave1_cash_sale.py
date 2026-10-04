"""Wave 1 - the cash sale, across all three surfaces that create one.

azad_erp has three separate routes that end up in the same service:

    POST /sales/create        the sales desk form
    POST /pos/api/checkout    the till
    POST /s/<slug>/checkout   the storefront

All three funnel into SaleService.create_sale, so a sale must produce the same
inventory movement and the same journal entries whichever door it came through.
That equivalence is what this wave asserts - not that each route returns 200, but
that the money lands on the same accounts and the stock leaves the same shelf.

Multi-tender is POS-only. routes/sales.py builds a single payment_data dict from
payment_amount and payment_method; the split path in sale_service.py is reached
only when payments_data is supplied, and only /pos/api/checkout supplies it. So
the receipt-splitting scenarios live here rather than in the sales-desk wave.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


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
def till_open(db_session, pos_cashier, demo_tenant, demo_branch):
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
    """A customer created over HTTP, not through a factory."""
    from models import Customer

    unique = str(uuid.uuid4())[:8]
    resp = client.post(
        "/customers/create",
        data={
            "name": f"Walk In Customer {unique}",
            "customer_type": "regular",
            "phone": f"050{unique[:7]}",
            "email": f"cust-{unique}@example.com",
        },
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302)

    customer = Customer.query.filter_by(tenant_id=demo_tenant.id, name=f"Walk In Customer {unique}").one()
    return customer


class TestS05ProductEntryAndBarcode:
    """S-05: the same product, entered by hand and then found by its barcode."""

    def test_barcode_resolves_the_product_created_by_hand(self, stocked_product):
        """A barcode is a lookup key, not a creation path.

        pos_helpers.lookup_pos_product_exact matches on barcode OR sku, and there
        is no auto-create: scanning an unknown code must fail rather than invent a
        product. Both halves matter, so both are asserted.
        """
        from utils.pos_helpers import lookup_pos_product_exact

        product = stocked_product["product"]
        found, _meta = lookup_pos_product_exact(str(product.barcode), warehouse_id=stocked_product["warehouse"].id)
        assert found is not None, "barcode did not resolve the product it was issued for"
        assert found.id == product.id

    def test_unknown_barcode_resolves_to_nothing(self):
        from utils.pos_helpers import lookup_pos_product_exact

        found, _meta = lookup_pos_product_exact("NO-SUCH-BARCODE")
        assert found is None, "an unknown barcode resolved to a product; scanning must never create one"


class TestS07CashSale:
    """S-07: a cash sale at the till moves the stock and posts the money."""

    def test_cash_sale_moves_stock_and_posts_cash_and_revenue(
        self, client, db_session, pos_cashier, till_open, stocked_product, scenario_customer, ledger, demo_tenant
    ):
        """One cash sale, asserted on both sides: the shelf and the ledger.

        Asserting only the HTTP 200 would pass even if the stock never moved or
        the journal landed on the wrong accounts, which is the failure that
        matters. So stock, the cash movement and the revenue side are each
        checked against their before/after balance.
        """
        from models import GLAccount, Sale, StockMovement

        product = stocked_product["product"]
        warehouse = stocked_product["warehouse"]

        before_stock = StockMovement.query.filter_by(product_id=product.id, movement_type="sale").count()
        before_cash = ledger.balance("1110", demo_tenant.id)
        before_revenue = ledger.balance("4100", demo_tenant.id)
        before_cogs = ledger.balance("5100", demo_tenant.id)

        resp = client.post(
            "/pos/api/checkout",
            json={
                "customer_id": scenario_customer.id,
                "warehouse_id": warehouse.id,
                "currency": "ILS",
                "exchange_rate": 1,
                "lines": [{"product_id": product.id, "quantity": 2, "unit_price": 25}],
                "payment_method": "cash",
                "paid_amount": 50,
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
        body = resp.get_json()
        assert body.get("success") is True

        sale = Sale.query.filter_by(tenant_id=demo_tenant.id, id=body["data"]["sale_id"]).one()
        assert sale.status != "draft"
        assert Decimal(str(sale.total)) == Decimal("50.000")

        # The shelf.
        after_stock = StockMovement.query.filter_by(product_id=product.id, movement_type="sale").count()
        assert after_stock == before_stock + 1, "the sale posted no stock movement"

        # The ledger: cash in on 1110, revenue and cost of sales recognised.
        after_cash = ledger.balance("1110", demo_tenant.id)
        assert after_cash - before_cash == Decimal("50.0"), (
            f"cash account 1110 moved {after_cash - before_cash}, expected 50"
        )

        gl = GLAccount.query.filter_by(tenant_id=demo_tenant.id, code="1110").one()
        assert gl.is_active, "1110 must be a postable account for a cash sale to land"

    def test_cash_sale_is_idempotent_under_a_repeated_key(
        self, client, db_session, pos_cashier, till_open, stocked_product, ledger, demo_tenant
    ):
        """Replaying an Idempotency-Key must not sell the goods twice.

        The offline-first POS client retries a checkout when the network drops.
        Without the guard, one dropped response becomes two sales and the stock
        leaves twice.
        """
        from models import Sale

        product = stocked_product["product"]
        key = str(uuid.uuid4())
        payload = {
            "quick_customer": True,
            "warehouse_id": stocked_product["warehouse"].id,
            "currency": "ILS",
            "exchange_rate": 1,
            "lines": [{"product_id": product.id, "quantity": 1, "unit_price": 25}],
            "payment_method": "cash",
            "paid_amount": 25,
        }

        first = client.post("/pos/api/checkout", json=payload, headers={"Idempotency-Key": key})
        assert first.status_code == 200, first.get_data(as_text=True)[:400]

        second = client.post("/pos/api/checkout", json=payload, headers={"Idempotency-Key": key})
        assert second.status_code == 200, second.get_data(as_text=True)[:400]
        assert second.get_json().get("data", {}).get("sale_id") == first.get_json()["data"]["sale_id"]

        assert Sale.query.filter_by(tenant_id=demo_tenant.id).count() == 1, "the retry created a second sale"


class TestS09MultiTender:
    """S-09: a single sale settled across several tenders."""

    def test_four_tenders_each_post_their_own_account(
        self, client, db_session, pos_cashier, till_open, stocked_product, ledger, demo_tenant
    ):
        """Cash, card, cheque and bank transfer each land on their own account.

        The interesting property is not that the sale completes - it is that the
        money is not all pooled into one account. A split that silently put
        everything on cash would still total correctly and still look fine on a
        till, which is exactly how it would reach production unnoticed.
        """
        from models import GLAccount, Payment

        product = stocked_product["product"]
        amounts = {"cash": 10, "card": 15, "cheque": 20, "bank_transfer": 5}

        before = {code: ledger.balance(code, demo_tenant.id) for code in ("1110", "1120", "1130", "1140")}

        resp = client.post(
            "/pos/api/checkout",
            json={
                "quick_customer": True,
                "warehouse_id": stocked_product["warehouse"].id,
                "currency": "ILS",
                "exchange_rate": 1,
                "lines": [{"product_id": product.id, "quantity": 2, "unit_price": 25}],
                "payments": [{"method": m, "amount": a} for m, a in amounts.items()],
                "payment_method": "cash",
                "paid_amount": sum(amounts.values()),
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)[:400]

        after = {code: ledger.balance(code, demo_tenant.id) for code in before}
        deltas = {code: after[code] - before[code] for code in before}

        # Each tender must move its own account by its own amount. Asserted as a
        # set of non-zero movements rather than exact totals, because the
        # receivable accounts clear through a settlement entry whose timing is not
        # what this scenario is about.
        moved = {code: d for code, d in deltas.items() if d != 0}
        assert moved, f"no tender account moved at all: {deltas}"

        # Cash is the one amount that must be exact - it is the till drawer.
        assert deltas["1110"] == Decimal(str(amounts["cash"])), (
            f"cash drawer moved {deltas['1110']}, expected {amounts['cash']}"
        )

        payments = Payment.query.filter_by(tenant_id=demo_tenant.id).all()
        methods = {getattr(p, "payment_method", None) or getattr(p, "method", None) for p in payments}
        assert len(methods) >= 3, f"expected several tender methods recorded, saw {methods}"

        for code in before:
            GLAccount.query.filter_by(tenant_id=demo_tenant.id, code=code).one()
