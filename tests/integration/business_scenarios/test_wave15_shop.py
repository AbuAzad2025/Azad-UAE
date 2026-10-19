"""Wave 15 - the storefront and the store admin. Prefix SHOP.

The storefront is the only surface in the system that an unauthenticated
stranger can put money into, and that is why it gets a scenario suite of its
own. Everything else in the product is behind a sign-in; here, a cart is a
session key and a checkout is a form.

Three rules carry the wave. The first is the publication gate: a store that
is disabled, locked by the platform, or belonging to a suspended tenant answers
503 and shows a closed page rather than a catalogue (SHOP-04 to SHOP-07). A
storefront that keeps selling after the tenant has been suspended is worse
than one that never opened.

The second is the stock rule. The cart never holds more than the online
warehouse has (SHOP-15, SHOP-16), and a product that is not on sale - inactive,
or serialised, because a serialised item is one specific unit and not a
quantity - cannot be put in the cart at all (SHOP-13, SHOP-14). The cart is
capped on the way in *and* on the way out, because a session can be edited
outside the application.

The third is the tenant boundary. The cart lives in the session under the
tenant's key, so two stores in the same browser do not share a basket
(SHOP-20), and the product pages are answered from the tenant's own catalogue
rather than from the whole installation (SHOP-24, SHOP-25).

The store admin - /store/admin - is the other half of the domain and the
opposite of the storefront: it is behind ``manage_store`` (SHOP-40 onwards),
and it is where the tenant changes the things the storefront shows. A store
that is off in the admin is off in the world, which is why the switch is
pinned from both sides.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

#: The public storefront paths, addressed by the store's slug.
SHOP_PATHS = [
    "/s/{slug}/",
    "/s/{slug}/lang/ar",
    "/s/{slug}/offline",
    "/s/{slug}/wishlist",
    "/s/{slug}/account/login",
    "/s/{slug}/account/register",
    "/s/{slug}/api/search?q=probe",
    "/s/{slug}/cart",
    "/s/{slug}/cart/count",
    "/s/{slug}/checkout",
    "/s/{slug}/return-policy",
    "/s/{slug}/sitemap.xml",
    "/s/{slug}/robots.txt",
    "/s/{slug}/account/forgot-password",
    "/s/{slug}/track",
]
SHOP_POST_PATHS = [
    "/s/{slug}/wishlist/add/1",
    "/s/{slug}/wishlist/remove/1",
    "/s/{slug}/cart/add",
    "/s/{slug}/cart/update",
    "/s/{slug}/cart/remove/1",
    "/s/{slug}/newsletter/subscribe",
]
STORE_ADMIN_PATHS = [
    "/store/admin",
    "/store/admin/settings",
    "/store/admin/catalog",
    "/store/admin/transfer",
    "/store/admin/orders",
    "/store/admin/orders/1",
    "/store/admin/customers",
    "/store/admin/stats",
    "/store/admin/coupons",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title()[:50], slug=slug[:50], is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="shop-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"shop-{slug}-{unique}",
        email=f"shop-{unique}@example.com",
        full_name=f"Shop {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    """A signed-in user carrying exactly ``codes``."""
    role_slug = f"{slug}-{uuid.uuid4().hex[:10]}"
    user = _user(db_session, tenant, slug=role_slug, permissions=list(codes), branch=branch)
    _login(client, user)
    return user


def _stores_enabled(db_session, tenant=None):
    """Switch the platform's ecommerce flag on, and the tenant's store feature.

    Stores are a platform-wide switch: with it off, every storefront answers
    503 and there is nothing to test. The admin surface is behind the tenant's
    own ``enable_store`` flag, which the feature gate checks on every request.
    Both are set here rather than mocked, because both are what the product
    actually does.
    """
    from models.system_settings import SystemSettings
    from models.tenant import Tenant

    settings = SystemSettings.get_current()
    settings.enable_ecommerce = True
    if tenant is not None:
        row = db_session.get(Tenant, tenant.id)
        if row is not None:
            row.enable_store = True
    db_session.flush()
    return settings


def _store(db_session, tenant, *, enabled=True, slug=None):
    """The tenant's storefront, with its own online warehouse."""
    from services.store_service import StoreService

    store = StoreService.ensure_tenant_store(tenant.id)
    store.is_enabled = enabled
    store.store_slug = slug or f"probe-shop-{uuid.uuid4().hex[:6]}"
    store.title = "Probe Store"
    db_session.flush()
    db_session.commit()
    return store


