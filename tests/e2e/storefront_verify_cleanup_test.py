"""Automated storefront verification + [TEST-STORE] cleanup."""
from __future__ import annotations

import re
import sys

from dotenv import load_dotenv

load_dotenv(".env")

from app import create_app
from extensions import db
from models import Product, Sale, SaleLine, StockMovement, Customer
from models.partner_commission import PartnerCommissionEntry
from models.shop_customer_account import ShopCustomerAccount
from models.system_settings import SystemSettings
from models.tenant_store import TenantStore
from models.user import User
from models import Warehouse
from services.shop_customer_auth_service import ShopCustomerAuthService
from services.store_checkout_service import StoreCheckoutService
from services.store_payment_method_service import StorePaymentMethodService
from services.store_service import StoreService
from services.stock_service import StockService

MARKER = "[TEST-STORE]"
T2_PRODUCTS = [36, 38]
T4_PRODUCTS = [86, 88]
T1_PRODUCT = 1
ORIGINAL_ECOMMERCE: bool | None = None


def _post_cart(client, slug: str, product_id: int, qty: float = 1):
    url = f"/s/{slug}"
    html = client.get(url).data.decode("utf-8", errors="ignore")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    tok = m.group(1) if m else ""
    return client.post(
        f"{url}/cart/add",
        data={"product_id": product_id, "quantity": qty, "csrf_token": tok},
        headers={"X-CSRFToken": tok, "Referer": f"http://localhost{url}"},
        follow_redirects=False,
    )


def _login_shop(client, tenant_id: int):
    acct = ShopCustomerAccount.query.filter(
        ShopCustomerAccount.tenant_id == tenant_id,
        ShopCustomerAccount.email.like("test-store-%@example.test"),
    ).first()
    with client.session_transaction() as sess:
        sess[ShopCustomerAuthService.session_key(tenant_id)] = acct.id


def _login_erp(client, username: str):
    u = User.query.filter_by(username=username).first()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True


def ensure_test_data():
    global ORIGINAL_ECOMMERCE
    settings = SystemSettings.get_current()
    if ORIGINAL_ECOMMERCE is None:
        ORIGINAL_ECOMMERCE = bool(settings.enable_ecommerce)
    if not settings.enable_ecommerce:
        settings.enable_ecommerce = True
    StorePaymentMethodService.ensure_defaults()
    for tenant_id, slug, pids in [(2, "test-a", T2_PRODUCTS), (4, "test-b", T4_PRODUCTS)]:
        store = StoreService.ensure_tenant_store(tenant_id)
        wh = StoreService.ensure_online_warehouse(tenant_id)
        store.warehouse_id = wh.id
        store.store_slug = slug
        store.is_enabled = True
        store.title = f"{MARKER} Store {slug.upper()}"
        for pid in pids:
            StockService.add_stock(
                pid,
                10,
                warehouse_id=wh.id,
                reference_type="test_store_setup",
                notes=f"{MARKER} stock",
            )
        email = f"test-store-{slug}@example.test"
        if not ShopCustomerAccount.query.filter_by(tenant_id=tenant_id, email=email).first():
            ShopCustomerAuthService.register(
                tenant_id=tenant_id,
                name=f"{MARKER} User {slug}",
                email=email,
                phone=f"0500000{tenant_id:03d}",
                password="TestStore123!",
                address=f"{MARKER} address",
            )
    db.session.commit()


def _product_markers(tenant_id: int, pids: list[int]):
    prods = Product.query.filter(Product.id.in_(pids)).all()
    return [p.name for p in prods] + [p.sku for p in prods if p.sku]


