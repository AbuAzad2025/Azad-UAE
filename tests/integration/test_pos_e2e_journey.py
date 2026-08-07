"""
POS Phase 5 — E2E journey matrix (real DB, full route stack) + concurrency stress.

Journeys combine the Phase 1-4 surfaces end-to-end: promotions + split tenders
+ upsell metadata + idempotent checkout replay + blind session close with
balanced GL. The stress class fires concurrent checkouts at one stock row and
proves the register never oversells.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC
from decimal import Decimal

import pytest

from extensions import db


def _bootstrap(db_or_session, *, tid=None, stock="100", price="25", cost="10"):
    """Create tenant(pro)+branch+role+user+warehouse+product with stock.

    Commits through the given session so rows are visible to any connection
    (the concurrency class relies on this). Returns a dict of entities.
    """
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
        perm = Permission(
            code="manage_sales",
            name="manage_sales",
            name_ar="manage_sales",
            category="sales",
        )
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
        name=f"WH {tid}",
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        allow_negative_inventory=False,
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
    return {
        "tenant": tenant,
        "branch": branch,
        "user": user,
        "warehouse": wh,
        "product": product,
    }


def _login_and_open(client, username):
    """Login + open POS session + shift through the real routes."""
    client.post(
        "/auth/login",
        data={"username": username, "password": "x"},
        follow_redirects=True,
    )
    resp = client.post(
        "/pos/api/session/open",
        json={"opening_balance": 0},
        content_type="application/json",
    )
    assert resp.status_code == 201, f"session open failed: {resp.get_json()}"
    resp = client.post(
        "/pos/api/shift/open",
        json={"starting_cash": 0},
        content_type="application/json",
    )
    assert resp.status_code == 201, f"shift open failed: {resp.get_json()}"


class TestPosE2EJourney:
    """Full register journeys across the Phase 1-4 feature surfaces."""

    def test_full_journey_promo_split_tender_close_gl(self, app, db_session, client):
        """promo discount + split tenders + upsell key + blind close + balanced GL."""
        from models import GLJournalEntry, Payment, PosSession, Sale

        env = _bootstrap(db_session)
        tenant, user, wh, product = (
            env["tenant"],
            env["user"],
            env["warehouse"],
            env["product"],
        )

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
                    "lines": [
                        {
                            "product_id": product.id,
                            "quantity": 4,
                            "unit_price": 25.0,
                            "discount_percent": 0,
                        },
                    ],
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
            data = resp.get_json()
            assert data["success"] is True
            assert Decimal(str(data["promotion_discount"])) == Decimal("10.0")
            assert "upsell_prompts" in data
            tenders = data.get("tenders") or []
            assert [t["method"] for t in tenders] == ["cash", "card"]

            sale = db.session.get(Sale, data["sale_id"])
            assert sale.total_amount == Decimal("90.000")
            payments = Payment.query.filter_by(sale_id=sale.id).order_by(Payment.id).all()
            assert len(payments) == 2

            session = PosSession.query.filter_by(tenant_id=tenant.id, status="open").first()
            assert session.total_cash_sales == Decimal("50.000")
            assert session.total_card_sales == Decimal("40.000")

            resp = client.post(
                "/pos/api/session/close",
                json={"counted_cash": 50, "notes": "e2e blind close"},
                content_type="application/json",
            )
            assert resp.status_code == 200, f"close failed: {resp.get_json()}"
            closed = resp.get_json()
            assert closed["success"] is True
            assert closed["session"]["status"] == "closed"

        entries = GLJournalEntry.query.filter_by(tenant_id=tenant.id).all()
        assert entries, "journey must post GL entries"
        for entry in entries:
            total_dr = sum(Decimal(str(line.debit or 0)) for line in entry.lines)
            total_cr = sum(Decimal(str(line.credit or 0)) for line in entry.lines)
            assert total_dr == total_cr, f"GL entry {entry.id} unbalanced"

    def test_checkout_idempotency_replay_returns_same_sale(self, app, db_session, client):
        """Same Idempotency-Key twice -> same sale, stock deducted exactly once."""
        from models import Sale
        from services.stock_service import StockService

        env = _bootstrap(db_session, stock="50")
        user, wh, product, tenant = (
            env["user"],
            env["warehouse"],
            env["product"],
            env["tenant"],
        )
        payload = {
            "lines": [
                {
                    "product_id": product.id,
                    "quantity": 3,
                    "unit_price": 25.0,
                    "discount_percent": 0,
                },
            ],
            "payment_method": "cash",
            "paid_amount": 75.0,
            "currency": "AED",
            "warehouse_id": wh.id,
        }
        key = f"e2e-idem-{uuid.uuid4().hex[:12]}"
        with client:
            _login_and_open(client, user.username)
            first = client.post(
                "/pos/api/checkout",
                json=payload,
                headers={"Idempotency-Key": key},
                content_type="application/json",
            )
            second = client.post(
                "/pos/api/checkout",
                json=payload,
                headers={"Idempotency-Key": key},
                content_type="application/json",
            )
        assert first.status_code == 200, f"first failed: {first.get_json()}"
        assert second.status_code == 200, f"replay failed: {second.get_json()}"
        first_id = first.get_json()["sale_id"]
        assert second.get_json()["sale_id"] == first_id

        sales = Sale.query.filter_by(tenant_id=tenant.id).all()
        assert len(sales) == 1
        assert StockService.get_product_stock(product.id, warehouse_id=wh.id) == 47

    def test_evaluate_endpoint_matches_checkout_discount(self, app, db_session, client):
        """The register's live evaluate preview must match checkout reality."""
        from datetime import datetime, timedelta

        from models.campaign import Campaign

        env = _bootstrap(db_session)
        tenant, user, wh, product = (
            env["tenant"],
            env["user"],
            env["warehouse"],
            env["product"],
        )
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

        lines = [
            {
                "product_id": product.id,
                "quantity": 2,
                "unit_price": 25.0,
                "discount_percent": 0,
            },
        ]
        with client:
            _login_and_open(client, user.username)
            preview = client.post(
                "/pos/api/promotions/evaluate",
                json={"lines": lines},
                content_type="application/json",
            )
            assert preview.status_code == 200, f"evaluate failed: {preview.get_json()}"
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
        assert checkout.status_code == 200, f"checkout failed: {checkout.get_json()}"
        preview_discount = Decimal(str(preview.get_json()["total_discount"]))
        checkout_discount = Decimal(str(checkout.get_json()["promotion_discount"]))
        assert preview_discount == checkout_discount == Decimal("5.0")


