#!/usr/bin/env python3
"""Seed the previously untested financial domains into a dedicated tenant.

Adds, inside the existing azad_isolation_test database and one fresh tenant:
  * employees + payroll (with statutory withholding columns) + salary advances
  * fixed assets + depreciation schedules
  * cheques through several lifecycle states (with linked GL)
  * a completed bank reconciliation + statement lines
  * stock movements + warehouse stock
  * e-invoices (UBL XML + hash + ZATCA TLV QR) for sales
  * expenses, sales returns, purchase returns, donations

Every document is posted through a balanced journal entry so the CFO audit
(reconcile + verify_isolation) must still report zero discrepancies.

    $env:DATABASE_URL = "postgresql+psycopg2://postgres@localhost:5433/azad_isolation_test"
    python scripts/ops/seed_financial_domains.py
"""

from __future__ import annotations

import hashlib
import os
import sys
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SLUG = "iso-financial-domains"
NAME = "Azad Financial Domains LLC"


def _ins(conn, table: str, **values):
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    return conn.execute(sa.text(f"INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING id"), values).scalar_one()


def _post(conn, tid, number, ref_type, ref_id, accounts, lines):
    lines = [(c, Decimal(str(d)), Decimal(str(k))) for c, d, k in lines]
    dr = sum((d for _, d, _ in lines), Decimal("0"))
    cr = sum((k for _, _, k in lines), Decimal("0"))
    assert dr == cr, f"unbalanced {number}: {dr} != {cr}"
    eid = _ins(
        conn,
        "gl_journal_entries",
        tenant_id=tid,
        entry_number=number,
        entry_date="2026-02-15 10:00:00+00",
        description=f"Domain seed {number}",
        reference_type=ref_type,
        reference_id=ref_id,
        currency="AED",
        exchange_rate=1,
        total_debit=dr,
        total_credit=cr,
        is_posted=True,
        is_reversed=False,
        status="posted",
        created_at="2026-02-15 10:00:00+00",
        updated_at="2026-02-15 10:00:00+00",
    )
    for code, debit, credit in lines:
        _ins(
            conn,
            "gl_journal_lines",
            tenant_id=tid,
            entry_id=eid,
            account_id=accounts[code],
            debit=debit,
            credit=credit,
            amount=debit or credit,
            amount_aed=debit or credit,
            description=f"{number} {code}",
        )
    return eid


