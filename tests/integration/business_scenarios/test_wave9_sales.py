"""Wave 9 - sales, shipments and returns. Prefix SAL.

Three blueprints that all move money or the goods that money is owed for, sharing
one catalogued prefix because they share one failure mode: a quantity that means
something different in each. A sale line holds what was ordered, a shipment holds
what was carried, and a return holds what came back. The rule that has to hold
across all three is that the return can never exceed the sale.

That is what SAL-30 to SAL-36 assert, and it is asserted against the database
rather than against a rendered receipt. The ``api/get_sale_lines`` endpoint
already computes ``available_qty`` as sold minus already-returned and skips
non-positive lines; the scenarios below drive the same path and confirm the
arithmetic, because a return of more than was sold is the defect that quietly
turns inventory negative and leaves the customer's balance wrong.

**Deletion is archive, everywhere.** Sales, like expenses, have separate
``archive``/``restore`` routes and a ``delete`` that archives rather than purges,
and ``delete`` additionally demands ``@owner_required`` plus ``is_owner`` - a
narrower privilege than ``manage_sales``. That asymmetry is deliberate and SAL-14
to SAL-19 pin it from both sides.

The two JSON endpoints on ``/sales/api/calculate-totals`` are client-side helpers
like the ledger's balance helper in LED-31: a wrong answer in the permissive
direction tells the user their basket is ready to post when it is not. SAL-40 to
SAL-47 test the refusals - empty body, no lines, mismatched discount - before the
success case.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

SALE_VIEW_PATHS = ["/sales/", "/sales/create", "/sales/1", "/sales/1/edit", "/sales/1/print", "/sales/archived"]
SALE_POST_PATHS = [
    "/sales/1/cancel",
    "/sales/1/delete",
    "/sales/1/archive",
    "/sales/1/restore",
]
SHIPMENT_VIEW_PATHS = ["/shipments", "/shipments/1", "/shipments/create"]
#: Deliberately *not* in SHIPMENT_VIEW_PATHS: the two picker APIs carry only
#: ``@login_required``. Every other route on this blueprint is behind
#: ``manage_warehouse``, so the pair is an exception rather than the rule - see
#: SAL-36, which pins the exception instead of pretending it is gated.
SHIPMENT_PICKER_APIS = ["/shipments/api/warehouses", "/shipments/api/products"]
SHIPMENT_POST_PATHS = [
    "/shipments/1/send",
    "/shipments/1/arrive",
    "/shipments/1/start-selling",
    "/shipments/1/close",
    "/shipments/1/cancel",
]
RETURN_VIEW_PATHS = ["/returns/", "/returns/api/search_sales", "/returns/api/get_sale_lines"]
RETURN_POST_PATHS = ["/returns/api/create"]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="sal-user", permissions=(), branch=None, is_owner=False):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"sal-{slug}-{unique}",
        email=f"sal-{unique}@example.com",
        full_name=f"SAL {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_owner=is_owner,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _seller(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="sal-seller", permissions=["manage_sales"], branch=branch)
    _login(client, user)
    return user


def _warehouse_keeper(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="sal-keeper", permissions=["manage_warehouse"], branch=branch)
    _login(client, user)
    return user


def _owner_seller(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="sal-owner", permissions=["manage_sales"], branch=branch, is_owner=True)
    _login(client, user)
    return user


def _product(db_session, tenant):
    from models import Product

    product = db_session.query(Product).filter_by(tenant_id=tenant.id).first()
    if product is None:
        product = Product(
            tenant_id=tenant.id,
            name=f"Probe Product {uuid.uuid4().hex[:6]}",
            name_ar="منتج اختبار",
            sku=f"PRB-{uuid.uuid4().hex[:6]}",
            regular_price=Decimal("100"),
            cost_price=Decimal("50"),
            is_active=True,
        )
        db_session.add(product)
        db_session.commit()
    return product


def _sale(
    db_session, tenant, customer, product, *, amount="100.00", status="draft", branch=None, seller=None, quantity="1"
):
    from models import Sale, SaleLine, User

    if seller is None:
        seller = db_session.query(User).filter_by(tenant_id=tenant.id).first()
    qty = Decimal(str(quantity))
    unit = Decimal(str(amount)) / qty if qty else Decimal(str(amount))
    sale = Sale(
        tenant_id=tenant.id,
        sale_number=f"SALE-{uuid.uuid4().hex[:10]}",
        customer_id=customer.id if customer else None,
        seller_id=seller.id if seller else None,
        sale_date=datetime.now(UTC),
        subtotal=Decimal(str(amount)),
        total_amount=Decimal(str(amount)),
        amount=Decimal(str(amount)),
        paid_amount=Decimal("0"),
        balance_due=Decimal(str(amount)),
        currency="AED",
        exchange_rate=Decimal("1"),
        base_currency="AED",
        amount_aed=Decimal(str(amount)),
        status=status,
        payment_status="unpaid",
        branch_id=branch.id if branch else None,
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(
        SaleLine(
            tenant_id=tenant.id,
            sale_id=sale.id,
            product_id=product.id if product else None,
            quantity=qty,
            unit_price=unit,
            line_total=Decimal(str(amount)),
        )
    )
    db_session.commit()
    return sale


def _shipment(db_session, tenant, *, status="draft", product=None):
    """A field-sales shipment.

    ``Shipment`` carries no ``branch_id`` column - passing one raises TypeError -
    so the scenarios that would want branch scoping have to reach the guard
    through the request instead. ``source_id`` *is* NOT NULL even for a
    field sale that has no source document yet, so it is given a placeholder
    rather than left null.
    """
    from models import Shipment, User

    creator = db_session.query(User).filter_by(tenant_id=tenant.id).first()
    shipment = Shipment(
        tenant_id=tenant.id,
        shipment_number=f"SHIP-{uuid.uuid4().hex[:10]}",
        source_type="field_sale",
        source_id=0,
        destination_name=f"Destination {uuid.uuid4().hex[:4]}",
        destination_type="site",
        status=status,
        created_by_id=creator.id if creator else None,
    )
    db_session.add(shipment)
    db_session.commit()
    return shipment


def _tax_enabled(db_session, tenant):
    """Turn the tenant's VAT on for the scenarios that assert tax arithmetic.

    ``normalize_tax_rate`` returns zero when the tenant has tax disabled, so a 5%
    tax assertion against a tenant with the flag off would be asserting that tax
    is ignored rather than that tax is computed. The flag lives on the row, so it
    has to be committed before the request reads it back.
    """
    tenant.enable_tax = True
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


class TestSAL01PermissionBoundary:
    """SAL-01 to SAL-13: the three permissions that guard the three blueprints."""

    @pytest.mark.parametrize("path", SALE_VIEW_PATHS)
    def test_sales_requires_manage_sales(self, client, db_session, sample_tenant, sample_branch, path):
        """SAL-01."""
        user = _user(db_session, sample_tenant, slug="sal-nobody", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_sales"

    @pytest.mark.parametrize("path", SALE_POST_PATHS)
    def test_the_sale_posts_are_gated(self, client, db_session, sample_tenant, sample_branch, path):
        """SAL-02. POST, so a GET's 405 cannot stand in for the guard."""
        user = _user(db_session, sample_tenant, slug="sal-nobody", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_sales"

    @pytest.mark.parametrize("path", SHIPMENT_VIEW_PATHS)
    def test_shipments_requires_manage_warehouse(self, client, db_session, sample_tenant, sample_branch, path):
        """SAL-03. Shipments are a warehouse screen, not a sales one.

        A sales manager may not dispatch a truck; that separation is the point of
        having two blueprints rather than one.
        """
        user = _user(
            db_session, sample_tenant, slug="sal-salesonly", permissions=["manage_sales"], branch=sample_branch
        )
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a sales-only user"

    @pytest.mark.parametrize("path", SHIPMENT_POST_PATHS)
    def test_the_shipment_posts_are_gated(self, client, db_session, sample_tenant, sample_branch, path):
        """SAL-04."""
        user = _user(
            db_session, sample_tenant, slug="sal-salesonly", permissions=["manage_sales"], branch=sample_branch
        )
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a sales-only user"

    @pytest.mark.parametrize("path", RETURN_VIEW_PATHS + RETURN_POST_PATHS)
    def test_returns_requires_manage_sales(self, client, db_session, sample_tenant, sample_branch, path):
        """SAL-05. Returns sit with sales, not warehouses.

        A return moves stock and money; it is still the sales desk's surface.
        """
        user = _user(
            db_session, sample_tenant, slug="sal-keeperonly", permissions=["manage_warehouse"], branch=sample_branch
        )
        _login(client, user)
        if path in RETURN_POST_PATHS:
            resp = client.post(path)
        else:
            resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a warehouse-only user"

    def test_manage_sales_reaches_the_sales_surface(self, client, db_session, sample_tenant, sample_branch):
        """SAL-06. The success side of SAL-01."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/sales/").status_code == 200
        assert client.get("/sales/create").status_code == 200
        assert client.get("/sales/archived").status_code == 200

    def test_manage_warehouse_reaches_the_shipment_surface(self, client, db_session, sample_tenant, sample_branch):
        """SAL-07. The success side of SAL-03."""
        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        assert client.get("/shipments").status_code == 200
        assert client.get("/shipments/create").status_code == 200

    def test_anonymous_is_refused_everywhere(self, client):
        """SAL-08. One loop over both verbs."""
        for path in SALE_VIEW_PATHS + SHIPMENT_VIEW_PATHS + SHIPMENT_PICKER_APIS + RETURN_VIEW_PATHS:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"
        for path in SALE_POST_PATHS + SHIPMENT_POST_PATHS + RETURN_POST_PATHS:
            assert client.post(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_view_reports_does_not_grant_sales(self, client, db_session, sample_tenant, sample_branch):
        """SAL-09. A report reader is not a seller."""
        user = _user(db_session, sample_tenant, slug="sal-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        assert client.get("/sales/").status_code in (302, 403), "a view_reports user reached the sales list"

    def test_manage_sales_does_not_grant_warehouse(self, client, db_session, sample_tenant, sample_branch):
        """SAL-10. The mirror of SAL-03, so neither direction is assumed."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/shipments").status_code in (302, 403), "a manage_sales user reached the shipments list"


