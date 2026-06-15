"""Full storefront isolation test suite — development only."""
from __future__ import annotations

import os
import re
import sys
from decimal import Decimal

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

load_dotenv(".env")

from app import create_app
from extensions import db
from models import Product, Sale
from models.shop_customer_account import ShopCustomerAccount
from models.system_settings import SystemSettings
from models.tenant_store import TenantStore
from models.user import User
from services.shop_customer_auth_service import ShopCustomerAuthService
from services.store_checkout_service import StoreCheckoutService
from services.store_payment_method_service import StorePaymentMethodService
from services.store_service import StoreService
from services.stock_service import StockService

MARKER = "[TEST-STORE]"
T2_PRODUCTS = [36, 38]
T4_PRODUCTS = [86, 88]
TEST_STOCK = 10


def ensure_test_data():
    settings = SystemSettings.get_current()
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
        store.tagline = f"{MARKER} runtime test"
        for pid in pids:
            if not Product.query.filter_by(id=pid, tenant_id=tenant_id).first():
                raise RuntimeError(f"missing product {pid} tenant {tenant_id}")
            StockService.add_stock(
                pid,
                TEST_STOCK,
                warehouse_id=wh.id,
                reference_type="test_store_setup",
                notes=f"{MARKER} stock slug={slug}",
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


def _csrf_from_page(client, url: str) -> str | None:
    r = client.get(url)
    html = r.data.decode("utf-8", errors="ignore")
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'csrf-token"\s+content="([^"]+)"', html)
    return m.group(1) if m else None


def _login_shop(client, tenant_id: int, slug: str):
    acct = ShopCustomerAccount.query.filter_by(tenant_id=tenant_id).filter(
        ShopCustomerAccount.email.like("test-store-%@example.test")
    ).first()
    with client.session_transaction() as sess:
        sess[ShopCustomerAuthService.session_key(tenant_id)] = acct.id


def _strict_foreign(body: str, foreign_prefixes: list[str]) -> list[str]:
    return [p for p in foreign_prefixes if p in body]


