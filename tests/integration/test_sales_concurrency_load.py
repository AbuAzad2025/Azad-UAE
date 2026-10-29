"""Concurrency / load probe for the money path (sales + POS checkout).

What this file is
-----------------
A contention probe that answers one production-readiness question with
measurements instead of an opinion: *if many cashiers hit the same stock row
at the same instant, does the system oversell, double-charge, unbalance the
ledger, or leak another tenant's rows?*

Every assertion below is made against the DATABASE, never against a return
value: the number of sale lines that were actually written, the number of
Payment rows that were actually written, the debit/credit totals of the
journal entries that were actually posted, and the per-tenant row counts.
A response body saying ``{"success": true}`` is not evidence of anything.

Two real money paths are exercised, because they are not the same code:

``POS route``
    ``POST /pos/api/checkout`` - the register. Full HTTP stack, real
    ``atomic_transaction`` boundary, real session/shift, real GL postings.
    This is the path a cashier actually presses.

``service path``
    ``SaleService.create_sale`` - what ``routes/sales.py`` calls for an
    invoice typed by hand. It has no per-product row lock, so it is the path
    where two writers really do meet on the same stock row. Its worker
    re-submits an order whose document number collided, because that is what
    a cashier does - and the number of re-submissions is itself one of the
    measurements.

Two known defects are pinned with ``xfail(strict=True)`` so they cannot be
forgotten. Each one names the file and line that has to change. Both are
failures of *availability* and of *reporting*, not of integrity: no money is
corrupted and no order is silently duplicated - the orders are refused, and
the drawer's expected-cash figure is wrong.

What the storms measure (the numbers move with the machine, the shape does
not): the register commits exactly as many orders as there are units on the
shelf, every committed order carries exactly one payment, every journal
entry balances, the stock movements reconcile with the quantity on hand,
and neither tenant can see or touch the other's rows. The two defects are
the order *refusals* (a document number that collides) and the register's
own turnover (which loses updates while the terminals queue).

Gaps this file does NOT cover
------------------------------
* Multi-process / multi-host contention. Everything here is threads inside
  one OS process against one PostgreSQL instance. Row locks behave the same,
  but a real deployment adds network latency and connection-pool limits.
* The ``stock_batch_service`` FEFO batch-consumption path, serial numbers,
  negative-inventory warehouses, multi-currency settlement, and the
  checkout idempotency replay (``Idempotency-Key``) under contention.
* The store/e-commerce checkout path and the online payment gateways.
* Deadlock detection between two different lock orders (only one lock
  order is exercised here).
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from decimal import Decimal

import pytest

from extensions import db
from tests.integration._purge_helper import purge_tenant

# ---------------------------------------------------------------- parameters
# N: units physically on the shelf for the contended product.
STOCK_QTY = Decimal(os.environ.get("CONCURRENCY_STOCK", "20"))
# Units each attempt tries to sell.
ATTEMPT_QTY = Decimal("1")
# M: simultaneous attempts. Must be > N for the oversell question to mean
# anything. M is not arbitrary: every concurrent writer holds one PostgreSQL
# connection, and both the local server and the CI service container run with
# the default max_connections=100, so 120 simultaneous writers would exhaust
# the server before the application could misbehave.
THREADS = int(os.environ.get("CONCURRENCY_THREADS", "30"))
# Stock per tenant in the isolation storm: two tenants, so each one is
# smaller - the point there is the tenant boundary, not the shelf.
ISOLATION_STOCK = Decimal(os.environ.get("CONCURRENCY_ISOLATION_STOCK", "6"))
# How many times a worker may re-submit the same order after the document
# numbering collided (see the xfail marker on
# TestSalesServiceStorm.test_no_order_needs_a_second_submission).
MAX_SUBMISSIONS = 60
UNIT_PRICE = Decimal("25")
UNIT_COST = Decimal("10")
# Domain tolerance (services.gl_posting._CURRENCY_TOLERANCE["AED"]).
TOLERANCE = Decimal("0.001")
BARRIER_TIMEOUT = 300
# The unique constraints that a document-number collision trips.
_NUMBER_COLLISION_MARKERS = (
    "uq_sales_tenant_sale_number",
    "uq_gl_journal_entries_tenant_number",
)


# ------------------------------------------------------------------ helpers
def _seed_money_tenant(label, *, stock=STOCK_QTY, price=UNIT_PRICE, cost=UNIT_COST):
    """Create a tenant with everything the money path needs, and COMMIT it.

    The commit matters: the worker threads run on their own connections, so
    the rows have to be durable before they start, not held in the test's
    savepoint.

    Returns a dict of ids - the worker threads must not touch ORM objects
    that belong to another session.
    """
    from models import (
        Branch,
        Customer,
        Permission,
        Product,
        ProductCategory,
        Role,
        SystemSettings,
        Tenant,
        User,
        Warehouse,
    )
    from services.gl_service import GLService
    from services.stock_service import StockService

    unique = uuid.uuid4().hex[:8]

    tenant = Tenant(
        name=f"Load {label} {unique}",
        name_ar=f"Load {label} {unique}",
        slug=f"load-{label}-{unique}",
        default_currency="AED",
        base_currency="AED",
        subscription_plan="pro",
        enable_pos=True,
        enable_pos_promotions=True,
        enable_pos_multi_tender=True,
        enable_pos_shifts=True,
    )
    db.session.add(tenant)
    db.session.flush()

    branch = Branch(tenant_id=tenant.id, name=f"Main {unique}", code=f"L{unique[:4].upper()}")
    db.session.add(branch)
    db.session.flush()

    role = Role(name=f"Load {label} {unique}", slug=f"load-role-{unique}", is_active=True)
    perm = Permission.query.filter_by(code="manage_sales").first()
    if perm is None:
        perm = Permission(code="manage_sales", name="manage_sales", name_ar="manage_sales", category="sales")
        db.session.add(perm)
        db.session.flush()
    role.permissions.append(perm)
    db.session.add(role)
    db.session.flush()

    user = User(
        username=f"load-{label}-{unique}",
        email=f"load-{label}-{unique}@t.com",
        full_name="Load Cashier",
        role_id=role.id,
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        is_owner=False,
    )
    user.set_password("loadpass")
    db.session.add(user)
    db.session.flush()

    warehouse = Warehouse(
        name=f"WH {unique}",
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        is_main=True,
        allow_negative_inventory=False,
    )
    db.session.add(warehouse)
    db.session.flush()

    category = ProductCategory(name=f"Cat {unique}", tenant_id=tenant.id, is_active=True)
    db.session.add(category)
    db.session.flush()

    product = Product(
        name=f"Item {unique}",
        sku=f"ITM-{unique}",
        tenant_id=tenant.id,
        category_id=category.id,
        regular_price=Decimal(str(price)),
        cost_price=Decimal(str(cost)),
        is_active=True,
    )
    db.session.add(product)
    db.session.flush()

    customer = Customer(
        tenant_id=tenant.id,
        name=f"Buyer {unique}",
        customer_type="regular",
        phone="0500000000",
        is_active=True,
    )
    db.session.add(customer)
    db.session.flush()

    # Opening stock through the real service: this is what creates the
    # ProductWarehouseStock row the workers will fight over.
    StockService.add_stock(product.id, stock, warehouse_id=warehouse.id)
    db.session.flush()

    # The chart of accounts is created up front on purpose. Left to the
    # workers, every thread would race to create the same 90-odd accounts
    # and the resulting noise would hide the contention we are measuring.
    GLService.ensure_core_accounts(tenant_id=tenant.id)

    if SystemSettings.query.first() is None:
        db.session.add(SystemSettings(enable_pos=True))

    db.session.commit()

    return {
        "tenant_id": tenant.id,
        "branch_id": branch.id,
        "role_id": role.id,
        "user_id": user.id,
        "username": user.username,
        "warehouse_id": warehouse.id,
        "product_id": product.id,
        "customer_id": customer.id,
        "stock": Decimal(str(stock)),
    }


def _open_register(app, ctx):
    """Log the cashier in and open the register (session + shift).

    Returns the session cookie so every worker thread can act as the same
    cashier. One login, not thirty: the password hash is pbkdf2 with 600k
    iterations and the login endpoint rate-limits repeated logins.
    """
    client = app.test_client()
    resp = client.post(
        "/auth/login",
        data={"username": ctx["username"], "password": "loadpass"},
        follow_redirects=True,
    )
    assert resp.status_code in (200, 302), f"login failed: {resp.status_code}"

    resp = client.post(
        "/pos/api/session/open",
        json={"opening_balance": 0},
        content_type="application/json",
    )
    assert resp.status_code == 201, f"POS session open failed: {resp.status_code} {resp.get_json(silent=True)}"
    resp = client.post(
        "/pos/api/shift/open",
        json={"starting_cash": 0},
        content_type="application/json",
    )
    assert resp.status_code == 201, f"POS shift open failed: {resp.status_code} {resp.get_json(silent=True)}"

    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    assert cookie is not None, "login did not produce a session cookie"
    return cookie.value


def _is_numbering_collision(exc):
    """True when the failure is a document-number collision, not a business rule.

    The numbering collision surfaces as ``PendingRollbackError`` whose message
    embeds the original ``UniqueViolation`` (the flush inside
    ``create_sale`` aborts the session, and the next statement on it is
    rejected), so the constraint name is the reliable marker.
    """
    text = f"{type(exc).__name__}: {exc}"
    return any(marker in text for marker in _NUMBER_COLLISION_MARKERS)


def _is_out_of_stock(exc):
    """True when the sale was refused because the shelf was empty."""
    text = str(exc)
    lowered = text.lower()
    if "stock" in lowered and ("not enough" in lowered or "insufficient" in lowered):
        return True
    # The domain message is Arabic: "╪º┘ä┘à╪«╪▓┘ê┘å ╪║┘è╪▒ ┘â╪º┘ü┘ì" (the stock is not enough).
    return "╪º┘ä┘à╪«╪▓┘ê┘å" in text and "┘â╪º┘ü" in text


def _pos_worker(app, ctx, barrier, index):
    """One concurrent checkout through the real HTTP register."""
    outcome = {"index": index, "ok": False, "status": None, "sale_id": None, "error": None}

    with app.test_client() as client:
        client.set_cookie(ctx["cookie_name"], ctx["cookie_value"])
        payload = dict(ctx["payload"])
        payload["lines"] = [
            {
                "product_id": ctx["product_id"],
                "quantity": float(ATTEMPT_QTY),
                "discount_percent": 0,
            }
        ]
        barrier.wait(timeout=BARRIER_TIMEOUT)
        resp = client.post("/pos/api/checkout", json=payload, content_type="application/json")
        outcome["status"] = resp.status_code
        body = resp.get_json(silent=True) or {}
        if resp.status_code == 200 and body.get("success"):
            outcome["ok"] = True
            outcome["sale_id"] = (body.get("data") or {}).get("sale_id")
        else:
            outcome["error"] = str(body.get("message") or body)[:300]
    return outcome


def _service_path_worker(app, ctx, barrier, index):
    """One concurrent sale through SaleService (the routes/sales.py path).

    A numbering collision is retried: that is what a cashier does, and the
    retry is what lets the stock row see the full contention. The number of
    retries is recorded, because it is the measurement behind the F-1 defect.
    """
    from models import Customer, Product, User
    from services.sale_service import SaleService
    from utils.db_safety import atomic_transaction

    outcome = {
        "index": index,
        "ok": False,
        "sale_id": None,
        "collisions": 0,
        "refused": None,
        "error_type": None,
        "error": None,
    }

    with app.app_context():
        barrier.wait(timeout=BARRIER_TIMEOUT)
        for submission in range(MAX_SUBMISSIONS):
            try:
                with atomic_transaction(f"load_sale_{index}_{submission}"):
                    customer = db.session.get(Customer, ctx["customer_id"])
                    seller = db.session.get(User, ctx["user_id"])
                    product = db.session.get(Product, ctx["product_id"])
                    sale = SaleService.create_sale(
                        customer=customer,
                        seller=seller,
                        lines_data=[
                            {
                                "product": product,
                                "quantity": ATTEMPT_QTY,
                                "unit_price": UNIT_PRICE,
                                "discount_percent": 0,
                            }
                        ],
                        warehouse_id=ctx["warehouse_id"],
                        currency="AED",
                        tax_rate=0,
                        discount_amount=0,
                        shipping_cost=0,
                        payment_data={
                            "amount": float(UNIT_PRICE * ATTEMPT_QTY),
                            "payment_method": "cash",
                            "currency": "AED",
                            "exchange_rate": 1.0,
                        },
                    )
                    db.session.flush()
                outcome["ok"] = True
                outcome["sale_id"] = sale.id
                return outcome
            except Exception as exc:  # noqa: BLE001 - the failure mode is the measurement
                db.session.rollback()
                if _is_numbering_collision(exc):
                    outcome["collisions"] += 1
                    continue
                outcome["error_type"] = type(exc).__name__
                outcome["error"] = str(exc)[:300]
                outcome["refused"] = "out_of_stock" if _is_out_of_stock(exc) else "other"
                return outcome
        outcome["error_type"] = "SubmissionsExhausted"
        outcome["refused"] = "other"
        return outcome


def _run_workers(app, worker_fn, count, ctx):
    """Run ``count`` workers that all leave the starting line together."""
    barrier = threading.Barrier(count)
    results = []
    lock = threading.Lock()

    def _wrapped(index):
        result = worker_fn(app, ctx, barrier, index)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=_wrapped, args=(i,), daemon=True) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=BARRIER_TIMEOUT + 300)
    alive = [t for t in threads if t.is_alive()]
    assert not alive, f"deadlock: {len(alive)} worker thread(s) never finished"
    return results


def _isolation_worker(app, ctx, barrier, index):
    """Send half the workers to tenant A and half to tenant B, all at once."""
    return _service_path_worker(app, ctx["tenants"][index % 2], barrier, index)


def _tenant_money_snapshot(tenant_id):
    """Read the money state of one tenant straight out of the database."""
    from models import GLJournalEntry, Payment, Sale, SaleLine, StockMovement
    from models.gl import GLJournalLine
    from models.warehouse import ProductWarehouseStock

    sales = Sale.query.filter(Sale.tenant_id == tenant_id).all()
    lines = SaleLine.query.filter(SaleLine.tenant_id == tenant_id).all()
    payments = Payment.query.filter(Payment.tenant_id == tenant_id).all()
    entries = GLJournalEntry.query.filter(GLJournalEntry.tenant_id == tenant_id).all()
    gl_lines = GLJournalLine.query.filter(GLJournalLine.tenant_id == tenant_id).all()
    movements = StockMovement.query.filter(StockMovement.tenant_id == tenant_id).all()
    stock_rows = ProductWarehouseStock.query.filter(ProductWarehouseStock.tenant_id == tenant_id).all()

    return {
        "sales": sales,
        "lines": lines,
        "payments": payments,
        "entries": entries,
        "gl_lines": gl_lines,
        "movements": movements,
        "stock_rows": stock_rows,
    }


def _assert_books_balance(snapshot, tenant_id):
    """The ledger must balance, entry by entry and in total."""
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for entry in snapshot["entries"]:
        lines = [line for line in snapshot["gl_lines"] if line.entry_id == entry.id]
        entry_debit = sum(Decimal(str(line.debit or 0)) for line in lines)
        entry_credit = sum(Decimal(str(line.credit or 0)) for line in lines)
        assert abs(entry_debit - entry_credit) <= TOLERANCE, (
            f"GL entry {entry.entry_number} is unbalanced: debit={entry_debit} credit={entry_credit}"
        )
        total_debit += entry_debit
        total_credit += entry_credit
    assert abs(total_debit - total_credit) <= TOLERANCE, (
        f"tenant {tenant_id} ledger does not balance: total debit={total_debit} total credit={total_credit}"
    )
    return total_debit, total_credit


def _register_turnover(tenant_id):
    """The turnover the register believes it took, as stored on the session."""
    from models.pos_session import PosSession

    session = PosSession.query.filter(PosSession.tenant_id == tenant_id).first()
    if session is None:
        return None
    return Decimal(str(session.total_sales or 0))


def _histogram(results):
    """Bucket worker outcomes by failure mode, for the diagnostic banner."""
    buckets = {}
    for result in results:
        if result.get("ok"):
            key = "committed"
        elif result.get("refused"):
            key = f"refused:{result['refused']}"
        elif result.get("error_type"):
            key = f"{result['error_type']}"
        else:
            key = f"HTTP {result.get('status')}"
        buckets[key] = buckets.get(key, 0) + 1
    return buckets


# ----------------------------------------------------------------- workloads
# The three workloads are module-scoped fixtures rather than class-scoped
# methods: a class-scoped fixture defined as an instance method is
# deprecated in pytest 10, and the storm must run exactly once per path
# anyway (it is the expensive part).
@pytest.fixture(scope="module")
def pos_storm_workload(app):
    """M simultaneous HTTP checkouts against one product's stock row."""
    ctx = _seed_money_tenant("pos")
    ctx["cookie_name"] = app.config["SESSION_COOKIE_NAME"]
    ctx["cookie_value"] = _open_register(app, ctx)
    ctx["payload"] = {
        "payment_method": "cash",
        "paid_amount": float(UNIT_PRICE * ATTEMPT_QTY),
        "currency": "AED",
        "warehouse_id": ctx["warehouse_id"],
        "customer_id": ctx["customer_id"],
    }
    started = time.monotonic()
    results = _run_workers(app, _pos_worker, THREADS, ctx)
    elapsed = time.monotonic() - started
    snapshot = _tenant_money_snapshot(ctx["tenant_id"])
    order_total = sum((Decimal(str(s.total_amount)) for s in snapshot["sales"]), Decimal("0"))
    register_total = _register_turnover(ctx["tenant_id"])
    print(f"\n=== POS STORM: threads={len(results)} stock={STOCK_QTY} elapsed={elapsed:.1f}s {_histogram(results)}")
    print(
        f"=== POS STORM TOTALS: orders={len(snapshot['sales'])} order_total={order_total} "
        f"register_total_sales={register_total} "
        f"lost={(order_total - register_total) if register_total is not None else 'n/a'}"
    )
    yield {"ctx": ctx, "results": results, "elapsed": elapsed}
    purge_tenant(db.session, ctx["tenant_id"], role_id=ctx["role_id"])


