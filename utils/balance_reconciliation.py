"""Full historical sub-ledger reconciliation.

Rebuilds the stored convenience balances from EVERY source document, not just
from the maintenance movements covered by the first repair migration. Used by
``scripts/ops/reconcile_historical_balances.py`` (dry-run / apply) and by the
Alembic revision that ships the repair to existing installations.

All reads/writes go through the supplied SQLAlchemy ``Connection`` so the same
code works in an Alembic migration, an app context and a test.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text

_Q = Decimal("0.001")


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _q(value: Decimal) -> Decimal:
    # Legacy rows can hold NULL in cached money columns that have no DB
    # default; treat them as zero rather than crashing the repair migration.
    return _d(value).quantize(_Q, rounding=ROUND_HALF_UP)


def _t(name: str, *columns: str):
    return sa.table(name, *[sa.column(c) for c in columns])


def _base(amount, currency, rate, base_currency) -> Decimal:
    from utils.currency_utils import convert_and_quantize_aed

    return _q(
        convert_and_quantize_aed(
            _d(amount),
            currency or base_currency,
            rate if rate is not None else Decimal("1"),
            base_currency=base_currency,
        )
    )


def _affects(amount, confirmed, method, rejection) -> Decimal:
    """A payment/receipt affects the balance when confirmed or a live cheque."""
    return _d(amount) if (confirmed or (method == "cheque" and not rejection)) else Decimal("0")


def _tenant_base_currencies(conn) -> dict[int, str]:
    rows = conn.execute(text("SELECT id, base_currency, default_currency FROM tenants"))
    return {r.id: (r.base_currency or r.default_currency or "AED").upper() for r in rows}


def _customer_expected(conn, tenant_base: dict[int, str]) -> dict[int, Decimal]:
    """The customer's closing balance from every document, sign conventions per models/customer.py."""
    expected: dict[int, Decimal] = {}

    for r in conn.execute(text("SELECT id FROM customers")):
        expected[r.id] = Decimal("0")

    # Archived sales have their GL entry reversed (archive_service.py), so
    # counting them here would resurrect a debt the books no longer carry.
    for r in conn.execute(
        text("SELECT customer_id, amount_aed FROM sales WHERE status='confirmed' AND is_active=true")
    ):
        if r.customer_id in expected:
            expected[r.customer_id] -= _d(r.amount_aed)

    payment_rows = conn.execute(
        text(
            "SELECT customer_id, direction, amount_aed, payment_confirmed, payment_method, "
            "rejection_reason, reference_number FROM payments WHERE customer_id IS NOT NULL"
        )
    ).all()
    allocated: dict[tuple[int, str], Decimal] = {}
    for r in payment_rows:
        if r.customer_id not in expected:
            continue
        effect = _affects(r.amount_aed, r.payment_confirmed, r.payment_method, r.rejection_reason)
        expected[r.customer_id] += effect if r.direction == "incoming" else -effect
        if r.reference_number and effect:
            key = (r.customer_id, r.reference_number)
            allocated[key] = allocated.get(key, Decimal("0")) + effect

    for r in conn.execute(
        text(
            "SELECT customer_id, receipt_number, amount_aed, payment_confirmed, payment_method, "
            "rejection_reason FROM receipts WHERE customer_id IS NOT NULL"
        )
    ).all():
        if r.customer_id not in expected:
            continue
        gross = _affects(r.amount_aed, r.payment_confirmed, r.payment_method, r.rejection_reason)
        unallocated = gross - allocated.get((r.customer_id, r.receipt_number or ""), Decimal("0"))
        expected[r.customer_id] += max(unallocated, Decimal("0"))

    for r in conn.execute(text("SELECT customer_id, amount_aed FROM product_returns WHERE status='approved'")):
        if r.customer_id in expected:
            expected[r.customer_id] += _d(r.amount_aed)

    orders = {
        r.id: r
        for r in conn.execute(
            text("SELECT id, customer_id, tenant_id, currency, exchange_rate, base_currency FROM maintenance_orders")
        )
    }
    for r in conn.execute(text("SELECT order_id, amount_aed FROM maintenance_invoices WHERE posted=true")):
        o = orders.get(r.order_id)
        if o and o.customer_id in expected:
            expected[o.customer_id] -= _d(r.amount_aed)
    # A maintenance receipt stores the amount in the ORDER's currency, while
    # Customer.balance and the GL carry the base-currency equivalent. Convert
    # exactly as services/maintenance_order_service.py::_customer_base_amount
    # does; using the raw amount overwrites correct balances with wrong ones.
    from utils.currency_utils import convert_and_quantize_aed

    for r in conn.execute(text("SELECT order_id, amount, is_refund FROM maintenance_receipts")):
        o = orders.get(r.order_id)
        if not o or o.customer_id not in expected:
            continue
        base = convert_and_quantize_aed(
            _d(r.amount),
            o.currency or "AED",
            o.exchange_rate or Decimal("1"),
            base_currency=o.base_currency or tenant_base.get(o.tenant_id, "AED"),
            tenant_id=o.tenant_id,
        )
        expected[o.customer_id] += -base if r.is_refund else base
    for r in conn.execute(text("SELECT order_id, total_value_aed FROM maintenance_returns WHERE posted=true")):
        o = orders.get(r.order_id)
        if o and o.customer_id in expected:
            expected[o.customer_id] += _d(r.total_value_aed)

    return {cid: _q(v) for cid, v in expected.items()}