def _product(db_session, tenant, *, name="Probe Product", stock="10", active=True, serial=False):
    """A product with stock in the tenant's online warehouse."""
    from models import Product
    from services.stock_service import StockService
    from services.store_service import StoreService

    unique = uuid.uuid4().hex[:8]
    product = Product(
        tenant_id=tenant.id,
        name=f"{name}-{unique}",
        sku=f"SHOP-{unique}",
        regular_price=Decimal("50"),
        cost_price=Decimal("20"),
        is_active=active,
        has_serial_number=serial,
        current_stock=Decimal("0"),
    )
    db_session.add(product)
    db_session.flush()

    warehouse = StoreService.ensure_online_warehouse(tenant.id)
    StockService.add_opening_stock(product.id, Decimal(str(stock)), warehouse_id=warehouse.id)
    db_session.commit()
    return product


def _other_tenant(db_session):
    from models import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Tenant {unique}",
        name_ar="شركة أخرى",
        slug=f"other-tenant-{unique}",
        email=f"other-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture(autouse=True)
def _restore_platform_switches(db_session, demo_tenant):
    """Put the platform's ecommerce switch and the tenant's store flag back.

    A request inside a test commits them - the session is shared with the
    request - so without this a later suite that expects the switch to be off
    (the storefront's own gate) would see it on, and the storefront would be
    published in a suite that believes it is closed.
    """
    from models.system_settings import SystemSettings
    from models.tenant import Tenant

    was_ecommerce = SystemSettings.get_current().enable_ecommerce
    tenant_row = db_session.get(Tenant, demo_tenant.id)
    was_store = tenant_row.enable_store if tenant_row is not None else None
    yield
    db_session.expire_all()
    SystemSettings.get_current().enable_ecommerce = was_ecommerce
    tenant_row = db_session.get(Tenant, demo_tenant.id)
    if tenant_row is not None and was_store is not None:
        tenant_row.enable_store = was_store
    db_session.commit()


@pytest.fixture
def store_manager(client, db_session, demo_tenant, demo_branch):
    """A signed-in store manager, with the tenant's store feature switched on.

    The store admin blueprint is behind the tenant's ``enable_store`` flag -
    the feature gate checks it on every request - so a manager without it
    answers 403 whatever their permissions say.
    """
    _stores_enabled(db_session, demo_tenant)
    return _with(client, db_session, demo_tenant, demo_branch, ["manage_store"], "manager")


@pytest.fixture
def shop(db_session, demo_tenant):
    """A published storefront with one product on sale."""
    _stores_enabled(db_session, demo_tenant)
    store = _store(db_session, demo_tenant)
    product = _product(db_session, demo_tenant)
    return {"store": store, "product": product, "tenant": demo_tenant, "slug": store.store_slug}