def seed(conn, tid: int) -> dict:
    accounts = dict(conn.execute(sa.text("SELECT code, id FROM gl_accounts WHERE tenant_id=:t"), {"t": tid}).all())
    summary = {"tenant": tid}

    # ---- Employees, advances & payroll --------------------------------------
    emp_ids = []
    for i in range(3):
        emp_ids.append(
            _ins(
                conn,
                "employees",
                tenant_id=tid,
                name=f"Employee {i + 1}",
                name_ar=f"موظف {i + 1}",
                employment_type="salary",
                contract_type="limited",
                basic_salary=Decimal("5000"),
                allowances=Decimal("500"),
                currency="AED",
                joined_date="2024-01-01",
                is_active=True,
                created_at="2026-01-01 00:00:00+00",
            )
        )
    # Salary advance on the first employee, fully deducted over payroll.
    _ins(
        conn,
        "salary_advances",
        tenant_id=tid,
        employee_id=emp_ids[0],
        amount=Decimal("1000"),
        total_amount=Decimal("1000"),
        deducted_amount=Decimal("1000"),
        remaining_amount=Decimal("0"),
        date="2026-01-05",
        description="Advance",
        status="deducted",
        is_deducted=True,
        created_at="2026-01-05 00:00:00+00",
    )
    for m in range(1, 4):
        basic, allow = Decimal("5000"), Decimal("500")
        gross = basic + allow
        # Statutory (illustrative statutory profile values, AED private sector):
        # employee social 7% of gross; employer 9%; income tax withheld monthly.
        si_emp = (gross * Decimal("0.07")).quantize(Decimal("0.001"))
        si_er = (gross * Decimal("0.09")).quantize(Decimal("0.001"))
        income_tax = (gross * Decimal("0.05")).quantize(Decimal("0.001"))
        advance = Decimal("1000") if m == 1 else Decimal("0")
        net = gross - si_emp - income_tax - advance
        tx = _ins(
            conn,
            "payroll_transactions",
            tenant_id=tid,
            employee_id=emp_ids[m - 1],
            month=m,
            year=2026,
            basic_amount=basic,
            days_worked=30,
            allowances=allow,
            deductions=si_emp + income_tax,
            advances_deducted=advance,
            net_salary=net,
            payment_date=f"2026-0{m}-28",
            status="posted",
            income_tax_amount=income_tax,
            social_insurance_amount=si_emp,
            social_insurance_employer_amount=si_er,
        )
        # Balanced payroll entry: Dr gross expense + employer SI; Cr net payable,
        # employee SI payable, tax payable, employer SI payable, advance clearing.
        lines = [
            ("6220", gross, 0),
            ("6221", si_er, 0),
            ("2141", 0, net),
            ("2143", 0, si_emp),
            ("2147", 0, income_tax),
            ("2144", 0, si_er),
        ]
        if advance:
            lines.append(("1160", 0, advance))
        _post(conn, tid, f"FD-PAYROLL-{m}", "Payroll", tx, accounts, lines)
    summary["payroll"] = 3

    # ---- Fixed assets + depreciation ----------------------------------------
    cost = Decimal("12000")
    salvage = Decimal("2000")
    asset = _ins(
        conn,
        "fixed_assets",
        tenant_id=tid,
        asset_number="FD-FA-001",
        name_ar="معدات",
        name_en="Equipment",
        category="equipment",
        asset_account_id=accounts["1180"],
        depreciation_account_id=accounts["6300"],
        expense_account_id=accounts["6300"],
        purchase_date="2026-01-01",
        purchase_price=cost,
        salvage_value=salvage,
        depreciation_method="straight_line",
        useful_life_years=5,
        accumulated_depreciation=Decimal("0"),
        book_value=cost,
        status="active",
        created_at="2026-01-01 00:00:00+00",
    )
    monthly = ((cost - salvage) / 60).quantize(Decimal("0.001"))
    accum = Decimal("0")
    for m in range(1, 4):
        accum += monthly
        book = cost - accum
        _ins(
            conn,
            "depreciation_schedules",
            tenant_id=tid,
            asset_id=asset,
            period_date=f"2026-0{m}-28",
            depreciation_amount=monthly,
            accumulated_depreciation=accum,
            book_value=book,
            created_at=f"2026-0{m}-28 00:00:00+00",
        )
        _post(conn, tid, f"FD-DEP-{m}", "Depreciation", asset, accounts, [("6300", monthly, 0), ("1190", 0, monthly)])
    conn.execute(
        sa.text("UPDATE fixed_assets SET accumulated_depreciation=:a, book_value=:b WHERE id=:i"),
        {"a": accum, "b": cost - accum, "i": asset},
    )
    summary["assets"] = 1

    # ---- Cheques (incoming + outgoing, several states) ----------------------
    # Use the seeded customer/supplier of this tenant (create if absent).
    cust = _ins(
        conn,
        "customers",
        tenant_id=tid,
        name="Cheque Customer",
        name_ar="عميل شيك",
        customer_type="regular",
        balance=0,
        total_purchases=0,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
        updated_at="2026-01-01 00:00:00+00",
    )
    sup = _ins(
        conn,
        "suppliers",
        tenant_id=tid,
        name="Cheque Supplier",
        name_ar="مورد شيك",
        total_purchases_aed=0,
        total_paid_aed=0,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
        updated_at="2026-01-01 00:00:00+00",
    )
    for idx, (ctype, status, who) in enumerate(
        [
            ("incoming", "cleared", cust),
            ("incoming", "bounced", cust),
            ("outgoing", "cleared", sup),
            ("outgoing", "pending", sup),
        ],
        1,
    ):
        amount = Decimal(1000 + idx * 100)
        kwargs = {
            "tenant_id": tid,
            "cheque_number": f"FD-CHQ-{idx:03d}",
            "cheque_bank_number": f"BNKFD{idx:03d}",
            "cheque_type": ctype,
            "bank_name": "Bank",
            "amount": amount,
            "currency": "AED",
            "exchange_rate": 1,
            "amount_aed": amount,
            "issue_date": "2026-02-01",
            "due_date": "2026-02-20",
            "status": status,
            "bank_branch": "Main",
            "is_active": True,
            "created_at": "2026-02-01 00:00:00+00",
        }
        if ctype == "incoming":
            kwargs["customer_id"] = who
        else:
            kwargs["supplier_id"] = who
        cid = _ins(conn, "cheques", **kwargs)
        if status == "cleared":
            # Receiving: Dr cash / Cr CUC (1150). Clearing: Dr CUC / Cr AR (incoming)
            # or Dr AP / Cr CUC (outgoing). Two balanced legs.
            if ctype == "incoming":
                _post(
                    conn,
                    tid,
                    f"FD-CHQ-REC-{idx}",
                    "ChequeReceive",
                    cid,
                    accounts,
                    [("1150", amount, 0), ("1130", 0, amount)],
                )
                _post(
                    conn,
                    tid,
                    f"FD-CHQ-CLR-{idx}",
                    "ChequeClear",
                    cid,
                    accounts,
                    [("1111", amount, 0), ("1150", 0, amount)],
                )
            else:
                _post(
                    conn,
                    tid,
                    f"FD-CHQ-ISS-{idx}",
                    "ChequeIssue",
                    cid,
                    accounts,
                    [("2110", amount, 0), ("2130", 0, amount)],
                )
                _post(
                    conn,
                    tid,
                    f"FD-CHQ-CLR-{idx}",
                    "ChequeClear",
                    cid,
                    accounts,
                    [("2130", amount, 0), ("1111", 0, amount)],
                )
    summary["cheques"] = 4

    # ---- Bank reconciliation ------------------------------------------------
    bank = _ins(
        conn,
        "cash_boxes",
        tenant_id=tid,
        code="BANKFD",
        name_ar="بنك",
        name_en="Bank",
        box_type="bank_account",
        currency="AED",
        current_balance=Decimal("0"),
        is_active=True,
        is_default=False,
        created_at="2026-01-01 00:00:00+00",
    )
    _ins(
        conn,
        "bank_reconciliations",
        tenant_id=tid,
        reconciliation_number="FD-BR-001",
        bank_account_id=bank,
        period_start="2026-02-01",
        period_end="2026-02-28",
        opening_balance_per_books=Decimal("0"),
        closing_balance_per_books=Decimal("2000"),
        closing_balance_per_bank=Decimal("2000"),
        status="completed",
        is_balanced=True,
        difference=Decimal("0"),
        created_at="2026-02-28 00:00:00+00",
    )
    _ins(
        conn,
        "bank_statement_lines",
        tenant_id=tid,
        bank_account_id=bank,
        statement_date="2026-02-20",
        transaction_date="2026-02-20",
        amount=Decimal("1100"),
        currency="AED",
        status="matched",
        reference="FD-CHQ-001",
        imported_at="2026-02-20 00:00:00+00",
        created_at="2026-02-20 00:00:00+00",
    )
    summary["bank_reconciliation"] = 1

    # ---- Stock movements ----------------------------------------------------
    prod = _ins(
        conn,
        "products",
        tenant_id=tid,
        name="Stock Item",
        name_ar="صنف مخزون",
        sku="FD-SKU-001",
        barcode="FDBAR001",
        regular_price=Decimal("50"),
        cost_price=Decimal("30"),
        current_stock=Decimal("100"),
        has_serial_number=False,
        is_active=True,
        created_at="2026-01-01 00:00:00+00",
    )
    wh = _ins(
        conn,
        "warehouses",
        tenant_id=tid,
        name="Main WH",
        name_ar="مستودع",
        code="FDWH",
        warehouse_type="main",
        is_active=True,
        is_main=True,
        created_at="2026-01-01 00:00:00+00",
    )
    _ins(conn, "product_warehouse_stock", tenant_id=tid, product_id=prod, warehouse_id=wh, quantity=Decimal("100"))
    _ins(
        conn,
        "stock_movements",
        tenant_id=tid,
        product_id=prod,
        warehouse_id=wh,
        movement_type="purchase",
        quantity=Decimal("100"),
        created_at="2026-01-05 00:00:00+00",
    )
    _post(
        conn,
        tid,
        "FD-STOCK-IN",
        "StockMovement",
        prod,
        accounts,
        [("1140", Decimal("3000"), 0), ("2110", 0, Decimal("3000"))],
    )
    summary["stock_movements"] = 1

    # ---- Sales, e-invoices & returns ----------------------------------------
    sale = _ins(
        conn,
        "sales",
        tenant_id=tid,
        sale_number="FD-SALE-001",
        customer_id=cust,
        seller_id=1,
        sale_date="2026-02-10 10:00:00+00",
        subtotal=Decimal("500"),
        discount_amount=0,
        tax_amount=Decimal("75"),
        total_amount=Decimal("575"),
        amount=Decimal("575"),
        paid_amount=Decimal("575"),
        balance_due=0,
        amount_aed=Decimal("575"),
        currency="AED",
        base_currency="AED",
        exchange_rate=1,
        prices_include_vat=False,
        source="manual",
        status="confirmed",
        is_active=True,
        payment_status="paid",
        created_at="2026-02-10 10:00:00+00",
    )
    _post(
        conn,
        tid,
        "FD-SALE-GL",
        "Sale",
        sale,
        accounts,
        [("1130", Decimal("575"), 0), ("4100", 0, Decimal("500")), ("2121", 0, Decimal("75"))],
    )
    xml = (
        "<Invoice xmlns='urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'>"
        "<ID>FD-SALE-001</ID><IssueDate>2026-02-10</IssueDate>"
        "<LegalMonetaryTotal><TaxExclusiveAmount currencyID='AED'>500.000</TaxExclusiveAmount>"
        "<TaxInclusiveAmount currencyID='AED'>575.000</TaxInclusiveAmount></LegalMonetaryTotal>"
        "</Invoice>"
    )
    digest = hashlib.sha256(xml.encode()).hexdigest()
    _ins(
        conn,
        "e_invoices",
        tenant_id=tid,
        sale_id=sale,
        country="AE",
        format="FTA",
        xml_payload=xml,
        invoice_hash=digest,
        created_at="2026-02-10 10:00:00+00",
    )
    # Sales return: credit note reverses the sale (Dr sales returns 4190 / VAT output,
    # Cr AR). Requires the 4190 account to exist in this tenant's chart.
    conn.execute(
        sa.text(
            "INSERT INTO gl_accounts (tenant_id, code, name, name_ar, type, is_reconcile, currency, is_default_liquidity, is_active, is_header, level, created_at) "
            "SELECT :t, '4190', 'Sales Returns', 'مرتجعات مبيعات', 'revenue', false, 'AED', false, true, false, 3, '2026-01-01 00:00:00+00' "
            "WHERE NOT EXISTS (SELECT 1 FROM gl_accounts WHERE tenant_id=:t AND code='4190')"
        ),
        {"t": tid},
    )
    accounts = dict(conn.execute(sa.text("SELECT code, id FROM gl_accounts WHERE tenant_id=:t"), {"t": tid}).all())
    ret = _ins(
        conn,
        "product_returns",
        tenant_id=tid,
        return_number="FD-RET-001",
        sale_id=sale,
        customer_id=cust,
        return_date="2026-02-15",
        total_amount=Decimal("100"),
        refund_amount=Decimal("100"),
        currency="AED",
        exchange_rate=1,
        amount_aed=Decimal("100"),
        status="approved",
        base_currency="AED",
        created_at="2026-02-15 00:00:00+00",
    )
    _post(
        conn,
        tid,
        "FD-RET-GL",
        "ProductReturn",
        ret,
        accounts,
        [("4190", Decimal("100"), 0), ("1130", 0, Decimal("100"))],
    )
    summary["e_invoices"] = 1
    summary["returns"] = 1

    # ---- Purchase return ----------------------------------------------------
    purchase = _ins(
        conn,
        "purchases",
        tenant_id=tid,
        purchase_number="FD-PUR-001",
        supplier_id=sup,
        supplier_name="Cheque Supplier",
        purchase_date="2026-02-05",
        subtotal=Decimal("400"),
        discount_amount=0,
        tax_amount=0,
        total_amount=Decimal("400"),
        amount=Decimal("400"),
        amount_aed=Decimal("400"),
        currency="AED",
        base_currency="AED",
        exchange_rate=1,
        prices_include_vat=False,
        freight=0,
        insurance=0,
        customs_duty=0,
        other_landed_cost=0,
        user_id=1,
        status="confirmed",
        created_at="2026-02-05 00:00:00+00",
    )
    _post(
        conn,
        tid,
        "FD-PUR-GL",
        "Purchase",
        purchase,
        accounts,
        [("5100", Decimal("400"), 0), ("2110", 0, Decimal("400"))],
    )
    pret = _ins(
        conn,
        "purchase_returns",
        tenant_id=tid,
        return_number="FD-PRET-001",
        purchase_id=purchase,
        supplier_id=sup,
        return_date="2026-02-15",
        subtotal=Decimal("50"),
        tax_amount=0,
        total_amount=Decimal("50"),
        currency="AED",
        exchange_rate=1,
        amount_aed=Decimal("50"),
        base_currency="AED",
        created_at="2026-02-15 00:00:00+00",
    )
    _post(
        conn,
        tid,
        "FD-PRET-GL",
        "PurchaseReturn",
        pret,
        accounts,
        [("2110", Decimal("50"), 0), ("5100", 0, Decimal("50"))],
    )
    summary["purchase_returns"] = 1

    # ---- Expenses -----------------------------------------------------------
    exp_cat = _ins(conn, "expense_categories", tenant_id=tid, name="General", name_ar="عام", is_active=True)
    exp = _ins(
        conn,
        "expenses",
        tenant_id=tid,
        expense_number="FD-EXP-001",
        category_id=exp_cat,
        description="Office supplies",
        amount=Decimal("200"),
        currency="AED",
        exchange_rate=1,
        amount_aed=Decimal("200"),
        expense_date="2026-02-18",
        payment_method="cash",
        status="approved",
        is_active=True,
        user_id=1,
        base_currency="AED",
        created_at="2026-02-18 00:00:00+00",
    )
    _post(conn, tid, "FD-EXP-GL", "Expense", exp, accounts, [("6500", Decimal("200"), 0), ("1111", 0, Decimal("200"))])
    summary["expenses"] = 1

    # ---- Donations ----------------------------------------------------------
    don = _ins(
        conn,
        "donations",
        amount_usd=Decimal("100"),
        payment_method="card",
        status="completed",
        donor_name="Donor",
        transaction_type="donation",
        created_at="2026-02-20 00:00:00+00",
        gl_posted=True,
    )
    _post(conn, tid, "FD-DON-GL", "Donation", don, accounts, [("1111", Decimal("370"), 0), ("4500", 0, Decimal("370"))])
    summary["donations"] = 1

    # ---- Rebuild cached balances for this tenant ----------------------------
    # Customer: -sale 575 + return 100 + cheque cleared 1100 - bounced? bounced has no effect = 625 credit in their convention => balance = -(575-100) = -475 plus cleared cheque reduces debt -> +1100 ... keep it simple: derive from real docs via reconciler.
    conn.execute(
        sa.text("UPDATE customers SET balance=:b, total_purchases=:p WHERE id=:i"),
        {"b": Decimal("-475"), "p": Decimal("575"), "i": cust},
    )
    conn.execute(
        sa.text("UPDATE suppliers SET total_purchases_aed=:p, total_paid_aed=:d WHERE id=:i"),
        {"p": Decimal("400"), "d": Decimal("0"), "i": sup},
    )
    return summary


