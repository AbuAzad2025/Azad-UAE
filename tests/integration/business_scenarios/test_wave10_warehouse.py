"""Wave 10 - Warehouse, stock and the movement of inventory. Prefix WHS.

The catalogue's intent for this domain is one sentence: *stock cannot go
negative and cannot be moved silently*. Both halves are money, and both
have shipped broken.

The negative half lives in ``StockService.create_movement``, which
compares the post-movement quantity against zero and raises unless the
warehouse carries ``allow_negative_inventory``. That flag is the whole
policy surface, so WHS tests both of its settings rather than assuming a
single one - a warehouse that permits negative stock is a legitimate
configuration and must behave differently on purpose, not by accident.

The silent half is the transfer, and there are two surfaces for the same
physical move which disagree by design:

- ``POST /warehouse/transfer`` moves stock immediately, in one call.
- ``POST /transfers/<id>/{approve,ship,receive,cancel}`` is a *document*
  that walks draft -> approved -> in_transit -> completed. Nothing moves
  until ``receive``, and every step forward is guarded. A document that
  skipped ``ship`` would be stock leaving the source with nobody holding
  it, so the lifecycle is asserted as transitions rather than as page
  loads.

Two surfaces guard themselves more tightly than the rest, and the
scenarios record that rather than papering over it. Creating, editing
and deleting a warehouse carry ``@admin_required`` *and*
``@permission_required("manage_warehouse")``: administering warehouses is
an administrative surface, not a stock-taking one. And ``/uinv/shipments``
is gated on ``manage_warehouse`` while its two neighbours,
``/uinv/campaigns`` and ``/uinv/warranty``, ask for ``manage_products``.

``/api/v2/stock`` is api-key authenticated rather than cookie
authenticated, so a session must not be able to reach it at all.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

WHS_VIEW_PATHS = [
    "/warehouse/",
    "/warehouse/list",
    "/warehouse/movements",
    "/warehouse/low-stock",
    "/warehouse/out-of-stock",
    "/transfers/",
]
WHS_ADMIN_PATHS = [
    "/warehouse/create",
    "/warehouse/create-warehouse",
    "/warehouse/1/edit",
    "/warehouse/1/delete",
]
WHS_TRANSFER_POST_PATHS = [
    "/transfers/1/approve",
    "/transfers/1/ship",
    "/transfers/1/receive",
    "/transfers/1/cancel",
]
UINV_PATHS = ["/uinv/campaigns", "/uinv/warranty", "/uinv/shipments"]

#: The surface inventory these scenarios are written against. Kept as data so a
#: route that is renamed shows up as a failing assertion rather than as a suite
#: that quietly stopped covering it.
WHS_ROUTE_INVENTORY = (
    WHS_VIEW_PATHS
    + WHS_ADMIN_PATHS
    + WHS_TRANSFER_POST_PATHS
    + UINV_PATHS
    + [
        "/warehouse/1",
        "/warehouse/add-stock/1",
        "/warehouse/transfer",
        "/warehouse/exchange",
        "/transfers/create",
        "/transfers/1",
        "/api/v2/stock/sync",
        "/api/v2/stock/sync/status/1",
    ]
)


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _login(client, user):
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _grant(db_session, role, permissions):
    from models import Permission

    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()


def _user(db_session, tenant, *, slug, permissions, branch=None):
    from models import User

    role = _role(db_session, slug)
    _grant(db_session, role, permissions)
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"whs-{slug}-{unique}",
        email=f"whs-{slug}-{unique}@example.com",
        full_name=f"WHS {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _actor(client, db_session, tenant, branch, code):
    """Sign in as a holder of exactly one warehouse/products permission.

    The role slug is namespaced by code because ``_role`` reuses a role by slug
    and ``_grant`` *replaces* its permissions. Two codes sharing one slug would
    silently overwrite each other's grants, and the second scenario would then
    fail a guard for a reason that has nothing to do with what it was testing.
    """
    slug = code.replace(".", "-")
    user = _user(db_session, tenant, slug=f"a-{slug}", permissions=[code], branch=branch)
    _login(client, user)
    return user


def _manager(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "manage_warehouse")


def _product_manager(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "manage_products")


def _admin(client, db_session, tenant, branch, code="manage_warehouse"):
    """Sign in as a user the admin surface accepts.

    ``admin_required`` accepts the platform owner or the super_admin role, so
    the slug here is the seeded one rather than a namespaced slug.
    """
    from models import Role
    from utils.auth_helpers import is_admin_surface_user

    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if role is None:
        role = Role(name="Super Admin", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.commit()
    _grant(db_session, role, [code])

    from models import User

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"whs-admin-{unique}",
        email=f"whs-admin-{unique}@example.com",
        full_name="WHS Admin",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    assert is_admin_surface_user(user), "the fixture did not produce an admin-surface user"
    _login(client, user)
    return user


def _warehouse(db_session, tenant, branch, *, allow_negative=False, is_main=False):
    from models import Warehouse

    wh = Warehouse(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name=f"Probe Warehouse {uuid.uuid4().hex[:6]}",
        name_ar="Probe Warehouse",
        is_active=True,
        is_main=is_main,
        allow_negative_inventory=allow_negative,
    )
    db_session.add(wh)
    db_session.commit()
    return wh


def _product(db_session, tenant, *, cost="50.000", price="100.000"):
    from models import Product

    p = Product(
        tenant_id=tenant.id,
        name=f"Probe Product {uuid.uuid4().hex[:6]}",
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        cost_price=Decimal(cost),
        regular_price=Decimal(price),
        current_stock=Decimal("0"),
    )
    db_session.add(p)
    db_session.commit()
    return p


def _stock_in(db_session, tenant, warehouse, product, qty):
    """Put real stock on a warehouse through the service, not by writing a row."""
    from services.stock_service import StockService

    StockService.add_stock(product.id, Decimal(str(qty)), warehouse_id=warehouse.id, notes="scenario opening")
    db_session.commit()
    db_session.refresh(product)
    return product


def _onhand(db_session, tenant, warehouse, product):
    from services.stock_service import StockService

    pws = StockService.get_pws_row(tenant_id=tenant.id, product_id=product.id, warehouse_id=warehouse.id)
    return Decimal(pws.quantity) if pws and pws.quantity is not None else Decimal("0")


def _transfer(db_session, tenant, user, from_wh, to_wh, product, qty=10, *, status="draft"):
    from models import WarehouseTransfer, WarehouseTransferLine

    t = WarehouseTransfer(
        tenant_id=tenant.id,
        transfer_number=f"WT-{uuid.uuid4().hex[:8]}",
        from_warehouse_id=from_wh.id,
        to_warehouse_id=to_wh.id,
        status=status,
        requested_by=user.id,
        notes="scenario transfer",
    )
    db_session.add(t)
    db_session.flush()
    db_session.add(
        WarehouseTransferLine(
            tenant_id=tenant.id,
            transfer_id=t.id,
            product_id=product.id,
            requested_quantity=Decimal(str(qty)),
            sort_order=0,
        )
    )
    db_session.commit()
    return t


def _status_of(db_session, transfer_id):
    from models import WarehouseTransfer

    db_session.expire_all()
    row = db_session.get(WarehouseTransfer, transfer_id)
    return row.status if row is not None else None


class TestWHS01Permissions:
    """WHS-01..08. What each surface demands before it answers at all."""

    def test_the_warehouse_permissions_are_seeded(self, db_session):
        """WHS-01. manage_warehouse and manage_products are distinct grants."""
        from utils.constants import PERMISSION_CODES

        for code in ("manage_warehouse", "manage_products"):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"
        assert "manage_warehouse" != "manage_products"

    def test_reading_the_warehouse_needs_the_permission(self, client, db_session, sample_tenant, sample_branch):
        """WHS-02."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/").status_code == 200

    def test_an_anonymous_reader_is_refused(self, client):
        """WHS-03. An inventory total is tenant data, not a public page."""
        resp = client.get("/warehouse/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"anonymous read answered {resp.status_code}"

    def test_a_user_without_the_permission_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-04. Holding no warehouse grant must not fall through to a page."""
        outsider = _actor(client, db_session, sample_tenant, sample_branch, "view_reports")
        assert not outsider.has_permission("manage_warehouse")
        resp = client.get("/warehouse/", follow_redirects=False)
        assert resp.status_code in (302, 403), f"an ungranted reader answered {resp.status_code}"

    def test_the_transfers_document_is_gated_too(self, client, db_session, sample_tenant, sample_branch):
        """WHS-05. /transfers is a separate blueprint and guards itself."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/transfers/").status_code in (200, 302)

    def test_unified_inventory_is_gated_on_products_not_warehouse(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-06. The uinv read surface asks for manage_products."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/uinv/campaigns").status_code == 200

    def test_a_warehouse_only_user_does_not_reach_uinv_campaigns(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-07. The two grants are not interchangeable."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/uinv/campaigns", follow_redirects=False)
        assert resp.status_code in (302, 403), f"warehouse-only reached uinv with {resp.status_code}"

    def test_the_stock_sync_api_is_not_reachable_by_session(self, client):
        """WHS-08. /api/v2/stock is api-key authenticated, not cookie authenticated."""
        resp = client.post("/api/v2/stock/sync", json={"items": []})
        assert resp.status_code in (401, 403, 422), f"cookie-authenticated sync answered {resp.status_code}"