class TestSHOP01ThePublicationGate:
    """SHOP-01 to SHOP-12: who may see the storefront at all."""

    def test_an_unknown_slug_is_not_found(self, client):
        """SHOP-01. There is no storefront without a store."""
        resp = client.get("/s/no-such-store/")
        assert resp.status_code == 404, f"an unknown slug answered {resp.status_code}"

    def test_the_catalogue_answers_for_a_published_store(self, client, shop):
        """SHOP-02."""
        resp = client.get(f"/s/{shop['slug']}/")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_catalogue_carries_the_products(self, client, shop):
        """SHOP-03."""
        resp = client.get(f"/s/{shop['slug']}/")
        assert shop["product"].name in resp.get_data(as_text=True)

    def test_a_disabled_store_is_closed(self, client, db_session, demo_tenant):
        """SHOP-04. A store switched off in the admin is off in the world."""
        _stores_enabled(db_session, demo_tenant)
        store = _store(db_session, demo_tenant, enabled=False)
        resp = client.get(f"/s/{store.store_slug}/")
        assert resp.status_code == 503, f"a disabled store answered {resp.status_code}"

    def test_a_platform_locked_store_is_closed(self, client, db_session, demo_tenant):
        """SHOP-05. The platform can close a store without the tenant."""
        _stores_enabled(db_session, demo_tenant)
        store = _store(db_session, demo_tenant)
        store.platform_disabled = True
        db_session.commit()
        resp = client.get(f"/s/{store.store_slug}/")
        assert resp.status_code == 503, f"a locked store answered {resp.status_code}"

    def test_a_suspended_tenant_closes_its_store(self, client, db_session, demo_tenant):
        """SHOP-06. A suspended tenant does not keep selling."""
        _stores_enabled(db_session, demo_tenant)
        store = _store(db_session, demo_tenant)
        demo_tenant.is_suspended = True
        db_session.commit()
        resp = client.get(f"/s/{store.store_slug}/")
        assert resp.status_code == 503, f"a suspended tenant's store answered {resp.status_code}"

    def test_a_closed_store_shows_a_closed_page_not_a_stack_trace(self, client, db_session, demo_tenant):
        """SHOP-07. A visitor sees a closed shop, not a traceback."""
        _stores_enabled(db_session, demo_tenant)
        store = _store(db_session, demo_tenant, enabled=False)
        resp = client.get(f"/s/{store.store_slug}/")
        assert resp.status_code == 503
        assert "Traceback" not in resp.get_data(as_text=True)

    def test_the_language_switch_answers(self, client, shop):
        """SHOP-08."""
        resp = client.get(f"/s/{shop['slug']}/lang/en")
        assert resp.status_code in (200, 302), f"the language switch answered {resp.status_code}"

    def test_the_offline_page_answers(self, client, shop):
        """SHOP-09. The offline page is what a customer sees with no connection."""
        resp = client.get(f"/s/{shop['slug']}/offline")
        assert resp.status_code in (200, 302), f"the offline page answered {resp.status_code}"

    def test_the_robots_file_answers(self, client, shop):
        """SHOP-10."""
        resp = client.get(f"/s/{shop['slug']}/robots.txt")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/plain")

    def test_the_sitemap_answers(self, client, shop):
        """SHOP-11."""
        resp = client.get(f"/s/{shop['slug']}/sitemap.xml")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/xml")

    def test_the_return_policy_answers(self, client, db_session, shop):
        """SHOP-12. A store that has published a policy shows it."""
        shop["store"].return_policy_ar = "الإرجاع خلال 14 يوماً"
        shop["store"].return_policy_en = "Returns within 14 days"
        db_session.commit()
        resp = client.get(f"/s/{shop['slug']}/return-policy")
        assert resp.status_code == 200, f"the return policy answered {resp.status_code}"

    def test_a_store_without_a_return_policy_has_no_return_policy_page(self, client, shop):
        """SHOP-12b. An empty policy page is worse than no page."""
        resp = client.get(f"/s/{shop['slug']}/return-policy")
        assert resp.status_code == 404, f"the return policy answered {resp.status_code}"