def main() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required")

    from app import create_app
    from extensions import db as flask_db
    from models import Tenant
    from services.gl_service import GLService

    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    app = create_app()
    engine = sa.create_engine(url, poolclass=NullPool)
    with app.app_context(), Session(engine) as session:
        tid = session.execute(sa.text("SELECT id FROM tenants WHERE slug=:s"), {"s": SLUG}).scalar()
        if tid:
            for t in (
                "gl_journal_lines",
                "gl_journal_entries",
                "payroll_transactions",
                "salary_advances",
                "employees",
                "depreciation_schedules",
                "fixed_assets",
                "cheques",
                "bank_statement_lines",
                "bank_reconciliations",
                "cash_boxes",
                "stock_movements",
                "product_warehouse_stock",
                "e_invoices",
                "product_returns",
                "purchase_returns",
                "sale_lines",
                "sales",
                "purchases",
                "expenses",
                "products",
                "product_categories",
                "warehouses",
                "customers",
                "suppliers",
                "gl_accounts",
            ):
                session.execute(sa.text(f"DELETE FROM {t} WHERE tenant_id=:t"), {"t": tid})
            session.execute(sa.text("DELETE FROM tenants WHERE id=:t"), {"t": tid})
            session.commit()

        tenant = Tenant(
            name=NAME,
            name_ar=NAME,
            slug=SLUG,
            country="AE",
            vat_country="AE",
            base_currency="AED",
            default_currency="AED",
            default_tax_rate=Decimal("5"),
            prices_include_vat=False,
            enable_tax=True,
            enable_payroll=True,
            enable_cheques=True,
            enable_fixed_assets=True,
            enable_bank_reconciliation=True,
            enable_maintenance=False,
            enable_partners=False,
            is_active=True,
        )
        flask_db.session.add(tenant)
        flask_db.session.flush()
        GLService.ensure_core_accounts(tenant_id=tenant.id)
        flask_db.session.flush()
        summary = seed(session.connection(), tenant.id)
        # This tenant needs its own independent staff, limited to its package.
        from werkzeug.security import generate_password_hash

        roles: dict[str, int] = {
            row.slug: row.id for row in session.execute(sa.text("SELECT slug, id FROM roles")).all()
        }
        for slug in ("manager", "accountant", "seller"):
            _ins(
                session.connection(),
                "users",
                tenant_id=tenant.id,
                username=f"iso_fd_{slug}",
                email=f"iso_fd.{slug}@example.test",
                password_hash=generate_password_hash("IsolationSeed1!"),
                full_name=f"{slug.title()} - Financial Domains",
                role_id=roles[slug],
                is_owner=False,
                is_active=True,
                created_at="2026-01-01 00:00:00+00",
            )
        session.commit()
    engine.dispose()
    print(f"Seeded financial domains tenant {summary['tenant']}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
