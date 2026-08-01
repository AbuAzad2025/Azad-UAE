"""
Dual-domain audit: Multi-Warehouse Inventory & Valuation + POS Offline Sync & Cash Sessions.

Two P0 invariants are locked here:

  Inventory / valuation
    * Every stock write is tenant-scoped: ``transfer_stock`` and
      ``create_movement`` refuse to touch a warehouse that belongs to a
      different tenant than the product.
    * ``transfer_stock`` is net-zero: ``product.current_stock`` and the PWS
      aggregate are conserved, two movement rows (out / in) are written.
    * A mid-transfer failure inside the route's ``atomic_transaction`` rolls
      back the partial out-leg — no orphaned movement or PWS drift survives.

  POS cash sessions
    * ``compute_expected_balance`` and blind ``close`` are Decimal-exact:
      expected = opening + cash − change − refunds + pay-ins − pay-outs.
    * Cash over/short always posts a *balanced* journal with the
      ``PosCashDifference`` reference; pay-in/pay-out legs balance too.
    * Session close is idempotent under a replay Idempotency-Key.
"""

import uuid
from decimal import Decimal

import pytest
from extensions import db
from models import Product, StockMovement
from models.gl import GLJournalEntry


def _bootstrap(db_or_session, *, tid=None, stock="100", price="25", cost="10"):
    """Create tenant+role+user + 2 warehouses + a product stocked in WH1."""
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
        name=f"Audit {tid}",
        name_ar=f"Audit {tid}",
        slug=f"audit-{tid}",
        default_currency="AED",
        base_currency="AED",
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
    for code in ("manage_sales", "manage_warehouse", "manage_inventory", "admin"):
        perm = Permission.query.filter_by(code=code).first()
        if not perm:
            perm = Permission(code=code, name=code, name_ar=code, category="audit")
            db_or_session.add(perm)
            db_or_session.flush()
        if perm not in role.permissions:
            role.permissions.append(perm)
    db_or_session.add(role)
    db_or_session.flush()

    user = User(
        username=f"audit-{tid}",
        email=f"audit-{tid}@t.com",
        full_name="Auditor",
        role_id=role.id,
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        is_owner=False,
    )
    user.set_password("x")
    db_or_session.add(user)
    db_or_session.flush()

    wh1 = Warehouse(
        name=f"WH1 {tid}",
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        allow_negative_inventory=False,
    )
    db_or_session.add(wh1)
    db_or_session.flush()
    wh2 = Warehouse(
        name=f"WH2 {tid}",
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        allow_negative_inventory=False,
    )
    db_or_session.add(wh2)
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

    StockService.add_stock(product.id, Decimal(stock), warehouse_id=wh1.id)
    db_or_session.flush()

    if not SystemSettings.query.first():
        db_or_session.add(SystemSettings(enable_pos=True))
    db_or_session.commit()
    return {
        "tenant": tenant,
        "branch": branch,
        "user": user,
        "warehouses": (wh1, wh2),
        "product": product,
    }


def _make_foreign_warehouse(db_or_session, tid=None):
    """Second tenant + a warehouse that belongs to it."""
    from models import Branch, Tenant, Warehouse

    tid = tid or uuid.uuid4().hex[:4]
    other = Tenant(
        name=f"Foreign {tid}",
        name_ar=f"Foreign {tid}",
        slug=f"foreign-{tid}",
        default_currency="AED",
        base_currency="AED",
    )
    db_or_session.add(other)
    db_or_session.flush()
    branch = Branch(tenant_id=other.id, name=f"FB {tid}", code=f"FB{tid[:4]}")
    db_or_session.add(branch)
    db_or_session.flush()
    wh = Warehouse(
        name=f"FWH {tid}",
        tenant_id=other.id,
        branch_id=branch.id,
        is_active=True,
        allow_negative_inventory=False,
    )
    db_or_session.add(wh)
    db_or_session.flush()
    return other, wh


def _login_and_open_pos(client, username):
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


def _pws_quantity(product_id, warehouse_id):
    from models.warehouse import ProductWarehouseStock

    row = ProductWarehouseStock.query.filter_by(
        product_id=product_id,
        warehouse_id=warehouse_id,
    ).first()
    return Decimal(str(row.quantity)) if row else Decimal("0")


def _assert_gl_balanced(entry):
    lines = list(entry.lines)
    assert lines, f"GL entry {entry.id} has no lines"
    total_dr = sum(Decimal(str(line.debit or 0)) for line in lines)
    total_cr = sum(Decimal(str(line.credit or 0)) for line in lines)
    assert total_dr == total_cr, f"GL entry {entry.id} unbalanced: dr={total_dr} cr={total_cr}"
    return total_dr


class TestMultiWarehouseInventoryIsolation:
    """P0: cross-tenant stock writes are impossible; transfers conserve stock."""

    def test_transfer_rejects_foreign_destination_warehouse(self, app, db_session):
        from services.stock_service import StockService

        env = _bootstrap(db_session)
        _, fwh = _make_foreign_warehouse(db_session)
        wh1, _wh2 = env["warehouses"]
        product = env["product"]

        with app.app_context():
            with pytest.raises(ValueError):
                StockService.transfer_stock(product.id, wh1.id, fwh.id, Decimal("5"), user=env["user"])
        db.session.expire_all()
        movements = StockMovement.query.filter(
            StockMovement.product_id == product.id,
            StockMovement.movement_type == "transfer",
        ).all()
        assert movements == [], "cross-tenant transfer leaked stock movements"

    def test_transfer_rejects_both_foreign_warehouses(self, app, db_session):
        from services.stock_service import StockService

        env = _bootstrap(db_session)
        _, fwh = _make_foreign_warehouse(db_session)
        product = env["product"]

        with app.app_context():
            with pytest.raises(ValueError):
                StockService.transfer_stock(product.id, fwh.id, fwh.id, Decimal("5"), user=env["user"])

    def test_create_movement_rejects_foreign_warehouse(self, app, db_session):
        from services.stock_service import StockService

        env = _bootstrap(db_session)
        _, fwh = _make_foreign_warehouse(db_session)
        product = env["product"]

        with app.app_context():
            with pytest.raises(ValueError):
                StockService.create_movement(
                    product_id=product.id,
                    quantity=Decimal("5"),
                    movement_type="adjustment",
                    warehouse_id=fwh.id,
                )

    def test_transfer_is_net_zero_and_conserves_total(self, app, db_session):
        from models import StockMovement
        from models.warehouse import ProductWarehouseStock
        from services.stock_service import StockService

        env = _bootstrap(db_session)
        wh1, wh2 = env["warehouses"]
        product = env["product"]
        tenant_id = env["tenant"].id

        out_m, in_m = StockService.transfer_stock(product.id, wh1.id, wh2.id, Decimal("30"), user=env["user"])
        db.session.flush()

        db.session.expire_all()
        product = db.session.get(Product, product.id)
        assert Decimal(str(product.current_stock)) == Decimal("100"), "transfer must not change total stock"
        assert _pws_quantity(product.id, wh1.id) == Decimal("70")
        assert _pws_quantity(product.id, wh2.id) == Decimal("30")
        total_pws = (
            db.session.query(db.func.coalesce(db.func.sum(ProductWarehouseStock.quantity), 0))
            .filter(ProductWarehouseStock.product_id == product.id)
            .scalar()
        )
        assert Decimal(str(total_pws)) == Decimal("100"), "PWS aggregate drifted"

        pairs = {
            (m.warehouse_id, Decimal(str(m.quantity)))
            for m in StockMovement.query.filter(
                StockMovement.tenant_id == tenant_id,
                StockMovement.product_id == product.id,
                StockMovement.movement_type == "transfer",
            ).all()
        }
        assert (wh1.id, Decimal("-30")) in pairs
        assert (wh2.id, Decimal("30")) in pairs
        assert out_m.id is not None and in_m.id is not None

    def test_transfer_route_rolls_back_partial_movement(self, app, db_session, client):
        """A failing target leg inside atomic_transaction leaves zero trace."""
        from unittest.mock import patch

        from models import StockMovement
        from services.stock_service import StockService

        env = _bootstrap(db_session, stock="100")
        user = env["user"]
        wh1, wh2 = env["warehouses"]
        product = env["product"]

        movements_before = StockMovement.query.filter(
            StockMovement.product_id == product.id,
            StockMovement.warehouse_id.in_([wh1.id, wh2.id]),
        ).count()
        real = StockService.create_movement
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("simulated target-warehouse failure")
            return real(*args, **kwargs)

        with client:
            client.post(
                "/auth/login",
                data={"username": user.username, "password": "x"},
                follow_redirects=True,
            )
            with patch("services.stock_service.StockService.create_movement", side_effect=flaky):
                resp = client.post(
                    "/warehouse/transfer",
                    json={
                        "product_id": product.id,
                        "source_id": wh1.id,
                        "destination_id": wh2.id,
                        "quantity": 20,
                    },
                    content_type="application/json",
                )
        assert resp.status_code == 500, f"expected failure, got {resp.status_code}: {resp.get_json()}"
        assert calls["n"] == 2, "expected exactly the out-leg to succeed before the in-leg failed"

        db.session.expire_all()
        movements_after = StockMovement.query.filter(
            StockMovement.product_id == product.id,
            StockMovement.warehouse_id.in_([wh1.id, wh2.id]),
        ).count()
        assert movements_after == movements_before, "partial transfer leaked stock movements"
        assert _pws_quantity(product.id, wh1.id) == Decimal("100"), "source PWS drifted after rollback"
        assert _pws_quantity(product.id, wh2.id) == Decimal("0"), "destination PWS leaked after rollback"


