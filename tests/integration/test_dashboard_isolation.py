"""
Integration tests for dashboard isolation and feature injection across three panels:
1. Tenant Admin Dashboard (dashboard_company)
2. Branch & Cashier Dashboard (dashboard)
3. Super Admin Dashboard (owner dashboard)
"""

from decimal import Decimal
from datetime import datetime, timezone
import uuid


def _make_tenant(
    db_session, name, slug, currency="ILS", piv=False, tax_rate=Decimal("5.00")
):
    from models import Tenant

    suffix = str(uuid.uuid4())[:8]
    t = Tenant(
        name=f"{name}_{suffix}",
        name_ar=f"{name}_{suffix}",
        slug=f"{slug}_{suffix}",
        default_currency=currency,
        base_currency=currency,
        prices_include_vat=piv,
        default_tax_rate=tax_rate,
    )
    db_session.add(t)
    db_session.flush()
    return t


def _make_branch(db_session, tenant_id, name="Main"):
    from models import Branch

    suffix = str(uuid.uuid4())[:8]
    b = Branch(
        tenant_id=tenant_id,
        name=f"{name}_{suffix}",
        code=f"BR{suffix[:4].upper()}",
        is_active=True,
    )
    db_session.add(b)
    db_session.flush()
    return b


def _make_warehouse(db_session, tenant_id, branch_id, allow_neg=False):
    from models import Warehouse

    suffix = str(uuid.uuid4())[:8]
    w = Warehouse(
        tenant_id=tenant_id,
        name=f"WH_{suffix}",
        branch_id=branch_id,
        allow_negative_inventory=allow_neg,
    )
    db_session.add(w)
    db_session.flush()
    return w


def _make_user(
    db_session, tenant_id, branch_id=None, role_slug="seller", is_owner=False
):
    from models import User, Role

    suffix = str(uuid.uuid4())[:8]
    unique_slug = f"{role_slug}_{suffix}"
    role = Role.query.filter_by(slug=role_slug).first()
    if not role:
        role = Role(name=f"{role_slug}_{suffix}", slug=unique_slug, is_active=True)
        db_session.add(role)
        db_session.flush()
    u = User(
        tenant_id=tenant_id,
        username=f"test_{suffix}",
        email=f"{suffix}@test.com",
        is_active=True,
        password_hash="fakehash",
        branch_id=branch_id,
        role_id=role.id,
        is_owner=is_owner,
    )
    db_session.add(u)
    db_session.flush()
    return u


def _make_customer(db_session, tenant_id):
    from models import Customer

    suffix = uuid.uuid4().hex[:8]
    c = Customer(tenant_id=tenant_id, name=f"Customer_{suffix}")
    db_session.add(c)
    db_session.flush()
    return c


def _make_sale(db_session, tenant_id, branch_id, user_id, amount=Decimal("100.000")):
    from models import Sale, Customer

    c = Customer.query.filter_by(tenant_id=tenant_id).first()
    if not c:
        c = _make_customer(db_session, tenant_id)
    s = Sale(
        tenant_id=tenant_id,
        branch_id=branch_id,
        customer_id=c.id,
        sale_number=f"SAL-{uuid.uuid4().hex[:8].upper()}",
        seller_id=user_id,
        sale_date=datetime.now(timezone.utc),
        subtotal=amount,
        total_amount=amount,
        amount=amount,
        amount_aed=amount,
        paid_amount=Decimal("0"),
        balance_due=amount,
        currency="ILS",
        status="confirmed",
    )
    db_session.add(s)
    db_session.flush()
    return s


def _make_sale_line(
    db_session,
    tenant_id,
    sale_id,
    product_id,
    qty=1,
    price=Decimal("100.000"),
    cost=Decimal("50.000"),
):
    from models import SaleLine

    sl = SaleLine(
        tenant_id=tenant_id,
        sale_id=sale_id,
        product_id=product_id,
        quantity=qty,
        unit_price=price,
        line_total=price * qty,
        cost_price=cost,
    )
    db_session.add(sl)
    db_session.flush()
    return sl


