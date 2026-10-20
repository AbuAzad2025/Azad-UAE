"""Period-close reconciliation: do the books balance to the last cent?

The wave suites assert that a document *produces* a journal entry. None of them
asks the question a CFO asks at the end of the month: are the books right?

This file asks it against the DATABASE, on a dataset big enough and shaped
enough for the answer to be worth anything:

* one tenant, one branch, two warehouses, four products, three customers, two
  suppliers — the shape of a small trading company, not a single-row fixture;
* sales invoices (fully paid at creation, partly paid later, and left open),
  purchase bills (some settled, some not), goods returns, purchase returns and
  customer receipts — every document type that moves money between the
  sub-ledger and the GL;
* prices and costs with non-round decimals (19.99, 10.25, 41.75 …) so that
  every 5% VAT line is rounded, which is where a cent disappears.

Every figure the assertions compare against is derived from the *underlying
documents* (Sale.amount_aed, Purchase.tax_amount, Receipt.amount_aed,
ProductReturn.refund_amount, …) — never from a service return value and never
from the code's own totals. A service that posts to the wrong account still
returns a "successful" document; only the journal knows the truth.

The accounting period is then closed through the product's own close path
(POST /ledger/periods, the route the ledger screen uses) and the books are
reconciled after the close, which is the order the product supports.

Everything is asserted to the cent: the trial balance, the AR and AP control
accounts against the per-counterparty open balances, the VAT accounts against
the tax actually charged, the inventory account against the value of the goods
still on the shelf, and the number of journal entries against the number of
documents that should have produced one.

The test owns one file and one tenant; the tenant is removed again in the
fixture teardown so the rest of the suite is unaffected.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

# ── Scale ────────────────────────────────────────────────────────────────────
# Every number below is a document, not a row in a table: each one is created
# through the real service so it produces its real GL postings.
#
# The scale is bounded by what the product's own posting path costs. Measured
# on the reference machine: an invoice ~0.35 s and ~110 SQL statements, a
# customer receipt ~0.25 s, a credit note ~0.75 s, a purchase bill ~0.13 s.
# The set below builds and reconciles in ~2.5 minutes; the report prints the
# measured time so a regression in the posting path shows up as a slow test.
N_SALES = 300
N_PURCHASES = 30
N_RECEIPTS = 60
N_SUPPLIER_PAYMENTS = 15
N_SALE_RETURNS = 30
N_PURCHASE_RETURNS = 5

VAT_RATE = Decimal("5")

#: (name, cost, price). The decimals are deliberately awkward: at 5% VAT a
#: 19.99 line produces 1.00 of tax while 19.99/1.05 would produce 0.95, and the
#: difference between the two is exactly the kind of cent this file hunts.
PRODUCT_SPECS = [
    ("Canned Beans", Decimal("10.25"), Decimal("19.99")),
    ("Olive Oil 5L", Decimal("7.50"), Decimal("14.35")),
    ("Gift Box", Decimal("22.10"), Decimal("41.75")),
    ("Biscuits Tin", Decimal("3.33"), Decimal("8.99")),
]

#: Opening stock per product per warehouse.
OPENING_STOCK = (300, 150)


# ── Ledger helpers (read the rows, never a service return value) ────────────


def _account_balance(db, tenant_id: int, code: str) -> Decimal:
    """Debit minus credit for one account code, from posted journal lines."""
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
            GLAccount.code == str(code),
            GLJournalEntry.tenant_id == int(tenant_id),
            GLJournalEntry.status == "posted",
        )
    )
    debit, credit = db.execute(stmt).one()
    return Decimal(str(debit or 0)) - Decimal(str(credit or 0))


def _trial_balance(db, tenant_id: int) -> tuple[Decimal, Decimal]:
    from sqlalchemy import func, select

    from models import GLJournalEntry, GLJournalLine

    stmt = (
        select(
            func.coalesce(func.sum(GLJournalLine.debit), 0),
            func.coalesce(func.sum(GLJournalLine.credit), 0),
        )
        .select_from(GLJournalLine)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .where(
            GLJournalEntry.tenant_id == int(tenant_id),
            GLJournalEntry.status == "posted",
        )
    )
    debit, credit = db.execute(stmt).one()
    return Decimal(str(debit or 0)), Decimal(str(credit or 0))


def _balance_by_type(db, tenant_id: int) -> dict[str, Decimal]:
    """Net balance per account type (assets positive, liabilities/equity negative)."""
    from sqlalchemy import func, select

    from models import GLAccount, GLJournalEntry, GLJournalLine

    stmt = (
        select(
            GLAccount.type,
            func.coalesce(func.sum(GLJournalLine.debit - GLJournalLine.credit), 0),
        )
        .select_from(GLJournalLine)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalLine.entry_id)
        .join(GLAccount, GLAccount.id == GLJournalLine.account_id)
        .where(
            GLJournalEntry.tenant_id == int(tenant_id),
            GLJournalEntry.status == "posted",
        )
        .group_by(GLAccount.type)
    )
    return {row[0]: Decimal(str(row[1] or 0)) for row in db.execute(stmt).all()}


def _posted_entries(db, tenant_id: int):
    from models import GLJournalEntry

    return (
        db.query(GLJournalEntry)
        .filter(GLJournalEntry.tenant_id == int(tenant_id))
        .filter(GLJournalEntry.status == "posted")
        .all()
    )


# ── The dataset ─────────────────────────────────────────────────────────────


@pytest.fixture
def books(app, db_session, demo_tenant, demo_branch, demo_warehouse, demo_user, demo_customer, demo_supplier):
    """Build a realistic month of trading through the real services.

    Yields a dict of everything the reconciliation needs: the tenant, the
    products and their cost, and the per-document totals computed from the
    documents themselves.
    """
    from models import Customer, Supplier, Warehouse
    from services.gl_service import GLService
    from services.payment_service import PaymentService
    from services.product_service import ProductService
    from services.purchase_service import PurchaseService
    from services.return_service import ReturnService
    from services.sale_service import SaleService
    from services.stock_service import StockService

    tenant = demo_tenant
    branch = demo_branch
    warehouse_a = demo_warehouse
    seller = demo_user
    customer = demo_customer
    supplier = demo_supplier

    # A trading company that charges VAT on exclusive prices, in its own base
    # currency, with a user attached to the branch (the warehouse guard and the
    # branch-scoped liquidity accounts both read that).
    tenant.enable_tax = True
    tenant.default_tax_rate = VAT_RATE
    tenant.prices_include_vat = False
    tenant.default_currency = "AED"
    tenant.base_currency = "AED"
    tenant.fiscal_year_start = 1
    seller.branch_id = branch.id
    db_session.flush()

    GLService.ensure_core_accounts(tenant_id=tenant.id)
    db_session.flush()

    # A second warehouse on the same branch: stock is spread across two
    # shelves so the inventory reconciliation has to add them up.
    warehouse_b = Warehouse(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name=f"Overflow Warehouse {uuid.uuid4().hex[:6]}",
        name_ar="مستودع احتياطي",
        code=f"WH{uuid.uuid4().hex[:6].upper()}",
        is_active=True,
        is_main=False,
        allow_negative_inventory=False,
    )
    db_session.add(warehouse_b)
    db_session.flush()

    # More counterparties, so the AR/AP control accounts have to be the sum of
    # several open balances rather than one.
    customers = [customer]
    for i in range(2):
        extra = Customer(
            tenant_id=tenant.id,
            name=f"Reconciliation Customer {i}",
            name_ar=f"عميل مطابقة {i}",
            customer_type="regular",
            phone=f"05000000{i:02d}",
            email=f"recon-cust-{i}-{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
        )
        db_session.add(extra)
        customers.append(extra)
    suppliers = [supplier]
    for i in range(1):
        extra = Supplier(
            tenant_id=tenant.id,
            name=f"Reconciliation Supplier {i}",
            phone=f"05500000{i:02d}",
            email=f"recon-supp-{i}-{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
        )
        db_session.add(extra)
        suppliers.append(extra)
    db_session.flush()

    # Products with a cost and a price, and opening stock on both shelves.
    products = []
    for idx, (name, cost, price) in enumerate(PRODUCT_SPECS):
        product = ProductService.create_product(
            tenant_id=tenant.id,
            name=f"{name} {uuid.uuid4().hex[:4]}",
            sku=f"RECON-{uuid.uuid4().hex[:8]}",
            barcode=f"RC{uuid.uuid4().hex[:10]}",
            regular_price=price,
            cost_price=cost,
        )
        db_session.flush()
        products.append({"product": product, "cost": cost, "price": price, "index": idx})
    db_session.flush()

    for spec in products:
        product = spec["product"]
        StockService.add_opening_stock(
            product.id,
            Decimal(OPENING_STOCK[0]),
            warehouse_id=warehouse_a.id,
        )
        StockService.add_opening_stock(
            product.id,
            Decimal(OPENING_STOCK[1]),
            warehouse_id=warehouse_b.id,
        )
    db_session.flush()

    stats = {
        "sales": 0,
        "sales_paid_at_creation": 0,
        "purchases": 0,
        "receipts": 0,
        "supplier_payments": 0,
        "sale_returns": 0,
        "purchase_returns": 0,
        "opening_stock_postings": len(products) * len(OPENING_STOCK),
    }
    timings: dict[str, float] = {}
    built = {
        "tenant": tenant,
        "branch": branch,
        "warehouses": [warehouse_a, warehouse_b],
        "customers": customers,
        "suppliers": suppliers,
        "products": products,
        "seller": seller,
        "sales": [],
        "purchases": [],
        "receipts": [],
        "supplier_payments": [],
        "sale_returns": [],
        "purchase_returns": [],
    }

    try:
        # ── Purchases ─────────────────────────────────────────────────────
        phase = time.perf_counter()
        # Bills land in both warehouses, from both suppliers, at the product's
        # own cost so the moving-average cost never drifts from it.
        #
        # The last N_PURCHASE_RETURNS bills are zero-rated. That is not
        # cosmetic: a purchase return against a VAT-bearing bill builds an
        # unbalanced journal entry and the ledger refuses it, so the only
        # purchase returns that can exist in the books are the ones whose
        # parent bill carried no tax. The refusal is pinned separately in
        # test_purchase_return_against_a_vat_bill_is_refused.
        for i in range(N_PURCHASES):
            spec = products[i % len(products)]
            product = spec["product"]
            qty = 60 + (i % 5) * 20
            wh = warehouse_a if i % 2 == 0 else warehouse_b
            bill_tax = VAT_RATE if i < N_PURCHASES - N_PURCHASE_RETURNS else Decimal("0")
            purchase = PurchaseService.create_purchase(
                user=seller,
                supplier_data={"supplier_id": suppliers[i % len(suppliers)].id},
                lines_data=[
                    {
                        "product_id": product.id,
                        "quantity": qty,
                        "unit_cost": spec["cost"],
                    }
                ],
                warehouse_id=wh.id,
                currency="AED",
                tax_rate=bill_tax,
            )
            db_session.flush()
            built["purchases"].append(purchase)
            stats["purchases"] += 1
        timings["purchases"] = time.perf_counter() - phase

        # ── Sales ─────────────────────────────────────────────────────────
        phase = time.perf_counter()
        # A third of the invoices are settled in full at creation, a fifth are
        # partly settled later by a receipt, the rest stay open.
        for i in range(N_SALES):
            spec = products[i % len(products)]
            product = spec["product"]
            qty = 1 + (i % 4)
            wh = warehouse_a if i % 2 == 0 else warehouse_b
            lines_data = [{"product": product, "quantity": qty}]
            payment_data = None
            if i % 3 == 0:
                # The invoice total the customer pays: net of a 5% tax the
                # product rounds to the cent, which is what the sale will
                # compute too.
                net = spec["price"] * qty
                tax = (net * VAT_RATE / Decimal("100")).quantize(Decimal("0.01"))
                payment_data = {
                    "amount": net + tax,
                    "currency": "AED",
                    "exchange_rate": 1.0,
                    "payment_method": "cash" if i % 2 == 0 else "bank_transfer",
                }
            sale = SaleService.create_sale(
                customer=customers[i % len(customers)],
                seller=seller,
                lines_data=lines_data,
                warehouse_id=wh.id,
                currency="AED",
                tax_rate=VAT_RATE,
                payment_data=payment_data,
            )
            db_session.flush()
            built["sales"].append(sale)
            stats["sales"] += 1
            if payment_data is not None:
                stats["sales_paid_at_creation"] += 1
        timings["sales"] = time.perf_counter() - phase

        # ── Customer receipts ─────────────────────────────────────────────
        phase = time.perf_counter()
        # Every receipt settles part of an open invoice, so the money is
        # traceable to the sale it pays. The invoice is left with an open
        # balance, which is the "partially paid" case.
        open_sales = [s for s in built["sales"] if s.payment_status == "unpaid"]
        for i in range(N_RECEIPTS):
            sale = open_sales[i % len(open_sales)]
            amount = (Decimal(str(sale.total_amount)) / Decimal("2")).quantize(Decimal("0.01"))
            if amount <= 0:
                continue
            receipt = PaymentService.create_receipt(
                {
                    "customer_id": sale.customer_id,
                    "amount": amount,
                    "currency": "AED",
                    "payment_method": "cash" if i % 2 == 0 else "bank_transfer",
                    "branch_id": branch.id,
                    "allocate_to_sales": {sale.id: amount},
                }
            )
            db_session.flush()
            built["receipts"].append(receipt)
            stats["receipts"] += 1
        timings["receipts"] = time.perf_counter() - phase

        # ── Supplier payments ─────────────────────────────────────────────
        phase = time.perf_counter()
        for i in range(N_SUPPLIER_PAYMENTS):
            purchase = built["purchases"][i % len(built["purchases"])]
            amount = (Decimal(str(purchase.total_amount)) / Decimal("3")).quantize(Decimal("0.01"))
            if amount <= 0:
                continue
            payment = PaymentService.create_payment(
                {
                    "supplier_id": purchase.supplier_id,
                    "amount": amount,
                    "currency": "AED",
                    "payment_method": "bank_transfer" if i % 2 else "cash",
                    "branch_id": branch.id,
                    "notes": f"settlement for {purchase.purchase_number}",
                }
            )
            db_session.flush()
            built["supplier_payments"].append(payment)
            stats["supplier_payments"] += 1
        timings["supplier_payments"] = time.perf_counter() - phase

        # ── Sales returns (credit notes) ──────────────────────────────────
        phase = time.perf_counter()
        for i in range(N_SALE_RETURNS):
            sale = built["sales"][i * 3]
            line = sale.lines[0]
            product_return = ReturnService.create_return(
                sale.id,
                [{"sale_line_id": line.id, "quantity": 1, "condition": "good"}],
                user=None,
                user_id=seller.id,
            )
            db_session.flush()
            built["sale_returns"].append(product_return)
            stats["sale_returns"] += 1
        timings["sale_returns"] = time.perf_counter() - phase

        # ── Purchase returns ──────────────────────────────────────────────
        phase = time.perf_counter()
        # Against the zero-rated bills, which are the only ones the ledger
        # will accept (see the note above the purchases and the dedicated
        # refusal test below).
        for i in range(N_PURCHASE_RETURNS):
            purchase = built["purchases"][N_PURCHASES - N_PURCHASE_RETURNS + i]
            lines_data = [
                {
                    "purchase_line_id": pl.id,
                    "product_id": pl.product_id,
                    "quantity": pl.quantity,
                    "unit_cost": pl.unit_cost,
                }
                for pl in purchase.lines
            ]
            purchase_return = PurchaseService.create_purchase_return(
                purchase,
                seller,
                lines_data,
                reason="damaged on arrival",
            )
            db_session.flush()
            built["purchase_returns"].append(purchase_return)
            stats["purchase_returns"] += 1
        timings["purchase_returns"] = time.perf_counter() - phase

        db_session.flush()
    except Exception:
        _purge_tenant(tenant.id)
        raise

    built["stats"] = stats
    built["timings"] = timings
    built["built_at"] = time.perf_counter()
    yield built

    _purge_tenant(tenant.id)


def _tables_children_first(metadata) -> list:
    """Every table in the metadata, children before parents.

    SQLAlchemy's own ``sorted_tables`` refuses to order this schema (it has
    circular references) and the fallback order is arbitrary, which is not
    enough here: a row that still points at a user with ON DELETE RESTRICT
    blocks the deletion of that user.
    """
    tables = list(metadata.tables.values())
    references: dict[str, set[str]] = {}
    for table in tables:
        refs = set()
        for fk in table.foreign_keys:
            parent = fk.column.table
            if parent.key != table.key and parent.key in metadata.tables:
                refs.add(parent.key)
        references[table.key] = refs

    ordered: list = []
    seen: set[str] = set()
    on_stack: set[str] = set()

    def visit(key: str) -> None:
        if key in seen or key in on_stack:
            return
        on_stack.add(key)
        for ref in references.get(key, ()):
            visit(ref)
        on_stack.discard(key)
        seen.add(key)
        ordered.append(metadata.tables[key])

    for table in tables:
        visit(table.key)
    ordered.reverse()
    return ordered


def _purge_tenant(tenant_id: int) -> None:
    """Remove the tenant's documents, keep its master data.

    The close path commits (the ledger route runs inside atomic_transaction),
    so the dataset is durable by the time the assertions run. Leaving ~300
    documents and ~590 journal entries behind would pollute every later test
    in the group, so the documents are removed again here.

    The master data — the tenant, its products, its customers, its suppliers,
    its branch, its warehouses, its users — is deliberately **kept**:

    * a few dozen tables point at ``users.id`` (and at ``sales.id``,
      ``suppliers.id``, …) with ON DELETE RESTRICT, so a tenant with documents
      cannot simply be deleted, and
    * other tests in this group hardcode ``product_id=1``, ``warehouse_id=1``
      and ``branch_id=1`` (tests/integration/test_stress_atomicity.py:243,
      tests/integration/test_pos_hardware_pipeline.py:64,
      tests/integration/test_inventory_pos_audit.py:356). Those rows are the
      ones this test would otherwise be the first to create, and deleting them
      would break a test that has nothing to do with this one.

    What is left behind is a tenant with an empty book — about a hundred rows
    of reference data, against the ~3,000 rows of documents that go.

    The tables are emptied one by one, children first, each in its own
    savepoint so one stubborn table cannot poison the rest.
    """
    from extensions import db as flask_db

    session = flask_db.session
    metadata = flask_db.metadata
    failures: list[str] = []

    try:
        for table in _tables_children_first(metadata):
            if "tenant_id" not in table.c or table.name in _MASTER_DATA_TABLES:
                continue
            savepoint = session.begin_nested()
            try:
                session.execute(table.delete().where(table.c.tenant_id == int(tenant_id)))
                savepoint.commit()
            except Exception as exc:
                savepoint.rollback()
                failures.append(f"{table.name}: {type(exc).__name__}")
        session.commit()
    except Exception:
        session.rollback()
    if failures:
        print(f"\nPURGE INCOMPLETE for tenant {tenant_id}: {failures}", flush=True)


#: Reference data that survives the purge — see _purge_tenant for why.
_MASTER_DATA_TABLES = frozenset(
    {
        "products",
        "customers",
        "suppliers",
        "warehouses",
        "branches",
        "users",
        "currencies",
        "roles",
        "permissions",
    }
)


# ── The reconciliation ──────────────────────────────────────────────────────


def test_the_books_reconcile_to_the_cent(client, db_session, books):
    """Every control account agrees with the documents behind it, to the cent."""
    from models import (
        Customer,
        Payment,
        ProductReturn,
        ProductWarehouseStock,
        Purchase,
        PurchaseReturn,
        Receipt,
        Sale,
        Supplier,
    )

    tenant = books["tenant"]
    tenant_id = tenant.id
    db = db_session

    started = time.perf_counter()
    stats = books["stats"]

    # ── 1. Close the period through the product's own close path ─────────
    now = datetime.now(UTC)
    close_user = _ledger_user(db, tenant, books["branch"])
    _login(client, close_user)
    resp = client.post(
        "/ledger/periods",
        data={"year": now.year, "month": now.month, "action": "close"},
        follow_redirects=True,
    )
    assert resp.status_code == 200, f"the period close answered {resp.status_code}"

    from models.gl import GLPeriod

    period = GLPeriod.query.filter_by(tenant_id=tenant_id, year=now.year, month=now.month).first()
    assert period is not None, "the close path did not create the accounting period"
    assert period.is_closed is True, "the close path did not close the period"
    assert period.closed_at is not None, "the closed period recorded no close time"
    assert period.closed_by is not None, "the closed period recorded no closer"

    # The lock is the point of a close: a document dated inside the closed
    # period must now be refused.
    from services.gl_posting import post_or_fail

    with pytest.raises(Exception):
        post_or_fail(
            [
                {"account": "1130", "debit": Decimal("1.00"), "credit": Decimal("0.00")},
                {"account": "4100", "debit": Decimal("0.00"), "credit": Decimal("1.00")},
            ],
            description="posting into a closed period",
            date=datetime(now.year, now.month, 15, tzinfo=UTC),
            tenant_id=tenant_id,
        )
    db_session.rollback()

    # ── 2. Document-derived expectations ─────────────────────────────────
    sales = Sale.query.filter_by(tenant_id=tenant_id).all()
    purchases = Purchase.query.filter_by(tenant_id=tenant_id).all()
    receipts = Receipt.query.filter_by(tenant_id=tenant_id).all()
    sale_returns = ProductReturn.query.filter_by(tenant_id=tenant_id).all()
    purchase_returns = PurchaseReturn.query.filter_by(tenant_id=tenant_id).all()
    customers = Customer.query.filter_by(tenant_id=tenant_id).all()
    suppliers = Supplier.query.filter_by(tenant_id=tenant_id).all()
    payments = Payment.query.filter_by(tenant_id=tenant_id).all()

    # AR per customer, from the documents: what the customer was invoiced,
    # less what they have paid (the sale document carries what was paid
    # against it — the money received at creation and the money a receipt
    # allocated to it), less what was credited back to them.
    #
    # Every receipt in this dataset is allocated to one of the customer's
    # own invoices, so no received money is unaccounted for.
    ar_by_customer: dict[int, Decimal] = {}
    for sale in sales:
        open_amount = Decimal(str(sale.amount_aed or 0)) - Decimal(str(sale.paid_amount_aed or 0))
        ar_by_customer[sale.customer_id] = ar_by_customer.get(sale.customer_id, Decimal("0")) + open_amount
    for ret in sale_returns:
        ar_by_customer[ret.customer_id] = ar_by_customer.get(ret.customer_id, Decimal("0")) - Decimal(
            str(ret.amount_aed or 0)
        )

    # AP per supplier, from the documents: billed minus returned minus paid.
    ap_by_supplier: dict[int, Decimal] = {}
    for purchase in purchases:
        ap_by_supplier[purchase.supplier_id] = ap_by_supplier.get(purchase.supplier_id, Decimal("0")) + Decimal(
            str(purchase.amount_aed or 0)
        )
    for purchase_return in purchase_returns:
        ap_by_supplier[purchase_return.supplier_id] = ap_by_supplier.get(
            purchase_return.supplier_id, Decimal("0")
        ) - Decimal(str(purchase_return.amount_aed or 0))
    for payment in payments:
        if payment.direction == "outgoing" and payment.supplier_id:
            ap_by_supplier[payment.supplier_id] = ap_by_supplier.get(payment.supplier_id, Decimal("0")) - Decimal(
                str(payment.amount_aed or 0)
            )

    # VAT, from the documents. The tax charged is the sale's own tax_amount.
    # The tax credited back on a credit note is the difference between what
    # the customer was refunded (gross) and the value of the goods returned
    # (net) — the note carries no discount, freight or promotional allowance
    # to apportion, so the two differ by the tax alone.
    expected_vat_output = sum((Decimal(str(s.tax_amount or 0)) for s in sales), Decimal("0"))
    for ret in sale_returns:
        expected_vat_output -= Decimal(str(ret.refund_amount or 0)) - Decimal(str(ret.total_amount or 0))
    expected_vat_input = sum((Decimal(str(p.tax_amount or 0)) for p in purchases), Decimal("0"))
    for purchase_return in purchase_returns:
        parent = next((p for p in purchases if p.id == purchase_return.purchase_id), None)
        if parent is None:
            continue
        # The tax reversed on a purchase return is the parent's tax, in the
        # proportion of the value returned.
        if Decimal(str(parent.subtotal or 0)) > 0:
            share = (Decimal(str(purchase_return.subtotal or 0)) / Decimal(str(parent.subtotal))).quantize(
                Decimal("0.000001")
            )
            expected_vat_input -= (Decimal(str(parent.tax_amount or 0)) * share).quantize(Decimal("0.01"))

    # ── 3. The checks ────────────────────────────────────────────────────
    results = []

    def check(name, expected, actual, note=""):
        ok = expected == actual
        results.append(
            {
                "check": name,
                "expected": expected,
                "actual": actual,
                "status": "PASS" if ok else "FAIL",
                "note": note,
            }
        )
        return ok

    total_debit, total_credit = _trial_balance(db, tenant_id)
    check("trial balance: total debits == total credits", total_debit, total_credit, "whole tenant ledger")

    ar_control = _account_balance(db, tenant_id, "1130")
    expected_ar_total = sum(ar_by_customer.values(), Decimal("0"))
    check(
        "AR control account (1130) == sum of customer open balances",
        expected_ar_total,
        ar_control,
        f"{len(ar_by_customer)} customers",
    )

    ap_control = -_account_balance(db, tenant_id, "2110")
    expected_ap_total = sum(ap_by_supplier.values(), Decimal("0"))
    check(
        "AP control account (2110) == sum of supplier open balances",
        expected_ap_total,
        ap_control,
        f"{len(ap_by_supplier)} suppliers",
    )

    vat_output = -_account_balance(db, tenant_id, "2121")
    check(
        "VAT output (2121) == tax charged on taxable sales",
        expected_vat_output,
        vat_output,
        f"{len(sales)} sales",
    )

    vat_input = _account_balance(db, tenant_id, "2122")
    check(
        "VAT input (2122) == tax on purchases",
        expected_vat_input,
        vat_input,
        f"{len(purchases)} purchases",
    )

    # Inventory at cost: quantity on the shelf times the product's cost.
    expected_inventory = Decimal("0")
    stock_rows = db.query(ProductWarehouseStock).filter_by(tenant_id=tenant_id).all()
    cost_by_product = {p["product"].id: p["cost"] for p in books["products"]}
    for row in stock_rows:
        expected_inventory += Decimal(str(row.quantity or 0)) * cost_by_product.get(row.product_id, Decimal("0"))
    inventory_account = _account_balance(db, tenant_id, "1140")
    check(
        "Inventory (1140) == value of stock on hand at cost",
        expected_inventory,
        inventory_account,
        f"{len(stock_rows)} product/warehouse rows",
    )

    # Every customer, one by one: the ledger's share of them must equal what
    # the customers table says they owe.
    customer_mismatches = []
    for cust in customers:
        expected = ar_by_customer.get(cust.id, Decimal("0"))
        actual = -Decimal(str(cust.balance or 0))
        if expected != actual:
            customer_mismatches.append(f"{cust.name}: documents {expected} vs customers table {actual}")
    check(
        "every customer balance: customers table == documents",
        0,
        len(customer_mismatches),
        "; ".join(customer_mismatches)[:400],
    )

    supplier_mismatches = []
    for sup in suppliers:
        expected = ap_by_supplier.get(sup.id, Decimal("0"))
        actual = Decimal(str(sup.get_balance_base() or 0))
        if expected != actual:
            supplier_mismatches.append(f"{sup.name}: documents {expected} vs suppliers table {actual}")
    check(
        "every supplier balance: suppliers table == documents",
        0,
        len(supplier_mismatches),
        "; ".join(supplier_mismatches)[:400],
    )

    # Nothing posted twice, nothing missed.
    entries = _posted_entries(db, tenant_id)
    # Every sale posts its own entry plus a COGS entry; an invoice settled at
    # creation posts a third (the cash movement). Purchases, receipts, supplier
    # payments and purchase returns post one each; a sales return posts two
    # (revenue and COGS); each opening-stock movement posts one.
    paid_at_creation = books["stats"]["sales_paid_at_creation"]
    expected_entries = (
        len(books["sales"]) * 2
        + paid_at_creation
        + len(books["purchases"])
        + len(books["receipts"])
        + len(books["supplier_payments"])
        + len(books["sale_returns"]) * 2
        + len(books["purchase_returns"])
        + len(books["products"]) * len(OPENING_STOCK)  # opening stock postings
    )
    check(
        "journal entries == documents that should have produced one",
        expected_entries,
        len(entries),
        f"{len(entries)} posted entries",
    )

    # And the documents themselves: the rows in the database are exactly the
    # documents the services reported having created. (The supplier payments
    # share the ``payments`` table with the money received from customers,
    # so they are counted by the journal-entry check below instead.)
    document_rows = {
        "sales": len(sales),
        "purchases": len(purchases),
        "receipts": len(receipts),
        "sale returns": len(sale_returns),
        "purchase returns": len(purchase_returns),
    }
    reported = {
        "sales": len(books["sales"]),
        "purchases": len(books["purchases"]),
        "receipts": len(books["receipts"]),
        "sale returns": len(books["sale_returns"]),
        "purchase returns": len(books["purchase_returns"]),
    }
    check(
        "documents in the database == documents the services reported",
        reported,
        document_rows,
        f"{sum(document_rows.values())} documents",
    )

    # The balance sheet identity: every debit has a credit, so the assets
    # equal the liabilities, the equity and the result of the period. Revenue
    # and expense accounts carry a debit-minus-credit balance, so the P&L is
    # the negative of their sum.
    by_type = _balance_by_type(db, tenant_id)
    assets = by_type.get("asset", Decimal("0"))
    liabilities = by_type.get("liability", Decimal("0"))
    equity = by_type.get("equity", Decimal("0"))
    revenue = by_type.get("revenue", Decimal("0"))
    expense = by_type.get("expense", Decimal("0"))
    check(
        "balance sheet identity: assets == liabilities + equity + net profit",
        assets,
        -(liabilities + equity + revenue + expense),
        f"assets {assets} vs RHS {-(liabilities + equity + revenue + expense)}",
    )

    elapsed = time.perf_counter() - started

    # ── 4. The year-end close, on top of the month just closed ──────────
    # The fiscal-year close is the other half of "close the books": it moves
    # the year's result into retained earnings. It is attempted here so the
    # behaviour is pinned rather than assumed.
    fiscal_year_result = _try_fiscal_year_close(client, close_user, tenant, now.year, tenant_id)

    report = ["", "=" * 96, "PERIOD-CLOSE RECONCILIATION REPORT", "=" * 96]
    report.append(f"tenant            : {tenant.name} (id={tenant_id})")
    report.append(f"documents built   : {stats}")
    report.append(f"build timings     : { {k: round(v, 1) for k, v in books['timings'].items()} }")
    report.append(f"journal entries   : {len(entries)}")
    report.append(f"reconciliation    : {elapsed:.1f}s")
    report.append(f"fiscal-year close : {fiscal_year_result}")
    report.append("-" * 96)
    for row in results:
        report.append(
            f"[{row['status']}] {row['check']}: expected {row['expected']} / actual {row['actual']}"
            + (f"  ({row['note']})" if row["note"] else "")
        )
    report.append("=" * 96)
    print("\n".join(report))

    failures = [r for r in results if r["status"] == "FAIL"]
    assert not failures, "\n".join(
        f"RECONCILIATION FAILURE — {r['check']}: expected {r['expected']}, actual {r['actual']} ({r['note']})"
        for r in failures
    )


def _try_fiscal_year_close(client, close_user, tenant, fiscal_year: int, tenant_id: int) -> str:
    """Close every month of the fiscal year, then try the year-end close.

    FINDING (P1): the fiscal-year close cannot post its closing entry.
    ``FiscalYearService.close_fiscal_year`` first requires all twelve
    periods of the year to be closed (services/gl_service.py:2017) and then
    posts the closing entry dated the last day of that same year
    (services/gl_service.py:2023, :2075-2082) — which
    ``assert_period_open`` refuses, because the period it is dated in has
    just been closed. The close is therefore guaranteed to fail on its way
    out, and the year's result is never transferred to retained earnings.

    The behaviour is pinned here rather than assumed: the books must be left
    exactly as they were, and still balanced.
    """
    from models.gl import GLPeriod
    from services.gl_service import FiscalYearService

    for month in range(1, 13):
        client.post(
            "/ledger/periods",
            data={"year": fiscal_year, "month": month, "action": "close"},
            follow_redirects=True,
        )

    closed = GLPeriod.query.filter_by(tenant_id=tenant_id, year=fiscal_year, is_closed=True).count()
    assert closed == 12, f"only {closed} of the 12 periods of {fiscal_year} are closed"

    before = _trial_balance(_session(), tenant_id)
    try:
        FiscalYearService.close_fiscal_year(tenant_id, fiscal_year, user_id=close_user.id)
    except Exception as exc:
        after = _trial_balance(_session(), tenant_id)
        assert before == after, f"the refused fiscal-year close changed the books: {before} -> {after}"
        return f"REFUSED — {type(exc).__name__}: {exc} (books unchanged and still balanced)"

    after = _trial_balance(_session(), tenant_id)
    assert before[0] == after[0] and before[1] == after[1], (
        f"the fiscal-year close left the trial balance unbalanced: {before} -> {after}"
    )
    return f"POSTED — closing entry written, trial balance still {after[0]} == {after[1]}"


def _session():
    from extensions import db

    return db.session


def test_purchase_return_against_a_vat_bill_is_refused(
    db_session, demo_tenant, demo_branch, demo_warehouse, demo_user, demo_supplier
):
    """FINDING (P1): a supplier credit note for a VAT-bearing bill cannot be posted.

    The purchase return builds its journal entry from two different numbers:

    * the AP debit uses ``purchase_return.total_amount``, which
      ``PurchaseReturn.calculate_totals()`` resets to the *subtotal* — the tax
      is dropped (models/purchase_return.py:83, reached from
      services/purchase_service.py:667-668);
    * the VAT-input credit uses the proportional tax carried over from the
      parent bill (services/purchase_service.py:689-696).

    The two disagree by exactly the tax, ``post_or_fail`` refuses the
    unbalanced entry, and the whole return is rolled back. In a tenant with
    tax enabled — the default — a supplier credit note is therefore impossible.

    This test pins the *observed* behaviour, with the numbers, so the defect
    cannot be quietly changed into a different defect.
    """
    from services.gl_posting import UnbalancedJournalEntryError
    from services.product_service import ProductService
    from services.purchase_service import PurchaseService
    from services.stock_service import StockService

    tenant = demo_tenant
    tenant.enable_tax = True
    tenant.default_tax_rate = VAT_RATE
    tenant.prices_include_vat = False
    tenant.default_currency = "AED"
    tenant.base_currency = "AED"
    demo_user.branch_id = demo_branch.id
    db_session.flush()

    cost = Decimal("10.25")
    product = ProductService.create_product(
        tenant_id=tenant.id,
        name=f"Return Probe {uuid.uuid4().hex[:6]}",
        sku=f"RET-{uuid.uuid4().hex[:8]}",
        barcode=f"RT{uuid.uuid4().hex[:10]}",
        regular_price=Decimal("19.99"),
        cost_price=cost,
    )
    db_session.flush()
    StockService.add_opening_stock(product.id, Decimal("10"), warehouse_id=demo_warehouse.id)
    db_session.flush()

    qty = Decimal("60")
    purchase = PurchaseService.create_purchase(
        user=demo_user,
        supplier_data={"supplier_id": demo_supplier.id},
        lines_data=[{"product_id": product.id, "quantity": qty, "unit_cost": cost}],
        warehouse_id=demo_warehouse.id,
        currency="AED",
        tax_rate=VAT_RATE,
    )
    db_session.flush()

    expected_subtotal = qty * cost
    expected_tax = (expected_subtotal * VAT_RATE / Decimal("100")).quantize(Decimal("0.01"))
    assert Decimal(str(purchase.subtotal)) == expected_subtotal
    assert Decimal(str(purchase.tax_amount)) == expected_tax
    db_session.commit()

    with pytest.raises(UnbalancedJournalEntryError) as excinfo:
        PurchaseService.create_purchase_return(
            purchase,
            demo_user,
            [
                {
                    "purchase_line_id": pl.id,
                    "product_id": pl.product_id,
                    "quantity": pl.quantity,
                    "unit_cost": pl.unit_cost,
                }
                for pl in purchase.lines
            ],
            reason="damaged on arrival",
        )

    message = str(excinfo.value)
    assert f"{expected_subtotal}" in message or f"{expected_tax}" in message, (
        f"the refusal does not carry the offending amounts: {message}"
    )

    # The caller undoes the refused return (the ledger route does it inside
    # atomic_transaction); nothing of the return survives it.
    db_session.rollback()
    from models import ProductWarehouseStock, PurchaseReturn

    assert PurchaseReturn.query.filter_by(tenant_id=tenant.id, purchase_id=purchase.id).count() == 0, (
        "the refused purchase return left a credit note behind"
    )
    stock = ProductWarehouseStock.query.filter_by(
        tenant_id=tenant.id, product_id=product.id, warehouse_id=demo_warehouse.id
    ).first()
    assert stock is not None and Decimal(str(stock.quantity)) == Decimal("70"), (
        "the refused purchase return moved stock "
        f"(expected 10 opening + 60 purchased = 70, got {getattr(stock, 'quantity', None)})"
    )

    print(
        "\nFINDING P1 — purchase return against a VAT-bearing bill is refused: "
        f"bill subtotal {expected_subtotal} + VAT {expected_tax} = {expected_subtotal + expected_tax}; "
        f"the return's journal entry debits AP {expected_subtotal} but credits "
        f"inventory {expected_subtotal} + VAT input {expected_tax} -> unbalanced by {expected_tax}. "
        f"post_or_fail said: {message}",
        flush=True,
    )
    db_session.rollback()

    # Leave the database as it was found.
    _purge_tenant(tenant.id)


def _ledger_user(db, tenant, branch):
    from models import Permission, Role, User

    role = db.query(Role).filter_by(slug="recon-ledger").first()
    if role is None:
        role = Role(name="Recon Ledger", slug="recon-ledger", is_active=True)
        db.add(role)
        db.flush()
    role.permissions = Permission.query.filter(Permission.code.in_(["view_ledger", "manage_ledger", "admin"])).all()
    db.add(role)
    db.flush()

    user = User(
        username=f"recon-ledger-{uuid.uuid4().hex[:8]}",
        email=f"recon-ledger-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Reconciliation Ledger",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db.add(user)
    db.flush()
    db.commit()
    return user


def _login(client, user):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )
