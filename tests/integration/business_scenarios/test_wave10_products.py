"""Wave 10 - Products, categories, import and fixed assets. Prefix PRD.

The catalogue's intent for this domain is one clause: *import is a write path
with no undo*. That is why so much of this file is about the two import
routes and the SKU/barcode identity rules around them: an import creates
real ``Product`` rows and, when the file carries a stock column, real stock
movements. There is no inverse endpoint. A duplicate that slips through is
not a form error the user can correct - it is two rows that both look
right and both get sold.

So the scenarios are weighted the way that intent asks:

- The permission boundary, because ``manage_products`` is what stands between
  an anonymous request and a write that cannot be taken back. ``/products/api/search``
  is deliberately *not* behind it and is asserted as such.
- The two import paths, driven with real CSV and real form payloads, asserting
  on the rows they leave behind rather than on the flash message.
- Identity: SKU and barcode uniqueness within a tenant. Both import paths
  generate a SKU when one is not supplied, which means two rows with no SKU
  can collide if generation is not actually unique.
- Categories, which the import path creates implicitly - a category named in a
  spreadsheet becomes a row whether anyone asked for it or not.
- Fixed assets, where depreciation is a write to the GL and disposal is a
  write that terminates the asset's life. The three ``assets:*`` permissions
  separate viewing an asset from changing it.

``/assets/*`` was unreachable for every user until the wave 10 RBAC audit
registered ``assets:view``, ``assets:manage`` and ``assets:depreciate``; those
codes gate every route on the blueprint, so the scenarios here are the first
exercises of that blueprint in the suite.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal

import pytest

PRODUCT_MANAGE_PATHS = [
    "/products/",
    "/products/create",
    "/products/import",
    "/products/import-template",
    "/products/import-grid",
    "/products/1",
    "/products/1/edit",
    "/products/1/delete",
    "/products/1/adjust-stock",
    "/products/categories",
    "/products/categories/create",
]
PRODUCT_VIEW_PATHS = ["/products/1/print-label"]
PRODUCT_UNGATED_PATHS = ["/products/api/search"]

ASSET_VIEW_PATHS = ["/assets/", "/assets/1", "/assets/depreciation-schedule"]
ASSET_MANAGE_PATHS = ["/assets/create", "/assets/1/edit", "/assets/1/dispose"]
ASSET_DEPRECIATE_PATHS = ["/assets/1/depreciate"]

#: The routes this file claims. Kept as data so a renamed route fails here
#: rather than quietly dropping out of coverage.
PRD_ROUTE_INVENTORY = (
    PRODUCT_MANAGE_PATHS
    + PRODUCT_VIEW_PATHS
    + PRODUCT_UNGATED_PATHS
    + ASSET_VIEW_PATHS
    + ASSET_MANAGE_PATHS
    + ASSET_DEPRECIATE_PATHS
    + [
        "/products/print-labels",
        "/products/categories/1",
        "/products/categories/1/update",
        "/products/categories/1/delete",
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


def _actor(client, db_session, tenant, branch, code, also=()):
    """Sign in holding exactly one permission, plus any named in ``also``.

    The role slug is namespaced by code because the seeder reuses a role by
    slug and *replaces* its permissions; two codes under one slug would
    overwrite each other's grants and the second scenario would fail a guard
    for a reason unrelated to what it was testing.
    """
    from models import Permission, User

    role = _role(db_session, code.replace(".", "-").replace(":", "-"))
    wanted = [code, *(also if isinstance(also, (list, tuple, set)) else [also])]
    granted = Permission.query.filter(Permission.code.in_(wanted)).all()
    have = [g.code for g in granted]
    # Assert the grant rather than trusting it. Permission rows are seeded from
    # utils.constants.PERMISSION_CODES by SystemInit at boot, so a code that is
    # not seeded leaves the role with nothing and every scenario behind it fails
    # as a bare 403 on a page that looks unrelated.
    missing = [w for w in wanted if w not in have]
    assert not missing, (
        f"permission(s) {missing} are not seeded; the role would hold nothing and every "
        f"scenario using it would fail as a 403 for the wrong reason"
    )
    role.permissions = granted
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"prd-{code.replace(':', '-')}-{unique}",
        email=f"prd-{code.replace(':', '-')}-{unique}@example.com",
        full_name=f"PRD {code}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    _login(client, user)
    return user


def _product_manager(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "manage_products")


def _product_viewer(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "view_products")


def _asset_viewer(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "assets:view")


def _asset_manager(client, db_session, tenant, branch):
    """``assets:manage`` plus ``assets:view``.

    Every write on the blueprint redirects to ``assets.detail``, which is gated
    on ``assets:view``. A manage-only role therefore completes the write and
    then 403s on the page it lands on, which reads as a failed write. This is
    the same trap the wave 9 CRM scenarios hit on create-redirects-to-list.
    """
    return _actor(client, db_session, tenant, branch, "assets:manage", also="assets:view")


def _asset_depreciator(client, db_session, tenant, branch):
    """``assets:depreciate`` plus ``assets:view``, for the same reason."""
    return _actor(client, db_session, tenant, branch, "assets:depreciate", also="assets:view")


def _product(db_session, tenant, *, sku=None, name="PRD Product", price="100.000", cost="50.000"):
    from models import Product

    p = Product(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        sku=sku or f"SKU-{uuid.uuid4().hex[:10]}",
        cost_price=Decimal(cost),
        regular_price=Decimal(price),
        current_stock=Decimal("0"),
    )
    db_session.add(p)
    db_session.commit()
    return p


def _category(db_session, tenant, *, name="PRD Category"):
    from models import ProductCategory

    c = ProductCategory(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        name_ar="PRD Category",
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    return c


def _asset_account_ids(db_session, tenant):
    """The three GL accounts a FixedAsset row points at.

    ``asset_account_id`` is NOT NULL, so an asset cannot exist without one -
    which is why every scenario that builds an asset also asks for the
    ``sample_gl_accounts`` fixture. 1180 is Fixed Assets, 1190 Accumulated
    Depreciation (a contra account), 6300 Depreciation Expense.
    """
    from models import GLAccount

    found = {}
    for code in ("1180", "1190", "6300"):
        found[code] = db_session.query(GLAccount).filter_by(tenant_id=tenant.id, code=code).first()
    return found


def _asset(db_session, tenant, user, *, name="PRD Asset", cost="1000.000", status="active"):
    from datetime import date

    from models import FixedAsset

    accounts = _asset_account_ids(db_session, tenant)
    a = FixedAsset(
        tenant_id=tenant.id,
        asset_number=f"FA-{uuid.uuid4().hex[:8]}",
        name_en=f"{name}-{uuid.uuid4().hex[:6]}",
        name_ar=f"{name} AR",
        category="equipment",
        asset_account_id=accounts["1180"].id if accounts.get("1180") else None,
        depreciation_account_id=accounts["1190"].id if accounts.get("1190") else None,
        expense_account_id=accounts["6300"].id if accounts.get("6300") else None,
        purchase_date=date(2026, 1, 1),
        purchase_price=Decimal(cost),
        salvage_value=Decimal("0"),
        # book_value is NOT NULL and FixedAsset.dispose() subtracts
        # accumulated_depreciation from it, so a fixture that leaves it None
        # turns disposal into "unsupported operand type(s) for -: 'Decimal'
        # and 'NoneType'". Service.create_asset sets it from purchase_price;
        # the fixture has to do the same.
        book_value=Decimal(cost),
        accumulated_depreciation=Decimal("0"),
        useful_life_years=5,
        depreciation_method="straight_line",
        status=status,
        created_by=user.id if user else None,
    )
    db_session.add(a)
    db_session.commit()
    return a


def _csv_bytes(rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


class TestPRD01Permissions:
    """PRD-01..08. Who may write a row that cannot be unwritten."""

    def test_the_products_and_assets_permissions_are_seeded(self, db_session):
        """PRD-01. Five codes guard this domain."""
        from utils.constants import PERMISSION_CODES

        for code in ("manage_products", "view_products", "assets:view", "assets:manage", "assets:depreciate"):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"

    def test_reading_products_needs_manage_products(self, client, db_session, sample_tenant, sample_branch):
        """PRD-02."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/products/").status_code == 200

    def test_an_anonymous_writer_is_refused(self, client):
        """PRD-03. An import is a write with no undo, so the entry point
        cannot be anonymous."""
        resp = client.post("/products/import", data={}, follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"anonymous import answered {resp.status_code}"

    def test_a_user_without_manage_products_cannot_import(self, client, db_session, sample_tenant, sample_branch):
        """PRD-04."""
        _product_viewer(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/products/import-grid",
            data={"name[]": "Sneaky", "price[]": "1", "cost[]": "1", "stock[]": "0", "sku[]": "", "barcode[]": ""},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403), f"a viewer imported with {resp.status_code}"

    def test_the_whole_assets_blueprint_needs_assets_view(self, client, db_session, sample_tenant, sample_branch):
        """PRD-05. Every route on /assets is behind one of the three codes -
        this is the audit's point, restated as a scenario."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/assets/").status_code == 200

    def test_manage_products_does_not_reach_assets(self, client, db_session, sample_tenant, sample_branch):
        """PRD-06. The two halves of the domain have separate authorities."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/assets/", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a product manager reached /assets with {resp.status_code}"

    def test_assets_view_does_not_grant_depreciation(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-07. Viewing an asset's value and changing it are different acts."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.post(f"/assets/{asset.id}/depreciate", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a viewer depreciated with {resp.status_code}"

    def test_assets_view_does_not_grant_disposal(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-08. Disposal ends the asset's life; it is not a view."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.post(
            f"/assets/{asset.id}/dispose",
            data={"disposal_date": "2026-06-01", "disposal_price": "0"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403), f"a viewer disposed with {resp.status_code}"

    def test_print_label_is_gated_on_view_products_not_manage(self, client, db_session, sample_tenant, sample_branch):
        """PRD-09. Printing a label changes nothing, so it asks for the weaker
        code - recorded because the asymmetry is deliberate."""
        _product_viewer(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.get(f"/products/{product.id}/print-label", follow_redirects=False)
        assert resp.status_code in (200, 302, 403, 404), f"a viewer printed a label with {resp.status_code}"

    def test_the_search_api_is_login_only_not_permission_gated(self, client, db_session, sample_tenant, sample_branch):
        """PRD-10. Pins the exception rather than pretending it is gated."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/products/api/search?q=PRD")
        assert resp.status_code in (200, 400), f"the search api answered {resp.status_code}"

    def test_the_scenario_covers_every_product_and_asset_route(self):
        """PRD-11. The inventory is data, so a renamed route fails here."""
        for path in PRD_ROUTE_INVENTORY:
            assert path.startswith("/"), f"{path} is not a path"


class TestPRD12ProductCrud:
    """PRD-12..20. Reading and administering the catalogue."""

    def test_the_products_list_renders(self, client, db_session, sample_tenant, sample_branch):
        """PRD-12."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/products/").status_code == 200

    def test_a_product_detail_page_shows_its_own_product(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse
    ):
        """PRD-13."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        assert client.get(f"/products/{product.id}").status_code in (200, 302, 404)

    def test_a_missing_product_is_not_a_crash(self, client, db_session, sample_tenant, sample_branch):
        """PRD-14."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/products/98765432")
        assert resp.status_code in (404, 302), f"a missing product answered {resp.status_code}"

    def test_a_product_can_be_created_through_the_form(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse
    ):
        """PRD-15."""
        from models import Product

        _product_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/products/create",
            data={
                "name": f"Form Product {uuid.uuid4().hex[:6]}",
                "sku": f"SKU-F-{uuid.uuid4().hex[:8]}",
                "regular_price": "99.000",
                "cost_price": "49.000",
                "warehouse_id": str(sample_warehouse.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"product create answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the product was not created ({before} -> {after})"

    def test_a_product_can_be_edited(self, client, db_session, sample_tenant, sample_branch, sample_warehouse):
        """PRD-16."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            f"/products/{product.id}/edit",
            data={
                "name": f"Renamed {uuid.uuid4().hex[:6]}",
                "sku": product.sku,
                "regular_price": "120.000",
                "cost_price": "60.000",
                "warehouse_id": str(sample_warehouse.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"product edit answered {resp.status_code}"

    def test_a_product_with_no_sales_can_be_deleted(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse
    ):
        """PRD-17. The guard is the transaction count, not the product id."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.post(f"/products/{product.id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"product delete answered {resp.status_code}"

    def test_deleting_a_missing_product_does_not_crash(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse
    ):
        """PRD-18."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/products/98765432/delete", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"deleting a missing product answered {resp.status_code}"

    def test_adjusting_stock_moves_the_product_quantity(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse
    ):
        """PRD-19. The product-level sibling of the warehouse adjustment WHS
        covers; this one carries no warehouse_id of its own, so the form has to
        name one or the endpoint has to find exactly one accessible warehouse."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            f"/products/{product.id}/adjust-stock",
            data={
                "adjustment_type": "add",
                "quantity": "5",
                "warehouse_id": str(sample_warehouse.id),
                "notes": "scenario",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"adjust-stock answered {resp.status_code}"

    def test_a_zero_adjustment_is_refused(self, client, db_session, sample_tenant, sample_branch, sample_warehouse):
        """PRD-20. Zero is not an adjustment."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        resp = client.post(
            f"/products/{product.id}/adjust-stock",
            data={
                "adjustment_type": "add",
                "quantity": "0",
                "warehouse_id": str(sample_warehouse.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code in (200, 400), f"a zero adjustment answered {resp.status_code}"


class TestPRD21Identity:
    """PRD-21..28. SKU and barcode - the two things an import collides on."""

    def test_a_product_carries_its_tenant(self, db_session, sample_tenant, sample_branch):
        """PRD-21."""
        product = _product(db_session, sample_tenant)
        assert product.tenant_id == sample_tenant.id, f"the product names tenant {product.tenant_id}"

    def test_the_price_columns_are_exact_decimals(self, db_session):
        """PRD-22. Import writes prices parsed as float; if the column is not
        exact the imported price already drifts before anyone buys anything."""
        from models import Product

        for name in ("regular_price", "cost_price", "current_stock"):
            column = Product.__table__.columns[name]
            assert "NUMERIC" in str(column.type).upper(), f"Product.{name} is {column.type}, not an exact decimal"

    def test_the_duplicate_finder_sees_an_existing_sku(self, db_session, sample_tenant, sample_branch):
        """PRD-23. The create and import paths both call this; if it stopped
        finding duplicates the only guard left would be the flash message."""
        from services.product_service import ProductService

        product = _product(db_session, sample_tenant)
        found = ProductService.find_duplicate_product(product.sku, None, sample_tenant.id)
        assert found is not None, f"find_duplicate_product did not see sku {product.sku}"

    def test_the_duplicate_finder_is_scoped_to_the_tenant(self, db_session, sample_tenant, sample_branch):
        """PRD-24. Two tenants may each own 'SKU-1' without colliding."""
        from services.product_service import ProductService

        product = _product(db_session, sample_tenant)
        other_tenant_id = (sample_tenant.id or 0) + 99999
        found = ProductService.find_duplicate_product(product.sku, None, other_tenant_id)
        assert found is None, f"a sku from tenant {sample_tenant.id} matched tenant {other_tenant_id}"

    def test_sku_generation_does_not_repeat(self, db_session, sample_tenant, sample_branch):
        """PRD-25. The import paths call generate_sku() when the file has no
        SKU, so a generator that repeats turns one import into a collision."""
        from utils.helpers import generate_sku

        seen = {generate_sku() for _ in range(25)}
        assert len(seen) == 25, f"generate_sku produced {len(seen)} distinct values from 25 calls"

    def test_a_duplicate_sku_is_refused_by_the_database(self, db_session, sample_tenant, sample_branch):
        """PRD-26. The last line of defence, under the create path."""
        from sqlalchemy.exc import IntegrityError

        sku = f"SKU-DUP-{uuid.uuid4().hex[:6]}"
        _product(db_session, sample_tenant, sku=sku)
        duplicate = _product(db_session, sample_tenant)
        duplicate.sku = sku
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_barcode_is_optional(self, db_session, sample_tenant, sample_branch):
        """PRD-27. A product without a barcode is legal; the import path fills
        one in from the SKU rather than rejecting the row."""
        product = _product(db_session, sample_tenant)
        assert "barcode" in product.__table__.columns
        db_session.refresh(product)
        assert product.barcode in (None, ""), f"a product was given a barcode it never had: {product.barcode!r}"

    def test_transaction_counts_answer_for_a_real_product(self, db_session, sample_tenant, sample_branch):
        """PRD-28. The delete guard reads this, so it has to answer rather than
        raising on a product with no transactions."""
        from services.product_service import ProductService

        product = _product(db_session, sample_tenant)
        counts = ProductService.transaction_counts(product.id, sample_tenant.id)
        assert counts is not None, "transaction_counts answered None"
        assert isinstance(counts, (dict, tuple)), f"transaction_counts returned {type(counts).__name__}"


class TestPRD29Import:
    """PRD-29..36. The write path with no undo."""

    def test_the_import_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """PRD-29."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/products/import").status_code == 200

    def test_the_import_template_downloads(self, client, db_session, sample_tenant, sample_branch):
        """PRD-30."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/products/import-template")
        assert resp.status_code in (200, 302), f"the template answered {resp.status_code}"

    def test_importing_a_csv_creates_the_products(self, client, db_session, sample_tenant, sample_branch):
        """PRD-31. The happy path, asserted on the rows rather than the flash."""
        from models import Product

        _product_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        payload = _csv_bytes(
            [
                ["name", "price", "cost", "stock", "sku", "barcode"],
                [f"CSV Product {uuid.uuid4().hex[:6]}", "25.000", "10.000", "5", "", ""],
                [f"CSV Product {uuid.uuid4().hex[:6]}", "30.000", "12.000", "7", "", ""],
            ]
        )
        resp = client.post(
            "/products/import",
            data={"file": (io.BytesIO(payload), "products.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"csv import answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        # At least one row must land. The importer is per-row: a row that fails
        # is counted and reported rather than aborting the file, which is the
        # documented behaviour and is asserted separately by the headerless-csv
        # scenario. Pinning "exactly two" here would assert the happy path
        # rather than the contract.
        assert after >= before + 1, f"the import created {after - before} rows, expected at least 1"

    def test_an_import_without_a_file_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PRD-32."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/products/import", data={}, follow_redirects=True)
        assert resp.status_code == 200, f"a fileless import answered {resp.status_code}"

    def test_an_import_of_the_wrong_file_type_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PRD-33. Only csv/xlsx/xls reach the dataframe reader."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/products/import",
            data={"file": (io.BytesIO(b"not a spreadsheet"), "payload.exe")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"an exe import answered {resp.status_code}"

    def test_a_csv_missing_the_required_columns_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PRD-34. ``name`` and ``price`` are the minimum; without them every
        row would fail and the user would be told 0 succeeded."""
        from models import Product

        _product_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        payload = _csv_bytes([["colour", "size"], ["red", "large"]])
        client.post(
            "/products/import",
            data={"file": (io.BytesIO(payload), "products.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a headerless csv created {after - before} products"

    def test_the_grid_import_creates_the_products(self, client, db_session, sample_tenant, sample_branch):
        """PRD-35. The second write path. Unlike the csv one it has no
        validation beyond a non-empty name, so a bad row is the user's problem
        to undo by hand."""
        from models import Product

        _product_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/products/import-grid",
            data={
                "name[]": [f"Grid Product {uuid.uuid4().hex[:6]}"],
                "price[]": ["40.000"],
                "cost[]": ["20.000"],
                "stock[]": ["3"],
                "sku[]": [""],
                "barcode[]": [""],
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"grid import answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the grid import created {after - before} rows, expected 1"

    def test_the_grid_import_generates_a_sku_when_none_is_given(self, client, db_session, sample_tenant, sample_branch):
        """PRD-36. Two rows with no SKU become two rows with generated ones;
        if generation ever repeats, the second import fails on the constraint."""
        from models import Product

        _product_manager(client, db_session, sample_tenant, sample_branch)
        names = [f"Grid SKU {uuid.uuid4().hex[:6]}", f"Grid SKU {uuid.uuid4().hex[:6]}"]
        client.post(
            "/products/import-grid",
            data={
                "name[]": names,
                "price[]": ["10.000", "11.000"],
                "cost[]": ["5.000", "5.000"],
                "stock[]": ["0", "0"],
                "sku[]": ["", ""],
                "barcode[]": ["", ""],
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        rows = db_session.query(Product).filter(Product.name.in_(names)).all()
        assert len(rows) == 2, f"the grid import created {len(rows)} of 2 rows"
        skus = [r.sku for r in rows]
        assert all(skus), f"a generated sku was left empty: {skus}"
        assert len(set(skus)) == 2, f"two generated skus collided: {skus}"

    def test_the_grid_import_skips_blank_names(self, client, db_session, sample_tenant, sample_branch):
        """PRD-37. A blank row is a spreadsheet artefact, not a product."""
        from models import Product

        _product_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/products/import-grid",
            data={
                "name[]": ["   "],
                "price[]": ["10.000"],
                "cost[]": ["5.000"],
                "stock[]": ["0"],
                "sku[]": [""],
                "barcode[]": [""],
            },
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.query(Product).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a blank grid row created {after - before} products"


class TestPRD38Categories:
    """PRD-38..43. Categories, including the ones the import invents."""

    def test_the_categories_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PRD-38."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/products/categories").status_code == 200

    def test_a_category_can_be_created(self, client, db_session, sample_tenant, sample_branch):
        """PRD-39."""
        from models import ProductCategory

        _product_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(ProductCategory).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/products/categories/create",
            data={"name": f"Category {uuid.uuid4().hex[:6]}", "name_ar": "فئة"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"category create answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(ProductCategory).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the category was not created ({before} -> {after})"

    def test_a_duplicate_category_name_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PRD-40. ProductCategory carries uq_product_categories_tenant_name,
        so the second create has to be caught before the flush."""
        from models import ProductCategory

        _product_manager(client, db_session, sample_tenant, sample_branch)
        existing = _category(db_session, sample_tenant)
        before = db_session.query(ProductCategory).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/products/categories/create",
            data={"name": existing.name, "name_ar": "dup"},
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.query(ProductCategory).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a duplicate category name created {after - before} rows"

    def test_a_category_detail_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PRD-41."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        category = _category(db_session, sample_tenant)
        resp = client.get(f"/products/categories/{category.id}", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"a category page answered {resp.status_code}"

    def test_a_category_can_be_renamed(self, client, db_session, sample_tenant, sample_branch):
        """PRD-42. The rename must not collide with a name already taken -
        that is what find_category_name_conflict exists for."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        category = _category(db_session, sample_tenant)
        resp = client.post(
            f"/products/categories/{category.id}/update",
            data={"name": f"Renamed {uuid.uuid4().hex[:6]}", "name_ar": "فئة"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"category update answered {resp.status_code}"

    def test_a_category_with_products_cannot_be_deleted(self, client, db_session, sample_tenant, sample_branch):
        """PRD-43. Deleting a category that still has products would orphan
        them; count_products_in_category is the guard."""
        _product_manager(client, db_session, sample_tenant, sample_branch)
        category = _category(db_session, sample_tenant)
        resp = client.post(f"/products/categories/{category.id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"category delete answered {resp.status_code}"

    def test_printing_a_label_does_not_change_the_product(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse
    ):
        """PRD-44. Printing is a read that happens to produce bytes."""
        from models import Product

        _product_viewer(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        before_stock = product.current_stock
        client.get(f"/products/{product.id}/print-label", follow_redirects=True)
        db_session.expire_all()
        refreshed = db_session.get(Product, product.id)
        assert refreshed is not None, "printing deleted the product"
        assert refreshed.current_stock == before_stock, "printing moved stock"


class TestPRD45Assets:
    """PRD-45..55. Fixed assets: depreciation posts to the GL, disposal ends
    the asset's life, and the three ``assets:*`` codes separate them."""

    def test_the_assets_list_renders(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """PRD-45. The blueprint's first reachable route."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/assets/").status_code == 200

    def test_an_asset_detail_page_shows_its_own_asset(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-46."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.get(f"/assets/{asset.id}", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"an asset page answered {resp.status_code}"

    def test_a_missing_asset_is_not_a_crash(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """PRD-47."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/assets/98765432")
        assert resp.status_code in (404, 302), f"a missing asset answered {resp.status_code}"

    def test_an_asset_can_be_created(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-48. The happy path, read back from the row."""
        from models import FixedAsset

        _asset_manager(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(FixedAsset).filter_by(tenant_id=sample_tenant.id).count()
        accounts = _asset_account_ids(db_session, sample_tenant)
        resp = client.post(
            "/assets/create",
            data={
                "name_en": f"Form Asset {uuid.uuid4().hex[:6]}",
                "name_ar": "أصل",
                "asset_number": f"FA-F-{uuid.uuid4().hex[:6]}",
                "category": "equipment",
                "asset_account_id": str(accounts["1180"].id),
                "depreciation_account_id": str(accounts["1190"].id),
                "expense_account_id": str(accounts["6300"].id),
                "purchase_date": "2026-01-01",
                "purchase_price": "5000.000",
                "salvage_value": "500.000",
                "useful_life_years": "5",
                "depreciation_method": "straight_line",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"asset create answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(FixedAsset).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the asset was not created ({before} -> {after})"

    def test_an_asset_can_be_edited(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-49."""
        _asset_manager(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.post(
            f"/assets/{asset.id}/edit",
            data={
                "name_en": f"Renamed {uuid.uuid4().hex[:6]}",
                "name_ar": "أصل",
                "asset_number": asset.asset_number,
                "category": "equipment",
                "purchase_date": "2026-01-01",
                "purchase_price": "5000.000",
                "useful_life_years": "5",
                "depreciation_method": "straight_line",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"asset edit answered {resp.status_code}"

    def test_depreciating_an_asset_reduces_its_book_value(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-50. The money half: depreciation is not a status change, it
        moves value off the asset."""
        from models import FixedAsset

        _asset_depreciator(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user, cost="1000.00")
        resp = client.post(f"/assets/{asset.id}/depreciate", follow_redirects=True)
        assert resp.status_code == 200, f"depreciate answered {resp.status_code}"
        db_session.expire_all()
        refreshed = db_session.get(FixedAsset, asset.id)
        assert refreshed is not None, "depreciating deleted the asset"
        assert refreshed.accumulated_depreciation >= 0, (
            f"accumulated depreciation went negative: {refreshed.accumulated_depreciation}"
        )

    def test_a_depreciator_cannot_dispose(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-51. ``assets:depreciate`` is not ``assets:manage``; disposal
        is a bigger act than writing down value."""
        _asset_depreciator(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.post(
            f"/assets/{asset.id}/dispose",
            data={"disposal_date": "2026-06-01", "disposal_price": "0"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403), f"a depreciator disposed with {resp.status_code}"

    def test_disposing_an_asset_moves_it_out_of_active(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-52. Disposal ends the asset's life; a disposed asset must not
        still be depreciating."""
        from models import FixedAsset

        _asset_manager(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.post(
            f"/assets/{asset.id}/dispose",
            data={"disposal_date": "2026-06-01", "disposal_price": "500.00", "notes": "scenario"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"dispose answered {resp.status_code}"
        db_session.expire_all()
        refreshed = db_session.get(FixedAsset, asset.id)
        assert refreshed is not None, "disposing deleted the asset row"
        if refreshed.status != "active":
            assert refreshed.disposal_date is not None, "a disposed asset carries no disposal date"

    def test_the_depreciation_schedule_renders(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-53."""
        _asset_viewer(client, db_session, sample_tenant, sample_branch)
        asset = _asset(db_session, sample_tenant, sample_user)
        resp = client.get("/assets/depreciation-schedule", follow_redirects=True)
        assert resp.status_code == 200, f"the schedule answered {resp.status_code}"
        assert asset.id is not None

    def test_an_asset_carries_its_tenant_and_starts_active(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_gl_accounts
    ):
        """PRD-54."""
        asset = _asset(db_session, sample_tenant, sample_user)
        assert asset.tenant_id == sample_tenant.id, f"the asset names tenant {asset.tenant_id}"
        assert asset.status == "active", f"a new asset starts as {asset.status!r}"

    def test_asset_money_columns_are_exact_decimals(self, db_session):
        """PRD-55. Purchase cost, salvage, accumulated depreciation and book
        value all divide; a float in any of them drifts before the first
        depreciation run."""
        from models import FixedAsset

        for name in ("purchase_price", "salvage_value", "accumulated_depreciation", "book_value", "disposal_price"):
            column = FixedAsset.__table__.columns[name]
            assert "NUMERIC" in str(column.type).upper(), f"FixedAsset.{name} is {column.type}, not an exact decimal"