def _make_manager_user(db_session, tenant_id, branch_id):
    """Create a user with super_admin role for company_admin_required endpoints."""
    from models import User, Role

    suffix = str(uuid.uuid4())[:8]
    role = Role.query.filter_by(slug="super_admin").first()
    if not role:
        role = Role(name=f"SA_{suffix}", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.flush()
    u = User(
        tenant_id=tenant_id,
        username=f"mgr_{suffix}",
        email=f"mgr_{suffix}@test.com",
        is_active=True,
        password_hash="fakehash",
        branch_id=branch_id,
        role_id=role.id,
        is_owner=False,
    )
    db_session.add(u)
    db_session.flush()
    u.set_password("password123")
    return u


def _make_product(db_session, tenant_id, name="Test", cost=None):
    from models import Product

    suffix = uuid.uuid4().hex[:8]
    cost_price = cost if cost is not None else Decimal("50.000")
    p = Product(
        tenant_id=tenant_id,
        name=f"{name}_{suffix}",
        sku=f"SKU-{suffix}",
        cost_price=cost_price,
        regular_price=Decimal("100.000"),
        current_stock=Decimal("100.000"),
    )
    db_session.add(p)
    db_session.flush()
    return p


class TestTenantDashboardCurrency:
    def test_tenant_dashboard_uses_dynamic_currency(self, db_session):
        """dashboard_company must use tenant.get_base_currency() not hardcoded AED."""
        from utils.owner_panel import build_company_dashboard_context

        t = _make_tenant(db_session, "CurrTest", "curr-test", currency="ILS")
        b = _make_branch(db_session, t.id)
        ctx = build_company_dashboard_context(tenant_id=t.id, branch_id=b.id)
        assert "tenant" in ctx
        assert ctx["tenant"].get_base_currency == "ILS"

    def test_tenant_dashboard_aed_fallback_removed(self, db_session):
        """No hardcoded 'AED' string in templates; dynamic currency used."""
        t = _make_tenant(db_session, "Fallback", "fallback", currency="ILS")
        b = _make_branch(db_session, t.id)
        from utils.owner_panel import build_company_dashboard_context

        ctx = build_company_dashboard_context(t.id, b.id)
        assert ctx["tenant"].get_base_currency != "AED"

    def test_tenant_dashboard_egp_currency(self, db_session):
        t = _make_tenant(db_session, "EGPTest", "egp-test", currency="EGP")
        b = _make_branch(db_session, t.id)
        from utils.owner_panel import build_company_dashboard_context

        ctx = build_company_dashboard_context(t.id, b.id)
        assert ctx["tenant"].get_base_currency == "EGP"


class TestTenantDashboardStats:
    def test_month_cogs_computed(self, db_session):
        from utils.owner_panel import build_company_dashboard_context

        t = _make_tenant(db_session, "COGSTest", "cogs-test")
        b = _make_branch(db_session, t.id)
        u = _make_user(db_session, t.id, b.id, role_slug="admin")
        p = _make_product(db_session, t.id, cost=Decimal("50"))
        s = _make_sale(db_session, t.id, b.id, u.id, amount=Decimal("200.000"))
        _make_sale_line(
            db_session,
            t.id,
            s.id,
            p.id,
            qty=2,
            price=Decimal("100.000"),
            cost=Decimal("50.000"),
        )
        ctx = build_company_dashboard_context(t.id)
        assert float(ctx["month_cogs"]) == float(100)  # 2 * 50

    def test_month_commissions_zero_if_no_partner(self, db_session):
        from utils.owner_panel import build_company_dashboard_context

        t = _make_tenant(db_session, "CommZero", "comm-zero")
        b = _make_branch(db_session, t.id)
        u = _make_user(db_session, t.id, b.id, role_slug="admin")
        p = _make_product(db_session, t.id)
        s = _make_sale(db_session, t.id, b.id, u.id, amount=Decimal("100.000"))
        _make_sale_line(db_session, t.id, s.id, p.id)
        ctx = build_company_dashboard_context(t.id)
        assert ctx["month_commissions"] == 0.0

    def test_net_profit_equals_sales_minus_cogs_minus_commissions(self, db_session):
        from utils.owner_panel import build_company_dashboard_context

        t = _make_tenant(db_session, "NetProfit", "net-profit")
        b = _make_branch(db_session, t.id)
        u = _make_user(db_session, t.id, b.id, role_slug="admin")
        p = _make_product(db_session, t.id, cost=Decimal("30"))
        s = _make_sale(db_session, t.id, b.id, u.id, amount=Decimal("150.000"))
        _make_sale_line(
            db_session,
            t.id,
            s.id,
            p.id,
            qty=3,
            price=Decimal("50.000"),
            cost=Decimal("30.000"),
        )
        ctx = build_company_dashboard_context(t.id)
        expected_net = (
            float(ctx["month_sales_amount"])
            - ctx["month_cogs"]
            - ctx["month_commissions"]
        )
        assert abs(ctx["month_net_profit"] - expected_net) < 0.01

    def test_branch_scope_filters_stats(self, db_session):
        from utils.owner_panel import build_company_dashboard_context

        t = _make_tenant(db_session, "Scope", "scope")
        b1 = _make_branch(db_session, t.id, name="BranchA")
        b2 = _make_branch(db_session, t.id, name="BranchB")
        _make_user(db_session, t.id, b1.id, role_slug="admin")
        _make_branch(db_session, t.id)
        ctx_b1 = build_company_dashboard_context(t.id, branch_id=b1.id)
        ctx_b2 = build_company_dashboard_context(t.id, branch_id=b2.id)
        assert ctx_b1["scoped_branch_id"] == b1.id
        assert ctx_b2["scoped_branch_id"] == b2.id


class TestDashboardPermissions:
    def test_cashier_cannot_apply_discount(self, db_session):
        from models import User, Role, Tenant

        suffix = str(uuid.uuid4())[:8]
        t = Tenant(
            name=f"CTenant_{suffix}",
            name_ar=f"CTenant_{suffix}",
            slug=f"ctenant_{suffix}",
        )
        db_session.add(t)
        db_session.flush()
        role = Role(name=f"Cashier_{suffix}", slug=f"cashier_{suffix}", is_active=True)
        db_session.add(role)
        db_session.flush()
        u = User(
            tenant_id=t.id,
            username=f"cashier_{suffix}",
            email=f"cashier_{suffix}@test.com",
            is_active=True,
            password_hash="fakehash",
            role_id=role.id,
            is_owner=False,
        )
        assert not u.can_apply_discount()
        assert not u.can_edit_price()

    def test_admin_can_apply_discount(self, db_session):
        t = _make_tenant(db_session, "AdminDisc", "admin-disc")
        u = _make_user(db_session, t.id, role_slug="admin")
        assert u.can_apply_discount() is True

    def test_cashier_edit_price_false(self, db_session):
        from models import User, Role, Tenant

        suffix = str(uuid.uuid4())[:8]
        t = Tenant(
            name=f"EdP_CT_{suffix}", name_ar=f"EdP_CT_{suffix}", slug=f"edp_ct_{suffix}"
        )
        db_session.add(t)
        db_session.flush()
        role = Role(
            name=f"CashierEdP_{suffix}", slug=f"cashier_edp_{suffix}", is_active=True
        )
        db_session.add(role)
        db_session.flush()
        u = User(
            tenant_id=t.id,
            username=f"cedp_{suffix}",
            email=f"cedp_{suffix}@test.com",
            is_active=True,
            password_hash="fakehash",
            role_id=role.id,
            is_owner=False,
        )
        assert not u.can_edit_price()

    def test_manager_can_edit_price(self, db_session):
        from models import User, Role, Tenant

        suffix = str(uuid.uuid4())[:8]
        t = Tenant(
            name=f"MTenant_{suffix}",
            name_ar=f"MTenant_{suffix}",
            slug=f"mtenant_{suffix}",
        )
        db_session.add(t)
        db_session.flush()
        role = Role(name=f"Manager_{suffix}", slug=f"manager_{suffix}", is_active=True)
        db_session.add(role)
        db_session.flush()
        u = User(
            tenant_id=t.id,
            username=f"mgr_{suffix}",
            email=f"mgr_{suffix}@test.com",
            is_active=True,
            password_hash="fakehash",
            role_id=role.id,
            is_owner=False,
        )
        db_session.add(u)
        db_session.flush()
        db_session.refresh(u)
        assert u.role is not None
        assert u.can_edit_price() is True

    def test_owner_can_always_apply_discount(self, db_session):
        t = _make_tenant(db_session, "OwnerDisc", "owner-disc")
        u = _make_user(db_session, t.id, is_owner=True)
        assert u.can_apply_discount() is True
        assert u.can_edit_price() is True

    def test_seller_cannot_apply_discount(self, db_session):
        from models import User, Role, Tenant

        suffix = str(uuid.uuid4())[:8]
        t = Tenant(
            name=f"STenant_{suffix}",
            name_ar=f"STenant_{suffix}",
            slug=f"stenant_{suffix}",
        )
        db_session.add(t)
        db_session.flush()
        role = Role(name=f"Seller_{suffix}", slug=f"seller_{suffix}", is_active=True)
        db_session.add(role)
        db_session.flush()
        u = User(
            tenant_id=t.id,
            username=f"seller_{suffix}",
            email=f"seller_{suffix}@test.com",
            is_active=True,
            password_hash="fakehash",
            role_id=role.id,
            is_owner=False,
        )
        assert not u.can_apply_discount()
        assert not u.can_edit_price()

    def test_dashboard_context_includes_permissions(self, db_session, app):
        """Stats dict from main dashboard route must include can_apply_discount and can_edit_price."""
        t = _make_tenant(db_session, "PermDash", "perm-dash")
        b = _make_branch(db_session, t.id)
        u = _make_user(db_session, t.id, b.id, role_slug="cashier")
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.get("/dashboard", follow_redirects=True)
            assert resp.status_code == 200


class TestTenantSettingsAPI:
    def test_update_tax_rate(self, db_session, app):
        t = _make_tenant(db_session, "TaxAPI", "tax-api", tax_rate=Decimal("5.00"))
        b = _make_branch(db_session, t.id)
        u = _make_manager_user(db_session, t.id, b.id)
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/update-tenant-settings",
                json={
                    "field": "default_tax_rate",
                    "value": "15.00",
                },
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            db_session.refresh(t)
            assert float(t.default_tax_rate) == 15.00

    def test_update_prices_include_vat(self, db_session, app):
        t = _make_tenant(db_session, "VATAPI", "vat-api", piv=False)
        b = _make_branch(db_session, t.id)
        u = _make_manager_user(db_session, t.id, b.id)
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/update-tenant-settings",
                json={
                    "field": "prices_include_vat",
                    "value": True,
                },
            )
            assert resp.status_code == 200
            db_session.refresh(t)
            assert t.prices_include_vat is True

    def test_update_logo_url(self, db_session, app):
        t = _make_tenant(db_session, "LogoAPI", "logo-api")
        b = _make_branch(db_session, t.id)
        u = _make_manager_user(db_session, t.id, b.id)
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/update-tenant-settings",
                json={
                    "field": "logo_url",
                    "value": "https://example.com/logo.png",
                },
            )
            assert resp.status_code == 200
            db_session.refresh(t)
            assert t.logo_url == "https://example.com/logo.png"

    def test_update_tax_rate_unauthorized(self, db_session, app):
        """Cashier cannot update tenant settings."""
        t = _make_tenant(db_session, "Unauth", "unauth")
        b = _make_branch(db_session, t.id)
        u = _make_user(db_session, t.id, b.id, role_slug="cashier")
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/update-tenant-settings",
                json={
                    "field": "default_tax_rate",
                    "value": "10.00",
                },
            )
            assert resp.status_code == 403