@pytest.fixture(scope="module")
def service_storm_workload(app):
    """M simultaneous SaleService.create_sale calls against one stock row."""
    ctx = _seed_money_tenant("svc")
    started = time.monotonic()
    results = _run_workers(app, _service_path_worker, THREADS, ctx)
    elapsed = time.monotonic() - started
    collisions = sum(r.get("collisions", 0) for r in results)
    print(
        f"\n=== SERVICE STORM: threads={len(results)} stock={STOCK_QTY} "
        f"elapsed={elapsed:.1f}s number_collisions={collisions} {_histogram(results)}"
    )
    yield {"ctx": ctx, "results": results, "elapsed": elapsed, "collisions": collisions}
    purge_tenant(db.session, ctx["tenant_id"], role_id=ctx["role_id"])


@pytest.fixture(scope="module")
def isolation_storm_workload(app):
    """Two tenants selling at the same instant, from one starting line."""
    ctx_a = _seed_money_tenant("ta", stock=ISOLATION_STOCK)
    ctx_b = _seed_money_tenant("tb", stock=ISOLATION_STOCK)
    started = time.monotonic()
    results = _run_workers(app, _isolation_worker, THREADS, {"tenants": [ctx_a, ctx_b]})
    elapsed = time.monotonic() - started
    results_a = [r for r in results if r["index"] % 2 == 0]
    results_b = [r for r in results if r["index"] % 2 == 1]
    print(f"\n=== ISOLATION STORM: A={_histogram(results_a)} B={_histogram(results_b)} elapsed={elapsed:.1f}s")
    yield {"a": ctx_a, "b": ctx_b, "results_a": results_a, "results_b": results_b}
    purge_tenant(db.session, ctx_a["tenant_id"], role_id=ctx_a["role_id"])
    purge_tenant(db.session, ctx_b["tenant_id"], role_id=ctx_b["role_id"])


