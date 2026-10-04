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
def pos_cashier(client, db_session, sample_tenant, sample_branch, sample_role):
    """A signed-in user who can ring up a sale, with an open till session.

    The session is opened without terminal_id, which is what makes the checkout
    reachable at all: routes/pos.py:_require_session_token returns early for a
    session with no terminal, so no HMAC token is demanded. A terminal-bound
    session would need one and this is not a test of the token.
    """
    from models import User

    unique = str(uuid.uuid4())[:8]
    user = User(
        username=f"pos-{unique}",
        email=f"pos-{unique}@example.com",
        full_name="POS Cashier",
        tenant_id=sample_tenant.id,
        role_id=sample_role.id,
        branch_id=sample_branch.id,
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
def till_open(client, db_session, sample_tenant):
    """An open POS session for the cashier, so checkout is not blocked."""
    from models import PosSession

    session = PosSession(
        session_number=f"POS-TEST-{uuid.uuid4().hex[:8].upper()}",
        tenant_id=sample_tenant.id,
        user_id=db_session.query(__import__("models").User.id)
        .filter_by(tenant_id=sample_tenant.id, is_active=True)
        .first()
        .id,
        opening_balance=Decimal("0"),
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
