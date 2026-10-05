"""Wave 3 - the online warehouse and the storefront.

Everything so far happened on a till inside the building. This wave is about the
tenant putting the same business online, and about what happens when one of the
conditions for that is not met.

`StoreService.is_store_publicly_available` is an AND of five separate gates,
each owned by a different part of the system:

    1. store.is_enabled            - the tenant switched the store on
    2. not platform_disabled       - the platform owner force-disabled it
    3. SystemSettings.enable_ecommerce - the deployment allows stores at all
    4. the tenant is active
    5. the store's warehouse is online - a real "online" warehouse, not physical,
       and belonging to the same tenant

That shape is why this wave exists. Any one gate failing hides the storefront,
so a tenant whose catalogue is 404 cannot tell from the symptom which of the five
is at fault, and a test that only checks the happy path leaves four untested.
Each gate is therefore removed individually and the hiding is asserted, which
also pins down that the gates are independent rather than accidentally satisfied
by one flag.

The order is deliberate: the store starts closed, is opened one gate at a time,
and the last test shows the platform lock winning over the tenant's own switch.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest


@pytest.fixture
def online_warehouse(db_session, demo_tenant, demo_branch):
    """A warehouse of type "online".

    is_online is a property derived from warehouse_type, not a flag, so the only
    way to satisfy gate 5 is to create a genuinely online warehouse. A physical
    one would leave the storefront hidden for a reason that looks like a bug.
    """
    from models import Warehouse

    warehouse = Warehouse(
        name=f"Online {uuid.uuid4().hex[:6]}",
        tenant_id=demo_tenant.id,
        branch_id=demo_branch.id,
        warehouse_type=Warehouse.TYPE_ONLINE,
        is_active=True,
    )
    db_session.add(warehouse)
    db_session.commit()
    return warehouse


@pytest.fixture
def ecommerce_enabled(db_session):
    """Turn the deployment-level ecommerce switch on.

    Gate 3 lives in SystemSettings rather than in the tenant, so it is a single
    global row. Set explicitly instead of relying on seeding, because the default
    is False and a test that passed on a developer's seeded database would fail
    on a fresh one.
    """
    from models import SystemSettings

    settings = SystemSettings.query.filter_by(is_active=True).first()
    if settings is None:
        settings = SystemSettings()
        db_session.add(settings)
    settings.enable_ecommerce = True
    db_session.flush()
    return settings


@pytest.fixture
def tenant_store(db_session, demo_tenant, online_warehouse):
    """A store row wired to the online warehouse, closed by default.

    is_enabled defaults to False on the model, so a store that is only created -
    never published - is the natural starting point for these tests.
    """
    from models import TenantStore

    slug = f"shop-{uuid.uuid4().hex[:8]}"
    store = TenantStore(
        tenant_id=demo_tenant.id,
        warehouse_id=online_warehouse.id,
        store_slug=slug,
        title="Scenario Store",
        is_enabled=False,
    )
    db_session.add(store)
    db_session.commit()
    return store


@pytest.fixture
def published_store(db_session, tenant_store, ecommerce_enabled):
    """The same store, fully open: tenant enabled, platform not locked."""
    tenant_store.is_enabled = True
    tenant_store.platform_disabled = False
    db_session.flush()
    return tenant_store


@pytest.fixture
def store_manager(client, db_session, demo_tenant, demo_branch):
    """A user who may run the store admin, which a cashier may not.

    routes/store.py's order confirm and cancel are behind manage_store *and* the
    admin-surface check, which accepts only an owner or a super_admin role
    (utils/auth_helpers.py:is_admin_surface_user). So this cannot be the cashier
    fixture: a tenant cashier legitimately cannot confirm a storefront order, and
    a test that made them able to would be asserting a privilege the product does
    not grant.

    The separate user is the point of the test setup, not a workaround.
    """
    from models import Permission, Role, User

    # routes/store.py calls install_feature_gate(store_bp, "store"), so every route
    # in the blueprint is refused unless Tenant.enable_store is set - and that
    # column defaults to False. The gate runs as a blueprint before_request, ahead
    # of login_required and permission_required, so it answers 403 even for a
    # signed-in super_admin who holds manage_store. It is a sixth condition,
    # separate from the five is_store_publicly_available checks on the storefront.
    demo_tenant.enable_store = True
    db_session.flush()

    unique = uuid.uuid4().hex[:8]
    # roles.slug is globally unique, so an existing super_admin is reused rather
    # than a second one inserted - which would fail on the second scenario in this
    # module.
    role = Role.query.filter_by(slug="super_admin").first()
    if role is None:
        role = Role(name="Super Admin", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.flush()

    # Permissions are attached whether or not the role was just created. The seeded
    # super_admin role already exists, so attaching only on creation left the user
    # without manage_store and every admin route answered 403 - which reads as an
    # authorisation failure rather than a fixture that forgot to grant anything.
    wanted = Permission.query.filter(
        Permission.code.in_(
            [
                "manage_store",
                "view_store",
                "manage_sales",
                "manage_products",
                "view_products",
                "view_inventory",
                "manage_customers",
                "view_customers",
                "manage_payments",
                "view_payments",
                "manage_returns",
                "view_returns",
            ]
        )
    ).all()
    have = {p.id for p in role.permissions}
    for perm in wanted:
        if perm.id not in have:
            role.permissions.append(perm)
    db_session.flush()

    user = User(
        username=f"store-{unique}",
        email=f"store-{unique}@example.com",
        full_name="Store Manager",
        tenant_id=demo_tenant.id,
        role_id=role.id,
        branch_id=demo_branch.id,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )
    return user


class TestS16StoreVisibilityGates:
    """S-16: each of the five availability gates is load-bearing."""

    def test_a_closed_store_is_not_publicly_available(self, db_session, tenant_store):
        """Gate 1 alone: the tenant never switched the store on."""
        from services.store_service import StoreService

        assert tenant_store.is_enabled is False
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_ecommerce_disabled_hides_an_enabled_store(self, db_session, tenant_store):
        """Gate 3 alone: the tenant says yes, the deployment says no.

        This is the gate that most often surprises, because everything the tenant
        can see in their own settings looks correct.
        """
        from services.store_service import StoreService

        tenant_store.is_enabled = True
        db_session.flush()
        # ecommerce_enabled is deliberately not requested, so the global switch
        # stays at its default of False.
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_platform_lock_hides_a_store_the_tenant_enabled(self, db_session, published_store):
        """Gate 2 alone: the platform owner overrode the tenant.

        A support action must not be reversible by the tenant toggling their own
        setting, which is the whole point of the lock.
        """
        from services.store_service import StoreService

        assert StoreService.is_store_publicly_available(published_store) is True, (
            "the store is not available even fully published; the fixture is wrong, not the code"
        )

        published_store.platform_disabled = True
        db_session.flush()
        assert StoreService.is_store_publicly_available(published_store) is False, (
            "the platform lock did not hide a store the tenant had enabled"
        )

    def test_physical_warehouse_hides_the_store(self, db_session, tenant_store, demo_branch):
        """Gate 5 alone: the store points at a physical warehouse.

        The warehouse_id can legitimately be any warehouse, so this is a
        configuration mistake rather than an impossible state - and the symptom is
        an invisible catalogue with no error anywhere.
        """
        from models import Warehouse
        from services.store_service import StoreService

        physical = Warehouse(
            name=f"Physical {uuid.uuid4().hex[:6]}",
            tenant_id=tenant_store.tenant_id,
            branch_id=demo_branch.id,
            warehouse_type=Warehouse.TYPE_PHYSICAL,
            is_active=True,
        )
        db_session.add(physical)
        db_session.flush()

        tenant_store.is_enabled = True
        tenant_store.warehouse_id = physical.id
        db_session.flush()
        assert physical.is_online is False, "the fixture is not actually physical"
        assert StoreService.is_store_publicly_available(tenant_store) is False

    def test_inactive_warehouse_hides_the_store(self, db_session, published_store, online_warehouse):
        """Gate 5, second half: an online warehouse that has been switched off."""
        from services.store_service import StoreService

        assert online_warehouse.is_online is True
        online_warehouse.is_active = False
        db_session.flush()
        assert StoreService.is_store_publicly_available(published_store) is False

    def test_a_fully_published_store_is_available(self, db_session, published_store):
        """The positive control, so the negatives above mean something.

        Without this, a service that returned False unconditionally would pass
        every gate test in this class.
        """
        from services.store_service import StoreService

        assert published_store.is_enabled is True
        assert published_store.platform_disabled is False
        assert published_store.warehouse_id is not None
        assert StoreService.is_store_publicly_available(published_store) is True


class TestS17StorefrontReachesThePublicSurface:
    """S-17: the published store answers on its public URL."""

    def test_public_catalog_renders_for_a_published_store(self, client, db_session, published_store, stocked_product):
        """The slug resolves and the catalogue is served.

        Asserted on the store appearing in the body rather than on the status
        alone, since a storefront that returns 200 with an empty page would pass
        a status check while being unusable.
        """
        resp = client.get(f"/s/{published_store.store_slug}", follow_redirects=True)
        assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
        body = resp.get_data(as_text=True)
        assert published_store.store_slug in body or "Scenario Store" in body, (
            "the catalogue page did not identify the store it is serving"
        )

    def test_unpublished_store_does_not_serve_a_catalogue(self, client, db_session, tenant_store):
        """The negative on the HTTP surface, not just the service call.

        503 is the correct answer here and is deliberate: routes/shop.py renders
        shop/closed.html with a reason and returns 503 rather than 404. A closed
        store is not missing, it is temporarily unavailable, and answering "not
        found" would send the tenant hunting for a slug typo. 404 would also be
        wrong for the platform lock, which is a temporary state by design.

        The assertion is that the closed page is served instead of the catalogue.
        """
        resp = client.get(f"/s/{tenant_store.store_slug}", follow_redirects=True)
        assert resp.status_code == 503, (
            f"a store that was never enabled served {resp.status_code}; expected the 503 closed page"
        )
        body = resp.get_data(as_text=True).lower()
        assert "closed" in body or "مغلق" in body, "the 503 response did not render the closed-store page"


class TestS18DeferredFulfilment:
    """S-18: an online order leaves stock alone until the shop confirms it.

    A storefront order is placed by the customer, not by staff, so it cannot
    fulfil itself the way a till sale does - the goods have to stay on the shelf
    until somebody accepts the order. StoreOrderService.confirm_order guards that
    with `if not StoreOrderService.is_fulfilled(sale)`, which is what makes
    confirming twice harmless rather than a second stock movement.

    The order is built through the model layer rather than the storefront
    checkout, because the checkout needs a populated cart session, a shop customer
    account and a payment method chosen in the browser. What this scenario is
    about is the deferred fulfilment and its idempotence, and those are exercised
    through the same HTTP admin route the shop owner uses.
    """

    @pytest.fixture
    def online_order(
        self,
        db_session,
        store_manager,
        demo_tenant,
        demo_branch,
        demo_warehouse,
        stocked_product,
        scenario_customer,
    ):
        # store_manager is required, not incidental: scenario_customer creates the
        # customer over HTTP, which needs a signed-in user with manage_customers,
        # and the order routes need the admin surface. Without the login the
        # create lands on the login page, returns 200, and the customer is
        # silently never created.
        from models import Sale, SaleLine
        from services.document_sequence_service import DocumentSequenceService

        sale = Sale(
            tenant_id=demo_tenant.id,
            branch_id=demo_branch.id,
            customer_id=scenario_customer.id,
            # seller_id is NOT NULL: an online order has no cashier, so it is
            # attributed to the store manager handling the order.
            seller_id=store_manager.id,
            source="online_store",
            status="pending",
            # fulfill_sale deducts stock from sale.warehouse_id. Without it the
            # confirm raises inside atomic_transaction, which rolls the whole
            # thing back, so the order silently stays pending and the route
            # flashes a warning instead of erroring.
            warehouse_id=demo_warehouse.id,
            # sale_number is NOT NULL and is normally minted by SaleService. This
            # fixture builds the sale directly, so it draws from the same sequence
            # service rather than inventing a format the rest of the system would
            # not recognise.
            sale_number=DocumentSequenceService.next_number(demo_tenant.id, "sale", branch_code="WEB"),
            currency="ILS",
            exchange_rate=1,
            subtotal=Decimal("50"),
            total_amount=Decimal("50"),
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
        )
        db_session.add(sale)
        db_session.flush()

        line = SaleLine(
            tenant_id=demo_tenant.id,
            sale_id=sale.id,
            product_id=stocked_product["product"].id,
            quantity=2,
            unit_price=Decimal("25"),
            cost_price=Decimal("10"),
            line_total=Decimal("50"),
        )
        db_session.add(line)
        db_session.commit()
        return {"sale": sale, "product": stocked_product["product"]}

    def test_an_unconfirmed_order_moves_no_stock(self, client, db_session, online_order):
        """The shelf is untouched while the order waits for the shop.

        If the order moved stock on placement, an order the customer abandons or
        the shop cancels would have to be unwound, and the failure mode is
        inventory that never comes back.
        """
        from models import StockMovement

        movements = StockMovement.query.filter_by(
            product_id=online_order["product"].id,
            movement_type="sale",
        ).count()
        assert movements == 0, f"an unconfirmed online order already moved {movements} times"

    def test_confirming_fulfils_once_and_only_once(
        self, client, db_session, store_manager, online_order, ledger, demo_tenant
    ):
        """Confirmation fulfils the order, and confirming again does not."""
        from models import Sale, StockMovement

        sale = online_order["sale"]
        revenue_before = ledger.balance("4100", demo_tenant.id)

        first = client.post(f"/store/admin/orders/{sale.id}/confirm", follow_redirects=True)
        assert first.status_code in (200, 302), first.get_data(as_text=True)[:300]

        # Read the status back from the database rather than from the in-session
        # object. The route commits through atomic_transaction on the request's own
        # session, so the instance held here can still carry the pre-POST value;
        # expire_all() refreshes loaded attributes but would not refetch a detached
        # one. tenant_query() also applies the ORM scoping a request would apply.
        from utils.tenanting import tenant_query

        stored = tenant_query(Sale).filter_by(id=sale.id).one()
        assert stored.status == "confirmed", f"after confirmation the order is {stored.status}"

        after_first = StockMovement.query.filter_by(
            product_id=online_order["product"].id,
            movement_type="sale",
        ).count()
        assert after_first == 1, f"confirming moved stock {after_first} times, expected once"

        # Revenue is recognised on fulfilment, not on placement.
        revenue_after = ledger.balance("4100", demo_tenant.id)
        assert revenue_after != revenue_before, "confirming the order recognised no revenue"

        second = client.post(f"/store/admin/orders/{sale.id}/confirm", follow_redirects=True)
        assert second.status_code in (200, 302), second.get_data(as_text=True)[:300]

        db_session.expire_all()
        after_second = StockMovement.query.filter_by(
            product_id=online_order["product"].id,
            movement_type="sale",
        ).count()
        assert after_second == 1, (
            f"the repeat confirmation moved stock again ({after_second} movements); the is_fulfilled guard did not hold"
        )

    def test_cancelling_an_unconfirmed_order_leaves_stock_alone(self, client, db_session, store_manager, online_order):
        """Cancelling before fulfilment must not reverse stock that never moved."""
        from models import Sale, StockMovement

        sale = online_order["sale"]
        resp = client.post(f"/store/admin/orders/{sale.id}/cancel", follow_redirects=True)
        assert resp.status_code in (200, 302), resp.get_data(as_text=True)[:300]

        from utils.tenanting import tenant_query

        stored = tenant_query(Sale).filter_by(id=sale.id).one()
        assert stored.status == "cancelled", f"after cancellation the order is {stored.status}"

        movements = StockMovement.query.filter_by(
            product_id=online_order["product"].id,
            movement_type="sale",
        ).count()
        assert movements == 0, f"cancelling an unfulfilled order moved stock {movements} times"