@pytest.mark.slow
class TestPosConcurrencyStress:
    """Concurrent checkouts against one stock row — the register must never
    oversell, deadlock, or leak a negative balance."""

    def test_concurrent_checkouts_never_oversell(self, app):
        """4 threads x qty 3 against stock 10 -> exactly 3 succeed, stock == 1."""
        from models import Product
        from services.stock_service import StockService

        with app.app_context():
            env = _bootstrap(db.session, stock="10")
            user, wh, product, tenant_id = (
                env["user"],
                env["warehouse"],
                env["product"],
                env["tenant"].id,
            )
            product_id, wh_id, username = product.id, wh.id, user.username

        results = []
        barrier = threading.Barrier(4)

        def worker():
            with app.test_client() as tclient:
                tclient.post(
                    "/auth/login",
                    data={"username": username, "password": "x"},
                    follow_redirects=True,
                )
                tclient.post(
                    "/pos/api/session/open",
                    json={"opening_balance": 0},
                    content_type="application/json",
                )
                tclient.post(
                    "/pos/api/shift/open",
                    json={"starting_cash": 0},
                    content_type="application/json",
                )
                barrier.wait(timeout=30)
                resp = tclient.post(
                    "/pos/api/checkout",
                    json={
                        "lines": [
                            {
                                "product_id": product_id,
                                "quantity": 3,
                                "unit_price": 25.0,
                                "discount_percent": 0,
                            },
                        ],
                        "payment_method": "cash",
                        "paid_amount": 75.0,
                        "currency": "AED",
                        "warehouse_id": wh_id,
                    },
                    content_type="application/json",
                )
                body = resp.get_json(silent=True) or {}
                results.append((resp.status_code, bool(body.get("success"))))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
        assert not any(t.is_alive() for t in threads), "deadlock: a checkout thread hung"

        successes = sum(1 for status, ok in results if status == 200 and ok)
        failures = len(results) - successes
        assert successes == 3, f"expected exactly 3 winners, got {successes}: {results}"
        assert failures == 1

        with app.app_context():
            db.session.expire_all()
            stock = StockService.get_product_stock(product_id, warehouse_id=wh_id)
            assert Decimal(str(stock)) == Decimal("1"), f"oversell detected: stock={stock}"
            row = db.session.get(Product, product_id)
            assert row is not None and row.tenant_id == tenant_id
