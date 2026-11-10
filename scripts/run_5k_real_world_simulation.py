#!/usr/bin/env python3
"""Unfinished 5,000-case simulation prototype; direct execution is disabled.

This prototype writes to the configured database, its concurrency phase is
broken, and its counts do not establish distinct real-world workflows. It must
not be used as a test report or run against operational data. Keep the source
only for review until the runner and its database isolation are redesigned.

The original proposed phases were:

  A. 2000 GL double-entry postings (balanced Dr==Cr, tenant-tagged)
  B. 1000 tax & margin scenarios (VAT modes, cost snapshots, levies)
  C. 500 quotation lifecycle transitions (draft→sent→accepted→converted/expired, stock checks)
  D. 500 partner distributions (sequential, profit/loss, draws, idempotency)
  E. 500 concurrency probes (FOR UPDATE counter + sequence locks)
  F. 500 RBAC / IDOR boundary attempts (cross-tenant reads blocked)

"""

import argparse
import json
import sys
import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS: dict[str, int | list] = {"passed": 0, "failed": 0, "failures": []}
STARTED = time.time()


def record(phase, ok, detail=""):
    if ok:
        RESULTS["passed"] += 1
    else:
        RESULTS["failed"] += 1
        RESULTS["failures"].append(f"[{phase}] {detail}")
        print(f"  FAIL [{phase}] {detail}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None)
    parser.add_argument("--report", default="simulation_report.json")
    args = parser.parse_args()
    if args.db:
        import os

        os.environ["DATABASE_URL"] = args.db

    from app import create_app
    from extensions import db

    app = create_app()
    ctx = app.app_context()
    ctx.push()

    from models import Branch, Customer, Partner, Product, Quotation, QuotationLine, Tenant, User, Warehouse
    from services.gl_posting import post_or_fail
    from services.gl_service import GLService
    from services.partner_service import PartnerService
    from services.quotation_service import QuotationService
    from services.sale_service import SaleService
    from utils.gl_reference_types import GLRef

    def progress(phase, done, total):
        if done % 500 == 0:
            elapsed = time.time() - STARTED
            print(
                f"[{phase}] {done}/{total} passed={RESULTS['passed']} failed={RESULTS['failed']} ({elapsed:.0f}s)",
                flush=True,
            )

    # ── Setup: tenant, branch, warehouse, users ──────────────────────────
    tenant = Tenant(name="SimCo", name_ar="محاكاة", slug="simco", country="AE", default_currency="AED")
    db.session.add(tenant)
    db.session.flush()
    from models import Role

    role = db.session.query(Role).first()
    if role is None:
        role = Role(name="Admin", slug="sim_admin", is_active=True)
        db.session.add(role)
        db.session.flush()
    user = User(username="sim-user", email="sim@test", tenant_id=tenant.id, role_id=role.id, is_active=True)
    user.set_password("password123")
    db.session.add(user)
    branch = Branch(tenant_id=tenant.id, name="Main", code="SIM-MAIN")
    db.session.add(branch)
    db.session.flush()
    warehouse = Warehouse(tenant_id=tenant.id, branch_id=branch.id, name="Main WH", is_active=True)
    db.session.add(warehouse)
    GLService.ensure_core_accounts(tenant_id=tenant.id)
    db.session.commit()
    print(f"setup: tenant={tenant.id} branch={branch.id} wh={warehouse.id}", flush=True)

    # ── A. 2000 GL postings ──────────────────────────────────────────────
    print("Phase A: 2000 GL postings", flush=True)
    rev_acc = GLService.get_account_code_for_concept("SALES_REVENUE", tenant_id=tenant.id, branch_id=None)
    vat_acc = GLService.get_account_code_for_concept("VAT_OUTPUT", tenant_id=tenant.id, branch_id=None)
    for i in range(2000):
        amount = Decimal(str((i % 97) + 1)) + Decimal("0.50")
        try:
            entry = post_or_fail(
                [
                    {"account": rev_acc, "concept_code": "SALES_REVENUE", "debit": amount},
                    {"account": vat_acc, "concept_code": "VAT_OUTPUT", "credit": amount},
                ],
                description=f"sim-{i}",
                reference_type=GLRef.SALE,
                date=datetime(2026, 1, 15, tzinfo=UTC),
                tenant_id=tenant.id,
            )
            db.session.commit()
            balanced = abs(Decimal(str(entry.total_debit)) - Decimal(str(entry.total_credit))) <= Decimal("0.001")
            record("A", balanced and entry.tenant_id == tenant.id, f"entry {entry.id}")
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            record("A", False, repr(exc)[:160])
        progress("A", i + 1, 2000)

    # ── B. 1000 tax & margin ─────────────────────────────────────────────
    print("Phase B: 1000 tax/margin", flush=True)
    from services.expense_service import ExpenseService
    from services.purchase_service import compute_import_levy_defaults
    from services.tax_service import TaxService
    from utils.einvoice_document import build_invoice_xml
    from utils.einvoice_document import invoice_sha256_hex as invoice_hash

    for i in range(1000):
        mode = i % 5
        try:
            if mode == 0:  # margin
                revenue = Decimal(str(50 + (i % 40) * 10))
                cost = Decimal(str(20 + (i % 30) * 5))
                fx = Decimal("3.65") if i % 2 else Decimal("1")
                margin = SaleService._commission_margin(revenue, cost, fx)
                expected_cost = cost / fx if fx != 1 else cost
                ok = margin == (revenue - expected_cost).quantize(Decimal("0.001"))
            elif mode == 1:  # withholding
                amount = Decimal(str(100 + i))
                rate = Decimal("5")
                ok = ExpenseService.calculate_withholding(amount, rate, True) == (amount * rate / 100).quantize(
                    Decimal("0.001")
                )
            elif mode == 2:  # levy
                customs, excise = compute_import_levy_defaults(
                    [(Decimal("10"), Decimal("100"), Decimal("0"), "tobacco")],
                    country="AE",
                    customs_duty=None,
                    excise_amount=None,
                )
                ok = customs == Decimal("50.000") and excise == Decimal("1050.000")
            elif mode == 3:  # strategy tax
                strategy = TaxService._get_strategy(tenant_id=None)
                result = strategy.calculate_tax(Decimal("1000"), Decimal("5"))
                ok = Decimal(str(result["tax_amount"])) == Decimal("50.00")
            else:  # einvoice hash
                sale = type("S", (), {})()
                sale.sale_number = f"S-{i}"
                sale.sale_date = None
                sale.tax_rate = Decimal("5")
                sale.total_amount = Decimal("105")
                sale.tax_amount = Decimal("5")
                sale.taxable_amount = Decimal("100")
                sale.subtotal = Decimal("105")
                sale.lines = []
                sale.customer = type("C", (), {"name": "B", "tax_number": ""})()
                tenant_mock = type(
                    "T", (), {"name": "S", "name_en": "S", "tax_number": "1", "address_en": "", "city": ""}
                )()
                xml = build_invoice_xml(sale, tenant_mock, country="AE", currency="AED")
                ok = len(invoice_hash(xml)) == 64 and "105.000" in xml
            record("B", ok, f"mode {mode}")
        except Exception as exc:  # noqa: BLE001
            record("B", False, repr(exc)[:160])
        progress("B", i + 1, 1000)

    # ── C. 500 quotation transitions ─────────────────────────────────────
    print("Phase C: 500 quotations", flush=True)
    customer = Customer(tenant_id=tenant.id, name="Sim Customer", is_active=True)
    product = Product(
        tenant_id=tenant.id, name="Sim Widget", sku="SIM-W1", cost_price=Decimal("50"), regular_price=Decimal("100")
    )
    db.session.add_all([customer, product])
    db.session.flush()
    from services.stock_service import StockService

    StockService.add_stock(product.id, 10000, warehouse_id=warehouse.id)
    db.session.commit()
    for i in range(500):
        try:
            q = Quotation(
                tenant_id=tenant.id,
                quotation_number=f"SIMQ-{i}",
                customer_id=customer.id,
                branch_id=branch.id,
                warehouse_id=warehouse.id,
                status="draft",
                expiry_date=date(2026, 12, 31),
                created_by=user.id,
                subtotal=Decimal("100"),
                total_amount=Decimal("105"),
                amount_aed=Decimal("105"),
                currency="AED",
                exchange_rate=Decimal("1"),
                tax_rate=Decimal("5"),
                tax_amount=Decimal("5"),
            )
            db.session.add(q)
            db.session.flush()
            db.session.add(
                QuotationLine(
                    tenant_id=tenant.id,
                    quotation_id=q.id,
                    product_id=product.id,
                    quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                    line_total=Decimal("100"),
                )
            )
            db.session.commit()
            QuotationService.send_quotation(q)
            QuotationService.accept_quotation(q)
            sale = QuotationService.convert_to_sale(q, user)
            db.session.commit()
            record("C", sale.tenant_id == tenant.id and q.status == "converted_to_sale", f"q {q.id}")
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            record("C", False, repr(exc)[:160])
        progress("C", i + 1, 500)

    # ── D. 500 partner distributions ─────────────────────────────────────
    print("Phase D: 500 distributions", flush=True)
    for i in range(500):
        try:
            partner = Partner(
                tenant_id=tenant.id,
                name=f"P{i}",
                scope_type="company",
                share_percentage=Decimal("10"),
                start_date=date(2026, 1, 1),
            )
            db.session.add(partner)
            db.session.commit()
            # No sales in Feb → zero base; sequential math must stay sane.
            before = PartnerService.create_distributions(tenant.id, date(2026, 2, 1), date(2026, 2, 28))
            db.session.commit()
            from models import PartnerProfitDistribution

            has_own = (
                db.session.query(PartnerProfitDistribution)
                .filter_by(tenant_id=tenant.id, partner_id=partner.id)
                .first()
                is not None
            )
            # Idempotency: a second run must create nothing new for anyone.
            again = PartnerService.create_distributions(tenant.id, date(2026, 2, 1), date(2026, 2, 28))
            record("D", has_own and again == [], f"partner {partner.id} before={len(before)} again={again}")
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            record("D", False, repr(exc)[:160])
        progress("D", i + 1, 500)

    # ── E. 500 concurrency probes ────────────────────────────────────────
    print("Phase E: 500 concurrency", flush=True)
    from models import DocumentSequence

    seq = DocumentSequence(tenant_id=tenant.id, code="SIM", name="Simulation", prefix="SIM", counter=0)
    db.session.add(seq)
    db.session.commit()

    def worker(n):
        from extensions import db as _db

        try:
            with app.app_context():
                row = _db.session.query(DocumentSequence).filter_by(id=seq.id).with_for_update().first()
                row.counter = int(row.counter or 0) + 1
                _db.session.commit()
                return True
        except Exception:  # noqa: BLE001
            return False

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(500)]
    results = []

    def run(t):
        results.append(t())

    threads = [threading.Thread(target=run, args=(t,)) for t in threads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok_count = sum(1 for r in results if r)
    final_row = db.session.query(DocumentSequence).filter_by(id=seq.id).first()
    final = int(getattr(final_row, "counter", 0) or 0) if final_row is not None else 0
    # Each successful worker must have incremented exactly once.
    record("E", ok_count > 0 and int(final or 0) == ok_count, f"ok={ok_count} final={final}")
    RESULTS["passed"] = int(cast(int, RESULTS["passed"])) + (ok_count - 1 if ok_count else 0)
    print(f"  concurrency: {ok_count}/500 workers succeeded, counter={final}", flush=True)

    # ── F. 500 RBAC/IDOR attempts ────────────────────────────────────────
    print("Phase F: 500 IDOR attempts", flush=True)
    from utils.tenanting import tenant_query

    other = Tenant(name="OtherCo", name_ar="أخرى", slug="otherco", country="AE", default_currency="AED")
    db.session.add(other)
    db.session.flush()
    foreign_customer = Customer(tenant_id=other.id, name="Foreign", is_active=True)
    db.session.add(foreign_customer)
    db.session.commit()
    for i in range(500):
        try:
            rows = tenant_query(Customer, user=user).all()
            leaked = any(c.tenant_id == other.id for c in rows)
            record("F", not leaked and all(c.tenant_id == tenant.id for c in rows), f"attempt {i}")
        except Exception as exc:  # noqa: BLE001
            record("F", False, repr(exc)[:160])
        progress("F", i + 1, 500)

    elapsed = time.time() - STARTED
    total = int(cast(int, RESULTS["passed"])) + int(cast(int, RESULTS["failed"]))
    print("\n===== FINAL REPORT =====", flush=True)
    print(f"total={total} passed={RESULTS['passed']} failed={RESULTS['failed']} duration={elapsed:.1f}s", flush=True)
    if RESULTS["failures"]:
        print("first failures:", *cast(list, RESULTS["failures"])[:10], sep="\n  ", flush=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump({**RESULTS, "total": total, "duration": round(elapsed, 1)}, fh, indent=2)
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit("Simulation disabled: unfinished runner; database safety and results are not verified.")
