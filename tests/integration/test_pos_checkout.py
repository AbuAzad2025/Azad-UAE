"""
POS checkout integration tests.
End-to-end flow verification for POS session, cart, checkout,
sale creation, stock deduction, GL entries, and tenant currency.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
import json
from unittest.mock import patch


@pytest.fixture
def pos_env(app, db_session):
    from extensions import db
    from services.gl_service import GLService
    from models import Tenant, Branch, User, Role, Customer, Product, Warehouse, ProductWarehouseCost
    from services.stock_service import StockService
    from models.system_settings import SystemSettings
    from models.pos_session import PosSession

    ss = SystemSettings.query.first()
    if not ss:
        ss = SystemSettings(enable_pos=True, default_currency="AED")
        db.session.add(ss)
        db.session.flush()
    ss.enable_pos = True

    tid = Tenant.query.order_by(Tenant.id).first()
    if not tid:
        tid = Tenant(name="POSTest", name_ar="POSTest", slug="postest", email="p@t.com", phone_1="0500000000", country="AE", subscription_plan="basic", default_currency="SAR")
        db.session.add(tid)
        db.session.flush()
    tenant_id = tid.id
    GLService.ensure_core_accounts(tenant_id=tenant_id)
    from services.gl_provisioning_service import GLProvisioningService
    GLProvisioningService.provision_tenant(tenant_id)

    branch = Branch.query.filter_by(tenant_id=tenant_id).first()
    if not branch:
        branch = Branch(tenant_id=tenant_id, name="Main", code="MAIN")
        db.session.add(branch)
        db.session.flush()

    role = Role.query.filter_by(slug="owner").first()
    if not role:
        role = Role(name="Owner", slug="owner")
        db.session.add(role)
        db.session.flush()

    user = User.query.filter_by(tenant_id=tenant_id).first()
    if not user:
        user = User(tenant_id=tenant_id, username="postestuser", email="u@t.com", full_name="Test", is_active=True, is_owner=True, branch_id=branch.id, role_id=role.id)
        user.set_password("p")
        db.session.add(user)
        db.session.flush()

    customer = Customer.query.filter_by(tenant_id=tenant_id).first()
    if not customer:
        customer = Customer(tenant_id=tenant_id, name="Walk-in Customer", phone="0500000001", customer_type="walkin")
        db.session.add(customer)
        db.session.flush()

    from uuid import uuid4
    uid = str(uuid4())[:8]
    product = Product(tenant_id=tenant_id, name=f"POS Test Product {uid}", cost_price=Decimal("50"), regular_price=Decimal("100"), has_serial_number=False, is_active=True)
    db.session.add(product)
    db.session.flush()

    wh = Warehouse.query.filter_by(tenant_id=tenant_id, code="TWH").first()
    if not wh:
        wh = Warehouse(tenant_id=tenant_id, name="Test WH", code="TWH", branch_id=branch.id, is_active=True)
        db.session.add(wh)
        db.session.flush()

    pwc = ProductWarehouseCost(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id, total_quantity=Decimal("0"), total_value=Decimal("0"), average_cost=Decimal("0"))
    db.session.add(pwc)
    db.session.flush()

    StockService.add_stock(product.id, Decimal("100"), reference_type="adjustment", reference_id=1, warehouse_id=wh.id)
    db.session.commit()

    env = {
        "tenant_id": tenant_id,
        "branch_id": branch.id,
        "user": user,
        "customer": customer,
        "product": product,
        "warehouse": wh,
        "pwc": pwc,
    }
    yield env
    db.session.rollback()


def _login_user(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        if user.branch_id:
            sess["active_branch_id"] = str(user.branch_id)
            sess["active_branch_mode"] = "single"


class TestPosSessionLifecycle:
    def test_open_and_close_session(self, app, client, pos_env):
        _login_user(client, pos_env["user"])
        with app.app_context():
            from extensions import db
            from models.pos_session import PosSession
            existing = PosSession.query.filter_by(tenant_id=pos_env["tenant_id"], status="open").first()
            if existing:
                existing.status = "closed"
                db.session.commit()

            resp = client.post("/pos/api/session/open", json={"opening_balance": 500})
            assert resp.status_code in (200, 201)
            data = json.loads(resp.data)
            assert data["success"] is True
            assert "session" in data
            session_id = data["session"]["id"]

            with app.app_context():
                session = PosSession.query.get(session_id)
                assert session is not None
                assert session.status == "open"
                assert float(session.opening_balance_cash) == 500.0

            resp2 = client.get("/pos/api/session/current")
            assert resp2.status_code == 200
            data2 = json.loads(resp2.data)
            assert data2["success"] is True
            assert data2["session"]["id"] == session_id

            resp3 = client.post("/pos/api/session/close", json={"closing_balance": 500, "notes": "test close"})
            assert resp3.status_code == 200
            data3 = json.loads(resp3.data)
            assert data3["success"] is True

            with app.app_context():
                session = PosSession.query.get(session_id)
                assert session.status == "closed"
                assert float(session.closing_balance_cash) == 500.0


class TestPosCheckoutFlow:
    @patch("services.sale_service.post_or_fail")
    def test_checkout_creates_sale_and_updates_stock(self, mock_post, app, client, pos_env):
        _login_user(client, pos_env["user"])
        with app.app_context():
            from extensions import db
            from models.pos_session import PosSession
            existing = PosSession.query.filter_by(tenant_id=pos_env["tenant_id"], status="open").first()
            if existing:
                existing.status = "closed"
                db.session.commit()

            client.post("/pos/api/session/open", json={"opening_balance": 0})

            product_id = pos_env["product"].id
            wh_id = pos_env["warehouse"].id
            tid = pos_env["tenant_id"]

            with app.app_context():
                from models import Product
                pre_stock = Product.query.get(product_id).current_stock
                assert pre_stock == 100

            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [{"product_id": product_id, "quantity": 3, "discount_percent": 0, "unit_price": None}],
                    "warehouse_id": wh_id,
                    "currency": "SAR",
                    "exchange_rate": 1.0,
                    "discount_amount": 0,
                    "shipping_cost": 0,
                    "tax_rate": 0,
                    "payment_method": "cash",
                    "paid_amount": 300,
                },
            )
            assert resp.status_code == 200, f"Checkout failed: {resp.get_json()}"
            data = json.loads(resp.data)
            assert data["success"] is True
            assert "sale_id" in data
            assert "sale_number" in data
            sale_id = data["sale_id"]

            with app.app_context():
                from models import Sale
                sale = Sale.query.get(sale_id)
                assert sale is not None
                assert sale.tenant_id == tid
                assert float(sale.total_amount) == 300.0
                assert sale.currency == "SAR"

            with app.app_context():
                from models import Product
                post_stock = Product.query.get(product_id).current_stock
                assert post_stock == 97

            with app.app_context():
                from models.pos_session import PosSession
                session = PosSession.query.filter_by(tenant_id=tid, status="open").first()
                assert session is not None
                assert float(session.total_sales) >= 300.0
                assert float(session.total_cash_sales) >= 300.0

    @patch("services.sale_service.post_or_fail")
    def test_checkout_with_tax_and_shipping(self, mock_post, app, client, pos_env):
        _login_user(client, pos_env["user"])
        with app.app_context():
            from extensions import db
            from models.pos_session import PosSession
            existing = PosSession.query.filter_by(tenant_id=pos_env["tenant_id"], status="open").first()
            if existing:
                existing.status = "closed"
                db.session.commit()
            client.post("/pos/api/session/open", json={"opening_balance": 0})

            product_id = pos_env["product"].id
            wh_id = pos_env["warehouse"].id

            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [{"product_id": product_id, "quantity": 2, "discount_percent": 10, "unit_price": None}],
                    "warehouse_id": wh_id,
                    "currency": "SAR",
                    "exchange_rate": 1.0,
                    "discount_amount": 10,
                    "shipping_cost": 20,
                    "tax_rate": 5,
                    "payment_method": "cash",
                    "paid_amount": 200,
                },
            )
            assert resp.status_code == 200, f"Checkout failed: {resp.get_json()}"
            data = json.loads(resp.data)
            assert data["success"] is True
            sale_id = data["sale_id"]

            with app.app_context():
                from models import Sale
                sale = Sale.query.get(sale_id)
                assert sale.currency == "SAR"
                assert float(sale.shipping_cost) == 20.0

    @patch("services.sale_service.post_or_fail")
    def test_checkout_uses_tenant_default_currency_when_not_specified(self, mock_post, app, client, pos_env):
        _login_user(client, pos_env["user"])
        with app.app_context():
            from extensions import db
            from models.pos_session import PosSession
            existing = PosSession.query.filter_by(tenant_id=pos_env["tenant_id"], status="open").first()
            if existing:
                existing.status = "closed"
                db.session.commit()
            client.post("/pos/api/session/open", json={"opening_balance": 0})

            product_id = pos_env["product"].id
            wh_id = pos_env["warehouse"].id

            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [{"product_id": product_id, "quantity": 1, "discount_percent": 0, "unit_price": None}],
                    "warehouse_id": wh_id,
                    "payment_method": "cash",
                    "paid_amount": 100,
                },
            )
            assert resp.status_code == 200, f"Checkout failed: {resp.get_json()}"
            data = json.loads(resp.data)
            assert data["success"] is True
            sale_id = data["sale_id"]

            with app.app_context():
                from models import Sale
                sale = Sale.query.get(sale_id)
                tenant = pos_env["user"].tenant
                assert sale.currency == tenant.default_currency


class TestPosTenantIsolation:
    @patch("services.sale_service.post_or_fail")
    def test_sale_belongs_to_correct_tenant(self, mock_post, app, client, pos_env):
        _login_user(client, pos_env["user"])
        with app.app_context():
            from extensions import db
            from models.pos_session import PosSession
            existing = PosSession.query.filter_by(tenant_id=pos_env["tenant_id"], status="open").first()
            if existing:
                existing.status = "closed"
                db.session.commit()
            client.post("/pos/api/session/open", json={"opening_balance": 0})

            product_id = pos_env["product"].id
            wh_id = pos_env["warehouse"].id
            tid = pos_env["tenant_id"]

            resp = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [{"product_id": product_id, "quantity": 1, "discount_percent": 0, "unit_price": None}],
                    "warehouse_id": wh_id,
                    "currency": "SAR",
                    "payment_method": "cash",
                    "paid_amount": 100,
                },
            )
            assert resp.status_code == 200
            data = json.loads(resp.data)
            sale_id = data["sale_id"]

            with app.app_context():
                from models import Sale
                sale = Sale.query.get(sale_id)
                assert sale.tenant_id == tid
                assert sale.branch_id == pos_env["branch_id"]


class TestPosPermissions:
    def test_checkout_requires_login(self, client):
        resp = client.post("/pos/api/checkout", json={"lines": []})
        assert resp.status_code in (302, 401, 403)

    def test_session_open_requires_login(self, client):
        resp = client.post("/pos/api/session/open", json={"opening_balance": 0})
        assert resp.status_code in (302, 401, 403)