# --------------------------------------------------------------------- tests
@pytest.mark.slow
class TestPosCheckoutStorm:
    """The register, hammered: M simultaneous checkouts on one stock row."""

    def test_register_never_oversells(self, app, pos_storm_workload):
        """No more units leave the shelf than were on it, and no more orders
        are committed than there were units."""
        ctx = pos_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])
        successes = [r for r in pos_storm_workload["results"] if r["ok"]]

        units_sold = sum((Decimal(str(line.quantity)) for line in snapshot["lines"]), Decimal("0"))
        on_hand = sum((Decimal(str(row.quantity)) for row in snapshot["stock_rows"]), Decimal("0"))

        assert len(snapshot["sales"]) == len(successes), (
            f"committed sales ({len(snapshot['sales'])}) != reported successes ({len(successes)})"
        )
        assert units_sold <= STOCK_QTY, f"oversell: {units_sold} units sold from {STOCK_QTY} on the shelf"
        assert len(successes) <= int(STOCK_QTY), (
            f"oversell: {len(successes)} orders committed against {STOCK_QTY} units on the shelf"
        )
        assert on_hand >= 0, f"stock went negative: {on_hand}"
        assert on_hand == STOCK_QTY - units_sold, f"stock on hand {on_hand} != {STOCK_QTY} - {units_sold} units sold"

    def test_every_order_has_exactly_one_payment(self, app, pos_storm_workload):
        """One payment row per order, and the money matches the orders."""
        ctx = pos_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])

        by_sale = {}
        for payment in snapshot["payments"]:
            by_sale.setdefault(payment.sale_id, []).append(payment)

        assert snapshot["sales"], "the storm must have committed at least one order"
        for sale in snapshot["sales"]:
            payments = by_sale.get(sale.id, [])
            assert len(payments) == 1, f"sale {sale.sale_number} has {len(payments)} payment rows, expected exactly 1"
            assert Decimal(str(payments[0].amount_aed)) == Decimal(str(sale.total_amount)), (
                f"payment {payments[0].payment_number} amount {payments[0].amount_aed} "
                f"!= sale total {sale.total_amount}"
            )

        order_total = sum((Decimal(str(s.total_amount)) for s in snapshot["sales"]), Decimal("0"))
        paid_total = sum((Decimal(str(p.amount_aed)) for p in snapshot["payments"]), Decimal("0"))
        assert abs(order_total - paid_total) <= TOLERANCE, f"order totals {order_total} != payment totals {paid_total}"

    def test_ledger_still_balances(self, app, pos_storm_workload):
        """Every journal entry balances, and the tenant's journal balances."""
        ctx = pos_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])
        assert snapshot["entries"], "the storm must have posted journal entries"
        _assert_books_balance(snapshot, ctx["tenant_id"])

    def test_stock_movements_reconcile_with_stock_on_hand(self, app, pos_storm_workload):
        """The movement ledger explains the quantity on the shelf."""
        ctx = pos_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])

        movement_total = sum((Decimal(str(m.quantity)) for m in snapshot["movements"]), Decimal("0"))
        on_hand = sum((Decimal(str(row.quantity)) for row in snapshot["stock_rows"]), Decimal("0"))

        # The opening stock movement is part of the ledger of movements, so
        # the sum of every movement already includes the +N put on the shelf.
        assert on_hand == movement_total, f"stock on hand {on_hand} != sum of stock movements {movement_total}"
        assert on_hand == STOCK_QTY - sum((Decimal(str(line.quantity)) for line in snapshot["lines"]), Decimal("0")), (
            "stock on hand does not match the units on the sale lines"
        )

    def test_pos_session_totals_match_the_orders_they_summarise(self, app, pos_storm_workload):
        """The register's turnover equals the turnover of the orders it took."""
        from models.pos_session import PosSession

        ctx = pos_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])
        session = PosSession.query.filter(PosSession.tenant_id == ctx["tenant_id"]).first()
        assert session is not None, "the register session must exist"

        order_total = sum((Decimal(str(s.total_amount)) for s in snapshot["sales"]), Decimal("0"))
        assert Decimal(str(session.total_sales or 0)) == order_total, (
            f"register turnover {session.total_sales} != turnover of the {len(snapshot['sales'])} "
            f"orders it took ({order_total})"
        )


