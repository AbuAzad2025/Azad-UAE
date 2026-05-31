"""Temporary [TEST-STORE] setup + smoke — tenants 2 & 4 only."""
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv(".env")

from app import create_app
from extensions import db
from models import Product, Warehouse
from models.system_settings import SystemSettings
from models.tenant_store import TenantStore
from services.store_payment_method_service import StorePaymentMethodService
from services.store_service import StoreService
from services.stock_service import StockService
from services.store_checkout_service import StoreCheckoutService
from services.shop_customer_auth_service import ShopCustomerAuthService
from models.shop_customer_account import ShopCustomerAccount

MARKER = "[TEST-STORE]"
T2_PRODUCTS = [36, 38]
T4_PRODUCTS = [86, 88]
TEST_STOCK_QTY = 10


def setup():
    results = {"created": [], "updated": []}

    settings = SystemSettings.get_current()
    if not settings.enable_ecommerce:
        settings.enable_ecommerce = True
        results["updated"].append("system_settings.enable_ecommerce=true")

    StorePaymentMethodService.ensure_defaults()

    configs = [
        (2, "test-a", T2_PRODUCTS),
        (4, "test-b", T4_PRODUCTS),
    ]

    store_ids = {}
    wh_ids = {}

    account_ids = {}

    for tenant_id, slug, product_ids in configs:
        store = StoreService.ensure_tenant_store(tenant_id)
        online_wh = StoreService.ensure_online_warehouse(tenant_id)
        store.warehouse_id = online_wh.id
        store.store_slug = slug
        store.is_enabled = True
        store.title = f"{MARKER} Store {slug.upper()}"
        store.tagline = f"{MARKER} runtime isolation test"
        if not store.delivery_note or MARKER not in (store.delivery_note or ""):
            store.delivery_note = f"{MARKER} test storefront"

        wh_ids[tenant_id] = online_wh.id
        store_ids[tenant_id] = store.id

        for pid in product_ids:
            product = Product.query.filter_by(id=pid, tenant_id=tenant_id).first()
            if not product:
                raise RuntimeError(f"Product {pid} not found for tenant {tenant_id}")
            StockService.add_stock(
                product_id=pid,
                quantity=TEST_STOCK_QTY,
                warehouse_id=online_wh.id,
                reference_type="test_store_setup",
                notes=f"{MARKER} initial stock for slug={slug}",
            )
            results["created"].append(f"stock product={pid} wh={online_wh.id} qty={TEST_STOCK_QTY}")

        results["created"].append(
            f"tenant_store id={store.id} tenant={tenant_id} slug={slug} wh={online_wh.id}"
        )

        email = f"test-store-{slug}@example.test"
        account = ShopCustomerAccount.query.filter_by(tenant_id=tenant_id, email=email).first()
        if not account:
            account = ShopCustomerAuthService.register(
                tenant_id=tenant_id,
                name=f"{MARKER} Shop User {slug}",
                email=email,
                phone=f"05000000{tenant_id:02d}",
                password="TestStore123!",
                address=f"{MARKER} address",
            )
            results["created"].append(f"shop_account id={account.id} tenant={tenant_id} email={email}")
        else:
            account_ids[tenant_id] = account.id

        account_ids[tenant_id] = account.id

    db.session.commit()
    return results, store_ids, wh_ids, account_ids


def _login_shop(client, tenant_id, account_id):
    with client.session_transaction() as sess:
        sess[ShopCustomerAuthService.session_key(tenant_id)] = account_id
        sess["_fresh"] = True


def _csrf_headers(client):
    with client.session_transaction() as sess:
        pass
    with client.application.test_request_context():
        from flask_wtf.csrf import generate_csrf
        token = generate_csrf()
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return {"X-CSRFToken": token}, token


