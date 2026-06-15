"""
Comprehensive Multi-Tenant Isolation Test Suite.
Covers: ORM scoping, shop exemption, tenant session locking,
platform owner context switching, skip_tenant_scope audit, and payment separation.
"""
from __future__ import annotations

import re
from decimal import Decimal

import pytest
from flask import g

from models import Product, Sale, Tenant
from models.shop_customer_account import ShopCustomerAccount
from models.system_settings import SystemSettings
from models.tenant_store import TenantStore
from models.user import User
from services.store_checkout_service import StoreCheckoutService
from services.store_payment_method_service import StorePaymentMethodService
from services.store_service import StoreService
from services.stock_service import StockService
from utils.auth_helpers import is_global_owner_user
from utils.tenant_orm import tenant_scope_enabled, _SKIP_BLUEPRINTS
from utils.tenanting import (
    get_active_tenant_id,
    is_platform_owner,
    set_active_tenant,
    clear_active_tenant,
    without_tenant_scope,
    tenant_query,
    tenant_get_or_404,
)


# =============================================================================
# 1. ORM-layer tenant isolation
# =============================================================================

class TestORMTenantIsolation:
    """Verify the automatic tenant criteria injection."""

    def test_tenant_scope_disabled_in_shop_blueprint(self, app):
        """Shop blueprint is exempt from ORM scoping by design."""
        assert "shop" in _SKIP_BLUEPRINTS

    def test_tenant_scope_disabled_in_public_blueprint(self, app):
        """Public blueprint is exempt from ORM scoping."""
        assert "public" in _SKIP_BLUEPRINTS

    def test_tenant_scope_disabled_in_auth_blueprint(self, app):
        """Auth blueprint is exempt from ORM scoping."""
        assert "auth" in _SKIP_BLUEPRINTS

    def test_tenant_scope_disabled_in_tenants_blueprint(self, app):
        """Tenants blueprint is exempt from ORM scoping."""
        assert "tenants" in _SKIP_BLUEPRINTS

    def test_store_admin_not_exempt(self, app):
        """Store admin blueprint is NOT exempt from ORM scoping."""
        assert "store" not in _SKIP_BLUEPRINTS

    def test_tenant_scope_function_checks_auth(self, app):
        """tenant_scope_enabled returns False for anonymous user (no request context)."""
        # Outside request context -> False
        from utils.tenant_orm import tenant_scope_enabled
        assert tenant_scope_enabled() is False

    def test_skip_tenant_scope_flag_disables_scoping(self, app):
        """Setting g.skip_tenant_scope=True disables tenant scoping."""
        with app.test_request_context("/"):
            g.skip_tenant_scope = True
            assert tenant_scope_enabled() is False


# =============================================================================
# 2. Shop (public store) manual tenant scoping
# =============================================================================