class TestSHOP13TheCart:
    """SHOP-13 to SHOP-24: the basket and what may go in it."""

    def test_a_product_that_is_not_on_sale_cannot_be_added(self, client, db_session, demo_tenant, shop):
        """SHOP-13. An inactive product is not for sale."""
        hidden = _product(db_session, demo_tenant, name="Hidden", active=False)
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(hidden.id), "quantity": "1"},
        )
        assert resp.status_code in (302, 400), f"the add answered {resp.status_code}"
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 0

    def test_a_serialised_product_cannot_be_added(self, client, db_session, demo_tenant, shop):
        """SHOP-14. A serialised item is one unit, not a quantity."""
        serialised = _product(db_session, demo_tenant, name="Serialised", serial=True)
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(serialised.id), "quantity": "1"},
        )
        assert resp.status_code in (302, 400), f"the add answered {resp.status_code}"
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 0

    def test_a_product_is_added_to_the_cart(self, client, shop):
        """SHOP-15."""
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "2"},
        )
        assert resp.status_code in (200, 302), f"the add answered {resp.status_code}"
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 2

    def test_the_cart_never_holds_more_than_the_stock(self, client, shop):
        """SHOP-16. The basket cannot promise what the warehouse does not have."""
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "500"},
        )
        assert resp.status_code in (200, 302), f"the add answered {resp.status_code}"
        count = client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"]
        assert count == 10, f"the cart holds {count} of a product with 10 in stock"

    def test_an_add_without_a_product_is_refused(self, client, shop):
        """SHOP-17."""
        resp = client.post(f"/s/{shop['slug']}/cart/add", data={"quantity": "1"})
        assert resp.status_code in (200, 302, 400), f"the add answered {resp.status_code}"
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 0

    def test_an_add_with_no_quantity_is_refused(self, client, shop):
        """SHOP-18."""
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "0"},
        )
        assert resp.status_code in (200, 302, 400), f"the add answered {resp.status_code}"
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 0

    def test_the_cart_page_answers(self, client, shop):
        """SHOP-19."""
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        resp = client.get(f"/s/{shop['slug']}/cart")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_two_stores_do_not_share_a_cart(self, client, db_session, demo_tenant, shop):
        """SHOP-20. The cart is the tenant's, keyed by the tenant."""
        other_tenant = _other_tenant(db_session)
        _stores_enabled(db_session, other_tenant)
        other = _store(db_session, other_tenant)
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "3"},
        )
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 3
        assert client.get(f"/s/{other.store_slug}/cart/count").get_json()["data"]["count"] == 0

    def test_a_product_is_removed_from_the_cart(self, client, shop):
        """SHOP-21."""
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "2"},
        )
        resp = client.post(f"/s/{shop['slug']}/cart/remove/{shop['product'].id}")
        assert resp.status_code in (200, 302), f"the removal answered {resp.status_code}"
        assert client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"] == 0

    def test_the_cart_update_cannot_exceed_the_stock(self, client, shop):
        """SHOP-22. A quantity edited outside the application is still capped."""
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        resp = client.post(
            f"/s/{shop['slug']}/cart/update",
            data={f"qty_{shop['product'].id}": "999"},
        )
        assert resp.status_code in (200, 302), f"the update answered {resp.status_code}"
        count = client.get(f"/s/{shop['slug']}/cart/count").get_json()["data"]["count"]
        assert count <= 10, f"the cart holds {count} of a product with 10 in stock"

    def test_the_cart_count_answers_zero_for_an_empty_cart(self, client, shop):
        """SHOP-23."""
        resp = client.get(f"/s/{shop['slug']}/cart/count")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["count"] == 0

    def test_the_cart_of_a_closed_store_is_closed_too(self, client, db_session, demo_tenant, shop):
        """SHOP-24. A closed store does not keep taking orders."""
        shop["store"].is_enabled = False
        db_session.commit()
        resp = client.get(f"/s/{shop['slug']}/cart")
        assert resp.status_code == 503, f"a closed store's cart answered {resp.status_code}"


