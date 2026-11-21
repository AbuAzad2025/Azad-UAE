"""Repair the stored counterparty balances from the historical movements.

The statement services were the first to carry every movement (maintenance
invoices, receipts, returns and refunds; workshop spare-part purchases; sale
commissions), but the stored convenience balances were only maintained by a
subset of those paths. This revision makes the stored numbers agree with the
documents:

* ``customers.balance`` is rebuilt from sales, payments, receipts, approved
  product returns and every maintenance money movement, with the same signs
  the customer statement uses (negative = the customer owes us).
* ``suppliers.total_purchases_aed`` is topped up with the received workshop
  spare-part purchase orders, which post to the very same AP account.
* Historic sale commissions become first-class ``PartnerTransaction`` rows,
  and the affected partners' running balances are rebuilt from their ledger.

The migration is data-only. Schema is untouched, so the downgrade is a
deliberate no-op, like the other data-repair revisions in this chain.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None

_QUANTUM = Decimal("0.001")


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _table(name: str, *columns: str):
    return sa.table(name, *[sa.column(column) for column in columns])


def _base_amount(amount, currency, rate, base_currency) -> Decimal:
    """Convert into the tenant base currency with the project's 3dp precision."""
    value = _decimal(amount)
    base = (base_currency or "AED").upper()
    if (currency or base).upper() == base:
        return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    factor = _decimal(rate)
    if factor <= 0:
        factor = Decimal("1")
    return (value * factor).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _has_table(connection, name: str) -> bool:
    return sa.inspect(connection).has_table(name)


def _has_columns(connection, name: str, *columns: str) -> bool:
    if not _has_table(connection, name):
        return False
    present = {column["name"] for column in sa.inspect(connection).get_columns(name)}
    return all(column in present for column in columns)


def _to_date(value):
    if value is None:
        return datetime.now(UTC).date()
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return datetime.now(UTC).date()
    return value


def _tenant_base_currencies(connection) -> dict:
    if not _has_columns(connection, "tenants", "id"):
        return {}
    columns = {"id"}
    for candidate in ("base_currency", "default_currency"):
        if candidate in {column["name"] for column in sa.inspect(connection).get_columns("tenants")}:
            columns.add(candidate)
    tenants = _table("tenants", *sorted(columns))
    result = {}
    for row in connection.execute(sa.select(tenants)):
        mapping = row._mapping
        result[mapping["id"]] = (mapping.get("base_currency") or mapping.get("default_currency") or "AED").upper()
    return result