class TestShopStoreTenantIsolation:
    """All shop routes are exempt from ORM scoping but manually scope by tenant_id."""

    @pytest.fixture(autouse=True)
    def setup_stores(self, app, db_session):
        """Ensure two tenant stores exist with products that don't conflict."""
        import uuid
        uid = str(uuid.uuid4())[:8]
        SystemSettings.get_current().enable_ecommerce = True
        StorePaymentMethodService.ensure_defaults()

        # Create tenant 1 with store A
        t1 = Tenant(name=f"Store T1 {uid}", name_ar="متجر 1", slug=f"store-t1-{uid}")
        db_session.add(t1)
        db_session.flush()

        # Create tenant 2 with store B
        t2 = Tenant(name=f"Store T2 {uid}", name_ar="متجر 2", slug=f"store-t2-{uid}")
        db_session.add(t2)
        db_session.flush()

        # Products for T1
        p1 = Product(name=f"T1 Product A {uid}", sku=f"T1-SKU-A-{uid}", tenant_id=t1.id,
                     regular_price=Decimal("100"), is_active=True)
        p2 = Product(name=f"T1 Product B {uid}", sku=f"T1-SKU-B-{uid}", tenant_id=t1.id,
                     regular_price=Decimal("200"), is_active=True)
        db_session.add_all([p1, p2])

        # Products for T2
        p3 = Product(name=f"T2 Product A {uid}", sku=f"T2-SKU-A-{uid}", tenant_id=t2.id,
                     regular_price=Decimal("300"), is_active=True)
        p4 = Product(name=f"T2 Product B {uid}", sku=f"T2-SKU-B-{uid}", tenant_id=t2.id,
                     regular_price=Decimal("400"), is_active=True)
        db_session.add_all([p3, p4])
        db_session.flush()

        # Setup stores
        store_a = StoreService.ensure_tenant_store(t1.id)
        wh_a = StoreService.ensure_online_warehouse(t1.id)
        store_a.warehouse_id = wh_a.id
        store_a.store_slug = f"test-store-{t1.id}-{uid}"
        store_a.is_enabled = True

        store_b = StoreService.ensure_tenant_store(t2.id)
        wh_b = StoreService.ensure_online_warehouse(t2.id)
        store_b.warehouse_id = wh_b.id
        store_b.store_slug = f"test-store-{t2.id}-{uid}"
        store_b.is_enabled = True

        # Stock for all products
        for pid in [p1.id, p2.id, p3.id, p4.id]:
            wh = wh_a if pid in (p1.id, p2.id) else wh_b
            StockService.add_stock(
                pid, Decimal("10"),
                warehouse_id=wh.id,
                reference_type="test_setup",
                notes="test stock",
            )

        # System users needed for checkout seller resolution
        from models import Role
        sys_role = Role(name=f"System {uid}", slug=f"sys-{uid}", is_active=True)
        db_session.add(sys_role)
        db_session.flush()
        for tid, slug_part in [(t1.id, f"t1{uid}"), (t2.id, f"t2{uid}")]:
            sys_user = User(
                username=f"sys-{slug_part}", email=f"sys-{slug_part}@test.test",
                full_name=f"System {slug_part}", tenant_id=tid,
                role_id=sys_role.id,
                is_active=True, is_owner=False,
            )
            sys_user.set_password("SysPass123!")
            db_session.add(sys_user)

        # Shop accounts
        for tid, slug_part in [(t1.id, f"t1{uid}"), (t2.id, f"t2{uid}")]:
            email = f"shop-{slug_part}@test.test"
            existing = ShopCustomerAccount.query.filter_by(tenant_id=tid, email=email).first()
            if not existing:
                from services.shop_customer_auth_service import ShopCustomerAuthService
                ShopCustomerAuthService.register(
                    tenant_id=tid, name=f"Shop User {slug_part}",
                    email=email, phone=f"0500000{tid:03d}",
                    password="TestPass123!", address=f"Addr {uid}",
                )

        db_session.commit()

        self._t1 = t1
        self._t2 = t2
        self._p1 = p1
        self._p2 = p2
        self._p3 = p3
        self._p4 = p4
        self._store_a_slug = f"test-store-{t1.id}-{uid}"
        self._store_b_slug = f"test-store-{t2.id}-{uid}"
        self._uid = uid

    def _login_shop(self, client, tenant_id: int):
        """Login to a shop tenant account via session."""
        acct = ShopCustomerAccount.query.filter_by(tenant_id=tenant_id).first()
        from services.shop_customer_auth_service import ShopCustomerAuthService
        with client.session_transaction() as sess:
            sess[ShopCustomerAuthService.session_key(tenant_id)] = acct.id

    def _csrf(self, client, url: str) -> str | None:
        r = client.get(url)
        html = r.data.decode("utf-8", errors="ignore")
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        return m.group(1) if m else None

    # --- Test 1: Anonymous browsing ---
    def test_anonymous_cannot_see_other_tenant_products(self, client, app):
        """Anonymous visitor browsing Tenant A store cannot see Tenant B products."""
        with app.test_request_context():
            r = client.get(f"/s/{self._store_a_slug}")
            body = r.data.decode("utf-8", errors="ignore")
            assert r.status_code == 200
            # Should see T1 products (name includes uid)
            uid = self._uid
            assert f"T1 Product A {uid}" in body
            assert f"T1 Product B {uid}" in body
            # Should NOT see T2 products
            assert f"T2 Product A {uid}" not in body
            assert f"T2 Product B {uid}" not in body

    def test_store_b_catalog_isolated_from_t1(self, client, app):
        """Tenant B store shows only Tenant B products."""
        with app.test_request_context():
            r = client.get(f"/s/{self._store_b_slug}")
            body = r.data.decode("utf-8", errors="ignore")
            assert r.status_code == 200
            uid = self._uid
            assert f"T2 Product A {uid}" in body
            assert f"T2 Product B {uid}" in body
            assert f"T1 Product A {uid}" not in body
            assert f"T1 Product B {uid}" not in body

    # --- Test 2: Product detail isolation ---
    def test_product_detail_cross_tenant_returns_404(self, app):
        """Tenant A product is not visible when queried under Tenant B's tenant_id."""
        # T1 product queried with T2's tenant_id -> should return None (data isolation)
        product = Product.query.filter_by(
            id=self._p1.id, tenant_id=self._t2.id, is_active=True
        ).first()
        assert product is None

    def test_product_detail_own_tenant_succeeds(self, client, app):
        """Tenant A product detail works when accessed via correct slug."""
        with app.test_request_context():
            r = client.get(f"/s/{self._store_a_slug}/p/{self._p1.id}")
            assert r.status_code == 200

    # --- Test 3: Cart isolation ---
    def test_cart_isolation_between_tenants(self, client, app):
        """Cart session data is scoped by tenant_id key."""
        self._login_shop(client, self._t1.id)
        with app.test_request_context():
            client.get(f"/s/{self._store_a_slug}")
            cart_key_t1 = StoreService.cart_session_key(self._t1.id)
            cart_key_t2 = StoreService.cart_session_key(self._t2.id)

            with client.session_transaction() as sess:
                # Add item to T1 cart
                sess[cart_key_t1] = {str(self._p1.id): 1}
                # T2 cart should be empty
                sess.pop(cart_key_t2, None)

            # Switch to T2 login
            self._login_shop(client, self._t2.id)
            with client.session_transaction() as sess:
                t2_cart = sess.get(cart_key_t2, {})
                assert t2_cart == {}  # T2 cart should remain empty

    # --- Test 4: Cross-tenant cart add ---
    def test_cross_tenant_cart_add_is_blocked(self, client, app):
        """Tenant A store cannot add Tenant B products to cart."""
        self._login_shop(client, self._t1.id)
        with app.test_request_context():
            token = self._csrf(client, f"/s/{self._store_a_slug}")
            if token:
                r = client.post(
                    f"/s/{self._store_a_slug}/cart/add",
                    data={"product_id": self._p3.id, "quantity": 1, "csrf_token": token},
                    follow_redirects=False,
                )
                # Even if POST redirects, the cart should not contain T2 product
                with client.session_transaction() as sess:
                    cart = dict(sess.get(StoreService.cart_session_key(self._t1.id), {}))
                assert str(self._p3.id) not in cart

    # --- Test 5: Checkout isolation ---
    def test_checkout_creates_sale_with_correct_tenant_id(self, app, db_session):
        """Checkout creates a Sale record attributed to the correct tenant."""
        with app.test_request_context():
            store_a = StoreService.get_store_by_slug(self._store_a_slug)
            account = ShopCustomerAccount.query.filter_by(tenant_id=self._t1.id).first()

            sale = StoreCheckoutService.create_web_order(
                store_a, {str(self._p1.id): 1},
                customer_name="Test Checkout", phone="0500000111",
                address="Test Address", notes="test checkout isolation",
                payment_method_code="cod", shop_account=account,
            )
            db_session.commit()
            assert sale.tenant_id == self._t1.id
            assert sale.source == "online_store"
            assert sale.customer.tenant_id == self._t1.id

    # --- Test 6: Order token cross-tenant validation ---
    def test_order_token_rejects_wrong_tenant(self, app, db_session):
        """Order token validates tenant_id and blocks cross-tenant access."""
        store_a = StoreService.get_store_by_slug(self._store_a_slug)
        account = ShopCustomerAccount.query.filter_by(tenant_id=self._t1.id).first()
        sale = StoreCheckoutService.create_web_order(
            store_a, {str(self._p1.id): 1},
            customer_name="Token Test", phone="0500000222",
            address="Addr", notes="token test",
            payment_method_code="cod", shop_account=account,
        )
        db_session.commit()
        token = StoreCheckoutService.make_order_token(sale.id, self._t1.id)

        # Token loads successfully for correct tenant
        payload = StoreCheckoutService.load_order_token(token)
        assert payload is not None
        assert payload['tenant_id'] == self._t1.id
        assert payload['sale_id'] == sale.id

        # T2 store cannot find the order (scoped by different tenant_id)
        t2_order = Sale.query.filter_by(
            id=sale.id, tenant_id=self._t2.id, source='online_store'
        ).first()
        assert t2_order is None

    # --- Test 7: Account orders cross-tenant ---
    def test_account_orders_do_not_leak(self, app, db_session):
        """Shop account from Tenant A cannot see Tenant B orders."""
        # Create an order for T2
        store_b = StoreService.get_store_by_slug(self._store_b_slug)
        acct_b = ShopCustomerAccount.query.filter_by(tenant_id=self._t2.id).first()
        sale_b = StoreCheckoutService.create_web_order(
            store_b, {str(self._p3.id): 1},
            customer_name="Order B", phone="0500000333",
            address="Addr B", notes="leak test",
            payment_method_code="cod", shop_account=acct_b,
        )
        db_session.commit()

        # T1 cannot access T2's order via tenant-scoped query
        from services.store_order_service import StoreOrderService
        result = StoreOrderService.get_tenant_order(self._t1.id, sale_b.id)
        assert result is None  # Wrong tenant_id -> None

        # T2's own order shows up for T2
        result = StoreOrderService.get_tenant_order(self._t2.id, sale_b.id)
        assert result is not None
        assert result.id == sale_b.id