def _supplier_expected(conn, tenant_base: dict[int, str]) -> tuple[dict[int, Decimal], dict[int, Decimal]]:
    purchases: dict[int, Decimal] = {}
    paid: dict[int, Decimal] = {}
    for r in conn.execute(text("SELECT id FROM suppliers")):
        purchases[r.id] = Decimal("0")
        paid[r.id] = Decimal("0")

    for r in conn.execute(text("SELECT supplier_id, amount_aed FROM purchases WHERE status='confirmed'")):
        if r.supplier_id in purchases:
            purchases[r.supplier_id] += _d(r.amount_aed)
    # Purchase returns have no status column - creating one is the approval.
    for r in conn.execute(text("SELECT supplier_id, amount_aed FROM purchase_returns")):
        if r.supplier_id in purchases:
            purchases[r.supplier_id] -= _d(r.amount_aed)

    for r in conn.execute(
        text(
            "SELECT supplier_id, direction, amount_aed, payment_confirmed, payment_method, rejection_reason "
            "FROM payments WHERE supplier_id IS NOT NULL"
        )
    ).all():
        if r.supplier_id not in paid:
            continue
        effect = _affects(r.amount_aed, r.payment_confirmed, r.payment_method, r.rejection_reason)
        # Outgoing payment reduces AP; an incoming supplier refund raises it.
        paid[r.supplier_id] += effect if r.direction == "outgoing" else -effect

    for r in conn.execute(
        text(
            "SELECT supplier_id, tenant_id, total_amount, currency, exchange_rate "
            "FROM maintenance_purchase_orders WHERE status='received' AND posted=true"
        )
    ).all():
        if r.supplier_id in purchases:
            purchases[r.supplier_id] += _base(
                r.total_amount, r.currency, r.exchange_rate, tenant_base.get(r.tenant_id, "AED")
            )
    return {k: _q(v) for k, v in purchases.items()}, {k: _q(v) for k, v in paid.items()}