def _repair_customer_balances(connection, tenant_base: dict) -> None:
    if not _has_columns(connection, "customers", "id", "balance"):
        return
    customers = _table("customers", "id", "tenant_id", "balance")
    balances = {}
    for row in connection.execute(sa.select(customers.c.id, customers.c.tenant_id)):
        balances[row.id] = Decimal("0")

    def _customer_base(customer_id):
        for row in connection.execute(sa.select(customers.c.tenant_id).where(customers.c.id == customer_id)):
            return tenant_base.get(row.tenant_id, "AED")
        return "AED"

    if _has_columns(connection, "sales", "customer_id", "status", "amount_aed"):
        sales = _table("sales", "customer_id", "status", "amount_aed")
        for row in connection.execute(sa.select(sales)):
            if row.customer_id in balances and (row.status or "") == "confirmed":
                balances[row.customer_id] -= _decimal(row.amount_aed)

    payment_references = set()
    if _has_columns(
        connection,
        "payments",
        "customer_id",
        "direction",
        "amount_aed",
        "payment_confirmed",
        "payment_method",
        "rejection_reason",
        "reference_number",
    ):
        payments = _table(
            "payments",
            "customer_id",
            "direction",
            "amount_aed",
            "payment_confirmed",
            "payment_method",
            "rejection_reason",
            "reference_number",
        )
        for row in connection.execute(sa.select(payments)):
            if row.reference_number:
                payment_references.add(row.reference_number)
            if row.customer_id not in balances:
                continue
            confirmed = bool(row.payment_confirmed) or (row.payment_method == "cheque" and not row.rejection_reason)
            if not confirmed:
                continue
            amount = _decimal(row.amount_aed)
            balances[row.customer_id] += amount if row.direction == "incoming" else -amount

    if _has_columns(
        connection,
        "receipts",
        "customer_id",
        "receipt_number",
        "amount_aed",
        "payment_confirmed",
        "payment_method",
        "rejection_reason",
    ):
        receipts = _table(
            "receipts",
            "customer_id",
            "receipt_number",
            "amount_aed",
            "payment_confirmed",
            "payment_method",
            "rejection_reason",
        )
        for row in connection.execute(sa.select(receipts)):
            if row.customer_id not in balances:
                continue
            confirmed = bool(row.payment_confirmed) or (row.payment_method == "cheque" and not row.rejection_reason)
            if not confirmed or (row.receipt_number or "") in payment_references:
                continue
            balances[row.customer_id] += _decimal(row.amount_aed)

    if _has_columns(connection, "product_returns", "customer_id", "status", "amount_aed"):
        returns = _table("product_returns", "customer_id", "status", "amount_aed")
        for row in connection.execute(sa.select(returns)):
            if row.customer_id in balances and (row.status or "") == "approved":
                balances[row.customer_id] += _decimal(row.amount_aed)

    if _has_columns(connection, "maintenance_orders", "id", "customer_id"):
        orders_table = _table(
            "maintenance_orders",
            "id",
            "customer_id",
            "currency",
            "exchange_rate",
            "base_currency",
        )
        order_ids = {}
        for row in connection.execute(sa.select(orders_table)):
            order_ids[row.id] = row

        def _movement_base(order_id, amount, fallback_currency):
            order = order_ids.get(order_id)
            if order is None:
                return _base_amount(amount, fallback_currency, 1, "AED")
            return _base_amount(
                amount,
                order.currency,
                order.exchange_rate,
                order.base_currency or fallback_currency,
            )

        if _has_columns(connection, "maintenance_invoices", "order_id", "amount_aed", "posted"):
            invoices = _table("maintenance_invoices", "order_id", "amount_aed", "posted")
            for row in connection.execute(sa.select(invoices)):
                order = order_ids.get(row.order_id)
                if order is None or not row.posted or order.customer_id not in balances:
                    continue
                balances[order.customer_id] -= _decimal(row.amount_aed)

        if _has_columns(connection, "maintenance_receipts", "order_id", "amount", "is_refund"):
            receipts_table = _table("maintenance_receipts", "order_id", "amount", "is_refund")
            for row in connection.execute(sa.select(receipts_table)):
                order = order_ids.get(row.order_id)
                if order is None or order.customer_id not in balances:
                    continue
                base = _movement_base(row.order_id, row.amount, _customer_base(order.customer_id))
                balances[order.customer_id] += -base if row.is_refund else base

        if _has_columns(connection, "maintenance_returns", "order_id", "total_value_aed", "posted"):
            returns_table = _table("maintenance_returns", "order_id", "total_value_aed", "posted")
            for row in connection.execute(sa.select(returns_table)):
                order = order_ids.get(row.order_id)
                if order is None or not row.posted or order.customer_id not in balances:
                    continue
                balances[order.customer_id] += _decimal(row.total_value_aed)

    for customer_id, balance in balances.items():
        connection.execute(
            sa.update(customers)
            .where(customers.c.id == customer_id)
            .values(balance=balance.quantize(_QUANTUM, rounding=ROUND_HALF_UP))
        )