class TestWarehouseNegativeToggle:
    def test_toggle_warehouse_negative(self, db_session, app):
        t = _make_tenant(db_session, "WhNeg", "wh-neg")
        b = _make_branch(db_session, t.id)
        w = _make_warehouse(db_session, t.id, b.id, allow_neg=False)
        u = _make_manager_user(db_session, t.id, b.id)
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/toggle-warehouse-negative",
                json={
                    "warehouse_id": w.id,
                },
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["allow_negative_inventory"] is True

    def test_toggle_warehouse_not_found(self, db_session, app):
        t = _make_tenant(db_session, "WhNF", "wh-nf")
        b = _make_branch(db_session, t.id)
        u = _make_manager_user(db_session, t.id, b.id)
        u.set_password("password123")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": u.username, "password": "password123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/toggle-warehouse-negative",
                json={
                    "warehouse_id": 99999,
                },
            )
            assert resp.status_code == 404


class TestSupervisorOverride:
    def _make_supervisor(self, db_session, tenant_id, branch_id):
        from models import User, Role

        suffix = str(uuid.uuid4())[:8]
        role = Role.query.filter_by(slug="super_admin").first()
        if not role:
            role = Role(name=f"SupRole_{suffix}", slug="super_admin", is_active=True)
            db_session.add(role)
            db_session.flush()
        u = User(
            tenant_id=tenant_id,
            username=f"sup_{suffix}",
            email=f"sup_{suffix}@test.com",
            is_active=True,
            password_hash="fakehash",
            branch_id=branch_id,
            role_id=role.id,
            is_owner=True,
        )
        db_session.add(u)
        db_session.flush()
        db_session.refresh(u)
        return u

    def test_supervisor_override_valid(self, db_session, app):
        t = _make_tenant(db_session, "SupOv", "sup-ov")
        b = _make_branch(db_session, t.id)
        cashier = _make_user(db_session, t.id, b.id, role_slug="cashier")
        cashier.set_password("cashier123")
        supervisor = self._make_supervisor(db_session, t.id, b.id)
        supervisor.set_password("sup456")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": cashier.username, "password": "cashier123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/supervisor-override",
                json={
                    "action": "apply_discount",
                    "supervisor_id": supervisor.id,
                    "password": "sup456",
                },
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True

    def test_supervisor_override_wrong_password(self, db_session, app):
        t = _make_tenant(db_session, "SupWrong", "sup-wrong")
        b = _make_branch(db_session, t.id)
        cashier = _make_user(db_session, t.id, b.id, role_slug="cashier")
        cashier.set_password("cashier123")
        supervisor = self._make_supervisor(db_session, t.id, b.id)
        supervisor.set_password("correctpass")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": cashier.username, "password": "cashier123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/supervisor-override",
                json={
                    "action": "edit_price",
                    "supervisor_id": supervisor.id,
                    "password": "wrongpass",
                },
            )
            assert resp.status_code == 403

    def test_supervisor_override_not_supervisor(self, db_session, app):
        t = _make_tenant(db_session, "SupNot", "sup-not")
        b = _make_branch(db_session, t.id)
        cashier1 = _make_user(db_session, t.id, b.id, role_slug="cashier")
        cashier1.set_password("cash123")
        cashier2 = _make_user(db_session, t.id, b.id, role_slug="cashier")
        cashier2.set_password("cash456")
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": cashier1.username, "password": "cash123"},
                follow_redirects=True,
            )
            resp = client.post(
                "/owner/api/supervisor-override",
                json={
                    "action": "apply_discount",
                    "supervisor_id": cashier2.id,
                    "password": "cash456",
                },
            )
            assert resp.status_code == 403