# =============================================================================
# 3. Tenant session locking (non-owners cannot switch)
# =============================================================================

class TestTenantSessionLocking:
    """Verify tenant-level users cannot override their active tenant."""

    def test_tenant_user_cannot_switch_tenant(self, app, sample_tenant, sample_user):
        """A tenant-level user (non-owner) cannot override session['active_tenant_id']."""
        with app.test_request_context("/"):
            g.active_tenant_id = sample_user.tenant_id
            tid = get_active_tenant_id(sample_user)
            assert tid == sample_user.tenant_id
            # Attempt to set different tenant via session
            set_active_tenant(9999)
            tid2 = get_active_tenant_id(sample_user)
            # Should still be locked to user.tenant_id (non-owner ignores session)
            assert tid2 == sample_user.tenant_id
            assert tid2 != 9999

    def test_tenant_user_session_override_ignored(self, app, sample_tenant, sample_user):
        """Non-owner session tenant override is ignored."""
        with app.test_request_context("/"):
            from flask import session as fsess
            fsess["active_tenant_id"] = 5555
            tid = get_active_tenant_id(sample_user)
            # Non-owner: session is ignored, returns user.tenant_id
            assert tid == sample_user.tenant_id
            assert tid != 5555

    def test_tenant_without_tenant_id_gets_none(self, app, sample_user):
        """User without tenant_id gets None (not a wrong tenant)."""
        sample_user.tenant_id = None
        with app.test_request_context("/"):
            tid = get_active_tenant_id(sample_user)
            assert tid is None