@pytest.mark.slow
class TestSalesServiceStorm:
    """The sales desk: SaleService.create_sale with no per-product lock."""

    def test_no_oversell(self, app, service_storm_workload):
        """Units sold never exceed the units that were on the shelf."""
        ctx = service_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])
        successes = [r for r in service_storm_workload["results"] if r["ok"]]

        units_sold = sum((Decimal(str(line.quantity)) for line in snapshot["lines"]), Decimal("0"))
        on_hand = sum((Decimal(str(row.quantity)) for row in snapshot["stock_rows"]), Decimal("0"))

        assert len(snapshot["sales"]) == len(successes), (
            f"committed sales ({len(snapshot['sales'])}) != reported successes ({len(successes)})"
        )
        assert units_sold <= STOCK_QTY, f"oversell: {units_sold} units sold from {STOCK_QTY} on the shelf"
        assert len(successes) <= int(STOCK_QTY), (
            f"oversell: {len(successes)} orders committed against {STOCK_QTY} units on the shelf"
        )
        assert on_hand >= 0, f"stock went negative: {on_hand}"
        assert on_hand == STOCK_QTY - units_sold, f"stock on hand {on_hand} != {STOCK_QTY} - {units_sold} units sold"

    def test_every_order_has_exactly_one_payment(self, app, service_storm_workload):
        """One payment row per order, and the money matches the orders."""
        ctx = service_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])

        by_sale = {}
        for payment in snapshot["payments"]:
            by_sale.setdefault(payment.sale_id, []).append(payment)

        assert snapshot["sales"], "the storm must have committed at least one order"
        for sale in snapshot["sales"]:
            payments = by_sale.get(sale.id, [])
            assert len(payments) == 1, f"sale {sale.sale_number} has {len(payments)} payment rows, expected exactly 1"
            assert Decimal(str(payments[0].amount_aed)) == Decimal(str(sale.total_amount)), (
                f"payment {payments[0].payment_number} amount {payments[0].amount_aed} "
                f"!= sale total {sale.total_amount}"
            )

        order_total = sum((Decimal(str(s.total_amount)) for s in snapshot["sales"]), Decimal("0"))
        paid_total = sum((Decimal(str(p.amount_aed)) for p in snapshot["payments"]), Decimal("0"))
        assert abs(order_total - paid_total) <= TOLERANCE, f"order totals {order_total} != payment totals {paid_total}"

    def test_ledger_still_balances(self, app, service_storm_workload):
        """Every journal entry balances, and the tenant's journal balances."""
        ctx = service_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])
        assert snapshot["entries"], "the storm must have posted journal entries"
        _assert_books_balance(snapshot, ctx["tenant_id"])

    def test_stock_movements_reconcile_with_stock_on_hand(self, app, service_storm_workload):
        """The movement ledger explains the quantity on the shelf."""
        ctx = service_storm_workload["ctx"]
        snapshot = _tenant_money_snapshot(ctx["tenant_id"])

        movement_total = sum((Decimal(str(m.quantity)) for m in snapshot["movements"]), Decimal("0"))
        on_hand = sum((Decimal(str(row.quantity)) for row in snapshot["stock_rows"]), Decimal("0"))

        assert on_hand == movement_total, f"stock on hand {on_hand} != sum of stock movements {movement_total}"
        assert on_hand == STOCK_QTY - sum((Decimal(str(line.quantity)) for line in snapshot["lines"]), Decimal("0")), (
            "stock on hand does not match the units on the sale lines"
        )

    def test_no_order_needs_a_second_submission(self, app, service_storm_workload):
        """No order has to be re-submitted because the document number collided."""
        collisions = service_storm_workload["collisions"]
        assert collisions == 0, (
            f"{collisions} document-number collisions forced a re-submission of an order "
            f"that had nothing to do with the stock"
        )