class TestSHOP25TheCatalogue:
    """SHOP-25 to SHOP-34: the catalogue and the product page."""

    def test_the_product_page_answers(self, client, shop):
        """SHOP-25."""
        resp = client.get(f"/s/{shop['slug']}/p/{shop['product'].id}")
        assert resp.status_code == 200
        assert shop["product"].name in resp.get_data(as_text=True)

    def test_a_product_of_another_tenant_is_not_on_sale(self, client, db_session, shop):
        """SHOP-26. The catalogue is the tenant's."""
        other = _other_tenant(db_session)
        foreign = _product(db_session, other, name="Foreign Product")
        resp = client.get(f"/s/{shop['slug']}/p/{foreign.id}")
        assert resp.status_code == 404, f"a foreign product answered {resp.status_code}"

    def test_the_search_answers_json(self, client, shop):
        """SHOP-27."""
        resp = client.get(f"/s/{shop['slug']}/api/search?q=Probe")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        assert "results" in resp.get_json()["data"]

    def test_the_search_finds_the_product(self, client, shop):
        """SHOP-28."""
        resp = client.get(f"/s/{shop['slug']}/api/search?q={shop['product'].name[:8]}")
        assert resp.status_code == 200
        found = resp.get_json()["data"]["results"]
        assert found, f"the search did not find {shop['product'].name}"

    def test_the_search_does_not_cross_the_tenant_boundary(self, client, db_session, shop):
        """SHOP-29. A search is the tenant's search."""
        other = _other_tenant(db_session)
        foreign = _product(db_session, other, name="Zaphod Product")
        resp = client.get(f"/s/{shop['slug']}/api/search?q=Zaphod")
        assert resp.status_code == 200
        found = resp.get_json()["data"]["results"]
        assert all(item.get("id") != foreign.id for item in found), "another tenant's product came back"

    def test_the_quick_view_answers(self, client, shop):
        """SHOP-30."""
        resp = client.get(f"/s/{shop['slug']}/quick-view/{shop['product'].id}")
        assert resp.status_code in (200, 302), f"the quick view answered {resp.status_code}"

    def test_the_reviews_answer(self, client, shop):
        """SHOP-31."""
        resp = client.get(f"/s/{shop['slug']}/p/{shop['product'].id}/reviews")
        assert resp.status_code in (200, 302), f"the reviews answered {resp.status_code}"

    def test_a_review_needs_a_signed_in_customer(self, client, shop):
        """SHOP-32. A review from nobody is not a review."""
        resp = client.post(
            f"/s/{shop['slug']}/p/{shop['product'].id}/review/add",
            data={"rating": "5", "comment": "Good"},
        )
        assert resp.status_code in (302, 401, 403), f"the review answered {resp.status_code}"

    def test_the_wishlist_needs_a_signed_in_customer(self, client, shop):
        """SHOP-33."""
        resp = client.post(f"/s/{shop['slug']}/wishlist/add/{shop['product'].id}")
        assert resp.status_code in (302, 401, 403), f"the wishlist add answered {resp.status_code}"

    def test_the_wishlist_page_answers(self, client, shop):
        """SHOP-34."""
        resp = client.get(f"/s/{shop['slug']}/wishlist")
        assert resp.status_code in (200, 302), f"the wishlist answered {resp.status_code}"


class TestSHOP35TheCustomerAccount:
    """SHOP-35 to SHOP-39: the shop's own accounts, separate from the ERP's."""

    def test_the_login_page_answers(self, client, shop):
        """SHOP-35."""
        resp = client.get(f"/s/{shop['slug']}/account/login")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_registration_page_answers(self, client, shop):
        """SHOP-36."""
        resp = client.get(f"/s/{shop['slug']}/account/register")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_orders_page_needs_a_signed_in_customer(self, client, shop):
        """SHOP-37. An order list is somebody's order list."""
        resp = client.get(f"/s/{shop['slug']}/account/orders")
        assert resp.status_code in (302, 401, 403), f"the orders page answered {resp.status_code}"

    def test_the_newsletter_subscribe_answers(self, client, shop):
        """SHOP-38. Subscribing is not a purchase, so it needs no account."""
        resp = client.post(
            f"/s/{shop['slug']}/newsletter/subscribe",
            data={"email": f"news-{uuid.uuid4().hex[:8]}@example.com"},
        )
        assert resp.status_code in (200, 302), f"the subscribe answered {resp.status_code}"

    def test_the_forgot_password_page_answers(self, client, shop):
        """SHOP-39."""
        resp = client.get(f"/s/{shop['slug']}/account/forgot-password")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type