def _repair_supplier_totals(connection, tenant_base: dict) -> None:
    if not _has_columns(connection, "suppliers", "id", "total_purchases_aed"):
        return
    if not _has_columns(
        connection,
        "maintenance_purchase_orders",
        "supplier_id",
        "tenant_id",
        "status",
        "posted",
        "total_amount",
        "currency",
        "exchange_rate",
    ):
        return
    suppliers = _table("suppliers", "id", "total_purchases_aed")
    supplier_ids = [row.id for row in connection.execute(sa.select(suppliers.c.id))]

    # Recompute from source documents rather than adding to the cached value:
    # adding is not idempotent if the revision is replayed after a downgrade.
    purchase_totals: dict[int, Decimal] = {sid: Decimal("0") for sid in supplier_ids}
    if _has_columns(connection, "purchases", "supplier_id", "status", "amount_aed"):
        purchases = _table("purchases", "supplier_id", "status", "amount_aed")
        for row in connection.execute(sa.select(purchases)):
            if (row.status or "") == "confirmed" and row.supplier_id in purchase_totals:
                purchase_totals[row.supplier_id] += _decimal(row.amount_aed)

    orders = _table(
        "maintenance_purchase_orders",
        "supplier_id",
        "tenant_id",
        "status",
        "posted",
        "total_amount",
        "currency",
        "exchange_rate",
    )
    additions: dict[int, Decimal] = {}
    for row in connection.execute(sa.select(orders)):
        if (row.status or "") != "received" or not row.posted or row.supplier_id not in purchase_totals:
            continue
        additions[row.supplier_id] = additions.get(row.supplier_id, Decimal("0")) + _base_amount(
            row.total_amount,
            row.currency,
            row.exchange_rate,
            tenant_base.get(row.tenant_id, "AED"),
        )
    # Only suppliers actually affected by the missing workshop purchases are
    # touched; a supplier with a manually set opening total and no workshop
    # orders is left exactly as it was.
    for supplier_id, addition in additions.items():
        total = purchase_totals.get(supplier_id, Decimal("0")) + addition
        connection.execute(
            sa.update(suppliers)
            .where(suppliers.c.id == supplier_id)
            .values(total_purchases_aed=total.quantize(_QUANTUM, rounding=ROUND_HALF_UP))
        )


def _repair_partner_commissions(connection) -> None:
    required = (
        "customers",
        "partners",
        "partner_commission_entries",
        "partner_transactions",
        "sales",
    )
    if not all(_has_table(connection, table) for table in required):
        return
    if not _has_columns(connection, "customers", "id", "partner_id"):
        return
    if not _has_columns(
        connection, "partner_commission_entries", "tenant_id", "sale_id", "partner_customer_id", "commission_amount_aed"
    ):
        return

    customers = _table("customers", "id", "partner_id")
    partner_by_customer = {}
    for row in connection.execute(sa.select(customers)):
        if row.partner_id:
            partner_by_customer[row.id] = row.partner_id

    sales = _table("sales", "id", "sale_number", "sale_date")
    sale_map = {}
    for row in connection.execute(sa.select(sales)):
        sale_map[row.id] = row

    transactions = _table(
        "partner_transactions",
        "id",
        "partner_id",
        "amount_base",
        "reference_type",
        "reference_id",
    )
    already_recorded = set()
    for row in connection.execute(sa.select(transactions)):
        if row.reference_type == "sale_commission":
            already_recorded.add((row.partner_id, row.reference_id))

    commissions = _table(
        "partner_commission_entries",
        "tenant_id",
        "sale_id",
        "partner_customer_id",
        "commission_amount_aed",
    )
    grouped: dict[tuple, Decimal] = {}
    for row in connection.execute(sa.select(commissions)):
        partner_id = partner_by_customer.get(row.partner_customer_id)
        if not partner_id or (partner_id, row.sale_id) in already_recorded:
            continue
        key = (row.tenant_id, partner_id, row.sale_id)
        grouped[key] = grouped.get(key, Decimal("0")) + _decimal(row.commission_amount_aed)

    if not grouped:
        return

    full_transactions = _table(
        "partner_transactions",
        "id",
        "tenant_id",
        "partner_id",
        "transaction_type",
        "amount",
        "amount_base",
        "balance_after",
        "reference_number",
        "reference_type",
        "reference_id",
        "transaction_date",
        "notes",
        "created_at",
    )
    for (tenant_id, partner_id, sale_id), amount in grouped.items():
        if amount == 0:
            continue
        sale = sale_map.get(sale_id)
        number = getattr(sale, "sale_number", None) or str(sale_id)
        amount = amount.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
        connection.execute(
            sa.insert(full_transactions).values(
                tenant_id=tenant_id,
                partner_id=partner_id,
                transaction_type="sale_commission",
                amount=amount,
                amount_base=amount,
                balance_after=Decimal("0"),  # rebuilt from the whole ledger below
                reference_number=number,
                reference_type="sale_commission",
                reference_id=sale_id,
                transaction_date=_to_date(getattr(sale, "sale_date", None)),
                notes=f"سجل ترحيل: عمولة مبيعات {number}",
                created_at=datetime.now(UTC),
            )
        )

    # Commissions are historical, so a newly inserted row can sort between
    # existing ones. Rebuild the running balance of every affected partner so
    # the statement, balance_after and current_balance all agree again.
    partners = _table("partners", "id", "current_balance")
    for partner_id in {partner_id for (_tid, partner_id, _sid) in grouped}:
        rows = connection.execute(
            sa.select(full_transactions.c.id, full_transactions.c.amount_base)
            .where(full_transactions.c.partner_id == partner_id)
            .order_by(full_transactions.c.transaction_date, full_transactions.c.id)
        ).all()
        running = Decimal("0")
        for row in rows:
            running += _decimal(row.amount_base)
            connection.execute(
                sa.update(full_transactions)
                .where(full_transactions.c.id == row.id)
                .values(balance_after=running.quantize(_QUANTUM, rounding=ROUND_HALF_UP))
            )
        connection.execute(
            sa.update(partners)
            .where(partners.c.id == partner_id)
            .values(current_balance=running.quantize(_QUANTUM, rounding=ROUND_HALF_UP))
        )