def run_verification(app) -> tuple[list[dict], bool]:
    results = []
    ok_all = True
    t2m = _product_markers(2, T2_PRODUCTS)
    t4m = _product_markers(4, T4_PRODUCTS)
    t1m = _product_markers(1, [T1_PRODUCT])

    with app.test_client() as client:
        # 1 Catalog
        for slug, own, forbid_prefixes in [
            ("test-a", t2m, ["T-ILS-", "T-AED-"] if False else ["T-ILS-", "HZM_", "Al Hazem"]),
            ("test-b", t4m, ["T-AED-", "HZM_", "Al Hazem"]),
        ]:
            # forbid: other tenant full prefixes only
            other = ["T-ILS-"] if slug == "test-a" else ["T-AED-"]
            other += ["HZM_", "Al Hazem"]
            r = client.get(f"/s/{slug}")
            body = r.data.decode("utf-8", errors="ignore")
            leaks = [p for p in other if p in body]
            row = {
                "test": f"catalog_{slug}",
                "status": r.status_code,
                "own": any(m in body for m in own),
                "leaks": leaks,
                "ok": r.status_code == 200 and not leaks and any(m in body for m in own),
            }
            results.append(row)
            ok_all &= row["ok"]

        # 2 Cart isolation via POST
        with client.session_transaction() as s:
            s.clear()
        _login_shop(client, 2)
        r = _post_cart(client, "test-a", T2_PRODUCTS[0], 1)
        with client.session_transaction() as s:
            c2 = dict(s.get("shop_cart_2") or {})
        _login_shop(client, 4)
        _post_cart(client, "test-b", T4_PRODUCTS[0], 1)
        with client.session_transaction() as s:
            c4 = dict(s.get("shop_cart_4") or {})
        row = {
            "test": "cart_isolation",
            "add_a_status": r.status_code,
            "cart_2": c2,
            "cart_4": c4,
            "ok": r.status_code in (302, 303)
            and str(T2_PRODUCTS[0]) in c2
            and str(T4_PRODUCTS[0]) in c4
            and c2 != c4,
        }
        results.append(row)
        ok_all &= row["ok"]

        # 3 Cross-tenant cart
        with client.session_transaction() as s:
            s.clear()
        _login_shop(client, 2)
        _post_cart(client, "test-a", T4_PRODUCTS[0], 1)
        with client.session_transaction() as s:
            after_t4 = dict(s.get("shop_cart_2") or {})
        _post_cart(client, "test-a", T1_PRODUCT, 1)
        with client.session_transaction() as s:
            after_t1 = dict(s.get("shop_cart_2") or {})
        row = {
            "test": "cross_tenant_cart",
            "cart_after_t4_product": after_t4,
            "cart_after_t1_product": after_t1,
            "ok": str(T4_PRODUCTS[0]) not in after_t4 and str(T1_PRODUCT) not in after_t1,
        }
        results.append(row)
        ok_all &= row["ok"]

        # 4 Checkout
        store_a = StoreService.get_store_by_slug("test-a")
        store_b = StoreService.get_store_by_slug("test-b")
        acct2 = ShopCustomerAccount.query.filter_by(tenant_id=2).filter(
            ShopCustomerAccount.email.like("test-store-%")
        ).first()
        acct4 = ShopCustomerAccount.query.filter_by(tenant_id=4).filter(
            ShopCustomerAccount.email.like("test-store-%")
        ).first()
        sale_a = StoreCheckoutService.create_web_order(
            store_a,
            {str(T2_PRODUCTS[0]): 1},
            customer_name=f"{MARKER} Checkout A",
            phone="0500000101",
            address=f"{MARKER} addr",
            notes=f"{MARKER} auto checkout a",
            payment_method_code="cod",
            shop_account=acct2,
        )
        sale_b = StoreCheckoutService.create_web_order(
            store_b,
            {str(T4_PRODUCTS[0]): 1},
            customer_name=f"{MARKER} Checkout B",
            phone="0500000401",
            address=f"{MARKER} addr",
            notes=f"{MARKER} auto checkout b",
            payment_method_code="cod",
            shop_account=acct4,
        )
        db.session.commit()
        for label, sale, tid in [("checkout_a", sale_a, 2), ("checkout_b", sale_b, 4)]:
            row = {
                "test": label,
                "sale_id": sale.id,
                "tenant_id": sale.tenant_id,
                "status": sale.status,
                "ok": sale.tenant_id == tid and sale.status == "pending" and sale.source == "online_store",
            }
            results.append(row)
            ok_all &= row["ok"]

        # 5 Order tokens
        tok_a = StoreCheckoutService.make_order_token(sale_a.id, 2)
        tok_b = StoreCheckoutService.make_order_token(sale_b.id, 4)
        row = {
            "test": "order_token",
            "a_on_a": client.get(f"/s/test-a/order/{tok_a}").status_code,
            "a_on_b": client.get(f"/s/test-b/order/{tok_a}").status_code,
            "b_on_b": client.get(f"/s/test-b/order/{tok_b}").status_code,
            "b_on_a": client.get(f"/s/test-a/order/{tok_b}").status_code,
            "ok": client.get(f"/s/test-a/order/{tok_a}").status_code == 200
            and client.get(f"/s/test-b/order/{tok_a}").status_code == 404
            and client.get(f"/s/test-b/order/{tok_b}").status_code == 200
            and client.get(f"/s/test-a/order/{tok_b}").status_code == 404,
        }
        results.append(row)
        ok_all &= row["ok"]

        # 6 Shop accounts
        _login_shop(client, 2)
        body_a = client.get("/s/test-a/account/orders").data.decode("utf-8", errors="ignore")
        row = {
            "test": "shop_account_a",
            "sees_b": sale_b.sale_number in body_a,
            "detail_b_status": client.get(f"/s/test-a/account/orders/{sale_b.id}").status_code,
            "ok": sale_b.sale_number not in body_a
            and client.get(f"/s/test-a/account/orders/{sale_b.id}").status_code == 404,
        }
        results.append(row)
        ok_all &= row["ok"]
        _login_shop(client, 4)
        body_b = client.get("/s/test-b/account/orders").data.decode("utf-8", errors="ignore")
        row = {
            "test": "shop_account_b",
            "sees_a": sale_a.sale_number in body_b,
            "ok": sale_a.sale_number not in body_b,
        }
        results.append(row)
        ok_all &= row["ok"]

        # 7 Store admin
        for uname, other in [("AED_manager", sale_b), ("ILS_manager", sale_a)]:
            _login_erp(client, uname)
            r = client.get("/store/admin/orders", follow_redirects=True)
            body = r.data.decode("utf-8", errors="ignore")
            row = {
                "test": f"store_admin_{uname}",
                "status": r.status_code,
                "shows_other": other.sale_number in body,
                "ok": r.status_code == 200 and other.sale_number not in body,
            }
            results.append(row)
            ok_all &= row["ok"]

    return results, ok_all