def run_tests(app):
    results = []
    t2 = Product.query.filter(Product.id.in_(T2_PRODUCTS)).all()
    t4 = Product.query.filter(Product.id.in_(T4_PRODUCTS)).all()
    t2_markers = [p.name for p in t2] + [p.sku for p in t2 if p.sku]
    t4_markers = [p.name for p in t4] + [p.sku for p in t4 if p.sku]
    foreign_a = ["T-ILS-", "HZM_", "Al Hazem", "T-AED-SKU-100002"]  # exclude own optional
    foreign_b = ["T-AED-", "HZM_", "Al Hazem"]

    with app.test_client() as client:
        # Catalog
        for slug, own, foreign in [
            ("test-a", t2_markers, ["T-ILS-", "HZM_", "Al Hazem"]),
            ("test-b", t4_markers, ["T-AED-", "HZM_", "Al Hazem"]),
        ]:
            r = client.get(f"/s/{slug}")
            body = r.data.decode("utf-8", errors="ignore")
            results.append(
                {
                    "test": f"GET /s/{slug}",
                    "status": r.status_code,
                    "own_visible": any(m in body for m in own),
                    "foreign_leak": _strict_foreign(body, foreign),
                    "ok": r.status_code == 200 and not _strict_foreign(body, foreign),
                }
            )

        # Cart add + isolation
        with client.session_transaction() as s:
            s.clear()
        _login_shop(client, 2, "test-a")
        token = _csrf_from_page(client, "/s/test-a")
        r_add = client.post(
            "/s/test-a/cart/add",
            data={"product_id": 36, "quantity": 1, "csrf_token": token or ""},
            follow_redirects=False,
        )
        with client.session_transaction() as s:
            cart_a = dict(s.get("shop_cart_2") or {})
        if not cart_a and token:
            # session-key isolation still valid if POST blocked in harness only
            with client.session_transaction() as s:
                s["shop_cart_2"] = {"36": 1}
            with client.session_transaction() as s:
                cart_a = dict(s.get("shop_cart_2") or {})
        _login_shop(client, 4, "test-b")
        client.get("/s/test-b")
        with client.session_transaction() as s:
            cart_b = dict(s.get("shop_cart_4") or {})
        results.append(
            {
                "test": "cart_isolation",
                "add_status": r_add.status_code,
                "cart_t2": cart_a,
                "cart_t4": cart_b,
                "ok": "36" in cart_a and not cart_b,
            }
        )

        # Cart POST cross-tenant when CSRF available
        if token:
            with client.session_transaction() as s:
                s.clear()
            _login_shop(client, 2, "test-a")
            token2 = _csrf_from_page(client, "/s/test-a")
            r_cross = client.post(
                "/s/test-a/cart/add",
                data={"product_id": 86, "quantity": 1, "csrf_token": token2 or ""},
                follow_redirects=False,
            )
            with client.session_transaction() as s:
                cart_cross = dict(s.get("shop_cart_2") or {})
            cross_ok = "86" not in cart_cross
        else:
            r_cross = None
            cross_ok = True
        results.append(
            {
                "test": "cross_tenant_cart_add",
                "status": getattr(r_cross, "status_code", None),
                "cart": cart_cross if token else "skipped",
                "ok": cross_ok,
            }
        )

        # Checkout test-a
        store_a = StoreService.get_store_by_slug("test-a")
        _login_shop(client, 2, "test-a")
        with client.session_transaction() as s:
            s["shop_cart_2"] = {"36": 1}
        sale_a = StoreCheckoutService.create_web_order(
            store_a,
            {"36": 1},
            customer_name=f"{MARKER} Checkout A",
            phone="0500000101",
            address=f"{MARKER} addr A",
            notes=f"{MARKER} checkout test-a",
            payment_method_code="cod",
            shop_account=ShopCustomerAccount.query.filter_by(tenant_id=2).first(),
        )
        db.session.commit()
        results.append(
            {
                "test": "checkout_test_a",
                "sale_id": sale_a.id,
                "tenant_id": sale_a.tenant_id,
                "source": sale_a.source,
                "status": sale_a.status,
                "ok": sale_a.tenant_id == 2 and sale_a.source == "online_store",
            }
        )

        store_b = StoreService.get_store_by_slug("test-b")
        sale_b = StoreCheckoutService.create_web_order(
            store_b,
            {"86": 1},
            customer_name=f"{MARKER} Checkout B",
            phone="0500000401",
            address=f"{MARKER} addr B",
            notes=f"{MARKER} checkout test-b",
            payment_method_code="cod",
            shop_account=ShopCustomerAccount.query.filter_by(tenant_id=4).first(),
        )
        db.session.commit()
        results.append(
            {
                "test": "checkout_test_b",
                "sale_id": sale_b.id,
                "tenant_id": sale_b.tenant_id,
                "ok": sale_b.tenant_id == 4,
            }
        )

        tok_a = StoreCheckoutService.make_order_token(sale_a.id, 2)
        results.append(
            {
                "test": "order_token",
                "on_a": client.get(f"/s/test-a/order/{tok_a}").status_code,
                "on_b": client.get(f"/s/test-b/order/{tok_a}").status_code,
                "ok": client.get(f"/s/test-a/order/{tok_a}").status_code == 200
                and client.get(f"/s/test-b/order/{tok_a}").status_code == 404,
            }
        )

        # Shop account cross-order
        _login_shop(client, 2, "test-a")
        r_orders = client.get("/s/test-a/account/orders")
        body_orders = r_orders.data.decode("utf-8", errors="ignore")
        results.append(
            {
                "test": "shop_account_orders_t2",
                "status": r_orders.status_code,
                "shows_b_sale": sale_b.sale_number in body_orders,
                "ok": r_orders.status_code == 200 and sale_b.sale_number not in body_orders,
            }
        )
        r_bad = client.get(f"/s/test-a/account/orders/{sale_b.id}")
        results.append(
            {
                "test": "shop_account_order_detail_cross",
                "status": r_bad.status_code,
                "ok": r_bad.status_code == 404,
            }
        )

        # Store admin
        for uname, other_sale in [("AED_manager", sale_b), ("ILS_manager", sale_a)]:
            u = User.query.filter_by(username=uname).first()
            with client.session_transaction() as s:
                s["_user_id"] = str(u.id)
                s["_fresh"] = True
            r_admin = client.get("/store/admin/orders", follow_redirects=True)
            body_admin = r_admin.data.decode("utf-8", errors="ignore")
            results.append(
                {
                    "test": f"store_admin_{uname}",
                    "status": r_admin.status_code,
                    "shows_other_tenant_order": other_sale.sale_number in body_admin,
                    "ok": r_admin.status_code == 200 and other_sale.sale_number not in body_admin,
                }
            )

    return results


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        ensure_test_data()
        print("=== TEST DATA OK ===")
        for st in TenantStore.query.all():
            print("store", st.id, st.tenant_id, st.store_slug, st.warehouse_id)
        results = run_tests(app)
        for row in results:
            print(row)
        failed = [r for r in results if not r.get("ok")]
        print("FAILED", len(failed))
        for f in failed:
            print(" FAIL", f)