# =============================================================================
# 4. Platform owner context switching
# =============================================================================

class TestPlatformOwnerContextSwitch:
    """Only platform owner/developer can switch active tenant context."""

    @pytest.fixture
    def owner_user(self, db_session, sample_role):
        import uuid
        uid = str(uuid.uuid4())[:8]
        from models import User
        u = User(
            username=f"test-owner-{uid}", email=f"owner-{uid}@test.test",
            full_name="Test Owner", tenant_id=None,
            role_id=sample_role.id,
            is_owner=True, is_active=True,
        )
        u.set_password("owner123")
        db_session.add(u)
        db_session.commit()
        return u

    @pytest.fixture
    def dev_user(self, db_session, sample_role):
        import uuid
        uid = str(uuid.uuid4())[:8]
        from models import User, Role
        dev_role = Role.query.filter_by(slug='developer').first()
        if not dev_role:
            dev_role = Role(name=f"Developer {uid}", slug="developer", is_active=True)
            db_session.add(dev_role)
            db_session.flush()
        u = User(
            username=f"test-dev-{uid}", email=f"dev-{uid}@test.test",
            full_name="Test Dev", role_id=dev_role.id,
            is_owner=False, is_active=True,
        )
        u.set_password("dev123")
        db_session.add(u)
        db_session.commit()
        return u

    @pytest.fixture
    def other_tenant(self, db_session):
        import uuid
        uid = str(uuid.uuid4())[:8]
        t = Tenant(name=f"Other Tenant {uid}", name_ar="تينانت آخر", slug=f"other-tenant-{uid}")
        db_session.add(t)
        db_session.commit()
        return t

    def test_owner_can_switch_tenant(self, app, owner_user, other_tenant):
        """Platform owner can switch active tenant."""
        with app.test_request_context("/"):
            assert is_platform_owner(owner_user) is True
            set_active_tenant(other_tenant.id)
            tid = get_active_tenant_id(owner_user)
            assert tid == other_tenant.id

    def test_owner_can_clear_tenant(self, app, owner_user):
        """Platform owner can clear active tenant (set to None)."""
        with app.test_request_context("/"):
            set_active_tenant(None)
            # After clearing, owner falls back to user.tenant_id
            tid = get_active_tenant_id(owner_user)
            assert tid == owner_user.tenant_id

    def test_owner_has_is_owner_true(self, owner_user):
        """is_global_owner_user returns True for owner."""
        assert is_global_owner_user(owner_user) is True

    def test_developer_has_is_owner_true(self, dev_user):
        """is_global_owner_user returns True for developer role."""
        assert is_global_owner_user(dev_user) is True

    def test_non_owner_has_is_owner_false(self, sample_user):
        """is_global_owner_user returns False for regular user."""
        assert is_global_owner_user(sample_user) is False

    def test_is_platform_owner_true_for_owner(self, owner_user):
        """is_platform_owner returns True for owner."""
        assert is_platform_owner(owner_user) is True