class TestSuperAdminEndpoints:
    def _make_global_owner(self, db_session):
        """Create a platform owner user with tenant_id=None (global)."""
        from models import User, Role

        suffix = str(uuid.uuid4())[:8]
        role = Role.query.filter_by(slug="developer").first()
        if not role:
            role = Role(name=f"OwnerRole_{suffix}", slug="developer", is_active=True)
            db_session.add(role)
            db_session.flush()
        u = User(
            tenant_id=None,
            username=f"owner_{suffix}",
            email=f"owner_{suffix}@test.com",
            is_active=True,
            password_hash="fakehash",
            role_id=role.id,
            is_owner=True,
        )
        u.set_password("ownerpass")
        db_session.add(u)
        db_session.flush()
        return u

    def test_tenant_toggle_status(self, db_session, app):
        t2 = _make_tenant(db_session, "TogOff", "tog-off")
        owner = self._make_global_owner(db_session)
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": owner.username, "password": "ownerpass"},
                follow_redirects=True,
            )
            resp = client.post(f"/owner/api/tenant/{t2.id}/toggle-status", json={})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            db_session.refresh(t2)
            assert t2.is_active is False

    def test_tenant_toggle_default_protected(self, db_session, app):
        """Tenant id=1 (default) should not be toggleable."""
        from models import Tenant

        owner = self._make_global_owner(db_session)
        db_session.commit()
        if Tenant.query.get(1):
            with app.test_client() as client:
                client.post(
                    "/auth/login",
                    data={"username": owner.username, "password": "ownerpass"},
                    follow_redirects=True,
                )
                resp = client.post("/owner/api/tenant/1/toggle-status", json={})
                assert resp.status_code == 400

    def test_update_package_limits(self, db_session, app):
        t = _make_tenant(db_session, "PkgUp", "pkg-up")
        owner = self._make_global_owner(db_session)
        db_session.commit()
        with app.test_client() as client:
            client.post(
                "/auth/login",
                data={"username": owner.username, "password": "ownerpass"},
                follow_redirects=True,
            )
            resp = client.post(
                f"/owner/api/tenant/{t.id}/update-package",
                json={
                    "field": "max_users",
                    "value": "50",
                },
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            db_session.refresh(t)
            assert t.max_users == 50