def cleanup_test_data():
    global ORIGINAL_ECOMMERCE
    sale_ids = [s.id for s in Sale.query.filter(Sale.notes.like(f"%{MARKER}%")).all()]

    if sale_ids:
        line_ids = [
            sl.id
            for sl in SaleLine.query.filter(SaleLine.sale_id.in_(sale_ids)).all()
        ]
        if line_ids:
            PartnerCommissionEntry.query.filter(
                PartnerCommissionEntry.sale_line_id.in_(line_ids)
            ).delete(synchronize_session=False)
        PartnerCommissionEntry.query.filter(
            PartnerCommissionEntry.sale_id.in_(sale_ids)
        ).delete(synchronize_session=False)
        SaleLine.query.filter(SaleLine.sale_id.in_(sale_ids)).delete(synchronize_session=False)

    for sid in sale_ids:
        sale = db.session.get(Sale, sid)
        if sale and sale.status == "pending":
            db.session.delete(sale)

    acct_ids = [
        a.id
        for a in ShopCustomerAccount.query.filter(
            ShopCustomerAccount.email.like("test-store-%@example.test")
        ).all()
    ]
    customer_ids = [
        a.customer_id
        for a in ShopCustomerAccount.query.filter(ShopCustomerAccount.id.in_(acct_ids)).all()
    ] if acct_ids else []

    if acct_ids:
        ShopCustomerAccount.query.filter(ShopCustomerAccount.id.in_(acct_ids)).delete(
            synchronize_session=False
        )

    for cid in customer_ids:
        c = db.session.get(Customer, cid)
        if c and MARKER in (c.name or ""):
            if not Sale.query.filter_by(customer_id=cid).first():
                db.session.delete(c)

    StockMovement.query.filter(
        db.or_(
            StockMovement.notes.like(f"%{MARKER}%"),
            StockMovement.reference_type == "test_store_setup",
        )
    ).delete(synchronize_session=False)

    wh_ids = []
    for slug in ("test-a", "test-b"):
        st = TenantStore.query.filter_by(store_slug=slug).first()
        if st:
            wh_ids.append(st.warehouse_id)
            db.session.delete(st)

    db.session.flush()

    for wh_id in set(wh_ids):
        wh = db.session.get(Warehouse, wh_id)
        if not wh or wh.warehouse_type != Warehouse.TYPE_ONLINE:
            continue
        remaining = StockMovement.query.filter_by(warehouse_id=wh_id).count()
        if remaining == 0 and wh.tenant_id in (2, 4):
            db.session.delete(wh)

    settings = SystemSettings.get_current()
    if ORIGINAL_ECOMMERCE is not None:
        settings.enable_ecommerce = ORIGINAL_ECOMMERCE

    db.session.commit()


def verify_cleanup(app) -> list[dict]:
    checks = []
    with app.test_client() as client:
        for slug in ("test-a", "test-b"):
            r = client.get(f"/s/{slug}")
            checks.append({"test": f"post_{slug}", "status": r.status_code, "ok": r.status_code == 404})
        remaining_sales = Sale.query.filter(Sale.notes.like(f"%{MARKER}%")).count()
        remaining_accts = ShopCustomerAccount.query.filter(
            ShopCustomerAccount.email.like("test-store-%@example.test")
        ).count()
        remaining_stores = TenantStore.query.filter(
            TenantStore.store_slug.in_(["test-a", "test-b"])
        ).count()
        remaining_moves = StockMovement.query.filter(
            StockMovement.notes.like(f"%{MARKER}%")
        ).count()
        checks.append({"test": "remaining_sales", "count": remaining_sales, "ok": remaining_sales == 0})
        checks.append({"test": "remaining_accounts", "count": remaining_accts, "ok": remaining_accts == 0})
        checks.append({"test": "remaining_stores", "count": remaining_stores, "ok": remaining_stores == 0})
        checks.append({"test": "remaining_movements", "count": remaining_moves, "ok": remaining_moves == 0})
    return checks


if __name__ == "__main__":
    app = create_app()
    app.config["WTF_CSRF_SSL_STRICT"] = False  # test client Referer/host (harness only)
    with app.app_context():
        ensure_test_data()
        results, passed = run_verification(app)
        print("=== VERIFICATION ===")
        for r in results:
            print(r)
        print("ALL_PASSED", passed)
        if not passed:
            sys.exit(1)
        cleanup_test_data()
        print("=== CLEANUP DONE ===")
        post = verify_cleanup(app)
        for r in post:
            print(r)
        if not all(r["ok"] for r in post):
            sys.exit(2)
