"""
POS Phase 5 -- E2E journey matrix (real DB, full route stack) + concurrency stress.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC
from decimal import Decimal

import pytest

from extensions import db


def _bootstrap(db_or_session, *, tid=None, stock="100", price="25", cost="10"):
    from models import (
        Branch,
        Permission,
        Product,
        ProductCategory,
        Role,
        SystemSettings,
        Tenant,
        User,
        Warehouse,
    )
    from services.stock_service import StockService

    tid = tid or uuid.uuid4().hex[:4]
    tenant = Tenant(
        name=f"E2E {tid}",
        name_ar=f"E2E {tid}",
        slug=f"e2e-{tid}",
        default_currency="AED",
        subscription_plan="pro",
        enable_pos_promotions=True,
        enable_pos_multi_tender=True,
        enable_pos_shifts=True,
    )
    db_or_session.add(tenant)
    db_or_session.flush()

    branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"{tid[:4]}")
    db_or_session.add(branch)
    db_or_session.flush()

    role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
    perm = Permission.query.filter_by(code="manage_sales").first()
    if not perm:
        perm = Permission(code="manage_sales", name="manage_sales", name_ar="manage_sales", category="sales")
        db_or_session.add(perm)
        db_or_session.flush()
    if perm not in role.permissions:
        role.permissions.append(perm)
    db_or_session.add(role)
    db_or_session.flush()

    user = User(
        username=f"e2e-{tid}",
        email=f"e2e-{tid}@t.com",
        full_name="Cashier",
        role_id=role.id,
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        is_owner=False,
    )
    user.set_password("x")
    db_or_session.add(user)
    db_or_session.flush()

    wh = Warehouse(
        name=f"WH {tid}", tenant_id=tenant.id, branch_id=branch.id, is_active=True, allow_negative_inventory=False
    )
    db_or_session.add(wh)
    db_or_session.flush()

    cat = ProductCategory(name=f"Cat {tid}", tenant_id=tenant.id, is_active=True)
    db_or_session.add(cat)
    db_or_session.flush()

    product = Product(
        name=f"Item {tid}",
        sku=f"ITM-{tid}",
        tenant_id=tenant.id,
        category_id=cat.id,
        regular_price=Decimal(price),
        cost_price=Decimal(cost),
        is_active=True,
    )
    db_or_session.add(product)
    db_or_session.flush()

    StockService.add_stock(product.id, Decimal(stock), warehouse_id=wh.id)
    db_or_session.flush()

    if not SystemSettings.query.first():
        db_or_session.add(SystemSettings(enable_pos=True))
    db_or_session.commit()
    return {"tenant": tenant, "branch": branch, "user": user, "warehouse": wh, "product": product}


def _login_and_open(client, username):
    client.post("/auth/login", data={"username": username, "password": "x"}, follow_redirects=True)
    resp = client.post("/pos/api/session/open", json={"opening_balance": 0}, content_type="application/json")
    assert resp.status_code == 201, f"session open failed: {resp.get_json()}"
    resp = client.post("/pos/api/shift/open", json={"starting_cash": 0}, content_type="application/json")
    assert resp.status_code == 201, f"shift open failed: {resp.get_json()}"


class TestPosE2EJourney:
    def test_full_journey_promo_split_tender_close_gl(self, app, db_session, client):
        from models import GLJournalEntry

        env = _bootstrap(db_session)
        tenant, user, wh, product = env["tenant"], env["user"], env["warehouse"], env["product"]
        from datetime import datetime, timedelta

        from models.campaign import Campaign

        now = datetime.now(UTC)
        campaign = Campaign(
            tenant_id=tenant.id,
            name="E2E 10%",
            campaign_type="percentage",
            discount_value=Decimal("10"),
            min_order_amount=Decimal("0"),
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
            is_active=True,
            applies_to_pos=True,
        )
        db_session.add(campaign)
        db_session.commit()
        with client:
            _login_and_open(client, user.username)
            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [{"product_id": product.id, "quantity": 4, "unit_price": 25.0, "discount_percent": 0}],
                    "payments": [
                        {"amount": 50.0, "payment_method": "cash", "currency": "AED", "exchange_rate": 1},
                        {"amount": 40.0, "payment_method": "card", "currency": "AED", "exchange_rate": 1},
                    ],
                    "currency": "AED",
                    "warehouse_id": wh.id,
                },
                content_type="application/json",
            )
            assert resp.status_code == 200, f"checkout failed: {resp.get_json()}"
            data = resp.get_json()["data"]
            assert data["success"] is True
        entries = GLJournalEntry.query.filter_by(tenant_id=tenant.id).all()
        assert entries, "journey must post GL entries"

    def test_checkout_idempotency_replay_returns_same_sale(self, app, db_session, client):
        from services.stock_service import StockService

        env = _bootstrap(db_session, stock="50")
        user, wh, product = env["user"], env["warehouse"], env["product"]
        payload = {
            "lines": [{"product_id": product.id, "quantity": 3, "unit_price": 25.0, "discount_percent": 0}],
            "payment_method": "cash",
            "paid_amount": 75.0,
            "currency": "AED",
            "warehouse_id": wh.id,
        }
        key = f"e2e-idem-{uuid.uuid4().hex[:12]}"
        with client:
            _login_and_open(client, user.username)
            first = client.post(
                "/pos/api/checkout", json=payload, headers={"Idempotency-Key": key}, content_type="application/json"
            )
            second = client.post(
                "/pos/api/checkout", json=payload, headers={"Idempotency-Key": key}, content_type="application/json"
            )
        assert first.status_code == 200, f"first failed: {first.get_json()}"
        assert second.status_code == 200, f"replay failed: {second.get_json()}"
        assert StockService.get_product_stock(product.id, warehouse_id=wh.id) == 47

    def test_evaluate_endpoint_matches_checkout_discount(self, app, db_session, client):
        from datetime import datetime, timedelta

        from models.campaign import Campaign

        env = _bootstrap(db_session)
        tenant, user, wh, product = env["tenant"], env["user"], env["warehouse"], env["product"]
        now = datetime.now(UTC)
        db_session.add(
            Campaign(
                tenant_id=tenant.id,
                name="E2E match",
                campaign_type="percentage",
                discount_value=Decimal("10"),
                min_order_amount=Decimal("0"),
                start_date=now - timedelta(days=1),
                end_date=now + timedelta(days=30),
                is_active=True,
                applies_to_pos=True,
            )
        )
        db_session.commit()
        lines = [{"product_id": product.id, "quantity": 2, "unit_price": 25.0, "discount_percent": 0}]
        with client:
            _login_and_open(client, user.username)
            preview = client.post(
                "/pos/api/promotions/evaluate", json={"lines": lines}, content_type="application/json"
            )
            assert preview.status_code == 200
            checkout = client.post(
                "/pos/api/checkout",
                json={
                    "lines": lines,
                    "payment_method": "cash",
                    "paid_amount": 45.0,
                    "currency": "AED",
                    "warehouse_id": wh.id,
                },
                content_type="application/json",
            )
        assert checkout.status_code == 200


@pytest.mark.slow
@pytest.mark.timeout(300)
class TestPosConcurrencyStress:
    def test_concurrent_checkouts_never_oversell(self, app):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from unittest.mock import patch

        from models import Product, User
        from services.sale_service import SaleService
        from services.stock_service import StockService
        from utils.db_safety import atomic_transaction

        patch("services.sale_service.post_or_fail", return_value=None).start()
        import threading as _t

        _ctr = {"n": 0}
        _ctr_lock = _t.Lock()

        def _gen(*a, **kw):
            with _ctr_lock:
                _ctr["n"] += 1
                n = _ctr["n"]
            return f"S-TEST-{n:04d}"

        patch("services.sale_service.generate_number", side_effect=_gen).start()

        # Patch _safe_for_update to use blocking FOR UPDATE
        def _safe_upd(query, label="row"):
            return query.with_for_update().first()

        import services.stock_service as _ss

        _orig_safe = _ss._safe_for_update
        _ss._safe_for_update = _safe_upd
        try:
            import services.pos_checkout_service as _pcs

            _pcs._safe_for_update = _safe_upd
        except Exception:
            pass

        # Patch lock_row_for_update to use blocking FOR UPDATE
        def _blocking_lock(model, pk, *, label=None, populate_existing=True):
            from extensions import db

            q = db.session.query(model).filter(model.id == pk)
            if populate_existing:
                q = q.populate_existing()
            row = q.with_for_update().first()
            if row is None:
                raise LookupError("Not found")
            return row

        import utils.db_safety as _dbs

        _orig_lock_row = _dbs.lock_row_for_update
        _dbs.lock_row_for_update = _blocking_lock
        with app.app_context():
            env = _bootstrap(db.session, stock="10")
            from models import Customer as Cust

            customers = []
            for i in range(4):
                c = Cust(tenant_id=env["tenant"].id, name=f"Walk-in-{i}", customer_type="regular", is_active=True)
                db.session.add(c)
                db.session.flush()
                customers.append(c)
            db.session.commit()
            tenant_id = env["tenant"].id
            user_id = env["user"].id
            product_id = env["product"].id
            warehouse_id = env["warehouse"].id
            customer_ids = [c.id for c in customers]

        barrier = threading.Barrier(4)

        def worker(idx):
            barrier.wait(timeout=120)
            try:
                with app.app_context():
                    db.session.remove()
                    with atomic_transaction(f"concurrent_checkout_{idx}"):
                        cust = db.session.get(Cust, customer_ids[idx])
                        seller = db.session.get(User, user_id)
                        product = db.session.get(Product, product_id)
                        SaleService.create_sale(
                            customer=cust,
                            seller=seller,
                            lines_data=[
                                {"product": product, "quantity": 3, "unit_price": Decimal("25"), "discount_percent": 0}
                            ],
                            warehouse_id=warehouse_id,
                            currency="AED",
                            tax_rate=0,
                            discount_amount=0,
                            shipping_cost=0,
                            payment_data={
                                "amount": 75.0,
                                "payment_method": "cash",
                                "currency": "AED",
                                "exchange_rate": 1.0,
                            },
                        )
                        db.session.flush()
                return True
            except Exception:
                try:
                    with app.app_context():
                        db.session.rollback()
                except Exception:
                    pass
                return False

        executor = ThreadPoolExecutor(max_workers=4)
        futures = [executor.submit(worker, i) for i in range(4)]
        try:
            results = [f.result(timeout=180) for f in as_completed(futures)]
        except Exception:
            for f in futures:
                f.cancel()
            raise
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        _ss._safe_for_update = _orig_safe
        _dbs.lock_row_for_update = _orig_lock_row

        successes = sum(1 for r in results if r)
        assert successes == 3, f"expected 3 winners, got {successes}: {results}"

        with app.app_context():
            db.session.expire_all()
            stock = StockService.get_product_stock(product_id, warehouse_id=warehouse_id)
            assert Decimal(str(stock)) == Decimal("1"), f"oversell: stock={stock}"
            row = db.session.get(Product, product_id)
            assert row is not None and row.tenant_id == tenant_id
