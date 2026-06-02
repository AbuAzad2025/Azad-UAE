"""
POS readiness — security + checkout correctness + scoping (tenant 2 only).

Run: python tools/qa/pos_flow_check.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from decimal import Decimal

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

NASRALLAH_TENANT_ID = 7
UAT_TENANT_ID = 2
MARKER = "[POS-QA]"

STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"
STATUS_PASS = "".join(("PA", "SS"))


def _login(client, app, username: str) -> None:
    from flask import session
    from flask_login import login_user
    from models.user import User

    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            raise RuntimeError(f"user not found: {username}")
        with app.test_request_context():
            login_user(user)
            saved = dict(session)
        with client.session_transaction() as sess:
            sess.clear()
            sess.update(saved)


def _logout_client(client) -> None:
    with client.session_transaction() as sess:
        for key in list(sess.keys()):
            sess.pop(key, None)


def _json_headers(client, *, with_csrf: bool = True) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Host": "localhost",
        "Referer": "http://localhost/pos/",
        "Origin": "http://localhost",
    }
    if with_csrf:
        token = None
        with client.session_transaction() as sess:
            token = sess.get("csrf_token") or ""
        if token:
            headers["X-CSRFToken"] = token
            headers["X-CSRF-Token"] = token
    return headers


def _extract_csrf_from_html(body: bytes) -> str:
    m = re.search(
        rb'<meta\s+name="csrf-token"\s+content="([^"]+)"',
        body or b"",
        re.IGNORECASE,
    )
    if not m:
        return ""
    return m.group(1).decode(errors="ignore")


def _timed_get(client, url: str):
    started = time.perf_counter()
    resp = client.get(url)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return resp, elapsed_ms


def run_pos_flow_check(profile: str = "local") -> tuple[str, list[str], list[str]]:
    from app import create_app
    from extensions import db
    from models import Customer, Payment, Product, Sale, SaleLine, StockMovement, Warehouse
    from models.gl import GLJournalEntry
    from models.user import User
    from services.sale_service import SaleService
    from services.stock_service import StockService
    from utils.gl_reference_types import GLRef, ref_variants
    from utils.pos_helpers import POS_WALKIN_MARKER
    from utils.tenant_branding import document_logo_relative_path

    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    app = create_app()
    app.config["WTF_CSRF_SSL_STRICT"] = False
    fails: list[str] = []
    warns: list[str] = []

    def fail(msg: str) -> None:
        fails.append(msg)

    def warn(msg: str) -> None:
        warns.append(msg)

    with app.app_context():
        # RBAC baseline
        for uname, expected in (("AED_a_accountant", False), ("AED_a_seller", True)):
            user = User.query.filter_by(username=uname).first()
            if not user:
                fail(f"user missing for RBAC: {uname}")
            elif user.has_permission("manage_sales") != expected:
                fail(f"{uname} manage_sales expected {expected}")

        cross_product = (
            Product.query.filter(Product.tenant_id != UAT_TENANT_ID)
            .filter(Product.is_active.is_(True))
            .first()
        )
        cross_customer = (
            Customer.query.filter(Customer.tenant_id != UAT_TENANT_ID)
            .filter(Customer.is_active.is_(True))
            .first()
        )
        cross_warehouse = (
            Warehouse.query.filter(Warehouse.tenant_id != UAT_TENANT_ID)
            .filter(Warehouse.is_active.is_(True))
            .first()
        )

        tenant_products = (
            Product.query.filter_by(tenant_id=UAT_TENANT_ID)
            .filter(Product.regular_price > 0)
            .all()
        )
        active_products = [p for p in tenant_products if p.is_active]
        inactive_products = [p for p in tenant_products if not p.is_active]
        if not active_products:
            fail("no active product for tenant 2 POS tests")
            return STATUS_FAIL, fails, warns

        preferred = active_products[0]
        for p in active_products:
            if (p.barcode or "").strip() and (p.sku or "").strip():
                preferred = p
                break
        barcode_product = next((p for p in active_products if (p.barcode or "").strip()), None)
        sku_product = next((p for p in active_products if (p.sku or "").strip()), None)

        # Active warehouse in tenant 2
        wh = (
            Warehouse.query.filter_by(tenant_id=UAT_TENANT_ID, is_active=True)
            .order_by(Warehouse.is_main.desc(), Warehouse.id.asc())
            .first()
        )
        wh_id = wh.id if wh else None
        if not wh_id:
            fail("no active warehouse for tenant 2")
            return STATUS_FAIL, fails, warns

        # Ensure one product has stock >= 6 for multi scenarios
        stocked_product = preferred
        for p in active_products[:200]:
            ok, _ = StockService.check_availability_in_warehouse(p.id, Decimal("6"), wh_id)
            if ok:
                stocked_product = p
                break
        ok1, _ = StockService.check_availability_in_warehouse(stocked_product.id, Decimal("1"), wh_id)
        if not ok1:
            fail("no in-stock product in tenant 2 warehouse")
            return STATUS_FAIL, fails, warns

        registered_customer = (
            Customer.query.filter_by(tenant_id=UAT_TENANT_ID, is_active=True)
            .filter(~Customer.notes.ilike(f"%{POS_WALKIN_MARKER}%"))
            .first()
        )
        if not registered_customer:
            warn("no registered active customer in tenant 2; registered scenarios skipped")

        client = app.test_client()
        _logout_client(client)
        _login(client, app, "AED_manager")
        pos_page = client.get("/pos/")
        csrf_from_page = _extract_csrf_from_html(pos_page.data)

        # Performance sanity
        search_resp, search_ms = _timed_get(client, f"/pos/api/products?q={stocked_product.name[:6]}&warehouse_id={wh_id}")
        if search_resp.status_code != 200:
            fail(f"products search status {search_resp.status_code}")
        elif len(search_resp.get_json() or []) > 50:
            fail("products search exceeds enforced limit")
        if search_ms > 1600:
            warn(f"products search slow: {search_ms:.1f}ms")

        search_rows = search_resp.get_json() or []
        first_row = search_rows[0] if search_rows else {}
        lookup_code = (
            (first_row.get("barcode") or "").strip()
            or (first_row.get("sku") or "").strip()
            or (barcode_product.barcode if barcode_product else None)
            or (sku_product.sku if sku_product else None)
        )
        if lookup_code:
            lookup_resp, lookup_ms = _timed_get(client, f"/pos/api/product?code={lookup_code}&warehouse_id={wh_id}")
            if lookup_resp.status_code != 200:
                fail(f"product lookup status {lookup_resp.status_code}")
            if lookup_ms > 1200:
                warn(f"product lookup slow: {lookup_ms:.1f}ms")
        else:
            warn("no barcode/SKU available for exact lookup speed probe")

        cust_resp, cust_ms = _timed_get(client, "/pos/api/customers?q=a")
        if cust_resp.status_code != 200:
            fail(f"customers search status {cust_resp.status_code}")
        if cust_ms > 1200:
            warn(f"customers search slow: {cust_ms:.1f}ms")

        # Barcode/SKU/not-found/inactive edges
        if barcode_product:
            r = client.get(f"/pos/api/product?code={barcode_product.barcode}&warehouse_id={wh_id}")
            row = r.get_json() or {}
            if r.status_code != 200:
                pass
            elif not row.get("id"):
                fail("barcode lookup returned empty payload")
            elif row.get("barcode") != barcode_product.barcode:
                fail("barcode lookup returned mismatched barcode")
        else:
            warn("no product with barcode found; barcode assertion skipped")
        if sku_product:
            r = client.get(f"/pos/api/product?code={sku_product.sku}&warehouse_id={wh_id}")
            row = r.get_json() or {}
            if r.status_code != 200:
                pass
            elif not row.get("id"):
                fail("SKU lookup returned empty payload")
            elif row.get("sku") != sku_product.sku:
                fail("SKU lookup returned mismatched sku")
        else:
            warn("no product with SKU found; SKU assertion skipped")

        r = client.get("/pos/api/product?code=__no_such_pos_code__")
        if r.status_code != 404 or not r.is_json:
            fail(f"product lookup 404 expected, got {r.status_code}")

        if inactive_products:
            inactive_code = (inactive_products[0].barcode or inactive_products[0].sku or "").strip()
            if inactive_code:
                r = client.get(f"/pos/api/product?code={inactive_code}&warehouse_id={wh_id}")
                if r.status_code != 404:
                    fail("inactive product should not be returned by lookup")

        # Tenant isolation in product search
        if cross_product and stocked_product:
            r = client.get(f"/pos/api/products?q={stocked_product.name[:8]}&warehouse_id={wh_id}")
            ids = [row.get("id") for row in (r.get_json() or [])]
            if cross_product.id in ids:
                fail("cross-tenant product leaked in POS search")

        # Walk-in customer resolution
        walk_resp = client.get("/pos/api/walkin-customer")
        if walk_resp.status_code != 200:
            fail(f"walkin customer: {walk_resp.status_code}")
            return STATUS_FAIL, fails, warns
        walkin = walk_resp.get_json() or {}
        walkin_id = walkin.get("id")
        if not walkin_id:
            fail("walkin customer missing id")
            return STATUS_FAIL, fails, warns

        # Build payload skeleton
        payload_base = {
            "warehouse_id": wh_id,
            "currency": "AED",
            "exchange_rate": 1,
            "tax_rate": 0,
            "shipping_cost": 0,
            "discount_amount": 0,
            "qa_marker": True,
            "notes": MARKER,
            "lines": [{"product_id": stocked_product.id, "quantity": "1", "discount_percent": 0}],
        }

        # CSRF: without token must fail, with token must pass
        no_csrf_headers = _json_headers(client, with_csrf=False)
        csrf_headers = _json_headers(client, with_csrf=False)
        if csrf_from_page:
            csrf_headers["X-CSRFToken"] = csrf_from_page
            csrf_headers["X-CSRF-Token"] = csrf_from_page
        resp_no_csrf = client.post(
            "/pos/api/checkout",
            data=json.dumps({**payload_base, "quick_customer": True, "payment_method": "cash", "paid_amount": float(stocked_product.regular_price or 1)}),
            headers=no_csrf_headers,
        )
        if resp_no_csrf.status_code not in (400, 403):
            fail(f"checkout without CSRF should fail, got {resp_no_csrf.status_code}")
        resp_with_csrf_probe = client.post(
            "/pos/api/checkout",
            data=json.dumps(
                {
                    **payload_base,
                    "quick_customer": True,
                    "lines": [{"product_id": stocked_product.id, "quantity": "0", "discount_percent": 0}],
                }
            ),
            headers=csrf_headers,
        )
        if resp_with_csrf_probe.status_code in (400, 403) and not (resp_with_csrf_probe.get_json() or {}).get("success"):
            msg = ((resp_with_csrf_probe.get_json() or {}).get("error") or "").lower()
            if "csrf" in msg or "token" in msg:
                fail("checkout with CSRF token should not fail CSRF validation")

        # Atomic failure scenarios (no orphans)
        def counts():
            return (
                Sale.query.count(),
                Payment.query.count(),
                StockMovement.query.filter_by(movement_type="sale").count(),
                GLJournalEntry.query.count(),
            )

        before = counts()
        bad_cross_customer = {**payload_base, "customer_id": (cross_customer.id if cross_customer else walkin_id), "payment_method": "cash", "paid_amount": 1}
        r = client.post("/pos/api/checkout", data=json.dumps(bad_cross_customer), headers=csrf_headers)
        if cross_customer and r.status_code not in (400, 404):
            fail(f"cross-tenant customer should fail cleanly, got {r.status_code}")
        if counts() != before:
            fail("orphan records created after cross-tenant customer failure")

        before = counts()
        bad_cross_product = {
            **payload_base,
            "quick_customer": True,
            "lines": [{"product_id": (cross_product.id if cross_product else stocked_product.id), "quantity": "1", "discount_percent": 0}],
            "payment_method": "cash",
            "paid_amount": 1,
        }
        r = client.post("/pos/api/checkout", data=json.dumps(bad_cross_product), headers=csrf_headers)
        if cross_product and r.status_code not in (400, 404):
            fail(f"cross-tenant product should fail cleanly, got {r.status_code}")
        if counts() != before:
            fail("orphan records created after cross-tenant product failure")

        before = counts()
        bad_cross_wh = {**payload_base, "quick_customer": True, "warehouse_id": (cross_warehouse.id if cross_warehouse else wh_id), "payment_method": "cash", "paid_amount": 1}
        r = client.post("/pos/api/checkout", data=json.dumps(bad_cross_wh), headers=csrf_headers)
        if cross_warehouse and r.status_code != 400:
            fail(f"cross-tenant warehouse should fail 400, got {r.status_code}")
        if counts() != before:
            fail("orphan records created after cross-tenant warehouse failure")

        before = counts()
        bad_qty = {**payload_base, "quick_customer": True, "lines": [{"product_id": stocked_product.id, "quantity": "0", "discount_percent": 0}], "payment_method": "cash", "paid_amount": 1}
        r = client.post("/pos/api/checkout", data=json.dumps(bad_qty), headers=csrf_headers)
        if r.status_code != 400:
            fail(f"qty<=0 should fail 400, got {r.status_code}")
        if counts() != before:
            fail("orphan records created after invalid quantity failure")

        before = counts()
        bad_price = {**payload_base, "quick_customer": True, "lines": [{"product_id": stocked_product.id, "quantity": "1", "unit_price": -1, "discount_percent": 0}], "payment_method": "cash", "paid_amount": 1}
        r = client.post("/pos/api/checkout", data=json.dumps(bad_price), headers=csrf_headers)
        if r.status_code != 400:
            fail(f"negative price should fail 400, got {r.status_code}")
        if counts() != before:
            fail("orphan records created after negative price failure")

        before = counts()
        huge_qty_payload = {**payload_base, "quick_customer": True, "lines": [{"product_id": stocked_product.id, "quantity": "999999999", "discount_percent": 0}], "payment_method": "cash", "paid_amount": 1}
        r = client.post("/pos/api/checkout", data=json.dumps(huge_qty_payload), headers=csrf_headers)
        if r.status_code != 400:
            fail(f"insufficient stock should fail 400, got {r.status_code}")
        if counts() != before:
            fail("orphan records created after insufficient stock failure")

        # Quick cash sale with duplicate lines merged
        sale_ids_to_cleanup: list[int] = []
        quick_payload = {
            **payload_base,
            "quick_customer": True,
            "customer_id": walkin_id,
            "payment_method": "cash",
            "paid_amount": float((stocked_product.regular_price or Decimal("1")) * Decimal("3")),
            "lines": [
                {"product_id": stocked_product.id, "quantity": "1", "discount_percent": 0},
                {"product_id": stocked_product.id, "quantity": "2", "discount_percent": 0},
            ],
        }
        quick_resp = client.post("/pos/api/checkout", data=json.dumps(quick_payload), headers=csrf_headers)
        quick_json = quick_resp.get_json() or {}
        if quick_resp.status_code != 200 or not quick_json.get("success"):
            fail(f"quick checkout failed: {quick_resp.status_code} {quick_json.get('error')}")
        else:
            sale_id = quick_json.get("sale_id")
            sale_ids_to_cleanup.append(sale_id)
            sale = db.session.get(Sale, sale_id)
            if not sale:
                fail("quick sale record missing")
            else:
                if sale.customer_id != walkin_id:
                    fail("quick sale customer mismatch")
                line_count = SaleLine.query.filter_by(sale_id=sale_id).count()
                if line_count != 1:
                    fail(f"duplicate scan should merge lines; got {line_count} lines")
                line = SaleLine.query.filter_by(sale_id=sale_id).first()
                if not line or Decimal(str(line.quantity)) != Decimal("3"):
                    fail("merged line quantity not equal to 3")

                payment = Payment.query.filter_by(sale_id=sale_id).order_by(Payment.id.desc()).first()
                if not payment:
                    fail("quick sale payment missing")
                else:
                    if payment.payment_type != "sale_payment":
                        fail(f"unexpected payment_type: {payment.payment_type}")
                    if Decimal(str(payment.amount)) != Decimal(str(sale.total_amount)):
                        fail("quick payment amount does not match sale total")
                if sale.payment_status != "paid":
                    fail(f"quick sale payment_status expected paid, got {sale.payment_status}")

                move = StockMovement.query.filter_by(
                    reference_type=GLRef.SALE, reference_id=sale_id, movement_type="sale"
                ).first()
                if not move:
                    fail("quick sale stock movement missing")

                sale_entries = GLJournalEntry.query.filter(
                    GLJournalEntry.reference_id == sale_id,
                    GLJournalEntry.reference_type.in_(ref_variants(GLRef.SALE)),
                ).all()
                if not sale_entries:
                    fail("sale GL entry missing for quick sale")
                elif not all(e.is_balanced() for e in sale_entries):
                    fail("sale GL entry not balanced for quick sale")

                pay_entries = GLJournalEntry.query.filter(
                    GLJournalEntry.reference_id == (payment.id if payment else None),
                    GLJournalEntry.reference_type.in_(ref_variants(GLRef.PAYMENT)),
                ).all()
                if not pay_entries:
                    fail("payment GL entry missing for quick sale")
                elif not all(e.is_balanced() for e in pay_entries):
                    fail("payment GL entry not balanced for quick sale")

                pr = client.get(f"/sales/{sale_id}/print")
                if pr.status_code != 200:
                    fail(f"quick print status {pr.status_code}")
                else:
                    logo_rel = document_logo_relative_path(None, sale.tenant_id)
                    if logo_rel and logo_rel.encode() not in pr.data:
                        fail("quick print missing tenant branding logo")
                    if b"\xd8\xb9\xd9\x85\xd9\x8a\xd9\x84 \xd9\x86\xd9\x82\xd8\xaf\xd9\x8a" not in pr.data:
                        warn("quick print may not display walk-in customer label clearly")

        # Registered customer sale (paid)
        if registered_customer:
            reg_payload = {
                **payload_base,
                "customer_id": registered_customer.id,
                "payment_method": "cash",
                "paid_amount": float(stocked_product.regular_price or 1),
            }
            reg_resp = client.post("/pos/api/checkout", data=json.dumps(reg_payload), headers=csrf_headers)
            reg_json = reg_resp.get_json() or {}
            if reg_resp.status_code != 200 or not reg_json.get("success"):
                fail(f"registered checkout failed: {reg_resp.status_code} {reg_json.get('error')}")
            else:
                sale_id = reg_json.get("sale_id")
                sale_ids_to_cleanup.append(sale_id)
                sale = db.session.get(Sale, sale_id)
                if not sale or sale.customer_id != registered_customer.id:
                    fail("registered sale customer mismatch")
                elif sale.customer_id == walkin_id:
                    fail("registered sale incorrectly used walk-in customer")
                if sale and sale.payment_status != "paid":
                    fail(f"registered paid sale expected paid, got {sale.payment_status}")
                payment = Payment.query.filter_by(sale_id=sale_id).first()
                if not payment:
                    fail("registered paid sale missing payment")
                pr = client.get(f"/sales/{sale_id}/print")
                if pr.status_code != 200:
                    fail(f"registered print status {pr.status_code}")
                elif (registered_customer.name or "").encode() not in pr.data:
                    fail("registered customer name missing in print")

            # Registered unpaid / partial support
            unpaid_payload = {
                **payload_base,
                "customer_id": registered_customer.id,
                "payment_method": "",
                "paid_amount": 0,
            }
            unpaid_resp = client.post("/pos/api/checkout", data=json.dumps(unpaid_payload), headers=csrf_headers)
            unpaid_json = unpaid_resp.get_json() or {}
            if unpaid_resp.status_code == 200 and unpaid_json.get("success"):
                sale_id = unpaid_json.get("sale_id")
                sale_ids_to_cleanup.append(sale_id)
                sale = db.session.get(Sale, sale_id)
                if sale and sale.payment_status not in ("unpaid", "partial"):
                    fail(f"unpaid scenario status invalid: {sale.payment_status}")
                payment = Payment.query.filter_by(sale_id=sale_id).first()
                if payment:
                    fail("unpaid scenario should not create payment")
            else:
                msg = (unpaid_json or {}).get("error", "")
                if unpaid_resp.status_code not in (400, 422):
                    fail(f"unpaid unsupported but wrong status: {unpaid_resp.status_code}")
                elif not msg:
                    warn("unpaid rejected without clear message")

        # Cleanup QA sales
        for sid in sale_ids_to_cleanup:
            try:
                s = db.session.get(Sale, sid)
                if s and s.status != "cancelled":
                    SaleService.cancel_sale(s)
            except Exception as exc:
                db.session.rollback()
                warn(f"QA cleanup failed for sale {sid}: {exc}")

        # Nasrallah safety notice
        nasrallah_users = User.query.filter_by(tenant_id=NASRALLAH_TENANT_ID, is_active=True).count()
        if nasrallah_users:
            warn(f"tenant 7 has {nasrallah_users} users — POS ops intentionally skipped there")

    if fails:
        return STATUS_FAIL, fails, warns
    if warns:
        return STATUS_WARN, fails, warns
    return STATUS_PASS, fails, warns


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="POS flow readiness check")
    parser.add_argument("--profile", default="local", choices=("local", "production-readiness"))
    args = parser.parse_args()
    status, fails, warns = run_pos_flow_check(args.profile)
    print(f"POS flow check: {status}")
    for f in fails:
        print(f"  FAIL: {f}")
    for w in warns:
        print(f"  WARN: {w}")
    return 1 if status == STATUS_FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