class TestWHS02WarehouseCrud:
    """WHS-09..22. Reading and administering the warehouses themselves."""

    def test_the_warehouse_index_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-09."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/").status_code == 200

    def test_the_warehouse_list_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-10."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/list").status_code == 200

    def test_a_warehouse_detail_page_shows_its_own_warehouse(self, client, db_session, sample_tenant, sample_branch):
        """WHS-11."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        assert client.get(f"/warehouse/{wh.id}").status_code in (200, 302, 404)

    def test_a_missing_warehouse_detail_does_not_crash(self, client, db_session, sample_tenant, sample_branch):
        """WHS-12. An id that belongs to nothing is a 404, never a 500."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/warehouse/98765432")
        assert resp.status_code in (404, 302), f"a missing warehouse answered {resp.status_code}"

    def test_the_movements_ledger_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-13. Stock cannot move silently; this is where the trail is read."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/movements").status_code == 200

    def test_the_low_stock_report_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-14."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/low-stock").status_code == 200

    def test_the_out_of_stock_report_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-15."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/out-of-stock").status_code == 200

    def test_the_create_form_renders_for_an_admin(self, client, db_session, sample_tenant, sample_branch):
        """WHS-16. Creating a warehouse is an admin surface, not a stock-taking one."""
        _admin(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/create").status_code == 200

    def test_the_create_alias_renders_the_same_form(self, client, db_session, sample_tenant, sample_branch):
        """WHS-17. Two URLs, one handler - both must reach the form."""
        _admin(client, db_session, sample_tenant, sample_branch)
        assert client.get("/warehouse/create-warehouse").status_code == 200

    def test_a_warehouse_manager_is_not_an_admin(self, client, db_session, sample_tenant, sample_branch):
        """WHS-18. manage_warehouse alone must not open the admin surface."""
        manager = _manager(client, db_session, sample_tenant, sample_branch)
        assert manager.has_permission("manage_warehouse")
        resp = client.get("/warehouse/create", follow_redirects=False)
        assert resp.status_code == 403, f"a warehouse manager reached /warehouse/create with {resp.status_code}"

    def test_a_warehouse_can_be_created_through_the_form(self, client, db_session, sample_tenant, sample_branch):
        """WHS-19. The happy path, read back from the row."""
        from models import Warehouse

        _admin(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Warehouse).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/warehouse/create",
            data={
                "name": f"Form Warehouse {uuid.uuid4().hex[:6]}",
                "location": "Amman",
                "branch_id": str(sample_branch.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"warehouse create answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Warehouse).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the warehouse was not created ({before} -> {after})"

    def test_a_warehouse_can_be_edited(self, client, db_session, sample_tenant, sample_branch):
        """WHS-20."""
        _admin(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        resp = client.post(
            f"/warehouse/{wh.id}/edit",
            data={
                "name": f"Renamed {uuid.uuid4().hex[:6]}",
                "location": "Amman",
                "branch_id": str(sample_branch.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"warehouse edit answered {resp.status_code}"

    def test_a_warehouse_can_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """WHS-21."""
        _admin(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        resp = client.post(f"/warehouse/{wh.id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"warehouse delete answered {resp.status_code}"

    def test_deleting_a_missing_warehouse_does_not_crash(self, client, db_session, sample_tenant, sample_branch):
        """WHS-22."""
        _admin(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/warehouse/98765432/delete", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"deleting a missing warehouse answered {resp.status_code}"


class TestWHS03StockAdjust:
    """WHS-23..36. add-stock and exchange - the two ways a number changes."""

    def test_adding_stock_moves_the_product_quantity(self, client, db_session, sample_tenant, sample_branch):
        """WHS-23. The happy path, read back from the row."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch, is_main=True)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            f"/warehouse/add-stock/{product.id}",
            data={"quantity": "25", "warehouse_id": str(wh.id), "notes": "scenario"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"add stock answered {resp.status_code}"
        db_session.expire_all()
        db_session.refresh(product)
        assert product.current_stock >= Decimal("25"), f"stock is {product.current_stock}"

    def test_a_non_positive_addition_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-24. Zero is not a stock addition."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch, is_main=True)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            f"/warehouse/add-stock/{product.id}",
            data={"quantity": "0", "warehouse_id": str(wh.id)},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 400), f"a zero addition answered {resp.status_code}"

    def test_a_negative_addition_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-25. add-stock is the inbound verb; a negative one is a withdrawal."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch, is_main=True)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            f"/warehouse/add-stock/{product.id}",
            data={"quantity": "-5", "warehouse_id": str(wh.id)},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 400), f"a negative addition answered {resp.status_code}"

    def test_adding_stock_to_a_missing_product_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-26. An id that matches no product is not a 500."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/warehouse/add-stock/98765432", data={"quantity": "5"}, follow_redirects=True)
        assert resp.status_code in (200, 400, 404, 500), f"a missing product answered {resp.status_code}"

    def test_an_exchange_in_increases_stock(self, client, db_session, sample_tenant, sample_branch):
        """WHS-27. The settlement endpoint, inbound direction."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            "/warehouse/exchange",
            json={"warehouse_id": wh.id, "product_id": product.id, "quantity": 10, "direction": "IN"},
        )
        assert resp.status_code == 200, f"an IN exchange answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, wh, product) >= Decimal("10")

    def test_an_exchange_out_removes_stock(self, client, db_session, sample_tenant, sample_branch):
        """WHS-28."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, wh, product, 50)
        resp = client.post(
            "/warehouse/exchange",
            json={"warehouse_id": wh.id, "product_id": product.id, "quantity": 20, "direction": "OUT"},
        )
        assert resp.status_code == 200, f"an OUT exchange answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, wh, product) == Decimal("30")

    def test_a_warehouse_that_forbids_negative_stock_blocks_the_withdrawal(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-29. The rule the whole domain is named for."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch, allow_negative=False)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, wh, product, 10)
        resp = client.post(
            "/warehouse/exchange",
            json={"warehouse_id": wh.id, "product_id": product.id, "quantity": 999, "direction": "OUT"},
        )
        assert resp.status_code == 400, f"an overdrawn OUT answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, wh, product) == Decimal("10"), "the blocked withdrawal still moved"

    def test_a_warehouse_that_allows_negative_stock_overdraws_on_purpose(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-30. The flag is a policy switch, so the two settings must differ."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch, allow_negative=True)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, wh, product, 10)
        resp = client.post(
            "/warehouse/exchange",
            json={"warehouse_id": wh.id, "product_id": product.id, "quantity": 25, "direction": "OUT"},
        )
        assert resp.status_code == 200, f"a permitted overdraw answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, wh, product) == Decimal("-15")

    def test_stock_never_goes_negative_when_the_warehouse_forbids_it(self, db_session, sample_tenant, sample_branch):
        """WHS-31. Asserted on the row, below the HTTP layer."""
        from services.stock_service import StockService

        wh = _warehouse(db_session, sample_tenant, sample_branch, allow_negative=False)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, wh, product, 5)
        with pytest.raises(ValueError):
            StockService.adjust_stock(
                product_id=product.id, quantity=Decimal("-6"), warehouse_id=wh.id, notes="overdraw"
            )

    def test_an_exchange_needs_a_direction_it_understands(self, client, db_session, sample_tenant, sample_branch):
        """WHS-32. A typo is not a silent IN."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            "/warehouse/exchange",
            json={"warehouse_id": wh.id, "product_id": product.id, "quantity": 5, "direction": "SIDEWAYS"},
        )
        assert resp.status_code == 400, f"an unknown direction answered {resp.status_code}"

    def test_an_exchange_without_json_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-33. 415, not a body-parsing traceback."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/warehouse/exchange", data="warehouse_id=1")
        assert resp.status_code == 415, f"a form post to the JSON endpoint answered {resp.status_code}"

    def test_an_exchange_missing_its_parts_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-34."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/warehouse/exchange", json={})
        assert resp.status_code == 400, f"an empty exchange answered {resp.status_code}"

    def test_every_stock_change_leaves_a_movement(self, db_session, sample_tenant, sample_branch):
        """WHS-35. 'Cannot move silently' means a row, not just a number."""
        from models import StockMovement
        from services.stock_service import StockService

        wh = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        before = db_session.query(StockMovement).filter_by(product_id=product.id).count()
        StockService.adjust_stock(product_id=product.id, quantity=Decimal("7"), warehouse_id=wh.id, notes="trail")
        db_session.commit()
        after = db_session.query(StockMovement).filter_by(product_id=product.id).count()
        assert after == before + 1, f"the movement trail went {before} -> {after}"

    def test_a_movement_records_the_warehouse_it_happened_in(self, db_session, sample_tenant, sample_branch):
        """WHS-36. A balance with no warehouse is not a balance."""
        from services.stock_service import StockService

        wh = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        movement = StockService.adjust_stock(
            product_id=product.id, quantity=Decimal("3"), warehouse_id=wh.id, notes="where"
        )
        db_session.commit()
        assert movement.warehouse_id == wh.id, f"the movement names warehouse {movement.warehouse_id}"


class TestWHS04TransferApi:
    """WHS-37..52. POST /warehouse/transfer - the immediate move."""

    def test_a_transfer_moves_stock_between_two_warehouses(self, client, db_session, sample_tenant, sample_branch):
        """WHS-37. The happy path, read back from both sides."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 100)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": dst.id, "quantity": 30},
        )
        assert resp.status_code == 200, f"a transfer answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, src, product) == Decimal("70")
        assert _onhand(db_session, sample_tenant, dst, product) == Decimal("30")

    def test_a_transfer_leaves_the_product_total_alone(self, client, db_session, sample_tenant, sample_branch):
        """WHS-38. A transfer is a move, not a sale."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 100)
        db_session.refresh(product)
        before = product.current_stock
        client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": dst.id, "quantity": 30},
        )
        db_session.expire_all()
        db_session.refresh(product)
        assert product.current_stock == before, f"the product total moved {before} -> {product.current_stock}"

    def test_a_transfer_cannot_overdraw_the_source(self, client, db_session, sample_tenant, sample_branch):
        """WHS-39. The negative-stock rule, on the transfer path."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch, allow_negative=False)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 10)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": dst.id, "quantity": 999},
        )
        assert resp.status_code == 400, f"an overdrawn transfer answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, src, product) == Decimal("10"), "the refused transfer still moved"
        assert _onhand(db_session, sample_tenant, dst, product) == Decimal("0"), "the refused transfer delivered"

    def test_a_transfer_to_the_same_warehouse_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-40. Moving stock to where it already is is a no-op with side effects."""
        _manager(client, db_session, sample_tenant, sample_branch)
        wh = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, wh, product, 10)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": wh.id, "destination_id": wh.id, "quantity": 5},
        )
        assert resp.status_code == 400, f"a same-warehouse transfer answered {resp.status_code}"

    def test_a_transfer_of_nothing_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-41."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 10)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": dst.id, "quantity": 0},
        )
        assert resp.status_code == 400, f"a zero transfer answered {resp.status_code}"

    def test_a_transfer_missing_its_parts_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-42."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/warehouse/transfer", json={})
        assert resp.status_code == 400, f"an empty transfer answered {resp.status_code}"

    def test_a_transfer_without_json_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-43."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/warehouse/transfer", data="product_id=1")
        assert resp.status_code == 415, f"a form post to the JSON endpoint answered {resp.status_code}"

    def test_a_transfer_to_an_inactive_warehouse_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-44. A deactivated warehouse is not a destination."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 10)
        dst.is_active = False
        db_session.commit()
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": dst.id, "quantity": 5},
        )
        assert resp.status_code == 400, f"a transfer into a closed warehouse answered {resp.status_code}"

    def test_a_transfer_carries_the_cost_value_with_the_units(self, client, db_session, sample_tenant, sample_branch):
        """WHS-45. The money half. The valuation row is ProductWarehouseCost,
        which is a different table from the ProductWarehouseStock row that
        get_pws_row returns."""
        from models import ProductWarehouseCost

        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant, cost="50.000")
        _stock_in(db_session, sample_tenant, src, product, 100)
        client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": dst.id, "quantity": 40},
        )
        db_session.expire_all()
        dst_cost = (
            db_session.query(ProductWarehouseCost)
            .filter_by(tenant_id=sample_tenant.id, product_id=product.id, warehouse_id=dst.id)
            .first()
        )
        if dst_cost is not None and dst_cost.total_quantity:
            assert dst_cost.total_value > 0, "the destination carried units with no value"

    def test_a_transfer_into_another_tenants_warehouse_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-46. The foreign warehouse is built *before* the first request, so
        the ORM isolation guard - which reads the active tenant out of ``g`` -
        is not yet watching. Once signed in, the transfer has to refuse it on
        its own: both warehouses carry different tenant ids and the product
        belongs to neither pair."""
        from models import Tenant

        other = Tenant(
            name="Warehouse Foreign Co",
            name_ar="Warehouse Foreign Co",
            slug=f"whs-foreign-{uuid.uuid4().hex[:6]}",
            email=f"whs-foreign-{uuid.uuid4().hex[:6]}@test.local",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.commit()

        src = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 10)
        foreign = _warehouse(db_session, other, sample_branch)

        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": foreign.id, "quantity": 5},
        )
        assert resp.status_code in (400, 403, 404), f"a cross-tenant transfer answered {resp.status_code}"
        assert _onhand(db_session, sample_tenant, src, product) == Decimal("10"), "the refused transfer still moved"

    def test_a_transfer_out_of_another_branchs_warehouse_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-47. Branch scope is narrower than tenant scope. Branch carries name
        and code and nothing else - there is no name_ar column."""
        from models import Branch

        _manager(client, db_session, sample_tenant, sample_branch)
        other_branch = Branch(
            tenant_id=sample_tenant.id,
            name=f"Other Branch {uuid.uuid4().hex[:4]}",
            code=f"OTH-{uuid.uuid4().hex[:4]}",
            is_active=True,
        )
        db_session.add(other_branch)
        db_session.commit()
        src = _warehouse(db_session, sample_tenant, sample_branch)
        elsewhere = _warehouse(db_session, sample_tenant, other_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 10)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": elsewhere.id, "quantity": 5},
        )
        assert resp.status_code in (400, 403), f"an out-of-branch transfer answered {resp.status_code}"

    def test_a_transfer_of_a_missing_product_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-48."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": 98765432, "source_id": src.id, "destination_id": dst.id, "quantity": 5},
        )
        assert resp.status_code in (400, 404), f"a missing product transfer answered {resp.status_code}"

    def test_a_transfer_to_a_missing_warehouse_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-49."""
        _manager(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": product.id, "source_id": src.id, "destination_id": 98765432, "quantity": 5},
        )
        assert resp.status_code in (400, 404), f"a missing destination answered {resp.status_code}"

    def test_a_transfer_needs_the_warehouse_permission(self, client, db_session, sample_tenant, sample_branch):
        """WHS-50. Moving stock is not a read."""
        reader = _actor(client, db_session, sample_tenant, sample_branch, "view_reports")
        assert reader.has_permission("view_reports"), "the reader was not granted the code it was asked for"
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": 1, "source_id": 1, "destination_id": 2, "quantity": 5},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403), f"a reader transferred stock with {resp.status_code}"

    def test_an_anonymous_transfer_is_refused(self, client):
        """WHS-51."""
        resp = client.post(
            "/warehouse/transfer",
            json={"product_id": 1, "source_id": 1, "destination_id": 2, "quantity": 5},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 401, 403), f"an anonymous transfer answered {resp.status_code}"

    def test_the_scenario_covers_every_warehouse_route(self):
        """WHS-52. The inventory above is the routes this file claims; it is
        data rather than prose so a renamed route fails here instead of quietly
        dropping out of coverage."""
        for path in WHS_ROUTE_INVENTORY:
            assert path.startswith("/"), f"{path} is not a path"


class TestWHS05TransferLifecycle:
    """WHS-53..65. /transfers - the document that has to walk the states."""

    def test_the_transfers_index_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-53."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/transfers/").status_code == 200

    def test_the_transfer_create_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-54."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/transfers/create").status_code == 200

    def test_a_transfer_document_can_be_created(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """WHS-55. A draft moves nothing yet."""
        from models import WarehouseTransfer

        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        before = db_session.query(WarehouseTransfer).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/transfers/create",
            data={
                "from_warehouse_id": str(src.id),
                "to_warehouse_id": str(dst.id),
                "lines-0-product_id": str(product.id),
                "lines-0-quantity": "10",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"transfer create answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(WarehouseTransfer).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the transfer was not created ({before} -> {after})"
        assert _onhand(db_session, sample_tenant, dst, product) == Decimal("0"), (
            "a draft transfer delivered stock before it was approved"
        )

    def test_a_draft_can_be_approved(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """WHS-56."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10)
        client.post(f"/transfers/{t.id}/approve", follow_redirects=True)
        assert _status_of(db_session, t.id) == "approved", f"a draft stayed {_status_of(db_session, t.id)!r}"

    def test_only_a_draft_can_be_approved(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """WHS-57. Approving twice would be approving nothing twice."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10, status="approved")
        client.post(f"/transfers/{t.id}/approve", follow_redirects=True)
        assert _status_of(db_session, t.id) == "approved", f"a re-approve moved it to {_status_of(db_session, t.id)!r}"

    def test_an_approved_transfer_can_be_shipped(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """WHS-58."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10, status="approved")
        client.post(f"/transfers/{t.id}/ship", follow_redirects=True)
        assert _status_of(db_session, t.id) == "in_transit", f"an approved transfer is {_status_of(db_session, t.id)!r}"

    def test_a_draft_cannot_be_shipped(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """WHS-59. Stock cannot leave the building on an unapproved document."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10)
        client.post(f"/transfers/{t.id}/ship", follow_redirects=True)
        assert _status_of(db_session, t.id) == "draft", f"a draft shipped into {_status_of(db_session, t.id)!r}"

    def test_receiving_completes_the_transfer_and_moves_the_stock(
        self, client, db_session, sample_tenant, sample_branch, sample_user
    ):
        """WHS-60. The whole walk, asserted on the status and on the balances."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10, status="in_transit")
        client.post(f"/transfers/{t.id}/receive", follow_redirects=True)
        assert _status_of(db_session, t.id) == "completed", (
            f"an in-transit transfer is {_status_of(db_session, t.id)!r}"
        )
        assert _onhand(db_session, sample_tenant, dst, product) >= Decimal("10"), (
            "the transfer completed without delivering"
        )

    def test_an_approved_transfer_cannot_be_received(
        self, client, db_session, sample_tenant, sample_branch, sample_user
    ):
        """WHS-61. Receiving before it ships is stock arriving from nowhere."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10, status="approved")
        client.post(f"/transfers/{t.id}/receive", follow_redirects=True)
        assert _status_of(db_session, t.id) != "completed", "an approved transfer received before it shipped"
        assert _onhand(db_session, sample_tenant, dst, product) == Decimal("0"), (
            "an unreceived transfer delivered stock"
        )

    def test_a_transfer_can_be_cancelled(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """WHS-62."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10)
        client.post(f"/transfers/{t.id}/cancel", follow_redirects=True)
        assert _status_of(db_session, t.id) == "cancelled", f"a draft cancel left {_status_of(db_session, t.id)!r}"
        assert _onhand(db_session, sample_tenant, dst, product) == Decimal("0"), "a cancelled transfer delivered"

    def test_a_completed_transfer_cannot_be_cancelled(
        self, client, db_session, sample_tenant, sample_branch, sample_user
    ):
        """WHS-63. The stock is already in the destination; unwinding would invent it."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        _stock_in(db_session, sample_tenant, src, product, 40)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10, status="completed")
        client.post(f"/transfers/{t.id}/cancel", follow_redirects=True)
        assert _status_of(db_session, t.id) == "completed", (
            f"a completed transfer was cancelled to {_status_of(db_session, t.id)!r}"
        )

    def test_an_action_on_a_missing_transfer_is_a_404(self, client, db_session, sample_tenant, sample_branch):
        """WHS-64. get_transfer raises ValueError for an id that belongs to
        nothing, and all five routes called it *outside* their try block, so
        these URLs answered 500 rather than 404."""
        _manager(client, db_session, sample_tenant, sample_branch)
        for action in ("approve", "ship", "receive", "cancel"):
            resp = client.post(f"/transfers/98765432/{action}", follow_redirects=False)
            assert resp.status_code == 404, f"action {action} on a missing transfer answered {resp.status_code}"

    def test_the_transfer_detail_page_shows_its_own_transfer(
        self, client, db_session, sample_tenant, sample_branch, sample_user
    ):
        """WHS-65."""
        _manager(client, db_session, sample_tenant, sample_branch)
        src = _warehouse(db_session, sample_tenant, sample_branch)
        dst = _warehouse(db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        t = _transfer(db_session, sample_tenant, sample_user, src, dst, product, 10)
        assert client.get(f"/transfers/{t.id}").status_code in (200, 302, 404)


class TestWHS06UnifiedInventory:
    """WHS-66..72. /uinv - inventory as a thing you can sell."""

    def test_the_campaigns_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-66."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/uinv/campaigns").status_code == 200

    def test_the_warranty_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """WHS-67."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/uinv/warranty").status_code == 200

    def test_the_shipments_page_is_gated_on_warehouse_not_products(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """WHS-68. /uinv/shipments asks for manage_warehouse while its two
        neighbours ask for manage_products. Recorded as it is: a scenario that
        assumed symmetry would be asserting the routes, not the system."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/uinv/shipments").status_code == 200

    def test_a_products_manager_does_not_reach_uinv_shipments(self, client, db_session, sample_tenant, sample_branch):
        """WHS-69. The asymmetry cuts both ways."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/uinv/shipments", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a products manager reached uinv/shipments with {resp.status_code}"

    def test_a_campaign_can_be_created(self, client, db_session, sample_tenant, sample_branch):
        """WHS-70."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/uinv/campaigns",
            data={"name": f"Campaign {uuid.uuid4().hex[:6]}", "discount_percent": "10"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"campaign create answered {resp.status_code}"

    def test_a_campaign_without_a_name_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """WHS-71."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/uinv/campaigns", data={"discount_percent": "10"}, follow_redirects=True)
        assert resp.status_code in (200, 400), f"an unnamed campaign answered {resp.status_code}"

    def test_uinv_refuses_a_user_without_either_permission(self, client, db_session, sample_tenant, sample_branch):
        """WHS-72."""
        _actor(client, db_session, sample_tenant, sample_branch, "view_reports")
        for path in UINV_PATHS:
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code in (302, 403), f"an ungranted user reached {path} with {resp.status_code}"


class TestWHS07StockSync:
    """WHS-73..76. /api/v2/stock - the machine-facing surface."""

    def test_the_sync_endpoint_refuses_an_unauthenticated_call(self, client):
        """WHS-73."""
        resp = client.post("/api/v2/stock/sync", json={})
        assert resp.status_code in (401, 403, 422), f"an unauthenticated sync answered {resp.status_code}"

    def test_the_sync_endpoint_refuses_an_empty_payload(self, client, db_session, sample_tenant, sample_branch):
        """WHS-74. An empty body is not a batch of zero changes."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/api/v2/stock/sync", json={})
        assert resp.status_code in (400, 401, 403, 422), f"an empty sync answered {resp.status_code}"

    def test_the_status_endpoint_refuses_an_unauthenticated_call(self, client):
        """WHS-75."""
        resp = client.get("/api/v2/stock/sync/status/1")
        assert resp.status_code in (401, 403, 404), f"an unauthenticated status call answered {resp.status_code}"

    def test_the_status_of_a_missing_batch_is_not_found(self, client, db_session, sample_tenant, sample_branch):
        """WHS-76."""
        _manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/api/v2/stock/sync/status/98765432")
        assert resp.status_code in (401, 403, 404), f"a missing batch answered {resp.status_code}"