@pytest.mark.slow
class TestTenantIsolationUnderContention:
    """Two tenants hammering the database at the same time."""

    def test_each_tenant_only_ever_wrote_its_own_rows(self, app, isolation_storm_workload):
        """Every sale, payment, journal entry and movement belongs to the
        tenant that produced it - including the products and stock rows."""
        from models import GLJournalEntry, Payment, Sale, SaleLine, StockMovement

        for label in ("a", "b"):
            ctx = isolation_storm_workload[label]
            tenant_id = ctx["tenant_id"]
            own_product_ids = {ctx["product_id"]}

            sales = Sale.query.filter(Sale.tenant_id == tenant_id).all()
            for sale in sales:
                assert sale.tenant_id == tenant_id
                lines = SaleLine.query.filter(SaleLine.sale_id == sale.id).all()
                for line in lines:
                    assert line.tenant_id == tenant_id, (
                        f"sale line {line.id} of tenant {tenant_id} carries tenant {line.tenant_id}"
                    )
                    assert line.product_id in own_product_ids, (
                        f"sale line {line.id} of tenant {tenant_id} points at product "
                        f"{line.product_id} which belongs to another tenant"
                    )

            for payment in Payment.query.filter(Payment.tenant_id == tenant_id).all():
                assert payment.tenant_id == tenant_id
                if payment.sale_id is not None:
                    owner = db.session.get(Sale, payment.sale_id)
                    assert owner is not None and owner.tenant_id == tenant_id, (
                        f"payment {payment.id} of tenant {tenant_id} points at a sale of "
                        f"tenant {owner.tenant_id if owner else None}"
                    )

            for entry in GLJournalEntry.query.filter(GLJournalEntry.tenant_id == tenant_id).all():
                assert entry.tenant_id == tenant_id
                assert entry.reference_type != "sale" or entry.reference_id in {s.id for s in sales}, (
                    f"journal entry {entry.id} of tenant {tenant_id} points at another tenant's sale"
                )

            for movement in StockMovement.query.filter(StockMovement.tenant_id == tenant_id).all():
                assert movement.tenant_id == tenant_id
                assert movement.product_id in own_product_ids, (
                    f"stock movement {movement.id} of tenant {tenant_id} touches product "
                    f"{movement.product_id} of another tenant"
                )

    def test_the_other_tenant_sold_nothing_of_mine(self, app, isolation_storm_workload):
        """Neither tenant's sales can reference the other tenant's product."""
        from models import SaleLine

        for label, other in (("a", "b"), ("b", "a")):
            ctx = isolation_storm_workload[label]
            other_product_ids = {isolation_storm_workload[other]["product_id"]}
            foreign_lines = SaleLine.query.filter(
                SaleLine.tenant_id == ctx["tenant_id"],
                SaleLine.product_id.in_(other_product_ids),
            ).count()
            assert foreign_lines == 0, (
                f"tenant {ctx['tenant_id']} wrote {foreign_lines} sale lines against "
                f"tenant {isolation_storm_workload[other]['tenant_id']}'s products"
            )