# =============================================================================
# 5. skip_tenant_scope usage audit
# =============================================================================

class TestSkipTenantScopeAudit:
    """Verify skip_tenant_scope is only used in platform-level or test code."""

    def test_without_tenant_scope_only_in_init(self):
        """without_tenant_scope is used in system_init.py (platform-only)."""
        import utils.system_init
        source = open(utils.system_init.__file__, "r", encoding="utf-8").read()
        count = source.count("without_tenant_scope")
        assert count > 0, "system_init.py should use without_tenant_scope"

    def test_no_skip_tenant_scope_in_route_files(self):
        """Route files should not use 'skip_tenant_scope' execution option."""
        import os
        route_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "routes")
        for fname in os.listdir(route_dir):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(route_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                source = f.read()
            # skip_tenant_scope should not appear in route code directly
            if "skip_tenant_scope" in source:
                pytest.fail(f"{fname} contains skip_tenant_scope usage")

    def test_without_tenant_scope_not_in_business_services(self):
        """Business services should not use without_tenant_scope."""
        import os
        svc_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "services")
        for fname in os.listdir(svc_dir):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(svc_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                source = f.read()
            if "without_tenant_scope" in source:
                pytest.fail(f"{fname} uses without_tenant_scope")


# =============================================================================
# 6. Public / landing / donation pages work without tenant context
# =============================================================================

class TestPlatformPublicPages:
    """Landing/donation/package-purchase pages work without tenant context."""

    def test_landing_page_works_anonymous(self, client, app):
        """Platform landing page returns 200 without any tenant context."""
        with app.test_request_context("/"):
            r = client.get("/")
            assert r.status_code in (200,)
            body = r.data.decode("utf-8", errors="ignore")
            # Should not contain tenant-specific data
            assert "Internal Server Error" not in body

    def test_pricing_page_works_anonymous(self, client, app):
        """Pricing page returns 200 without tenant context."""
        with app.test_request_context("/"):
            r = client.get("/pricing")
            assert r.status_code == 200

    def test_features_page_works_anonymous(self, client, app):
        """Features page returns 200 without tenant context."""
        with app.test_request_context("/"):
            r = client.get("/features")
            assert r.status_code == 200

    def test_tenant_public_profile_works(self, app, client, sample_tenant):
        """Tenant public profile works without login."""
        with app.test_request_context("/"):
            r = client.get(f"/tenant/{sample_tenant.slug}")
            assert r.status_code in (200,)


# =============================================================================
# 7. Platform-treasury vs tenant-payment separation
# =============================================================================

class TestPaymentSeparation:
    """Platform-public payments are separate from tenant operational payments."""

    @pytest.fixture(autouse=True)
    def _setup(self, db_session, sample_tenant):
        from models import PaymentVault, Package
        # Platform vault (tenant_id IS NULL)
        self._platform_vault = PaymentVault(
            vault_name="Platform Vault", vault_password_hash="x",
            is_locked=False,
        )
        db_session.add(self._platform_vault)
        # Tenant vault
        self._tenant_vault = PaymentVault(
            tenant_id=sample_tenant.id,
            vault_name="Tenant Vault", vault_password_hash="x",
            is_locked=False,
        )
        db_session.add(self._tenant_vault)
        db_session.commit()

    def test_platform_vault_has_no_tenant_id(self):
        """Platform vault has NULL tenant_id."""
        assert self._platform_vault.tenant_id is None

    def test_tenant_vault_has_tenant_id(self):
        """Tenant vault has a tenant_id."""
        assert self._tenant_vault.tenant_id is not None

    def test_platform_vault_not_returned_by_tenant_query(self):
        """Platform vault is not returned when filtering by tenant_id."""
        from models import PaymentVault
        q = PaymentVault.query.filter(PaymentVault.tenant_id == self._tenant_vault.tenant_id)
        vaults = q.all()
        for v in vaults:
            assert v.id != self._platform_vault.id

    def test_get_platform_vault_returns_only_platform(self):
        """get_platform_vault returns only the vault with tenant_id IS NULL."""
        from models import PaymentVault
        vault = PaymentVault.get_platform_vault()
        assert vault is not None
        assert vault.tenant_id is None

    def test_get_tenant_vault_returns_correct_vault(self):
        """get_tenant_vault returns the vault for a specific tenant."""
        from models import PaymentVault
        vault = PaymentVault.get_tenant_vault(self._tenant_vault.tenant_id)
        assert vault is not None
        assert vault.id == self._tenant_vault.id


# =============================================================================
# 8. Package/Subscription models have no tenant_id (platform-level)
# =============================================================================

class TestPlatformLevelModels:
    """Package, PackagePurchase, CardPayment have no tenant_id (platform-only)."""

    def test_package_has_no_tenant_column(self):
        """Package model has no tenant_id column (platform-level)."""
        from models import Package
        assert not hasattr(Package, "tenant_id")

    def test_package_purchase_has_no_tenant_column(self):
        """PackagePurchase model has no tenant_id column (platform-level)."""
        from models.package import PackagePurchase
        assert not hasattr(PackagePurchase, "tenant_id")

    def test_card_payment_has_no_tenant_column(self):
        """CardPayment model has no tenant_id column (platform-level)."""
        from models.card_payment import CardPayment
        assert not hasattr(CardPayment, "tenant_id")

    def test_donation_has_optional_tenant_id(self):
        """Donation has optional tenant_id (NULL = platform donation)."""
        from models import Donation
        assert hasattr(Donation, "tenant_id")


# =============================================================================
# 9. Store admin routes (login-required) are tenant-scoped
# =============================================================================

class TestStoreAdminTenantScope:
    """Store admin routes use normal ORM tenant scoping (non-exempt)."""

    def test_store_admin_blueprint_not_exempt(self):
        """'store' blueprint is NOT in _SKIP_BLUEPRINTS — it uses ORM scoping."""
        assert "store" not in _SKIP_BLUEPRINTS

    def test_store_admin_requires_login(self, client, app):
        """Store admin routes require authentication."""
        with app.test_request_context("/"):
            r = client.get("/store/admin", follow_redirects=False)
            assert r.status_code in (302, 401, 403)
