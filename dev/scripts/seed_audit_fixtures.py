#!/usr/bin/env python3
"""Seed a small, fully balanced financial dataset for audit/reconciliation runs.

Idempotent: re-running deletes and rebuilds the dedicated tenant
(``seed-audit-tenant``) and every row that belongs to it. All documents are
planted together with their balanced GL journal entries and the cached
sub-ledger balances that the authoritative services would have written, so a
reconciliation pass must report ZERO discrepancies.

Use it to validate the controls against real data instead of an empty schema::

    $env:DATABASE_URL = "postgresql+psycopg2://postgres@localhost:5433/AzadFull2026"
    python dev/scripts/seed_audit_fixtures.py
    python scripts/ops/reconcile_historical_balances.py
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TENANT_SLUG = "seed-audit-tenant"
BASE = "AED"


def _ins(conn, table: str, **values):
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    sql = text(f"INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING id")
    return conn.execute(sql, values).scalar_one()


def _post(
    conn, tid: int, number: str, ref_type: str, ref_id: int, lines: list[tuple[str, int | Decimal, int | Decimal]]
):
    """Post one balanced journal entry; raises if the lines do not balance."""
    lines = [(code, Decimal(str(d)), Decimal(str(c))) for code, d, c in lines]
    dr = sum((d for _, d, _ in lines), Decimal("0"))
    cr = sum((c for _, _, c in lines), Decimal("0"))
    if dr != cr:
        raise AssertionError(f"unbalanced seed entry {number}: {dr} != {cr}")
    eid = _ins(
        conn,
        "gl_journal_entries",
        tenant_id=tid,
        entry_number=number,
        entry_date="2026-01-15 10:00:00+00",
        description=f"Seed entry {number}",
        reference_type=ref_type,
        reference_id=ref_id,
        currency=BASE,
        exchange_rate=1,
        total_debit=dr,
        total_credit=cr,
        is_posted=True,
        is_reversed=False,
        status="posted",
        created_at="2026-01-15 10:00:00+00",
        updated_at="2026-01-15 10:00:00+00",
    )
    acct = dict(conn.execute(text("SELECT code, id FROM gl_accounts WHERE tenant_id=:t"), {"t": tid}).all())
    for code, debit, credit in lines:
        _ins(
            conn,
            "gl_journal_lines",
            tenant_id=tid,
            entry_id=eid,
            account_id=acct[code],
            description=f"Seed {number} {code}",
            debit=debit,
            credit=credit,
            amount=debit or credit,
            amount_aed=debit or credit,
        )
    return eid


def _clean(conn, tid: int | None) -> None:
    if tid is None:
        return
    tables = [
        "gl_journal_lines",
        "gl_journal_entries",
        "partner_transactions",
        "partners",
        "maintenance_receipts",
        "maintenance_invoices",
        "maintenance_orders",
        "payments",
        "receipts",
        "sales",
        "purchases",
        "customers",
        "suppliers",
        "gl_accounts",
    ]
    for table in tables:
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id=:t"), {"t": tid})
    conn.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": tid})


def seed(conn) -> dict:
    tid = conn.execute(text("SELECT id FROM tenants WHERE slug=:s"), {"s": TENANT_SLUG}).scalar()
    _clean(conn, tid)

    tid = _ins(
        conn,
        "tenants",
        name="Financial Seed Audit",
        name_ar="تدقيق مالي",
        slug=TENANT_SLUG,
        country="AE",
        vat_country="AE",
        base_currency=BASE,
        default_currency=BASE,
        default_tax_rate=5,
        prices_include_vat=False,
        enable_tax=True,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
        updated_at="2026-01-01 00:00:00+00",
    )

    for code, name, typ in (
        ("1111", "Cash", "asset"),
        ("1120", "Bank", "asset"),
        ("1130", "Accounts Receivable", "asset"),
        ("1134", "Maintenance Receivable", "asset"),
        ("2110", "Accounts Payable", "liability"),
        ("2150", "Partner Current Account", "liability"),
        ("4100", "Sales Revenue", "revenue"),
        ("5100", "Cost of Sales", "expense"),
    ):
        _ins(
            conn,
            "gl_accounts",
            tenant_id=tid,
            code=code,
            name=name,
            name_ar=name,
            type=typ,
            is_reconcile=False,
            currency=BASE,
            is_default_liquidity=False,
            is_active=True,
            is_header=False,
            level=3,
            created_at="2026-01-01 00:00:00+00",
            updated_at="2026-01-01 00:00:00+00",
        )

    # --- Customer 1: ordinary sale, payment and a separate receipt -----------
    c1 = _ins(
        conn,
        "customers",
        tenant_id=tid,
        name="Seed Customer One",
        name_ar="عميل واحد",
        customer_type="regular",
        balance=0,
        total_purchases=1000,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
        updated_at="2026-01-01 00:00:00+00",
    )
    s1 = _ins(
        conn,
        "sales",
        tenant_id=tid,
        sale_number="SEED-SALE-1",
        customer_id=c1,
        sale_date="2026-01-10 10:00:00+00",
        seller_id=1,
        subtotal=1000,
        discount_amount=0,
        tax_amount=0,
        total_amount=1000,
        amount=1000,
        paid_amount=1000,
        balance_due=0,
        amount_aed=1000,
        currency=BASE,
        base_currency=BASE,
        exchange_rate=1,
        prices_include_vat=False,
        source="manual",
        status="confirmed",
        is_active=True,
        payment_status="paid",
        created_at="2026-01-10 10:00:00+00",
    )
    p1 = _ins(
        conn,
        "payments",
        tenant_id=tid,
        payment_number="SEED-PAY-1",
        payment_type="sale_payment",
        direction="incoming",
        customer_id=c1,
        sale_id=s1,
        amount=400,
        amount_aed=400,
        currency=BASE,
        base_currency=BASE,
        exchange_rate=1,
        payment_method="cash",
        payment_confirmed=True,
        payment_date="2026-01-11 10:00:00+00",
        created_at="2026-01-11 10:00:00+00",
    )
    r1 = _ins(
        conn,
        "receipts",
        tenant_id=tid,
        receipt_number="SEED-RCPT-1",
        customer_id=c1,
        sale_id=s1,
        source_type="sale",
        direction="incoming",
        amount=600,
        amount_aed=600,
        currency=BASE,
        base_currency=BASE,
        exchange_rate=1,
        payment_method="cash",
        payment_confirmed=True,
        receipt_date="2026-01-12 10:00:00+00",
        created_at="2026-01-12 10:00:00+00",
    )
    _post(conn, tid, "SEED-GL-1", "Sale", s1, [("1130", 1000, 0), ("4100", 0, 1000)])
    _post(conn, tid, "SEED-GL-2", "Payment", p1, [("1111", 400, 0), ("1130", 0, 400)])
    _post(conn, tid, "SEED-GL-3", "Receipt", r1, [("1111", 600, 0), ("1130", 0, 600)])

    # --- Customer 2: maintenance in USD, exercises the FX conversion --------
    c2 = _ins(
        conn,
        "customers",
        tenant_id=tid,
        name="Seed Customer Two",
        name_ar="عميل اثنان",
        customer_type="regular",
        balance=-175,  # -350 invoice + 175 receipt
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
        updated_at="2026-01-01 00:00:00+00",
    )
    mo = _ins(
        conn,
        "maintenance_orders",
        tenant_id=tid,
        order_number="SEED-MORDER-1",
        order_date="2026-01-13 10:00:00+00",
        customer_id=c2,
        subtotal=100,
        discount_line_total=0,
        discount_total_percent=0,
        discount_total_value=0,
        tax_rate=0,
        tax_amount=0,
        taxable_amount=100,
        total_amount=100,
        amount=100,
        paid_amount=50,
        balance_due=50,
        deposit_amount=0,
        refunded_amount=0,
        amount_aed=350,
        paid_amount_aed=175,
        balance_due_aed=175,
        currency="USD",
        exchange_rate=3.5,
        base_currency=BASE,
        prices_include_vat=False,
        received_by=1,
        status="closed",
        priority="normal",
        warranty_status="unknown",
        warranty_checked=False,
        color_tag="#10b981",
        customer_signature=False,
        is_archived=False,
        created_at="2026-01-13 10:00:00+00",
        updated_at="2026-01-13 10:00:00+00",
    )
    mi = _ins(
        conn,
        "maintenance_invoices",
        tenant_id=tid,
        order_id=mo,
        invoice_number="SEED-MINV-1",
        invoice_date="2026-01-13 10:00:00+00",
        subtotal=100,
        discount_total_percent=0,
        discount_total_value=0,
        tax_rate=0,
        tax_amount=0,
        taxable_amount=100,
        total_amount=100,
        amount=100,
        paid_amount=50,
        balance_due=50,
        amount_aed=350,
        paid_amount_aed=175,
        balance_due_aed=175,
        currency="USD",
        exchange_rate=3.5,
        base_currency=BASE,
        prices_include_vat=False,
        posted=True,
        gl_posted=True,
        is_archived=False,
        created_at="2026-01-13 10:00:00+00",
    )
    mr = _ins(
        conn,
        "maintenance_receipts",
        tenant_id=tid,
        order_id=mo,
        receipt_number="SEED-MRCPT-1",
        receipt_date="2026-01-14 10:00:00+00",
        amount=50,  # 50 USD * 3.5 = 175 AED
        payment_mode="cash",
        cashier_id=1,
        is_deposit=False,
        is_refund=False,
        gl_posted=True,
        is_archived=False,
        created_at="2026-01-14 10:00:00+00",
    )
    _post(conn, tid, "SEED-GL-4", "MaintenanceInvoice", mi, [("1134", 350, 0), ("4100", 0, 350)])
    _post(conn, tid, "SEED-GL-5", "MaintenanceReceipt", mr, [("1111", 175, 0), ("1134", 0, 175)])

    # --- Supplier: purchase and outgoing payment ----------------------------
    sup = _ins(
        conn,
        "suppliers",
        tenant_id=tid,
        name="Seed Supplier",
        name_ar="مورد",
        total_purchases_aed=500,
        total_paid_aed=200,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
        updated_at="2026-01-01 00:00:00+00",
    )
    pu = _ins(
        conn,
        "purchases",
        tenant_id=tid,
        purchase_number="SEED-PUR-1",
        supplier_id=sup,
        supplier_name="Seed Supplier",
        purchase_date="2026-01-10 10:00:00+00",
        subtotal=500,
        discount_amount=0,
        tax_amount=0,
        total_amount=500,
        amount=500,
        amount_aed=500,
        currency=BASE,
        base_currency=BASE,
        exchange_rate=1,
        prices_include_vat=False,
        freight=0,
        insurance=0,
        customs_duty=0,
        other_landed_cost=0,
        user_id=1,
        status="confirmed",
        created_at="2026-01-10 10:00:00+00",
    )
    p2 = _ins(
        conn,
        "payments",
        tenant_id=tid,
        payment_number="SEED-SPAY-1",
        payment_type="supplier_payment",
        direction="outgoing",
        supplier_id=sup,
        purchase_id=pu,
        amount=200,
        amount_aed=200,
        currency=BASE,
        base_currency=BASE,
        exchange_rate=1,
        payment_method="cash",
        payment_confirmed=True,
        payment_date="2026-01-12 10:00:00+00",
        created_at="2026-01-12 10:00:00+00",
    )
    _post(conn, tid, "SEED-GL-6", "Purchase", pu, [("5100", 500, 0), ("2110", 0, 500)])
    _post(conn, tid, "SEED-GL-7", "Payment", p2, [("2110", 200, 0), ("1111", 0, 200)])

    # --- Partner ledger ------------------------------------------------------
    partner = _ins(
        conn,
        "partners",
        tenant_id=tid,
        name="Seed Partner",
        code="SEED-PARTNER",
        partner_type="investor",
        scope_type="company",
        current_balance=100,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
    )
    _ins(
        conn,
        "partner_transactions",
        tenant_id=tid,
        partner_id=partner,
        transaction_type="additional_investment",
        amount=100,
        amount_base=100,
        balance_after=100,
        currency=BASE,
        exchange_rate=1,
        transaction_date="2026-01-15",
    )
    _post(conn, tid, "SEED-GL-8", "PartnerTransaction", partner, [("1111", 100, 0), ("2150", 0, 100)])

    return {
        "tenant_id": tid,
        "customers": 2,
        "suppliers": 1,
        "partners": 1,
        "sales": 1,
        "purchases": 1,
        "maintenance_orders": 1,
        "gl_entries": 8,
    }


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required")
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            summary = seed(conn)
    finally:
        engine.dispose()
    print(f"Seeded tenant {summary['tenant_id']}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