def _repair_maintenance_base_mirrors(connection, tenant_base: dict) -> None:
    """Rebuild the base-currency mirrors that the statement and e-invoice render.

    ``close_and_collect`` updates ``paid_amount``/``balance_due`` when the
    receipt is taken, but older rows never had their ``*_aed`` counterparts
    refreshed, so a fully paid maintenance invoice still rendered as unpaid.
    """
    if not _has_columns(connection, "maintenance_orders", "id", "tenant_id"):
        return
    orders_columns = {"id", "tenant_id", "currency", "exchange_rate"}
    present = {column["name"] for column in sa.inspect(connection).get_columns("maintenance_orders")}
    orders_columns &= present
    orders_table = _table("maintenance_orders", *sorted(orders_columns))
    orders = {}
    for row in connection.execute(sa.select(orders_table)):
        mapping = row._mapping
        base = mapping.get("base_currency") or tenant_base.get(mapping["tenant_id"], "AED")
        orders[mapping["id"]] = (
            mapping.get("currency"),
            mapping.get("exchange_rate"),
            base,
        )

    def _repair_table(name: str, keys: tuple[str, ...], *, has_order_ref: bool) -> None:
        required = {"id", "paid_amount", "balance_due", "paid_amount_aed", "balance_due_aed"}
        if has_order_ref:
            required.add("order_id")
        table_columns = {column["name"] for column in sa.inspect(connection).get_columns(name)}
        if not required.issubset(table_columns):
            return
        columns = sorted(required | ({"currency", "exchange_rate", "base_currency"} & table_columns))
        table = _table(name, *columns)
        for row in connection.execute(sa.select(table)):
            mapping = row._mapping
            order = orders.get(mapping["order_id"]) if has_order_ref else None
            currency = mapping.get("currency") or (order[0] if order else None) or "AED"
            rate = mapping.get("exchange_rate")
            if rate is None and order:
                rate = order[1]
            base = mapping.get("base_currency") or (order[2] if order else None) or "AED"
            values = {
                f"{key}_aed": _base_amount(mapping[key], currency, rate, base).quantize(
                    _QUANTUM, rounding=ROUND_HALF_UP
                )
                for key in keys
            }
            connection.execute(sa.update(table).where(table.c.id == mapping["id"]).values(**values))

    _repair_table("maintenance_orders", ("paid_amount", "balance_due"), has_order_ref=False)
    if _has_table(connection, "maintenance_invoices"):
        _repair_table("maintenance_invoices", ("paid_amount", "balance_due"), has_order_ref=True)


def upgrade():
    connection = op.get_bind()
    tenant_base = _tenant_base_currencies(connection)
    _repair_customer_balances(connection, tenant_base)
    _repair_supplier_totals(connection, tenant_base)
    _repair_maintenance_base_mirrors(connection, tenant_base)
    _repair_partner_commissions(connection)


def downgrade():
    """Deliberately one-way: the pre-repair balances were wrong by construction.

    Every value written here was recomputed from the source documents (sales,
    payments, maintenance movements, workshop purchases and partner ledger
    rows). No snapshot of the old, incorrect cached numbers was kept, so there
    is nothing honest to restore — reverting would reinstate balances that
    disagreed with the documents. Schema is untouched; this is a data-only
    repair, not a reversible schema change.
    """
    pass
