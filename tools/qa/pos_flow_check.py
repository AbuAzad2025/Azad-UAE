"""
POS readiness — product lookup, checkout, RBAC, branding (tenant 2 only; never tenant 7 ops).

Run: python tools/qa/pos_flow_check.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

NASRALLAH_TENANT_ID = 7
UAT_TENANT_ID = 2
MARKER = "[POS-QA]"

FAIL = "FAIL"
WARN = "WARN"
PASS = "PASS"


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


def _json_headers(client) -> dict:
    with client.session_transaction() as sess:
        token = sess.get("csrf_token") or ""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["X-CSRFToken"] = token
    return headers


def run_pos_flow_check(profile: str = "local") -> tuple[str, list[str], list[str]]:
    from decimal import Decimal

    from app import create_app
    from extensions import db
    from models import Product, Sale, StockMovement
    from models.user import User
    from services.stock_service import StockService
    from utils.gl_reference_types import GLRef

    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")
    app = create_app()
    fails: list[str] = []
    warns: list[str] = []

    def fail(msg: str) -> None:
        fails.append(msg)

    def warn(msg: str) -> None:
        warns.append(msg)

    with app.app_context():
        cross = (
            Product.query.filter(Product.tenant_id != UAT_TENANT_ID)
            .filter(Product.is_active == True)
            .first()
        )
        uat_product = (
            Product.query.filter_by(tenant_id=UAT_TENANT_ID, is_active=True)
            .filter(Product.regular_price > 0)
            .first()
        )
        if not uat_product:
            fail("no active product for tenant 2 POS tests")

        # RBAC (programmatic — Flask test clients share login state across requests)
        for uname, expected in (("AED_a_accountant", False), ("AED_a_seller", True)):
            user = User.query.filter_by(username=uname).first()
            if not user:
                fail(f"user missing for RBAC: {uname}")
            elif user.has_permission("manage_sales") != expected:
                fail(f"{uname} manage_sales expected {expected}")

        # Manager POS + walk-in (HTTP)
        try:
            c = app.test_client()
            _logout_client(c)
            _login(c, app, "AED_manager")
            c.get("/pos/")
            headers = _json_headers(c)
            r = c.get("/pos/api/product?code=__no_such_pos_code__")
            if r.status_code != 404 or not r.is_json:
                fail(f"product lookup 404 expected, got {r.status_code}")
            body = r.get_json() or {}
            if body.get("success") is not False:
                fail("product lookup JSON should set success=false on 404")

            r = c.get("/pos/api/walkin-customer")
            if r.status_code != 200:
                fail(f"walkin customer: {r.status_code}")
            walkin = (r.get_json() or {}).get("id")
            if not walkin:
                fail("walkin customer missing id")

            if cross and uat_product:
                r = c.get(f"/pos/api/products?q={uat_product.sku or uat_product.name[:8]}")
                data = r.get_json() or []
                if cross.id in [row.get("id") for row in data]:
                    fail("cross-tenant product leaked in POS search")

            if uat_product:
                from models import Warehouse

                wh = (
                    Warehouse.query.filter_by(tenant_id=UAT_TENANT_ID, is_active=True)
                    .order_by(Warehouse.is_main.desc(), Warehouse.id.asc())
                    .first()
                )
                wh_id = wh.id if wh else None
                stocked_product = uat_product
                if wh_id:
                    from utils.branching import get_branch_stock_map

                    candidates = (
                        Product.query.filter_by(tenant_id=UAT_TENANT_ID, is_active=True)
                        .limit(200)
                        .all()
                    )
                    smap = get_branch_stock_map(
                        product_ids=[p.id for p in candidates],
                        warehouse_ids=[wh_id],
                    )
                    for p in candidates:
                        if smap.get(p.id, Decimal("0")) >= Decimal("1"):
                            stocked_product = p
                            break

                huge_qty = Decimal("999999999")
                payload = {
                    "quick_customer": True,
                    "warehouse_id": wh_id,
                    "lines": [
                        {
                            "product_id": stocked_product.id,
                            "quantity": str(huge_qty),
                            "discount_percent": 0,
                        }
                    ],
                    "qa_marker": True,
                    "notes": MARKER,
                }
                r = c.post("/pos/api/checkout", data=json.dumps(payload), headers=headers)
                if r.status_code != 400:
                    fail(f"insufficient stock should 400, got {r.status_code}")
                err = (r.get_json() or {}).get("error", "")
                if "مخزون" not in err and "stock" not in err.lower():
                    warn(f"stock error message unclear: {err[:80]}")

                avail, _ = StockService.check_availability_in_warehouse(
                    stocked_product.id, Decimal("1"), wh_id
                )
                if avail:
                    payload = {
                        "customer_id": walkin,
                        "warehouse_id": wh_id,
                        "currency": "AED",
                        "exchange_rate": 1,
                        "payment_method": "cash",
                        "paid_amount": float(stocked_product.regular_price or 1),
                        "lines": [
                            {
                                "product_id": stocked_product.id,
                                "quantity": "1",
                                "discount_percent": 0,
                            }
                        ],
                        "qa_marker": True,
                        "notes": MARKER,
                    }
                    r = c.post("/pos/api/checkout", data=json.dumps(payload), headers=headers)
                    j = r.get_json() or {}
                    if r.status_code != 200 or not j.get("success"):
                        fail(f"checkout failed: {r.status_code} {j.get('error')}")
                    else:
                        sale_id = j.get("sale_id")
                        sale = db.session.get(Sale, sale_id)
                        if not sale or MARKER not in (sale.notes or ""):
                            warn("QA sale missing marker in notes")
                        if sale and sale.warehouse_id != wh_id:
                            fail(f"sale warehouse mismatch: {sale.warehouse_id} vs {wh_id}")
                        mov = StockMovement.query.filter_by(
                            reference_type=GLRef.SALE,
                            reference_id=sale_id,
                            movement_type="sale",
                        ).first()
                        if not mov or mov.warehouse_id != wh_id:
                            fail("stock movement missing or wrong warehouse")
                        pr = c.get(f"/sales/{sale_id}/print")
                        if pr.status_code != 200:
                            fail(f"print receipt: {pr.status_code}")
                        else:
                            from models.invoice_settings import InvoiceSettings
                            from utils.tenant_branding import document_logo_relative_path

                            settings = InvoiceSettings.get_active(sale.tenant_id)
                            logo_rel = document_logo_relative_path(settings, sale.tenant_id)
                            if logo_rel and logo_rel.encode() not in pr.data:
                                fail(
                                    f"print missing tenant logo path: {logo_rel[:80]}"
                                )
                        try:
                            from services.sale_service import SaleService

                            s = db.session.get(Sale, sale_id)
                            if s and s.status != "cancelled":
                                SaleService.cancel_sale(s)
                        except Exception as exc:
                            db.session.rollback()
                            warn(f"QA sale cleanup (cancel): {exc}")
                else:
                    warn("skip checkout test — no stock in default warehouse")
        except Exception as exc:
            fail(f"manager POS flow: {exc}")

        nasrallah_users = User.query.filter_by(
            tenant_id=NASRALLAH_TENANT_ID, is_active=True
        ).count()
        if nasrallah_users:
            warn(
                f"tenant 7 has {nasrallah_users} users — POS check skipped ops there by design"
            )

    if fails:
        return FAIL, fails, warns
    if warns and profile == "production-readiness":
        return WARN, fails, warns
    if warns:
        return WARN, fails, warns
    return PASS, fails, warns


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="POS flow readiness check")
    parser.add_argument(
        "--profile",
        default="local",
        choices=("local", "production-readiness"),
    )
    args = parser.parse_args()
    status, fails, warns = run_pos_flow_check(args.profile)
    print(f"POS flow check: {status}")
    for f in fails:
        print(f"  FAIL: {f}")
    for w in warns:
        print(f"  WARN: {w}")
    return 1 if status == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