def smoke_tests(app, store_ids, wh_ids, account_ids):
    from flask import session as flask_session

    outcomes = []

    t2_prods = Product.query.filter(Product.id.in_(T2_PRODUCTS)).all()
    t4_prods = Product.query.filter(Product.id.in_(T4_PRODUCTS)).all()
    t1_prods = Product.query.filter(Product.tenant_id == 1, Product.is_active == True).limit(3).all()
    t2_names = {p.name for p in t2_prods}
    t4_names = {p.name for p in t4_prods}
    t2_skus = {p.sku for p in t2_prods if p.sku}
    t4_skus = {p.sku for p in t4_prods if p.sku}
    t1_names = {p.name for p in t1_prods}
    t1_skus = {p.sku for p in t1_prods if p.sku}

    with app.test_client() as client:
        # Catalog tests
        for slug, own_names, foreign_names, own_skus, foreign_skus, foreign_ids in [
            ("test-a", t2_names, t4_names | t1_names, t2_skus, t4_skus | t1_skus, T4_PRODUCTS + [1, 2]),
            ("test-b", t4_names, t2_names | t1_names, t4_skus, t2_skus | t1_skus, T2_PRODUCTS + [1, 2]),
        ]:
            r = client.get(f"/s/{slug}")
            body = r.data.decode("utf-8", errors="ignore")
            leak_foreign = [n for n in foreign_names if n and n in body]
            leak_skus = [s for s in foreign_skus if s and s in body]
            has_own = any(n in body for n in own_names if n)
            outcomes.append(
                {
                    "test": f"GET /s/{slug}",
                    "status": r.status_code,
                    "has_own_products": has_own,
                    "leak_foreign_names": leak_foreign[:5],
                    "leak_foreign_skus": leak_skus[:5],
                    "leak": bool(leak_foreign or leak_skus),
                }
            )

        # Cart isolation via POST on test-a
        with client.session_transaction() as sess:
            sess.clear()
        _login_shop(client, 2, account_ids[2])
        headers, csrf = _csrf_headers(client)
        r_add = client.post(
            "/s/test-a/cart/add",
            data={"product_id": 36, "quantity": 1, "csrf_token": csrf},
            headers=headers,
            follow_redirects=False,
        )
        with client.session_transaction() as sess:
            cart_a = dict(sess.get("shop_cart_2", {}))
        _login_shop(client, 4, account_ids[4])
        client.get("/s/test-b")
        with client.session_transaction() as sess:
            cart_b = dict(sess.get("shop_cart_4", {}))
        outcomes.append(
            {
                "test": "cart_isolation",
                "add_status": r_add.status_code,
                "cart_t2": cart_a,
                "cart_t4": cart_b,
                "isolated": bool(cart_a) and not cart_b,
            }
        )

        # Cross-tenant add to test-a cart: product 86 (tenant 4)
        with client.session_transaction() as sess:
            sess.clear()
        _login_shop(client, 2, account_ids[2])
        headers, csrf = _csrf_headers(client)
        r_cross = client.post(
            "/s/test-a/cart/add",
            data={"product_id": 86, "quantity": 1, "csrf_token": csrf},
            headers=headers,
            follow_redirects=False,
        )
        with client.session_transaction() as sess:
            cart_cross = sess.get("shop_cart_2", {})
        outcomes.append(
            {
                "test": "cross_tenant_cart_add_t4_product_to_test_a",
                "status": r_cross.status_code,
                "cart_t2": cart_cross,
                "rejected": "86" not in cart_cross and str(86) not in cart_cross,
            }
        )

        # Order token isolation — create pending sale via service (rollback after token test)
        token = None
        sale_id = None
        with app.app_context():
            store_a = StoreService.get_store_by_slug("test-a")
            cart = {"36": 1}
            try:
                sale = StoreCheckoutService.create_web_order(
                    store_a,
                    cart=cart,
                    customer_name=f"{MARKER} Buyer",
                    phone="0500000001",
                    address=f"{MARKER} Test Address",
                    notes=f"{MARKER} token isolation test",
                    payment_method_code="cod",
                )
                sale_id = sale.id
                token = StoreCheckoutService.make_order_token(sale.id, store_a.tenant_id)
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                outcomes.append({"test": "create_test_order", "error": str(exc)})
                token = None

        if token:
            r_ok = client.get(f"/s/test-a/order/{token}")
            r_bad = client.get(f"/s/test-b/order/{token}")
            outcomes.append(
                {
                    "test": "order_token_isolation",
                    "token_on_test_a": r_ok.status_code,
                    "token_on_test_b": r_bad.status_code,
                    "isolated": r_ok.status_code == 200 and r_bad.status_code == 404,
                    "test_sale_id": sale_id,
                }
            )

    return outcomes


if __name__ == "__main__":
    import sys
    app = create_app()
    with app.app_context():
        if "--smoke-only" not in sys.argv:
            print("=== SETUP ===")
            setup_result, store_ids, wh_ids, account_ids = setup()
            for k, v in setup_result.items():
                print(k, v)
        else:
            store_ids = {2: TenantStore.query.filter_by(tenant_id=2).first().id, 4: TenantStore.query.filter_by(tenant_id=4).first().id}
            wh_ids = {2: TenantStore.query.filter_by(tenant_id=2).first().warehouse_id, 4: TenantStore.query.filter_by(tenant_id=4).first().warehouse_id}
            account_ids = {2: ShopCustomerAccount.query.filter_by(tenant_id=2).first().id, 4: ShopCustomerAccount.query.filter_by(tenant_id=4).first().id}
        print("store_ids", store_ids)
        print("warehouse_ids", wh_ids)
        print("account_ids", account_ids)
        print("=== SMOKE ===")
        for row in smoke_tests(app, store_ids, wh_ids, account_ids):
            print(row)