def reconcile(conn, *, apply: bool = False) -> dict[str, Any]:
    """Return a report of every discrepancy; write corrections only when ``apply``."""
    tenant_base = _tenant_base_currencies(conn)
    report: dict[str, Any] = {
        "customers": [],
        "suppliers": [],
        "partners": [],
        "cash_boxes": [],
        "applied": apply,
    }

    # total_purchases drives the customer VIP classification and is written
    # incrementally by the sale service. Rebuild it from the same documents:
    # confirmed, active sales. Cancelled/archived sales never counted.
    purchases_by_customer: dict[int, Decimal] = {}
    for r in conn.execute(
        text("SELECT customer_id, amount_aed FROM sales WHERE status='confirmed' AND is_active=true")
    ):
        purchases_by_customer[r.customer_id] = purchases_by_customer.get(r.customer_id, Decimal("0")) + _d(r.amount_aed)

    customers_tbl = _t("customers", "id", "balance", "total_purchases")
    stored_customers = {r.id: (_q(r.balance), _q(r.total_purchases)) for r in conn.execute(sa.select(customers_tbl))}
    for cid, expected in _customer_expected(conn, tenant_base).items():
        expected_purchases = _q(purchases_by_customer.get(cid, Decimal("0")))
        before_balance, before_purchases = stored_customers.get(cid, (Decimal("0"), Decimal("0")))
        if (before_balance, before_purchases) != (expected, expected_purchases):
            report["customers"].append(
                {
                    "id": cid,
                    "before": str(before_balance),
                    "after": str(expected),
                    "before_purchases": str(before_purchases),
                    "after_purchases": str(expected_purchases),
                }
            )
            if apply:
                conn.execute(
                    sa.update(customers_tbl)
                    .where(customers_tbl.c.id == cid)
                    .values(balance=expected, total_purchases=expected_purchases)
                )

    purchases, paid = _supplier_expected(conn, tenant_base)
    suppliers_tbl = _t("suppliers", "id", "total_purchases_aed", "total_paid_aed")
    stored_suppliers = {
        r.id: (_q(r.total_purchases_aed), _q(r.total_paid_aed)) for r in conn.execute(sa.select(suppliers_tbl))
    }
    for sid, expected_purchase in purchases.items():
        expected_paid = paid[sid]
        before_p, before_paid = stored_suppliers.get(sid, (Decimal("0"), Decimal("0")))
        if (before_p, before_paid) != (expected_purchase, expected_paid):
            report["suppliers"].append(
                {
                    "id": sid,
                    "before_purchases": str(before_p),
                    "after_purchases": str(expected_purchase),
                    "before_paid": str(before_paid),
                    "after_paid": str(expected_paid),
                }
            )
            if apply:
                conn.execute(
                    sa.update(suppliers_tbl)
                    .where(suppliers_tbl.c.id == sid)
                    .values(total_purchases_aed=expected_purchase, total_paid_aed=expected_paid)
                )

    # Partner balances are the exact sum of their ledger; also rebuild the
    # running balance column in transaction-date order.
    partners_tbl = _t("partners", "id", "current_balance")
    txn_tbl = _t(
        "partner_transactions",
        "id",
        "partner_id",
        "transaction_date",
        "amount_base",
        "balance_after",
    )
    stored_partners = {r.id: _q(r.current_balance) for r in conn.execute(sa.select(partners_tbl))}
    for row in conn.execute(sa.select(partners_tbl.c.id)).all():
        pid = row.id
        txs = conn.execute(
            sa.select(txn_tbl).where(txn_tbl.c.partner_id == pid).order_by(txn_tbl.c.transaction_date, txn_tbl.c.id)
        ).all()
        running = Decimal("0")
        for tx in txs:
            running += _q(tx.amount_base)
            if _q(tx.balance_after) != running and apply:
                conn.execute(sa.update(txn_tbl).where(txn_tbl.c.id == tx.id).values(balance_after=running))
        if stored_partners.get(pid, Decimal("0")) != _q(running):
            report["partners"].append(
                {"id": pid, "before": str(stored_partners.get(pid, Decimal("0"))), "after": str(_q(running))}
            )
            if apply:
                conn.execute(
                    sa.update(partners_tbl).where(partners_tbl.c.id == pid).values(current_balance=_q(running))
                )

    # Cash boxes are the denormalised view of their linked GL liquidity
    # account. The service never updates current_balance after creation, so
    # the column goes stale; derive it from posted GL lines instead.
    cash_boxes_tbl = _t("cash_boxes", "id", "gl_account_id", "current_balance")
    for box in conn.execute(sa.select(cash_boxes_tbl)).all():
        if box.gl_account_id is None:
            continue  # no GL link -> nothing authoritative to derive from
        balance = conn.execute(
            text(
                "SELECT COALESCE(SUM(l.debit - l.credit), 0) "
                "FROM gl_journal_lines l JOIN gl_journal_entries e ON e.id = l.entry_id "
                "WHERE l.account_id = :a AND e.status = 'posted'"
            ),
            {"a": box.gl_account_id},
        ).scalar()
        expected = _q(balance)
        before = _q(box.current_balance)
        if before != expected:
            report["cash_boxes"].append({"id": box.id, "before": str(before), "after": str(expected)})
            if apply:
                conn.execute(
                    sa.update(cash_boxes_tbl).where(cash_boxes_tbl.c.id == box.id).values(current_balance=expected)
                )

    report["total_discrepancies"] = sum(len(report[k]) for k in ("customers", "suppliers", "partners", "cash_boxes"))
    return report
