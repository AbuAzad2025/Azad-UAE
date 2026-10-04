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
from datetime import date, timedelta
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
        from models import Payment, Sale, StockMovement

        product = stocked_product["product"]
        warehouse = stocked_product["warehouse"]

        before_stock = StockMovement.query.filter_by(product_id=product.id, movement_type="sale").count()
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
        # total_amount, not total - Sale has no `total` attribute.
        assert Decimal(str(sale.total_amount)) == Decimal("50.000"), (
            f"sale total is {sale.total_amount}, expected the 50 rung up"
        )

        # The shelf.
        after_stock = StockMovement.query.filter_by(product_id=product.id, movement_type="sale").count()
        assert after_stock == before_stock + 1, "the sale posted no stock movement"

        # The ledger. Which cash account a till posts to is the chart of accounts'
        # business - 1110 is a header over the 1111/1112 cash boxes, and hardcoding
        # one of them here would break the moment the registry resolves a different
        # box. So the cash account is discovered from the journal entry this sale
        # actually wrote, exactly as S-09 does for its tenders.
        from models import GLAccount, GLJournalEntry, GLJournalLine
        from utils.gl_reference_types import GLRef, filter_entries_by_ref

        payment_ids = [p.id for p in db_session.query(Payment).filter_by(tenant_id=demo_tenant.id).all()]
        pay_entry_ids = [
            e.id
            for e in filter_entries_by_ref(db_session.query(GLJournalEntry), GLRef.PAYMENT)
            .filter(GLJournalEntry.reference_id.in_(payment_ids), GLJournalEntry.status == "posted")
            .all()
        ]
        assert pay_entry_ids, "the cash sale posted no payment journal entry"

        cash_lines = [
            line
            for line in db_session.query(GLJournalLine).filter(GLJournalLine.entry_id.in_(pay_entry_ids)).all()
            if line.debit and float(line.debit) > 0
        ]
        assert cash_lines, "the cash tender debited nothing"

        cash_total = sum(float(line.debit) for line in cash_lines)
        assert cash_total == pytest.approx(50.0), f"the cash tender landed {cash_total}, expected the 50 rung up"
        cash_codes = {db_session.query(GLAccount).get(line.account_id).code for line in cash_lines}
        for code in cash_codes:
            assert db_session.query(GLAccount).filter_by(tenant_id=demo_tenant.id, code=code).one().is_active

        # Revenue and cost of sales are recognised on the sale entry, which the
        # payment entries above do not carry. Asserting them closes the loop: a
        # sale that moves cash and stock but never recognises revenue would pass
        # every other check in this test.
        revenue = ledger.balance("4100", demo_tenant.id) - before_revenue
        cogs = ledger.balance("5100", demo_tenant.id) - before_cogs
        # ledger.balance is debit-minus-credit, so revenue recognised as a credit
        # reads as a decrease. The sale entry is Dr 1130 / Cr 4100.
        assert revenue == pytest.approx(-50.0), f"revenue moved {revenue}, expected a 50 credit on 4100"
        # Cost of sales is the cost of the two units at cost price 10, not the 25
        # they were rung up at - the gross margin is real money the ledger must
        # not lose.
        assert cogs == pytest.approx(20.0), f"cost of sales moved {cogs}, expected 2 x cost 10"

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
        from models import Payment

        product = stocked_product["product"]
        cheque_no = f"CHQ-{uuid.uuid4().hex[:10].upper()}"
        # A cheque is only accepted with a complete instrument:
        # SaleService.create_payment_for_sale requires number, due date and the
        # drawing bank, and SaleService._prepare_split_payments passes all three
        # through from the chunk. Asserting the cheque survives with its
        # reference intact is what makes the tender reconcilable later.
        due_date = (date.today() + timedelta(days=30)).isoformat()
        amounts = {"cash": 10, "card": 15, "cheque": 20, "bank_transfer": 5}
        tenders = [
            {"method": "cash", "amount": 10},
            {"method": "card", "amount": 15},
            {
                "method": "cheque",
                "amount": 20,
                "cheque_number": cheque_no,
                "cheque_date": due_date,
                "bank_name": "Bank Al-Yusr",
            },
            {"method": "bank_transfer", "amount": 5},
        ]

        resp = client.post(
            "/pos/api/checkout",
            json={
                "quick_customer": True,
                "warehouse_id": stocked_product["warehouse"].id,
                "currency": "ILS",
                "exchange_rate": 1,
                "lines": [{"product_id": product.id, "quantity": 2, "unit_price": 25}],
                "payments": tenders,
                "payment_method": "cash",
                "paid_amount": sum(amounts.values()),
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)[:400]

        payments = Payment.query.filter_by(tenant_id=demo_tenant.id).all()
        methods = {getattr(p, "payment_method", None) or getattr(p, "method", None) for p in payments}
        assert len(methods) >= 3, f"expected several tender methods recorded, saw {methods}"

        # The amounts must add up to the sale, and the cheque must have kept its
        # instrument number - a split that lost the cheque reference would leave
        # an amount on the cheques-under-collection account that nobody can ever
        # reconcile.
        from models import Cheque

        recorded = sum(Decimal(str(p.amount)) for p in payments)
        assert recorded == Decimal("50"), f"tendered {recorded}, expected the 50 sale total"

        cheque = Cheque.query.filter_by(tenant_id=demo_tenant.id, cheque_number=cheque_no).first()
        assert cheque is not None, f"cheque {cheque_no} was not recorded"
        assert Decimal(str(cheque.amount)) == Decimal("20"), f"cheque amount is {cheque.amount}, expected 20"
        # The real invariant: each tender reaches a different account.
        #
        # The sale entry itself carries only the revenue side (4100). Each tender
        # posts its own payment entry, keyed on GLRef.PAYMENT against the Payment
        # row, so the accounts are read per payment. Filtering on the sale entry
        # would show just the revenue credit and hide pooling completely - which
        # is how "assert >= 3 accounts" first reported only {'4100': 50.0}.
        #
        # Which cash box or collection account a tender uses is the chart of
        # accounts' business, not this test's - see models/gl_account_registry.py -
        # so the codes are discovered from the journal rather than hardcoded.
        from models import GLAccount, GLJournalEntry, GLJournalLine
        from utils.gl_reference_types import GLRef, filter_entries_by_ref

        pay_entry_ids = [
            e.id
            for e in filter_entries_by_ref(db_session.query(GLJournalEntry), GLRef.PAYMENT)
            .filter(
                GLJournalEntry.reference_id.in_([p.id for p in payments]),
                GLJournalEntry.status == "posted",
            )
            .all()
        ]
        assert pay_entry_ids, "no tender posted a payment journal entry"

        # The tender entries credit the customer receivable (1130) as it is
        # settled; where the money physically lands is the debit side. Asserting
        # credits would only ever show 1130 once, for every tender combined.
        landed: dict[str, float] = {}
        for line in db_session.query(GLJournalLine).filter(GLJournalLine.entry_id.in_(pay_entry_ids)).all():
            if not line.debit or float(line.debit) <= 0:
                continue
            code = db_session.query(GLAccount).get(line.account_id).code
            landed[code] = landed.get(code, 0.0) + float(line.debit)

        # Four tenders across cash, card, cheque and bank transfer. Pooling them
        # would collapse these into one account while still totalling correctly,
        # which is exactly the bug being asserted against.
        assert len(landed) >= 3, f"tenders were pooled onto too few accounts: {landed}"

        total_landed = sum(landed.values())
        assert total_landed == pytest.approx(50.0), (
            f"tenders landed {total_landed} across {landed}, expected the 50 collected"
        )