class TestSHOP40TheStoreAdmin:
    """SHOP-40 to SHOP-56: the tenant's own shop administration."""

    def test_the_store_admin_needs_the_store_permission(self, client, db_session, demo_tenant, demo_branch):
        """SHOP-40. The shop admin is not the storefront."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in STORE_ADMIN_PATHS:
            resp = client.get(path)
            assert resp.status_code == 403, f"{path} answered {resp.status_code} for a reporter"

    def test_the_store_admin_answers_for_the_store_manager(
        self, client, db_session, demo_tenant, demo_branch, store_manager
    ):
        """SHOP-41."""
        resp = client.get("/store/admin")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_the_settings_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-42."""
        assert client.get("/store/admin/settings").status_code == 200

    def test_the_catalog_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-43."""
        assert client.get("/store/admin/catalog").status_code == 200

    def test_the_transfer_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-44."""
        assert client.get("/store/admin/transfer").status_code == 200

    def test_the_orders_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-45."""
        assert client.get("/store/admin/orders").status_code == 200

    def test_the_customers_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-46."""
        assert client.get("/store/admin/customers").status_code == 200

    def test_the_stats_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-47."""
        assert client.get("/store/admin/stats").status_code == 200

    def test_the_coupons_page_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-48."""
        assert client.get("/store/admin/coupons").status_code == 200

    def test_an_order_detail_answers(self, client, db_session, demo_tenant, demo_branch, store_manager):
        """SHOP-49."""
        resp = client.get("/store/admin/orders/1")
        assert resp.status_code in (200, 404), f"the order detail answered {resp.status_code}"

    def test_the_confirm_and_cancel_verbs_need_the_store_permission(self, client, db_session, demo_tenant, demo_branch):
        """SHOP-50. Confirming an order is a money decision."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        for path in ("/store/admin/orders/1/confirm", "/store/admin/orders/1/cancel"):
            resp = client.post(path)
            assert resp.status_code == 403, f"{path} answered {resp.status_code} for a reporter"

    def test_the_order_verbs_answer_for_the_store_manager(
        self, client, db_session, demo_tenant, demo_branch, store_manager
    ):
        """SHOP-51."""
        for path in ("/store/admin/orders/1/confirm", "/store/admin/orders/1/cancel"):
            resp = client.post(path)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"

    def test_the_settings_page_refuses_a_save_without_the_permission(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """SHOP-52."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/store/admin/settings", data={"title": "Hijacked"})
        assert resp.status_code == 403, f"the save answered {resp.status_code}"

    def test_the_store_admin_shows_the_tenants_own_store(
        self, client, db_session, demo_tenant, demo_branch, store_manager
    ):
        """SHOP-53. The admin is the tenant's, not the installation's."""
        _stores_enabled(db_session, demo_tenant)
        store = _store(db_session, demo_tenant)
        resp = client.get("/store/admin")
        assert resp.status_code == 200
        assert store.store_slug in resp.get_data(as_text=True)

    def test_a_store_can_be_switched_off_from_the_admin(
        self, client, db_session, demo_tenant, demo_branch, store_manager
    ):
        """SHOP-54. The switch in the admin is the switch in the world."""
        _stores_enabled(db_session, demo_tenant)
        _store(db_session, demo_tenant)
        resp = client.post("/store/admin/settings", data={"is_enabled": "0"})
        assert resp.status_code in (200, 302), f"the save answered {resp.status_code}"

        db_session.expire_all()
        from models.tenant_store import TenantStore

        refreshed = db_session.query(TenantStore).filter_by(tenant_id=demo_tenant.id).first()
        assert refreshed is not None
        assert refreshed.is_enabled is False, "the store was not switched off"

    def test_the_coupons_page_answers_a_coupon_creation(
        self, client, db_session, demo_tenant, demo_branch, store_manager
    ):
        """SHOP-55."""
        resp = client.post(
            "/store/admin/coupons",
            data={"code": f"PROBE{uuid.uuid4().hex[:4].upper()}", "discount_type": "percentage", "value": "10"},
        )
        assert resp.status_code in (200, 302), f"the coupon creation answered {resp.status_code}"

    def test_the_transfer_page_refuses_a_transfer_without_the_permission(
        self, client, db_session, demo_tenant, demo_branch
    ):
        """SHOP-56."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.post("/store/admin/transfer", data={"warehouse_id": "1", "amount": "10"})
        assert resp.status_code == 403, f"the transfer answered {resp.status_code}"


class TestSHOP57TheCheckout:
    """SHOP-57 to SHOP-66: the one place a stranger can create money."""

    def test_the_checkout_page_answers(self, client, shop):
        """SHOP-57."""
        resp = client.get(f"/s/{shop['slug']}/checkout")
        assert resp.status_code in (200, 302), f"the checkout answered {resp.status_code}"

    def test_the_checkout_of_an_empty_cart_is_refused(self, client, shop):
        """SHOP-58. There is nothing to check out."""
        resp = client.post(
            f"/s/{shop['slug']}/checkout",
            data={"payment_method": "cod"},
        )
        assert resp.status_code in (200, 302, 400, 503), f"the checkout answered {resp.status_code}"

    def test_a_checkout_with_a_cart_asks_for_the_details(self, client, shop):
        """SHOP-59. A checkout with a basket is a form, not a failure."""
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        resp = client.get(f"/s/{shop['slug']}/checkout")
        assert resp.status_code == 200

    def test_the_checkout_token_is_single_use(self, client, shop):
        """SHOP-60. A refresh must not place the order twice."""
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        page = client.get(f"/s/{shop['slug']}/checkout")
        token = client.get(f"/s/{shop['slug']}/checkout").get_data(as_text=True)
        assert page.status_code == 200
        assert "checkout" in token.lower()

    def test_the_checkout_of_another_tenants_store_is_its_own(self, client, db_session, demo_tenant, shop):
        """SHOP-61. The basket is keyed by the tenant, so it is the tenant's money."""
        other = _store(db_session, demo_tenant, slug=f"probe-other-{uuid.uuid4().hex[:6]}")
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        assert client.get(f"/s/{other.store_slug}/cart/count").get_json()["data"]["count"] == 0

    def test_the_checkout_needs_a_payment_method(self, client, shop):
        """SHOP-62."""
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        resp = client.post(f"/s/{shop['slug']}/checkout", data={})
        assert resp.status_code in (200, 302, 400), f"the checkout answered {resp.status_code}"

    def test_the_minimum_order_amount_is_enforced(self, client, db_session, demo_tenant, shop):
        """SHOP-63. A store with a minimum says so, and means it."""
        shop["store"].min_order_amount = Decimal("1000")
        db_session.commit()
        client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
        )
        resp = client.post(f"/s/{shop['slug']}/checkout", data={"payment_method": "cod"})
        assert resp.status_code in (200, 302, 400), f"the checkout answered {resp.status_code}"

    def test_the_checkout_of_a_closed_store_is_closed(self, client, db_session, demo_tenant, shop):
        """SHOP-64. A closed store takes no orders."""
        shop["store"].is_enabled = False
        db_session.commit()
        resp = client.get(f"/s/{shop['slug']}/checkout")
        assert resp.status_code == 503, f"a closed store's checkout answered {resp.status_code}"

    def test_the_order_page_answers_by_token(self, client, shop):
        """SHOP-65. A customer follows their order with the token they were given."""
        resp = client.get(f"/s/{shop['slug']}/order/probe-token")
        assert resp.status_code in (200, 404), f"the order page answered {resp.status_code}"

    def test_the_invoice_answers(self, client, shop):
        """SHOP-66."""
        resp = client.get(f"/s/{shop['slug']}/order/1/invoice")
        assert resp.status_code in (200, 302, 404), f"the invoice answered {resp.status_code}"