class TestPosCashSessionMath:
    """P0: expected-drawer math and blind close are Decimal-exact + balanced GL."""

    def test_compute_expected_balance_formula(self):
        from models import PosSession

        session = PosSession(
            tenant_id=1,
            branch_id=1,
            user_id=1,
            session_number="PURE-MATH",
            opening_balance_cash=Decimal("100"),
            total_cash_sales=Decimal("50"),
            total_change_given=Decimal("5"),
            total_cash_refunds=Decimal("0"),
            total_pay_ins=Decimal("20"),
            total_pay_outs=Decimal("10"),
            status=PosSession.STATUS_OPEN,
        )
        expected = session.compute_expected_balance()
        assert expected == Decimal("155.000"), f"formula broke: expected={expected}"
        assert expected == (
            Decimal("100") + Decimal("50") - Decimal("5") - Decimal("0") + Decimal("20") - Decimal("10")
        )

    def test_blind_close_sets_expected_and_difference(self):
        from models import PosSession

        session = PosSession(
            tenant_id=1,
            branch_id=1,
            user_id=1,
            session_number="PURE-CLOSE",
            opening_balance_cash=Decimal("100"),
            total_cash_sales=Decimal("50"),
            total_change_given=Decimal("5"),
            total_cash_refunds=Decimal("0"),
            total_pay_ins=Decimal("20"),
            total_pay_outs=Decimal("10"),
            status=PosSession.STATUS_OPEN,
        )
        session.close(Decimal("150"))
        assert session.status == PosSession.STATUS_CLOSED
        assert session.closing_balance_cash == Decimal("150.000")
        assert session.expected_balance == Decimal("155.000")
        assert session.difference == Decimal("-5.000"), "shortage must be negative"

        session2 = PosSession(
            tenant_id=1,
            branch_id=1,
            user_id=1,
            session_number="PURE-CLOSE2",
            opening_balance_cash=Decimal("0"),
            total_cash_sales=Decimal("50"),
            status=PosSession.STATUS_OPEN,
        )
        session2.close(Decimal("55"))
        assert session2.difference == Decimal("5.000"), "overage must be positive"

    def test_checkout_close_shortage_posts_balanced_gl(self, app, db_session, client):
        from models import PosSession, Sale

        env = _bootstrap(db_session)
        user, wh1 = env["user"], env["warehouses"][0]
        product, tenant = env["product"], env["tenant"]

        with client:
            _login_and_open_pos(client, user.username)
            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [
                        {
                            "product_id": product.id,
                            "quantity": 2,
                            "unit_price": 25.0,
                            "discount_percent": 0,
                        }
                    ],
                    "payment_method": "cash",
                    "paid_amount": 50.0,
                    "currency": "AED",
                    "warehouse_id": wh1.id,
                },
                content_type="application/json",
            )
            assert resp.status_code == 200, f"checkout failed: {resp.get_json()}"

            resp = client.post(
                "/pos/api/session/close",
                json={"counted_cash": 45, "notes": "audit shortage"},
                content_type="application/json",
            )
            assert resp.status_code == 200, f"close failed: {resp.get_json()}"

        session = PosSession.query.filter_by(tenant_id=tenant.id).first()
        assert session.status == "closed"
        assert Decimal(str(session.expected_balance)) == Decimal("50.000")
        assert Decimal(str(session.difference)) == Decimal("-5.000")

        entries = GLJournalEntry.query.filter_by(
            tenant_id=tenant.id,
            reference_type="PosCashDifference",
            reference_id=session.id,
        ).all()
        assert len(entries) == 1, "shortage must post exactly one GL journal"
        assert _assert_gl_balanced(entries[0]) == Decimal("5.000")

        sales = Sale.query.filter_by(tenant_id=tenant.id).all()
        assert len(sales) == 1
        assert _pws_quantity(product.id, wh1.id) == Decimal("98")

    def test_checkout_close_overage_posts_balanced_gl(self, app, db_session, client):
        from models import PosSession

        env = _bootstrap(db_session)
        user, wh1 = env["user"], env["warehouses"][0]
        product, tenant = env["product"], env["tenant"]

        with client:
            _login_and_open_pos(client, user.username)
            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "unit_price": 25.0,
                            "discount_percent": 0,
                        }
                    ],
                    "payment_method": "cash",
                    "paid_amount": 25.0,
                    "currency": "AED",
                    "warehouse_id": wh1.id,
                },
                content_type="application/json",
            )
            assert resp.status_code == 200, f"checkout failed: {resp.get_json()}"

            resp = client.post(
                "/pos/api/session/close",
                json={"counted_cash": 30, "notes": "audit overage"},
                content_type="application/json",
            )
            assert resp.status_code == 200, f"close failed: {resp.get_json()}"

        session = PosSession.query.filter_by(tenant_id=tenant.id).first()
        assert Decimal(str(session.expected_balance)) == Decimal("25.000")
        assert Decimal(str(session.difference)) == Decimal("5.000")

        entries = GLJournalEntry.query.filter_by(
            tenant_id=tenant.id,
            reference_type="PosCashDifference",
            reference_id=session.id,
        ).all()
        assert len(entries) == 1, "overage must post exactly one GL journal"
        assert _assert_gl_balanced(entries[0]) == Decimal("5.000")

    def test_pay_in_pay_out_update_drawer_and_post_balanced_gl(self, app, db_session):
        from models import PosSession
        from services.pos_cash_service import PosCashMovementService

        env = _bootstrap(db_session)
        tenant, user, branch = env["tenant"], env["user"], env["branch"]
        session = PosSession(
            tenant_id=tenant.id,
            branch_id=branch.id,
            user_id=user.id,
            session_number=f"SES-{uuid.uuid4().hex[:8]}",
            opening_balance_cash=Decimal("100"),
            status=PosSession.STATUS_OPEN,
        )
        db_session.add(session)
        db_session.commit()

        mov_in = PosCashMovementService.create_movement(
            user=user,
            session=session,
            movement_type="pay_in",
            amount=Decimal("50"),
            reason="audit pay-in",
        )
        mov_out = PosCashMovementService.create_movement(
            user=user,
            session=session,
            movement_type="pay_out",
            amount=Decimal("20"),
            reason="audit pay-out",
        )
        db.session.flush()
        db.session.expire_all()
        session = db.session.get(PosSession, session.id)
        assert Decimal(str(session.total_pay_ins)) == Decimal("50.000")
        assert Decimal(str(session.total_pay_outs)) == Decimal("20.000")

        expected = session.compute_expected_balance()
        assert expected == Decimal("130.000"), f"drawer formula after pay-in/out drifted: {expected}"

        for movement, amount in ((mov_in, Decimal("50.000")), (mov_out, Decimal("20.000"))):
            entries = GLJournalEntry.query.filter_by(
                tenant_id=tenant.id,
                reference_type="PosCashMovement",
                reference_id=movement.id,
            ).all()
            assert len(entries) == 1, f"pay movement {movement.movement_type} must post exactly one journal"
            assert _assert_gl_balanced(entries[0]) == amount

    def test_session_close_idempotent_replay_posts_gl_once(self, app, db_session, client):
        from models import PosSession

        env = _bootstrap(db_session)
        user, wh1 = env["user"], env["warehouses"][0]
        product, tenant = env["product"], env["tenant"]
        key = f"audit-close-{uuid.uuid4().hex[:10]}"

        with client:
            _login_and_open_pos(client, user.username)
            client.post(
                "/pos/api/checkout",
                json={
                    "lines": [
                        {
                            "product_id": product.id,
                            "quantity": 1,
                            "unit_price": 25.0,
                            "discount_percent": 0,
                        }
                    ],
                    "payment_method": "cash",
                    "paid_amount": 25.0,
                    "currency": "AED",
                    "warehouse_id": wh1.id,
                },
                content_type="application/json",
            )
            payload = {"counted_cash": 22, "notes": "audit idempotent"}
            first = client.post(
                "/pos/api/session/close",
                json=payload,
                headers={"Idempotency-Key": key},
                content_type="application/json",
            )
            second = client.post(
                "/pos/api/session/close",
                json=payload,
                headers={"Idempotency-Key": key},
                content_type="application/json",
            )
        assert first.status_code == 200, f"first close failed: {first.get_json()}"
        assert second.status_code == 200, f"replay failed: {second.get_json()}"

        session = PosSession.query.filter_by(tenant_id=tenant.id).first()
        assert session.status == "closed"
        assert Decimal(str(session.difference)) == Decimal("-3.000")

        entries = GLJournalEntry.query.filter_by(
            tenant_id=tenant.id,
            reference_type="PosCashDifference",
            reference_id=session.id,
        ).all()
        assert len(entries) == 1, "idempotent replay must not double-post the difference journal"
        assert _assert_gl_balanced(entries[0]) == Decimal("3.000")