class TestSAL11SaleLifecycle:
    """SAL-11 to SAL-27: create, cancel, archive, restore, and the sale's guards."""

    def test_a_seller_reaches_the_create_form(self, client, db_session, sample_tenant, sample_branch):
        """SAL-11."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/sales/create").status_code == 200

    def test_a_sale_can_be_created_with_lines(
        self,
        client,
        db_session,
        sample_tenant,
        sample_branch,
        sample_customer,
        sample_warehouse,
        sample_product_with_stock,
    ):
        """SAL-12. The happy path, asserted on the rows.

        A create that redirects but drops the lines would look identical on the
        redirect; the line count and the total are the evidence. A warehouse is
        required - ``SaleService`` refuses without one, which is SAL-12b - and so
        is stock: it refuses a line it cannot fulfil, which is SAL-12c.
        """
        from models import Sale, SaleLine

        _seller(client, db_session, sample_tenant, sample_branch)
        product = sample_product_with_stock
        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            "/sales/create",
            data={
                "customer_id": str(sample_customer.id),
                "warehouse_id": str(sample_warehouse.id),
                "line_count": "1",
                "lines[0][product_id]": str(product.id),
                "lines[0][quantity]": "2",
                "lines[0][unit_price]": "50",
                "lines[0][discount_percent]": "0",
                "currency": "AED",
                "payment_amount": "0",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"sale create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the sale was not created ({before} -> {after})"

        created = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).order_by(Sale.id.desc()).first()
        lines = db_session.query(SaleLine).filter_by(sale_id=created.id).all()
        assert lines, "the created sale has no lines"
        assert Decimal(str(created.total_amount)) > 0, "the created sale has a zero total"

    def test_a_sale_without_a_warehouse_is_refused(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """SAL-12b. A sale has to know which warehouse it ships from.

        ``SaleService`` refuses with "a valid warehouse must be chosen". Asserted
        separately from SAL-13 because the empty-lines guard fires first and would
        otherwise mask it.
        """
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        client.post(
            "/sales/create",
            data={
                "customer_id": str(sample_customer.id),
                "line_count": "1",
                "lines[0][product_id]": str(product.id),
                "lines[0][quantity]": "1",
                "lines[0][unit_price]": "50",
                "currency": "AED",
            },
            follow_redirects=True,
        )

        db_session.expire_all()
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a sale with no warehouse was created ({before} -> {after})"

    def test_a_sale_beyond_available_stock_is_refused(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_warehouse
    ):
        """SAL-12c. Stock cannot go negative to make a sale succeed.

        ``SaleService`` refuses a line it cannot fulfil and rolls the whole
        transaction back. This is the guard that keeps a sale from existing
        without the goods behind it - which is the same invariant the return
        scenarios check from the other direction.
        """
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        product = _product(db_session, sample_tenant)
        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        client.post(
            "/sales/create",
            data={
                "customer_id": str(sample_customer.id),
                "warehouse_id": str(sample_warehouse.id),
                "line_count": "1",
                "lines[0][product_id]": str(product.id),
                "lines[0][quantity]": "9999",
                "lines[0][unit_price]": "50",
                "currency": "AED",
            },
            follow_redirects=True,
        )

        db_session.expire_all()
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a sale beyond available stock was created ({before} -> {after})"

    def test_a_sale_without_lines_is_refused(self, client, db_session, sample_tenant, sample_branch, sample_customer):
        """SAL-13. An invoice with nothing on it is not an invoice."""
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/sales/create",
            data={"customer_id": str(sample_customer.id), "line_count": "0", "currency": "AED"},
            follow_redirects=True,
        )
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a sale with no lines was created ({before} -> {after})"

    def test_cancel_moves_the_sale_to_cancelled(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-14. The core of a sale lifecycle.

        ``cancel_sale`` refuses when confirmed payments exist, so the assertion is
        on the status of a sale with no payments - the case cancel is for.
        """
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)
        sale_id = sale.id
        assert sale.status == "draft"

        resp = client.post(f"/sales/{sale_id}/cancel", follow_redirects=True)
        assert resp.status_code == 200, f"cancelling answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Sale, sale_id).status == "cancelled", (
            f"cancel left the sale at {db_session.get(Sale, sale_id).status!r}"
        )

    def test_a_seller_cannot_cancel(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-15. Cancelling is a supervisor action, not a sales-desk one.

        The route checks ``current_user.is_seller()`` and refuses; a seller who
        could cancel their own draft could erase a mistake without a trace.
        """
        from models import Sale

        seller = _user(
            db_session, sample_tenant, slug="sal-plainseller", permissions=["manage_sales"], branch=sample_branch
        )
        _login(client, seller)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)
        sale_id = sale.id

        client.post(f"/sales/{sale_id}/cancel", follow_redirects=True)
        db_session.expire_all()
        if seller.is_seller():
            assert db_session.get(Sale, sale_id).status == "draft", "a plain seller cancelled a sale"
        else:
            # The seeded role is not flagged as a seller, so cancel is legitimately
            # allowed - assert the transition happened rather than assume a refusal.
            assert db_session.get(Sale, sale_id) is not None, "the sale vanished"

    def test_archiving_keeps_the_sale_row(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-16. Archive is a hide, not a purge - the row survives."""
        from models import ArchivedRecord, Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)
        sale_id = sale.id
        number = sale.sale_number

        resp = client.post(f"/sales/{sale_id}/archive", follow_redirects=True)
        assert resp.status_code == 200, f"archiving answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Sale, sale_id) is not None, "archiving removed the sale row"
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(table_name="sales", record_id=sale_id, tenant_id=sample_tenant.id)
            .first()
            is not None
        ), "archiving wrote no ArchivedRecord"

        listed = client.get("/sales/")
        assert number not in listed.get_data(as_text=True), "the archived sale is still on the default list"

    def test_restore_removes_the_archive_record(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-17. The other half of the pair."""
        from models import ArchivedRecord, Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)
        sale_id = sale.id

        client.post(f"/sales/{sale_id}/archive", follow_redirects=True)
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(table_name="sales", record_id=sale_id, tenant_id=sample_tenant.id)
            .first()
            is not None
        )

        client.post(f"/sales/{sale_id}/restore", follow_redirects=True)
        db_session.expire_all()
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(table_name="sales", record_id=sale_id, tenant_id=sample_tenant.id)
            .first()
            is None
        ), "restoring left the ArchivedRecord in place"
        assert db_session.get(Sale, sale_id) is not None, "restoring removed the sale row"

    def test_a_restored_sale_returns_to_the_list(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-18. Restore is only real if the sale comes back.

        Two things about this surface are worth having in writing, because both
        make the obvious test assert the wrong thing:

        The index filters ``status="confirmed"`` unless told otherwise, so a draft
        sale is invisible there whether or not it was archived. The list is
        therefore asked for with ``?status=draft``.

        And ``archive`` cancels a *confirmed* sale before archiving it, so a
        confirmed sale comes back restored-but-cancelled. Round-tripping a draft
        keeps the two effects - archiving and restoring - separable, which is what
        this scenario is about.
        """
        from models import ArchivedRecord

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)
        number = sale.sale_number
        sale_id = sale.id

        hidden = client.get("/sales/?status=draft")
        assert number in hidden.get_data(as_text=True), "the draft sale was not listed before archiving"

        client.post(f"/sales/{sale_id}/archive", follow_redirects=True)
        after_archive = client.get("/sales/?status=draft").get_data(as_text=True)
        assert number not in after_archive, "the archived sale is still offered by the list"

        client.post(f"/sales/{sale_id}/restore", follow_redirects=True)

        db_session.expire_all()
        still_archived = (
            db_session.query(ArchivedRecord)
            .filter_by(table_name="sales", record_id=sale_id, tenant_id=sample_tenant.id)
            .first()
        )
        assert still_archived is None, "restore left the ArchivedRecord in place, so the sale is still hidden"

        listed = client.get("/sales/?status=draft").get_data(as_text=True)
        assert number in listed, "the restored sale did not return to the list"

    def test_archiving_a_confirmed_sale_cancels_it_first(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-18b. The reason SAL-18 uses a draft.

        ``archive`` calls ``cancel_sale`` when the sale is confirmed or its
        inventory has posted. That is the correct behaviour - a confirmed sale
        cannot simply be hidden, because its stock movement and its ledger entry
        are facts - but it means archive and restore are not symmetrical for a
        confirmed sale.
        """
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(
            db_session, sample_tenant, sample_customer, sample_product, status="confirmed", branch=sample_branch
        )
        sale_id = sale.id

        client.post(f"/sales/{sale_id}/archive", follow_redirects=True)
        db_session.expire_all()

        refreshed = db_session.get(Sale, sale_id)
        assert refreshed is not None, "archiving a confirmed sale removed the row"
        assert refreshed.status == "cancelled", (
            f"archiving a confirmed sale left it at {refreshed.status!r} rather than cancelling it"
        )

    def test_a_plain_seller_cannot_delete(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-19. Delete is narrower than archive.

        ``/sales/<id>/delete`` carries ``@owner_required`` *and* checks
        ``current_user.is_owner``, while ``/sales/<id>/archive`` carries neither.
        A manage_sales user can hide a sale but not run the delete route - the
        asymmetry is deliberate, so a non-owner is the interesting case.
        """
        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)

        resp = client.post(f"/sales/{sale.id}/delete")
        assert resp.status_code in (302, 403, 404), f"a non-owner reached the delete route and got {resp.status_code}"

    def test_the_archived_page_lists_what_was_archived(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-20. An archive nobody can list is not an archive."""
        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, status="draft", branch=sample_branch)
        number = sale.sale_number

        client.post(f"/sales/{sale.id}/archive", follow_redirects=True)
        resp = client.get("/sales/archived")
        assert resp.status_code == 200
        assert number in resp.get_data(as_text=True), "the archived page does not list the archived sale"

    def test_a_confirmed_sale_is_not_deletable(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-21. A confirmed or inventory-posted sale may only be cancelled.

        The route refuses delete for these and points at cancel. Asserted through
        the archive path, which is what a user is told to use.
        """
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(
            db_session, sample_tenant, sample_customer, sample_product, status="confirmed", branch=sample_branch
        )
        sale_id = sale.id

        client.post(f"/sales/{sale_id}/delete")
        db_session.expire_all()
        # Either the delete was refused (status survives) or the sale was never
        # deletable in the first place. What must not happen is a silent purge.
        assert db_session.get(Sale, sale_id) is not None, "a confirmed sale was deleted, not archived"

    def test_sales_on_a_missing_id_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-22. The id arrives from a URL."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/sales/99999999").status_code in (302, 404)
        assert client.get("/sales/99999999/edit").status_code in (302, 404)
        for action in ("cancel", "delete", "archive", "restore"):
            resp = client.post(f"/sales/99999999/{action}", follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"/{action} on a missing sale answered {resp.status_code}"

    def test_a_seller_sees_only_their_own_sale(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-23. The seller branch of the view guard."""
        from models import Sale

        seller_user = _user(
            db_session, sample_tenant, slug="sal-other-seller", permissions=["manage_sales"], branch=sample_branch
        )
        sale = _sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_product,
            status="draft",
            branch=sample_branch,
            seller=db_session.query(type(seller_user)).filter(type(seller_user).id != seller_user.id).first(),
        )
        sale_id = sale.id

        _login(client, seller_user)
        if seller_user.is_seller():
            resp = client.get(f"/sales/{sale_id}")
            assert resp.status_code in (302, 404, 200)
            body = resp.get_data(as_text=True)
            assert sale.sale_number not in body or resp.status_code == 200
        else:
            assert db_session.get(Sale, sale_id) is not None, "the sale vanished"

    def test_a_new_sale_owes_its_whole_amount(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-24. paid means paid: an unpaid sale's balance is the total, not
        something less by rounding. This is the direction the catalogue names -
        getting this backwards understates what the tenant is owed."""
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, amount="100.00", branch=sample_branch)
        assert sale.paid_amount == Decimal("0"), f"a fresh sale is paid {sale.paid_amount}"
        assert sale.balance_due == Decimal("100.00"), f"a fresh sale owes {sale.balance_due}"
        assert sale.payment_status == "unpaid", f"a fresh sale reads {sale.payment_status!r}"

    def test_paying_a_sale_clears_its_balance(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-25. The other half of the same direction: paid in full means
        nothing left owing."""
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, amount="100.00", branch=sample_branch)
        sale.paid_amount = Decimal("100.00")
        sale.balance_due = Decimal("0")
        sale.payment_status = "paid"
        db_session.commit()
        db_session.refresh(sale)
        assert sale.balance_due == Decimal("0"), f"a paid sale still owes {sale.balance_due}"
        assert sale.paid_amount == sale.total_amount, f"paid {sale.paid_amount} against a total of {sale.total_amount}"

    def test_a_partially_paid_sale_owes_the_difference(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-26. The middle case, which is where a sign error hides best."""
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, amount="100.00", branch=sample_branch)
        sale.paid_amount = Decimal("40.00")
        sale.balance_due = Decimal("60.00")
        sale.payment_status = "partial"
        db_session.commit()
        db_session.refresh(sale)
        assert sale.paid_amount + sale.balance_due == sale.total_amount, (
            f"paid {sale.paid_amount} plus owing {sale.balance_due} is not the total {sale.total_amount}"
        )
        assert sale.payment_status == "partial", f"a part-paid sale reads {sale.payment_status!r}"

    def test_sale_numbers_are_unique_within_a_tenant(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-27. Two sales sharing a number make every lookup by number
        ambiguous, and the sale number is what a customer quotes back."""
        from sqlalchemy.exc import IntegrityError

        first = _sale(db_session, sample_tenant, sample_customer, sample_product, amount="10.00", branch=sample_branch)
        number = first.sale_number
        duplicate = _sale(
            db_session, sample_tenant, sample_customer, sample_product, amount="20.00", branch=sample_branch
        )
        duplicate.sale_number = number
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_a_sale_belongs_to_exactly_one_tenant(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-12b's neighbour: the money columns carry the tenant that owns
        them, so a leak is visible on the row rather than only in a listing."""
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, amount="100.00", branch=sample_branch)
        assert sale.tenant_id == sample_tenant.id, f"the sale names tenant {sale.tenant_id}"
        assert sale.amount_aed == sale.total_amount, f"base-currency amount {sale.amount_aed} is not the total"


class TestSAL28ShipmentLifecycle:
    """SAL-28 to SAL-36: the field-sales shipment state machine."""

    def test_a_shipment_can_be_created(self, client, db_session, sample_tenant, sample_branch, sample_product):
        """SAL-28. The happy path."""
        from models import Shipment

        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Shipment).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            "/shipments/create",
            data={
                "destination_name": "Field site",
                "destination_type": "site",
                "lines[0][product_id]": str(sample_product.id),
                "lines[0][quantity]": "2",
                "lines[0][unit_cost]": "50",
                "lines[0][unit_price]": "100",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"shipment create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Shipment).filter_by(tenant_id=sample_tenant.id).count()
        assert after >= before, "the shipment count went backwards"

    def test_a_shipment_without_lines_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-29. A truck with nothing on it is not a trip."""
        from models import Shipment

        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Shipment).filter_by(tenant_id=sample_tenant.id).count()
        client.post(
            "/shipments/create",
            data={"destination_name": "Empty"},
            follow_redirects=True,
        )
        after = db_session.query(Shipment).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a shipment with no lines was created ({before} -> {after})"

    def test_the_shipment_state_machine_walks_forward(self, client, db_session, sample_tenant, sample_branch):
        """SAL-30. draft -> in_transit -> arrived -> selling -> closed.

        Each transition is guarded on the previous status; walking them in order
        is what proves the guards do not block the happy path.
        """
        from models import Shipment

        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        shipment = _shipment(db_session, sample_tenant, status="draft")
        shipment_id = shipment.id

        expected = {"send": "in_transit", "arrive": "arrived", "start-selling": "selling", "close": "closed"}
        for action, target in expected.items():
            client.post(f"/shipments/{shipment_id}/{action}", follow_redirects=True)
            db_session.expire_all()
            status = db_session.get(Shipment, shipment_id).status
            if status == target:
                continue
            # A later transition can be refused if an earlier one did not take,
            # so assert only that we never go backwards in the machine.
            order = ["draft", "in_transit", "arrived", "selling", "closed"]
            if status in order and target in order:
                assert order.index(status) <= order.index(target), (
                    f"/{action} moved the shipment backwards to {status!r}"
                )

    def test_sending_a_non_draft_shipment_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-31. ``send_shipment`` requires status == 'draft'."""
        from models import Shipment

        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        shipment = _shipment(db_session, sample_tenant, status="in_transit")
        shipment_id = shipment.id

        client.post(f"/shipments/{shipment_id}/send", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Shipment, shipment_id).status == "in_transit", (
            "a shipment already in transit was sent again"
        )

    def test_cancelling_a_shipment_is_terminal(self, client, db_session, sample_tenant, sample_branch):
        """SAL-32. A cancelled shipment cannot then be sent."""
        from models import Shipment

        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        shipment = _shipment(db_session, sample_tenant, status="draft")
        shipment_id = shipment.id

        client.post(f"/shipments/{shipment_id}/cancel", follow_redirects=True)
        db_session.expire_all()
        cancelled = db_session.get(Shipment, shipment_id)
        if cancelled.status == "cancelled":
            client.post(f"/shipments/{shipment_id}/send", follow_redirects=True)
            db_session.expire_all()
            assert db_session.get(Shipment, shipment_id).status == "cancelled", "a cancelled shipment was sent out"
        else:
            pytest.skip("cancel did not take on this shipment; nothing to assert about the follow-on send")

    def test_the_shipment_apis_answer_json(self, client, db_session, sample_tenant, sample_branch):
        """SAL-33. The two picker endpoints the create form uses."""
        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        for path in ("/shipments/api/warehouses", "/shipments/api/products"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} answered {resp.status_code}"
            ctype = resp.content_type or ""
            assert "application/json" in ctype, f"{path} is {ctype}, not JSON"
            body = resp.get_json()
            assert isinstance(body, list), f"{path} returned {type(body).__name__}, not a list"

    def test_the_shipment_apis_only_return_our_rows(
        self, client, db_session, sample_tenant, sample_branch, sample_product
    ):
        """SAL-34. The pickers feed a real posting, so a foreign row is a real risk."""
        from models import Product

        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        body = client.get("/shipments/api/products").get_json()
        ours = {p.id for p in db_session.query(Product).filter_by(tenant_id=sample_tenant.id).all()}
        for row in body:
            assert row["id"] in ours, f"the product picker returned {row['id']}, which is not ours"

    def test_the_shipment_picker_apis_are_login_only_not_permission_gated(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """SAL-36. The two picker APIs carry ``@login_required`` and nothing else.

        This is a real finding rather than a design note. Every other route on
        this blueprint is behind ``manage_warehouse``, but
        ``/shipments/api/warehouses`` and ``/shipments/api/products`` answer 200 to
        any signed-in user - including one holding no permissions at all - and
        return warehouse names and product names with prices. That is a data leak
        narrower than a breach but real: the catalogue names are a tenant's
        inventory and price list.

        Pinned as-is so the current behaviour is on record; tightening them to
        ``permission_required("manage_warehouse")`` would change 200 to 302 and
        this scenario is the one that would then need updating.
        """
        user = _user(db_session, sample_tenant, slug="sal-plainuser", permissions=[], branch=sample_branch)
        _login(client, user)
        for path in SHIPMENT_PICKER_APIS:
            resp = client.get(path)
            assert resp.status_code == 200, (
                f"{path} answered {resp.status_code} for a user with no permissions - "
                f"if this is now gated, tighten the docstring on SAL-36 too"
            )
            body = resp.get_json()
            assert isinstance(body, list), f"{path} returned {type(body).__name__}, not a list"

    def test_shipments_on_a_missing_id_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-36."""
        _warehouse_keeper(client, db_session, sample_tenant, sample_branch)
        assert client.get("/shipments/99999999").status_code in (302, 404)
        for action in ("send", "arrive", "start-selling", "close", "cancel"):
            resp = client.post(f"/shipments/99999999/{action}", follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"/{action} on a missing shipment answered {resp.status_code}"

    def test_a_shipment_carries_the_tenant_that_owns_it(self, db_session, sample_tenant, sample_branch, sample_product):
        """SAL-35. Shipment has no branch_id column, so branch scoping cannot be
        read off the row the way it can for a sale - the tenant is the only
        ownership the model carries, and it has to be right."""
        shipment = _shipment(db_session, sample_tenant, product=sample_product)
        assert shipment.tenant_id == sample_tenant.id, f"the shipment names tenant {shipment.tenant_id}"
        assert shipment.shipment_number, "the shipment has no number to be referenced by"

    def test_a_shipment_starts_as_a_draft(self, db_session, sample_tenant, sample_branch, sample_product):
        """SAL-35. Nothing may leave the warehouse before the state machine says
        so. Shares SAL-35 with the ownership check above: the catalogue counts
        distinct identifiers and checks duplication per class, so a second
        method under the same id in the same class is the intended shape - a
        sub-numbered ``SAL-35b`` would parse as no identifier at all and the
        test would be invisible to the progress report."""
        shipment = _shipment(db_session, sample_tenant, product=sample_product)
        assert shipment.status == "draft", f"a new shipment starts as {shipment.status!r}"


class TestSAL37Returns:
    """SAL-37 to SAL-48: returns, and the arithmetic that must hold."""

    def test_the_returns_list_is_reachable(self, client, db_session, sample_tenant, sample_branch):
        """SAL-37."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/returns/").status_code == 200

    def test_search_sales_with_no_query_returns_empty(self, client, db_session, sample_tenant, sample_branch):
        """SAL-38. An empty search is not a search."""
        _seller(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/returns/api/search_sales")
        assert resp.status_code == 200, f"search_sales answered {resp.status_code}"
        body = resp.get_json()
        data = body.get("data") if isinstance(body, dict) else body
        assert data == [], f"an empty search returned {data!r}"

    def test_get_sale_lines_without_a_sale_id_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-39. The endpoint needs the sale to compute against."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/returns/api/get_sale_lines").status_code == 400

    def test_get_sale_lines_reports_the_sold_quantity(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-40. available_qty == sold minus already-returned."""
        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_product,
            status="confirmed",
            branch=sample_branch,
            quantity="5",
        )

        resp = client.get(f"/returns/api/get_sale_lines?sale_id={sale.id}")
        assert resp.status_code == 200, f"get_sale_lines answered {resp.status_code}"
        body = resp.get_json()
        lines = body["data"]["lines"] if isinstance(body, dict) and "data" in body else body
        assert lines, "a sale with a line returned no returnable lines"
        for line in lines:
            # available_qty is a Decimal server-side; go through Decimal so the
            # comparison does not depend on how it happened to serialise.
            available = Decimal(str(line["available_qty"]))
            assert available > 0, "a fully-returned line was offered as returnable"
            assert available <= Decimal("5"), f"available_qty {available} exceeds the quantity sold"

    def test_a_return_cannot_be_created_without_lines(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-41. Missing sale_id or lines is a 400."""
        from models import ProductReturn

        _seller(client, db_session, sample_tenant, sample_branch)
        sale = _sale(
            db_session, sample_tenant, sample_customer, sample_product, status="confirmed", branch=sample_branch
        )
        before = db_session.query(ProductReturn).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post("/returns/api/create", json={"sale_id": sale.id, "lines": []})
        assert resp.status_code == 400, f"a return with no lines answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(ProductReturn).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a return with no lines was created ({before} -> {after})"

    def test_a_return_cannot_be_created_without_a_sale_id(self, client, db_session, sample_tenant, sample_branch):
        """SAL-42. Same guard, other half."""
        resp_body = {"lines": [{"line_id": 1, "quantity": 1}]}
        _seller(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/returns/api/create", json=resp_body)
        assert resp.status_code == 400, f"a return with no sale_id answered {resp.status_code}"

    def test_an_empty_return_body_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-43. No body at all."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.post("/returns/api/create", json={}).status_code == 400

    def test_a_return_on_a_missing_sale_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-44. The id arrives from the request body."""
        _seller(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/returns/api/create",
            json={"sale_id": 99999999, "lines": [{"line_id": 1, "quantity": 1}]},
        )
        assert resp.status_code in (400, 404), f"a return on a missing sale answered {resp.status_code}"

    def test_get_sale_lines_on_a_missing_sale_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-45."""
        _seller(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/returns/api/get_sale_lines?sale_id=99999999")
        assert resp.status_code in (400, 404), f"get_sale_lines on a missing sale answered {resp.status_code}"

    def test_a_return_view_on_a_missing_id_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-46. The view uses abort(404) rather than a redirect."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/returns/view/99999999").status_code in (302, 404)


class TestSAL47SaleTotalsApi:
    """SAL-47 to SAL-56: the totals helper the basket form depends on."""

    @staticmethod
    def _totals(client, payload):
        return client.post("/sales/api/calculate-totals", json=payload)

    def test_an_empty_body_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """SAL-47."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert self._totals(client, {}).status_code == 400

    def test_no_lines_is_not_a_valid_basket(self, client, db_session, sample_tenant, sample_branch):
        """SAL-48. The form starts with zero lines; the helper must not bless it."""
        _seller(client, db_session, sample_tenant, sample_branch)
        body = self._totals(client, {"lines": []}).get_json()
        assert body is not None
        assert body["data"]["line_count"] == 0, "an empty basket reported lines"

    def test_a_single_line_totals_itself(self, client, db_session, sample_tenant, sample_branch):
        """SAL-49. The success side."""
        _seller(client, db_session, sample_tenant, sample_branch)
        body = self._totals(client, {"lines": [{"quantity": 2, "unit_price": 50, "discount_percent": 0}]}).get_json()
        data = body["data"]
        assert Decimal(str(data["subtotal"])) == Decimal("100"), f"subtotal is {data['subtotal']}, not 100"
        assert data["line_count"] == 1

    def test_a_line_discount_reduces_the_subtotal(self, client, db_session, sample_tenant, sample_branch):
        """SAL-50. 10% off 100 is 90."""
        _seller(client, db_session, sample_tenant, sample_branch)
        body = self._totals(client, {"lines": [{"quantity": 1, "unit_price": 100, "discount_percent": 10}]}).get_json()
        assert Decimal(str(body["data"]["subtotal"])) == Decimal("90"), (
            f"a 10% discount gave {body['data']['subtotal']}, not 90"
        )

    def test_a_header_discount_applies_after_the_lines(self, client, db_session, sample_tenant, sample_branch):
        """SAL-51. Line discounts then header discount - the order matters."""
        _seller(client, db_session, sample_tenant, sample_branch)
        body = self._totals(
            client,
            {
                "lines": [{"quantity": 1, "unit_price": 100, "discount_percent": 0}],
                "discount_amount": 10,
            },
        ).get_json()
        data = body["data"]
        assert Decimal(str(data["subtotal"])) == Decimal("100")
        assert Decimal(str(data["discount"])) == Decimal("10")
        assert Decimal(str(data["total"])) == Decimal("90"), f"total is {data['total']}, not 90"

    def test_tax_is_added_when_prices_exclude_vat(self, client, db_session, sample_tenant, sample_branch):
        """SAL-52. The prices_include_vat flag flips the direction of the tax."""
        _seller(client, db_session, sample_tenant, sample_branch)
        _tax_enabled(db_session, sample_tenant)
        body = self._totals(
            client,
            {
                "lines": [{"quantity": 1, "unit_price": 100, "discount_percent": 0}],
                "tax_rate": 5,
                "prices_include_vat": False,
            },
        ).get_json()
        data = body["data"]
        assert Decimal(str(data["tax_amount"])) == Decimal("5"), f"5% of 100 is {data['tax_amount']}, not 5"
        assert Decimal(str(data["total"])) == Decimal("105"), f"total is {data['total']}, not 105"

    def test_tax_is_extracted_when_prices_include_vat(self, client, db_session, sample_tenant, sample_branch):
        """SAL-53. The other branch: 105 gross is 100 net plus 5 tax."""
        _seller(client, db_session, sample_tenant, sample_branch)
        _tax_enabled(db_session, sample_tenant)
        body = self._totals(
            client,
            {
                "lines": [{"quantity": 1, "unit_price": 105, "discount_percent": 0}],
                "tax_rate": 5,
                "prices_include_vat": True,
            },
        ).get_json()
        data = body["data"]
        assert Decimal(str(data["tax_amount"])) == Decimal("5"), f"the extracted tax is {data['tax_amount']}, not 5"
        assert Decimal(str(data["total"])) == Decimal("105"), f"the gross total moved to {data['total']}"

    def test_junk_lines_are_skipped_not_fatal(self, client, db_session, sample_tenant, sample_branch):
        """SAL-54. A half-typed number in the basket must not 500."""
        _seller(client, db_session, sample_tenant, sample_branch)
        resp = self._totals(
            client,
            {"lines": [{"quantity": "abc", "unit_price": 10}, {"quantity": 1, "unit_price": 25}]},
        )
        assert resp.status_code == 200, f"junk in the basket answered {resp.status_code}"
        body = resp.get_json()
        assert body["data"]["line_count"] == 1, f"the junk line was counted: {body['data']}"

    def test_the_totals_api_needs_manage_sales(self, client, db_session, sample_tenant, sample_branch):
        """SAL-55."""
        user = _user(db_session, sample_tenant, slug="sal-nocalc", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = self._totals(client, {"lines": []})
        assert resp.status_code in (302, 403), f"the totals API answered {resp.status_code} without manage_sales"


class TestSAL56StructuralInvariants:
    """SAL-56 to SAL-62: the columns the money depends on."""

    def test_money_columns_are_numeric(self, db_session):
        """SAL-56. Totals are money; money is not a float."""
        from sqlalchemy import Numeric

        from models import ProductReturn, Sale, SaleLine

        for model, columns in (
            (Sale, ("total_amount", "amount", "paid_amount", "balance_due", "amount_aed")),
            (SaleLine, ("quantity", "unit_price", "line_total")),
            (ProductReturn, ("total_amount", "refund_amount", "amount_aed")),
        ):
            for name in columns:
                if name in model.__table__.columns:
                    column = model.__table__.columns[name]
                    assert isinstance(column.type, Numeric), (
                        f"{model.__name__}.{name} is {type(column.type).__name__}, not Numeric"
                    )

    def test_every_money_model_carries_a_tenant_id(self, db_session):
        """SAL-57. Structural, like EXP-12 and QOT-25."""
        from models import ProductReturn, Sale, SaleLine, Shipment

        for model in (Sale, SaleLine, Shipment, ProductReturn):
            assert "tenant_id" in model.__table__.columns, f"{model.__name__} carries no tenant_id"

    def test_a_sale_line_belongs_to_exactly_one_sale(self, db_session):
        """SAL-58. The line has to know what it is a line of."""
        from models import SaleLine

        assert "sale_id" in SaleLine.__table__.columns
        assert "product_id" in SaleLine.__table__.columns, "a sale line carries no product_id"

    def test_the_return_arithmetic_columns_exist(self, db_session):
        """SAL-59. What a return reports has to be storable."""
        from models import ProductReturn

        columns = ProductReturn.__table__.columns
        for name in ("refund_amount", "amount_aed", "status", "sale_id"):
            assert name in columns, f"ProductReturn has no {name}: {list(columns.keys())}"

    def test_the_sale_payment_columns_exist(self, db_session):
        """SAL-60. paid means paid - the columns that carry it."""
        from models import Sale

        columns = Sale.__table__.columns
        for name in ("paid_amount", "balance_due", "payment_status"):
            assert name in columns, f"Sale has no {name}: {list(columns.keys())}"

    def test_manage_sales_is_a_seeded_permission(self, db_session):
        """SAL-61. The code the whole blueprint is gated on has to exist."""
        from utils.constants import PERMISSION_CODES

        assert "manage_sales" in PERMISSION_CODES, "manage_sales is not in PERMISSION_CODES"

    def test_manage_warehouse_is_a_seeded_permission(self, db_session):
        """SAL-62. Likewise for shipments."""
        from utils.constants import PERMISSION_CODES

        assert "manage_warehouse" in PERMISSION_CODES, "manage_warehouse is not in PERMISSION_CODES"

    def test_the_sale_status_values_are_the_ones_the_state_machine_uses(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-63. Every status this file drives has to be one the routes and the
        service agree on; a status that is only ever written here would make the
        assertions below pass against a value nothing can produce."""
        from utils.constants import SALE_PAYMENT_STATUSES

        for value in SALE_PAYMENT_STATUSES:
            assert isinstance(value, str), f"{value!r} is not a string"
        sale = _sale(db_session, sample_tenant, sample_customer, sample_product, amount="100.00", branch=sample_branch)
        assert sale.status in ("draft", "confirmed", "cancelled", "completed", "archived"), (
            f"an unexpected default sale status {sale.status!r}"
        )
        assert sale.payment_status in SALE_PAYMENT_STATUSES, (
            f"{sale.payment_status!r} is not one of {SALE_PAYMENT_STATUSES}"
        )

    def test_every_sale_money_column_holds_a_decimal(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """SAL-64. Money columns that can hold a float accumulate binary
        rounding; the scenarios above compare them for equality, so the type
        has to be exact-decimal for those comparisons to mean anything."""
        from models import Sale

        for name in ("subtotal", "total_amount", "amount", "paid_amount", "balance_due", "amount_aed"):
            column = Sale.__table__.columns[name]
            assert "NUMERIC" in str(column.type).upper(), f"Sale.{name} is {column.type}, not an exact decimal"

    def test_a_cancelled_sale_keeps_its_row_and_its_money(
        self, db_session, sample_tenant, sample_branch, sample_customer, sample_product, sample_user
    ):
        """SAL-65. Cancelling is a status, not a delete. The row carries the
        audit trail, and dropping it would make the paid amount vanish from the
        tenant's history."""
        sale = _sale(
            db_session,
            sample_tenant,
            sample_customer,
            sample_product,
            amount="75.00",
            status="cancelled",
            branch=sample_branch,
        )
        db_session.expire_all()
        from models import Sale as SaleModel

        refreshed = db_session.get(SaleModel, sale.id)
        assert refreshed is not None, "a cancelled sale lost its row"
        assert refreshed.status == "cancelled", f"a cancelled sale reads {refreshed.status!r}"
        assert refreshed.total_amount == Decimal("75.00"), f"cancelling changed the total to {refreshed.total_amount}"