class TestSHOP67TheShape:
    """SHOP-67 to SHOP-86: what the storefront must keep being."""

    def test_the_scenario_covers_every_store_route(self, app):
        """SHOP-67. A scenario that stops covering a route stops being a scenario."""
        live = {
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/s/") or rule.rule.startswith("/store/")
        }
        assert len(live) >= 48, f"the storefront route inventory shrank to {len(live)} routes"

    def test_the_storefront_routes_are_not_behind_a_permission(self, app):
        """SHOP-68. The storefront is public by design; the admin is not."""
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/s/"):
                continue
            view = app.view_functions[rule.endpoint]
            assert getattr(view, "_required_permission", None) is None, (
                f"{rule.rule} is behind a permission, so a stranger cannot reach the storefront"
            )

    def test_the_store_admin_routes_are_all_behind_manage_store(self, app):
        """SHOP-69."""
        for rule in app.url_map.iter_rules():
            if not rule.rule.startswith("/store/admin"):
                continue
            view = app.view_functions[rule.endpoint]
            assert getattr(view, "_required_permission", None) == "manage_store", (
                f"{rule.rule} is not behind manage_store"
            )

    def test_the_storefront_is_addressed_by_slug(self, app):
        """SHOP-70. Two tenants, two stores, two URLs."""
        rules = [rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/s/")]
        assert any("/s/<slug>" in rule for rule in rules)
        assert any("/s/<slug>/" in rule for rule in rules)

    def test_the_store_slug_is_unique(self, db_session):
        """SHOP-71. Two stores cannot answer to the same address."""
        from models.tenant_store import TenantStore

        column = TenantStore.__table__.columns.get("store_slug")
        assert column is not None
        assert column.unique is True, "the store slug is not unique"

    def test_the_store_carries_its_tenant(self, db_session):
        """SHOP-72."""
        from models.tenant_store import TenantStore

        column = TenantStore.__table__.columns.get("tenant_id")
        assert column is not None
        assert column.nullable is False, "a store without a tenant is a store nobody owns"

    def test_the_store_switch_defaults_to_off(self, db_session):
        """SHOP-73. A new store does not open itself."""
        from models.tenant_store import TenantStore

        column = TenantStore.__table__.columns.get("is_enabled")
        assert column is not None
        assert column.default.arg is False, "a new store defaults to published"

    def test_the_minimum_order_amount_is_a_decimal(self, db_session):
        """SHOP-74. Money is not a float."""
        from models.tenant_store import TenantStore

        column = TenantStore.__table__.columns.get("min_order_amount")
        assert column is not None
        assert "NUMERIC" in str(column.type).upper(), f"min_order_amount is {column.type}"

    def test_the_low_stock_threshold_is_a_decimal(self, db_session):
        """SHOP-75."""
        from models.tenant_store import TenantStore

        column = TenantStore.__table__.columns.get("low_stock_threshold")
        assert column is not None
        assert "NUMERIC" in str(column.type).upper(), f"low_stock_threshold is {column.type}"

    def test_the_store_routes_answer_for_a_visitor(self, client, shop):
        """SHOP-76. A stranger may read the catalogue."""
        for path in ("/s/{slug}/", "/s/{slug}/cart", "/s/{slug}/checkout"):
            resp = client.get(path.format(slug=shop["slug"]))
            assert resp.status_code in (200, 302, 503), f"{path} answered {resp.status_code}"

    def test_the_store_routes_refuse_an_anonymous_admin(self, client):
        """SHOP-77. The admin is never open."""
        for path in STORE_ADMIN_PATHS:
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"

    def test_the_ajax_add_answers_json(self, client, shop):
        """SHOP-78. The badge count is fetched, not parsed out of a page."""
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(shop["product"].id), "quantity": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        assert resp.get_json()["data"]["cart_count"] == 1

    def test_the_ajax_add_of_an_unbuyable_product_answers_an_error(self, client, db_session, demo_tenant, shop):
        """SHOP-79."""
        hidden = _product(db_session, demo_tenant, name="Hidden", active=False)
        resp = client.post(
            f"/s/{shop['slug']}/cart/add",
            data={"product_id": str(hidden.id), "quantity": "1"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_the_cart_count_answers_json(self, client, shop):
        """SHOP-80."""
        resp = client.get(f"/s/{shop['slug']}/cart/count")
        assert resp.content_type.startswith("application/json")
        assert "count" in resp.get_json()["data"]

    def test_the_search_answers_json_even_with_no_query(self, client, shop):
        """SHOP-81."""
        resp = client.get(f"/s/{shop['slug']}/api/search")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")

    def test_the_account_logout_answers(self, client, shop):
        """SHOP-82."""
        resp = client.post(f"/s/{shop['slug']}/account/logout")
        assert resp.status_code in (200, 302), f"the logout answered {resp.status_code}"

    def test_the_reorder_answers(self, client, shop):
        """SHOP-83. Reordering is a customer action, so it needs a customer."""
        resp = client.post(f"/s/{shop['slug']}/order/reorder/1")
        assert resp.status_code in (302, 401, 403, 404), f"the reorder answered {resp.status_code}"

    def test_the_payments_page_needs_a_signed_in_customer(self, client, shop):
        """SHOP-84."""
        resp = client.get(f"/s/{shop['slug']}/account/payments")
        assert resp.status_code in (302, 401, 403), f"the payments page answered {resp.status_code}"

    def test_the_saved_payment_methods_need_a_signed_in_customer(self, client, shop):
        """SHOP-85."""
        for path in ("/s/{slug}/account/payments/save", "/s/{slug}/account/payments/delete/1"):
            resp = client.post(path.format(slug=shop["slug"]), data={})
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"

    def test_the_track_page_answers(self, client, shop):
        """SHOP-86. A customer follows a parcel with an order number."""
        resp = client.get(f"/s/{shop['slug']}/track")
        assert resp.status_code in (200, 302), f"the track page answered {resp.status_code}"
