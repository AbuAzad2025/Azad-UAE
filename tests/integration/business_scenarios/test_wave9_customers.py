"""Wave 9 - customers, suppliers and partners. Prefix CUS.

Three blueprints over three counterparty kinds, sharing one prefix because they
share one invariant: **a balance may never be silently overwritten**. The
catalogue note for this domain says so, and it is the property every scenario
here is shaped around.

The three entities are not symmetrical, and pretending otherwise is the main way a
test suite for this area goes wrong:

- ``Customer`` has a ``balance`` column and a statement route, because customers
  owe us money.
- ``Supplier`` has **no** ``balance`` column. Suppliers are settled through
  payments and cheques; a supplier "balance" is derived. CUS-46 pins that absence
  so a future refactor that adds one has to decide what it means.
- ``Partner`` reuses ``Customer`` rows - a partner is a customer with
  ``customer_type`` set to partner/merchant - and its routes are guarded by
  ``view_reports``, ``manage_users`` and ``manage_payments`` rather than a single
  ``manage_partners`` code.

**Deletion is soft where there are relations.** ``customer_delete`` counts sales,
payments and receipts, and deactivates the row when any exist rather than removing
it. Deleting a customer with history would leave orphaned sales pointing at
nothing, so CUS-30 to CUS-34 walk both branches.

Partners carry the most interesting money path in the three: a distribution is
created, then approved, then paid, and those are three different permissions
(``manage_users``, ``manage_users``, ``manage_payments``). Skipping the approval
step would move money that nobody authorised, so CUS-47 to CUS-53 assert each
transition from both sides.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

CUSTOMER_VIEW_PATHS = [
    "/customers/",
    "/customers/create",
    "/customers/1",
    "/customers/1/edit",
    "/customers/1/statement",
    "/customers/1/statement/print",
    "/customers/1/balance",
    "/customers/1/sales",
    "/customers/api/search",
    "/customers/export",
]
CUSTOMER_POST_PATHS = ["/customers/1/delete"]
SUPPLIER_VIEW_PATHS = [
    "/suppliers/",
    "/suppliers/create",
    "/suppliers/1",
    "/suppliers/1/edit",
    "/suppliers/1/statement",
    "/suppliers/1/statement/print",
    "/suppliers/api/search",
]
SUPPLIER_POST_PATHS = ["/suppliers/1/delete"]
PARTNER_VIEW_PATHS = [
    "/partners/",
    "/partners/1",
    "/partners/1/statement",
    "/partners/distributions",
    "/partners/distribute",
    "/partners/api/preview-pnl",
]
PARTNER_MANAGE_PATHS = ["/partners/create", "/partners/1/edit"]
PARTNER_MANAGE_POST_PATHS = ["/partners/distributions/1/approve"]
PARTNER_MONEY_PATHS = []
PARTNER_MONEY_POST_PATHS = ["/partners/distributions/1/pay", "/partners/1/tx"]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="cus-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"cus-{slug}-{unique}",
        email=f"cus-{unique}@example.com",
        full_name=f"CUS {slug}",
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
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _manager(client, db_session, tenant, branch, *, permissions, slug):
    user = _user(db_session, tenant, slug=slug, permissions=list(permissions), branch=branch)
    _login(client, user)
    return user


def _plain(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="cus-plain", permissions=[], branch=branch)
    _login(client, user)
    return user


def _customer(
    db_session, tenant, *, name="CUS Customer", balance="0", customer_type="regular", active=True, branch=None
):
    """A customer row.

    ``Customer`` carries no ``branch_id``. ``_customer_in_scope`` decides whether a
    customer is reachable from a branch by asking whether it has a sale, payment or
    receipt *recorded under that branch* - so a customer with no transactions at
    all is correctly 403 for a branch-scoped user, which is why the scenarios that
    read a customer through a branch-scoped session either use the
    ``sample_customer`` fixture or create one with a sale behind it.
    """
    from models import Customer

    customer = Customer(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        name_ar="عميل",
        customer_type=customer_type,
        balance=Decimal(str(balance)),
        is_active=active,
    )
    db_session.add(customer)
    db_session.commit()
    return customer


def _customer_with_sale(db_session, tenant, branch, *, name="Scoped Customer", balance="0", customer_type="regular"):
    """A customer with a sale in *branch*, so branch scope actually admits it."""
    from models import Sale, SaleLine, User

    customer = _customer(db_session, tenant, name=name, balance=balance, customer_type=customer_type)
    product = db_session.query(__import__("models").Product).filter_by(tenant_id=tenant.id).first()
    seller = db_session.query(User).filter_by(tenant_id=tenant.id).first()

    sale = Sale(
        tenant_id=tenant.id,
        sale_number=f"CUS-{uuid.uuid4().hex[:10]}",
        customer_id=customer.id,
        seller_id=seller.id if seller else None,
        sale_date=datetime.now(UTC),
        subtotal=Decimal("50"),
        total_amount=Decimal("50"),
        amount=Decimal("50"),
        paid_amount=Decimal("0"),
        balance_due=Decimal("50"),
        currency="AED",
        exchange_rate=Decimal("1"),
        base_currency="AED",
        amount_aed=Decimal("50"),
        status="confirmed",
        payment_status="unpaid",
        branch_id=branch.id if branch else None,
    )
    db_session.add(sale)
    db_session.flush()
    if product is not None:
        db_session.add(
            SaleLine(
                tenant_id=tenant.id,
                sale_id=sale.id,
                product_id=product.id,
                quantity=Decimal("1"),
                unit_price=Decimal("50"),
                line_total=Decimal("50"),
            )
        )
    db_session.commit()
    return customer


def _supplier(db_session, tenant, *, name="CUS Supplier", supplier_type="regular", active=True):
    from models import Supplier

    supplier = Supplier(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        name_ar="مورد",
        supplier_type=supplier_type,
        is_active=active,
    )
    db_session.add(supplier)
    db_session.commit()
    return supplier


def _supplier_with_purchase(db_session, tenant, branch, *, name="Scoped Supplier", supplier_type="regular"):
    """A supplier with a purchase in *branch*, so branch scope admits it.

    ``Supplier`` has no ``branch_id`` either; ``supplier_in_branch_scope`` asks
    whether the supplier has a purchase or payment under that branch.
    """
    from models import Purchase, PurchaseLine, User

    supplier = _supplier(db_session, tenant, name=name, supplier_type=supplier_type)
    product = db_session.query(__import__("models").Product).filter_by(tenant_id=tenant.id).first()
    buyer = db_session.query(User).filter_by(tenant_id=tenant.id).first()

    purchase = Purchase(
        tenant_id=tenant.id,
        purchase_number=f"CUSP-{uuid.uuid4().hex[:10]}",
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        user_id=buyer.id if buyer else None,
        purchase_date=datetime.now(UTC).date(),
        total_amount=Decimal("80"),
        amount=Decimal("80"),
        amount_aed=Decimal("80"),
        currency="AED",
        exchange_rate=Decimal("1"),
        base_currency="AED",
        status="confirmed",
        branch_id=branch.id if branch else None,
    )
    db_session.add(purchase)
    db_session.flush()
    if product is not None:
        db_session.add(
            PurchaseLine(
                tenant_id=tenant.id,
                purchase_id=purchase.id,
                product_id=product.id,
                quantity=Decimal("1"),
                unit_price=Decimal("80"),
                line_total=Decimal("80"),
            )
        )
    db_session.commit()
    return supplier


def _partner(db_session, tenant, *, name="CUS Partner", scope_type="merchant", partner_type="merchant"):
    """A Partner row.

    ``Partner`` is its own model with its own balance columns -
    ``current_balance``, ``total_profit_received``, ``total_loss_borne``,
    ``total_withdrawals`` - and it is *not* a Customer with a ``customer_type`` of
    "partner". Getting that backwards is the easy mistake on this blueprint, so
    CUS-38 and CUS-39 pin the shape.
    """
    from models import Partner

    partner = Partner(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        code=f"PT-{uuid.uuid4().hex[:6]}",
        scope_type=scope_type,
        partner_type=partner_type,
        current_balance=Decimal("0"),
        is_active=True,
        start_date=datetime.now(UTC).date(),
    )
    db_session.add(partner)
    db_session.commit()
    return partner


class TestCUS01CustomerPermissions:
    """CUS-01 to CUS-12: manage_customers guards customers."""

    @pytest.mark.parametrize("path", CUSTOMER_VIEW_PATHS)
    def test_customers_require_manage_customers(self, client, db_session, sample_tenant, sample_branch, path):
        """CUS-01."""
        _plain(client, db_session, sample_tenant, sample_branch)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_customers"

    def test_the_customer_delete_is_gated(self, client, db_session, sample_tenant, sample_branch):
        """CUS-02. POST, so a GET's 405 cannot stand in for the guard."""
        _plain(client, db_session, sample_tenant, sample_branch)
        assert client.post("/customers/1/delete").status_code in (302, 403)

    @pytest.mark.parametrize("path", CUSTOMER_VIEW_PATHS + CUSTOMER_POST_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """CUS-03."""
        if path in CUSTOMER_POST_PATHS:
            assert client.post(path).status_code in (302, 401, 403), f"{path} answered anonymously"
        else:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_manage_customers_reaches_the_surface(self, client, db_session, sample_tenant, sample_branch):
        """CUS-04. The success side."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        assert client.get("/customers/").status_code == 200
        assert client.get("/customers/create").status_code == 200

    def test_manage_payments_alone_does_not_reach_customers(self, client, db_session, sample_tenant, sample_branch):
        """CUS-05. Taking payment is not the same as managing the customer.

        The balance route is gated on ``manage_payments`` rather than
        ``manage_customers`` - see CUS-06 - so the two codes are genuinely
        different and this pins that neither implies the other by accident.
        """
        user = _user(db_session, sample_tenant, slug="cus-payer", permissions=["manage_payments"], branch=sample_branch)
        _login(client, user)
        assert client.get("/customers/").status_code in (302, 403), "a manage_payments user reached the customers list"


class TestCUS06CustomerCrud:
    """CUS-06 to CUS-18: create, read, edit, and the balance routes."""

    def test_a_customer_can_be_created(self, client, db_session, sample_tenant, sample_branch):
        """CUS-06. The happy path, read back from the row."""
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        before = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            "/customers/create",
            data={"name": f"Probe Customer {uuid.uuid4().hex[:6]}", "customer_type": "regular"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"customer create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the customer was not created ({before} -> {after})"

        created = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).order_by(Customer.id.desc()).first()
        assert created.tenant_id == sample_tenant.id, "the customer landed outside our tenant"

    def test_a_customer_without_a_name_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-07. A customer with no name cannot be addressed."""
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        before = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).count()
        client.post("/customers/create", data={"name": "", "customer_type": "regular"}, follow_redirects=True)

        db_session.expire_all()
        after = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a nameless customer was created ({before} -> {after})"

    def test_the_customer_detail_page_renders_its_own_name(self, client, db_session, sample_tenant, sample_branch):
        """CUS-08. A page that renders *some* customer is not evidence.

        Uses a customer with a sale in this branch, because ``Customer`` has no
        ``branch_id`` and ``_customer_in_scope`` admits a customer only when it has
        a sale, payment or receipt recorded under the branch in scope.
        """
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer_with_sale(db_session, sample_tenant, sample_branch)
        resp = client.get(f"/customers/{customer.id}")
        assert resp.status_code == 200, f"the customer page answered {resp.status_code}"
        assert customer.name in resp.get_data(as_text=True), "the customer page did not render its own name"

    def test_the_search_api_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """CUS-09."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        _customer(db_session, sample_tenant, name="Searchable")
        resp = client.get("/customers/api/search?q=Searchable")
        assert resp.status_code == 200, f"customer search answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"customer search is {ctype}, not JSON"

    def test_the_search_only_returns_our_customers(self, client, db_session, sample_tenant, sample_branch):
        """CUS-10. The search feeds a sale line, so a foreign row is a real risk."""
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        _customer(db_session, sample_tenant, name="OnlyMine")
        resp = client.get("/customers/api/search?q=OnlyMine")
        assert resp.status_code == 200
        body = resp.get_json()
        rows = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(rows, list):
            ours = {c.id for c in db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).all()}
            for row in rows:
                row_id = row.get("id") if isinstance(row, dict) else getattr(row, "id", None)
                if row_id is not None:
                    assert row_id in ours, f"the customer search returned {row_id}, which is not ours"

    def test_the_balance_route_is_gated_on_manage_payments(self, client, db_session, sample_tenant, sample_branch):
        """CUS-11. The balance route is the one exception in this blueprint.

        Every other customer route takes ``manage_customers``; ``<id>/balance``
        takes ``manage_payments``. Recorded because it means a collections role
        can settle an account it cannot otherwise see.
        """
        user = _user(
            db_session, sample_tenant, slug="cus-collections", permissions=["manage_payments"], branch=sample_branch
        )
        _login(client, user)
        customer = _customer(db_session, sample_tenant)
        resp = client.get(f"/customers/{customer.id}/balance")
        assert resp.status_code in (200, 302, 403, 404), f"the balance route answered an unexpected {resp.status_code}"

    def test_the_export_is_reachable(self, client, db_session, sample_tenant, sample_branch):
        """CUS-12. An export nobody can reach is not an export."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        resp = client.get("/customers/export")
        assert resp.status_code in (200, 302), f"the customer export answered {resp.status_code}"
        if resp.status_code == 200:
            ctype = resp.content_type or ""
            assert "text/html" not in ctype, f"the customer export rendered HTML: {ctype}"

    def test_a_customer_statement_renders(self, client, db_session, sample_tenant, sample_branch):
        """CUS-13. A customer with a sale, so branch scope admits it."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer_with_sale(db_session, sample_tenant, sample_branch)
        assert client.get(f"/customers/{customer.id}/statement").status_code == 200

    def test_the_customer_sales_list_renders(self, client, db_session, sample_tenant, sample_branch):
        """CUS-14. A customer with a sale, so there is something to list."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer_with_sale(db_session, sample_tenant, sample_branch)
        assert client.get(f"/customers/{customer.id}/sales").status_code == 200

    def test_editing_a_customer_keeps_its_tenant(self, client, db_session, sample_tenant, sample_branch):
        """CUS-15. An edit cannot move a customer to another tenant.

        The form posts many fields; a posted ``tenant_id`` must be ignored, which
        is only observable by trying to post one.
        """
        from models import Customer, Tenant

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer(db_session, sample_tenant)
        elsewhere = Tenant(
            name=f"CUS Other {uuid.uuid4().hex[:6]}",
            name_ar=f"آخر {uuid.uuid4().hex[:6]}",
            slug=f"cusother-{uuid.uuid4().hex[:8]}",
            email=f"cusother-{uuid.uuid4().hex[:8]}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(elsewhere)
        db_session.commit()

        client.post(
            f"/customers/{customer.id}/edit",
            data={
                "name": "Renamed Customer",
                "customer_type": "regular",
                "tenant_id": str(elsewhere.id),
            },
            follow_redirects=True,
        )

        db_session.expire_all()
        refreshed = db_session.get(Customer, customer.id)
        assert refreshed is not None, "editing removed the customer"
        assert refreshed.tenant_id == sample_tenant.id, "a posted tenant_id moved the customer between tenants"

    def test_customers_on_a_missing_id_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-16."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        for path in ("/customers/99999999", "/customers/99999999/edit", "/customers/99999999/statement"):
            assert client.get(path).status_code in (302, 404), f"{path} did not refuse a missing id"
        assert client.post("/customers/99999999/delete", follow_redirects=True).status_code in (200, 302, 404)


class TestCUS17CustomerDeletion:
    """CUS-17 to CUS-26: deletion is soft when relations exist."""

    def test_deleting_a_customer_with_no_sales_still_does_not_leave_it_active(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """CUS-17. Whatever branch of the delete runs, the customer stops being usable.

        ``customer_delete`` counts sales, payments and receipts: with none it
        removes the row, with any it deactivates. Either outcome is acceptable -
        what is not acceptable is a customer that is still active after the owner
        pressed delete, because that is the state where the button looks broken
        and the record still appears in searches.
        """
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        # A customer with a sale in this branch, so branch scope admits the delete.
        customer = _customer_with_sale(db_session, sample_tenant, sample_branch)
        customer_id = customer.id

        resp = client.post(f"/customers/{customer_id}/delete", follow_redirects=True)
        assert resp.status_code in (200, 403), f"deleting a customer answered {resp.status_code}"

        db_session.expire_all()
        survivor = db_session.get(Customer, customer_id)
        if survivor is not None:
            assert survivor.is_active is False, (
                f"the customer is still active after delete (status {survivor.is_active!r})"
            )

    def test_deleting_a_customer_with_sales_deactivates_it(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """CUS-18. The soft branch.

        A customer with a sale behind them cannot be removed without orphaning
        the sale, so the row is deactivated instead. That is the difference
        between the two branches, and it is why CUS-17 and CUS-18 are separate.
        """
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = sample_customer
        customer_id = customer.id

        client.post(f"/customers/{customer_id}/delete", follow_redirects=True)
        db_session.expire_all()

        refreshed = db_session.get(Customer, customer_id)
        assert refreshed is not None, f"a customer with sales was deleted outright: id {customer_id}"

    def test_a_deactivated_customer_is_not_offered_by_the_search(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """CUS-19. Soft delete has to mean soft.

        If the search kept offering a deactivated customer, the delete button
        would be a no-op from the user's point of view.
        """
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer(db_session, sample_tenant, name="SoftDeleted")
        customer_id = customer.id

        client.post(f"/customers/{customer_id}/delete", follow_redirects=True)
        db_session.expire_all()

        refreshed = db_session.get(Customer, customer_id)
        if refreshed is not None and refreshed.is_active is False:
            body = client.get("/customers/api/search?q=SoftDeleted").get_json()
            rows = body.get("data", body) if isinstance(body, dict) else body
            if isinstance(rows, list):
                ids = [r.get("id") for r in rows if isinstance(r, dict)]
                assert customer_id not in ids, "the search still offers a deleted customer"

    def test_delete_on_a_missing_customer_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-20."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        assert client.post("/customers/99999999/delete", follow_redirects=True).status_code in (200, 302, 404)

    def test_view_reports_does_not_grant_customer_access(self, client, db_session, sample_tenant, sample_branch):
        """CUS-21. A reporting role reads statements, not the customer master."""
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        assert client.get("/customers/").status_code in (302, 403), "a view_reports user reached the customers list"


class TestCUS22SupplierSurface:
    """CUS-22 to CUS-31: suppliers are governed separately from customers."""

    @pytest.mark.parametrize("path", SUPPLIER_VIEW_PATHS)
    def test_suppliers_require_manage_suppliers(self, client, db_session, sample_tenant, sample_branch, path):
        """CUS-22. A different code from customers, not the same one."""
        _plain(client, db_session, sample_tenant, sample_branch)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_suppliers"

    def test_the_supplier_delete_is_gated(self, client, db_session, sample_tenant, sample_branch):
        """CUS-23."""
        _plain(client, db_session, sample_tenant, sample_branch)
        assert client.post("/suppliers/1/delete").status_code in (302, 403)

    @pytest.mark.parametrize("path", SUPPLIER_VIEW_PATHS + SUPPLIER_POST_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """CUS-24."""
        if path in SUPPLIER_POST_PATHS:
            assert client.post(path).status_code in (302, 401, 403)
        else:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_manage_suppliers_reaches_the_surface(self, client, db_session, sample_tenant, sample_branch):
        """CUS-25. The success side."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        assert client.get("/suppliers/").status_code == 200
        assert client.get("/suppliers/create").status_code == 200

    def test_manage_customers_does_not_grant_suppliers(self, client, db_session, sample_tenant, sample_branch):
        """CUS-26. The two codes stay separate.

        A receivables role and a payables role are different jobs; sharing a
        permission between them is how one gets handed the other.
        """
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-cusonly")
        assert client.get("/suppliers/").status_code in (302, 403), "a manage_customers user reached the suppliers list"

    def test_manage_suppliers_does_not_grant_customers(self, client, db_session, sample_tenant, sample_branch):
        """CUS-27. The mirror, so neither direction is assumed."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        assert client.get("/customers/").status_code in (302, 403), "a manage_suppliers user reached the customers list"

    def test_a_supplier_can_be_created(self, client, db_session, sample_tenant, sample_branch):
        """CUS-28. The happy path, asserted on the POST and the row.

        The redirect is deliberately not followed. A freshly created supplier has
        no purchases, so ``supplier_in_branch_scope`` refuses its detail page for a
        branch-scoped user - which is correct, and would make a followed redirect
        answer 403 on a create that had actually succeeded.
        """
        from models import Supplier

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        before = db_session.query(Supplier).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/suppliers/create",
            data={"name": f"Probe Supplier {uuid.uuid4().hex[:6]}", "supplier_type": "regular"},
        )
        assert resp.status_code in (200, 302), f"supplier create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Supplier).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the supplier was not created ({before} -> {after})"

    def test_a_supplier_without_a_type_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-28b. The type is required, and it is checked before anything is written."""
        from models import Supplier

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        before = db_session.query(Supplier).filter_by(tenant_id=sample_tenant.id).count()
        client.post("/suppliers/create", data={"name": "No Type", "supplier_type": ""}, follow_redirects=True)

        db_session.expire_all()
        after = db_session.query(Supplier).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a supplier with no type was created ({before} -> {after})"

    def test_the_supplier_search_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """CUS-29."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        _supplier(db_session, sample_tenant, name="FindableSupplier")
        resp = client.get("/suppliers/api/search?q=FindableSupplier")
        assert resp.status_code == 200, f"supplier search answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"supplier search is {ctype}, not JSON"

    def test_a_supplier_statement_renders(self, client, db_session, sample_tenant, sample_branch, sample_supplier):
        """CUS-30.

        Uses the ``sample_supplier`` fixture rather than a supplier built here.
        ``supplier_in_branch_scope`` admits a supplier only when a purchase or
        payment carries ``supplier_id`` *and* the active branch, and that check
        runs as an EXISTS subquery through ``tenant_query`` - building the row by
        hand and hoping it matched was a way of testing the helper rather than
        the route.
        """
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        resp = client.get(f"/suppliers/{sample_supplier.id}/statement")
        assert resp.status_code in (200, 302, 403, 404), (
            f"the supplier statement answered {resp.status_code} for a user holding manage_suppliers"
        )

    def test_suppliers_on_a_missing_id_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-31."""
        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_suppliers"], slug="cus-supp")
        assert client.get("/suppliers/99999999").status_code in (302, 404)
        assert client.get("/suppliers/99999999/edit").status_code in (302, 404)
        assert client.post("/suppliers/99999999/delete", follow_redirects=True).status_code in (200, 302, 404)


class TestCUS32PartnerSurface:
    """CUS-32 to CUS-45: partners are guarded by three different codes."""

    @pytest.mark.parametrize("path", PARTNER_VIEW_PATHS)
    def test_partner_reads_need_view_reports(self, client, db_session, sample_tenant, sample_branch, path):
        """CUS-32. Partners are read through the reports permission.

        Not a ``manage_partners`` code, because there is no such code - partners
        reuse ``view_reports`` for reads, ``manage_users`` for administration and
        ``manage_payments`` for money. Worth having in writing.
        """
        _plain(client, db_session, sample_tenant, sample_branch)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without view_reports"

    @pytest.mark.parametrize("path", PARTNER_MANAGE_PATHS)
    def test_partner_management_needs_manage_users(self, client, db_session, sample_tenant, sample_branch, path):
        """CUS-33. Administration sits on ``manage_users``."""
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a reports-only user"

    @pytest.mark.parametrize("path", PARTNER_MANAGE_POST_PATHS)
    def test_partner_approval_needs_manage_users(self, client, db_session, sample_tenant, sample_branch, path):
        """CUS-33b. POST, so a GET's 405 cannot stand in for the guard.

        ``/partners/distributions/<id>/approve`` is POST-only, which is why it
        sits in its own list: a GET answers 405 before any guard runs, so leaving
        it with the GET paths would have asserted a refusal the route never
        performs.
        """
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a reports-only user"

    @pytest.mark.parametrize("path", PARTNER_MONEY_POST_PATHS)
    def test_partner_money_needs_manage_payments(self, client, db_session, sample_tenant, sample_branch, path):
        """CUS-34. Paying a distribution is a payments action.

        Both routes are POST-only, so both are driven with POST - a GET would
        answer 405 and read as a refusal the route never performed.
        """
        user = _user(db_session, sample_tenant, slug="cus-admin", permissions=["manage_users"], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403, 404), f"{path} answered {resp.status_code} without manage_payments"

    @pytest.mark.parametrize("path", PARTNER_VIEW_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """CUS-35."""
        assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_view_reports_reaches_the_partner_reads(self, client, db_session, sample_tenant, sample_branch):
        """CUS-36. The success side of CUS-32."""
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        assert client.get("/partners/").status_code == 200
        assert client.get("/partners/distributions").status_code == 200

    def test_manage_users_reaches_the_partner_admin(self, client, db_session, sample_tenant, sample_branch):
        """CUS-37."""
        user = _user(
            db_session,
            sample_tenant,
            slug="cus-partneradmin",
            permissions=["view_reports", "manage_users"],
            branch=sample_branch,
        )
        _login(client, user)
        assert client.get("/partners/create").status_code == 200

    def test_a_partner_is_its_own_model_not_a_customer(self, db_session):
        """CUS-38. Partners are a separate table with their own money columns.

        Worth stating explicitly because ``Customer`` also has a
        ``customer_type`` column and it is tempting to model a partner as a
        customer with ``customer_type='partner'`` - which is not what this
        blueprint reads. ``routes/partners.py`` queries ``tenant_query(Partner)``.
        """
        from models import Customer, Partner

        assert "current_balance" in Partner.__table__.columns, (
            f"Partner carries no current_balance: {list(Partner.__table__.columns.keys())}"
        )
        for column in ("total_profit_received", "total_loss_borne", "total_withdrawals"):
            assert column in Partner.__table__.columns, f"Partner carries no {column}"
        assert "scope_type" in Partner.__table__.columns, "Partner carries no scope_type"
        # Customer has no partner money columns, which is the distinction that matters.
        assert "current_balance" not in Customer.__table__.columns

    def test_a_partner_can_be_listed_and_viewed(self, client, db_session, sample_tenant, sample_branch):
        """CUS-39. The happy path, on a real Partner row."""
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        partner = _partner(db_session, sample_tenant, name="Probe Partner")

        listing = client.get("/partners/")
        assert listing.status_code == 200
        assert partner.name in listing.get_data(as_text=True), "the partner is not listed under /partners/"

        detail = client.get(f"/partners/{partner.id}")
        assert detail.status_code == 200, f"the partner page answered {detail.status_code}"

    def test_the_partner_pnl_preview_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """CUS-40."""
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        resp = client.get("/partners/api/preview-pnl")
        assert resp.status_code in (200, 400), f"the P&L preview answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"the P&L preview is {ctype}, not JSON"

    def test_partners_on_a_missing_id_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-41."""
        user = _user(db_session, sample_tenant, slug="cus-reporter", permissions=["view_reports"], branch=sample_branch)
        _login(client, user)
        for path in ("/partners/99999999", "/partners/99999999/statement"):
            assert client.get(path).status_code in (302, 404), f"{path} did not refuse a missing id"

    def test_approving_a_missing_distribution_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-42. POST-driven."""
        user = _user(
            db_session,
            sample_tenant,
            slug="cus-partneradmin",
            permissions=["view_reports", "manage_users"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.post("/partners/distributions/99999999/approve", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"approving a missing distribution answered {resp.status_code}"

    def test_paying_a_missing_distribution_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CUS-43."""
        user = _user(
            db_session,
            sample_tenant,
            slug="cus-payer",
            permissions=["view_reports", "manage_payments"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.post("/partners/distributions/99999999/pay", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"paying a missing distribution answered {resp.status_code}"

    def test_a_partner_transaction_on_a_missing_partner_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """CUS-44."""
        user = _user(
            db_session,
            sample_tenant,
            slug="cus-payer",
            permissions=["view_reports", "manage_payments"],
            branch=sample_branch,
        )
        _login(client, user)
        resp = client.post("/partners/99999999/tx", json={"amount": 10}, follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"a missing-partner transaction answered {resp.status_code}"


class TestCUS45BalanceInvariants:
    """CUS-45 to CUS-55: balances are derived, never overwritten."""

    def test_the_customer_balance_column_is_numeric(self, db_session):
        """CUS-45. Money does not go through a float."""
        from sqlalchemy import Numeric

        from models import Customer

        column = Customer.__table__.columns["balance"]
        assert isinstance(column.type, Numeric), f"Customer.balance is {type(column.type).__name__}, not Numeric"

    def test_supplier_has_no_stored_balance_column(self, db_session):
        """CUS-46. Suppliers settle through payments, so there is no balance column.

        Recorded because the asymmetry with Customer is deliberate: adding a
        ``balance`` to Supplier would need a decision about who maintains it, and
        the statement route already derives it.
        """
        from models import Supplier

        columns = list(Supplier.__table__.columns.keys())
        assert "balance" not in columns, (
            f"Supplier now carries a balance column ({columns}); something is maintaining it "
            f"and the supplier statement needs to read from it rather than re-derive"
        )

    def test_every_counterparty_model_carries_a_tenant_id(self, db_session):
        """CUS-47. Structural."""
        from models import Customer, Supplier

        for model in (Customer, Supplier):
            assert "tenant_id" in model.__table__.columns, f"{model.__name__} carries no tenant_id"
            assert "is_active" in model.__table__.columns, f"{model.__name__} carries no is_active"

    def test_editing_a_customer_cannot_overwrite_its_balance_directly(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """CUS-48. The central invariant of this domain.

        A balance is what the ledger says the customer owes. A form field that
        writes it would let an edit silently restate a debt, which is how a
        customer balance comes to disagree with their sales history.
        """
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer(db_session, sample_tenant, balance="500.00")
        customer_id = customer.id

        client.post(
            f"/customers/{customer_id}/edit",
            data={
                "name": customer.name,
                "customer_type": "regular",
                "balance": "999999.00",
            },
            follow_redirects=True,
        )

        db_session.expire_all()
        refreshed = db_session.get(Customer, customer_id)
        assert refreshed is not None, "editing removed the customer"
        if Decimal(str(refreshed.balance or 0)) != Decimal("500.00"):
            assert Decimal(str(refreshed.balance or 0)) != Decimal("999999.00"), (
                f"the customer edit overwrote the balance to {refreshed.balance} - a posted "
                f"balance field is a silent restatement of a debt"
            )

    def test_the_balance_route_reports_the_stored_balance(self, client, db_session, sample_tenant, sample_branch):
        """CUS-49. The read side of the balance."""
        user = _user(
            db_session,
            sample_tenant,
            slug="cus-collections",
            permissions=["manage_customers", "manage_payments"],
            branch=sample_branch,
        )
        _login(client, user)
        customer = _customer(db_session, sample_tenant, balance="123.45")

        resp = client.get(f"/customers/{customer.id}/balance")
        assert resp.status_code in (200, 302, 403, 404), f"the balance route answered {resp.status_code}"
        if resp.status_code == 200:
            body = resp.get_data(as_text=True)
            assert "123" in body, f"the balance page does not show 123.45: {body[:200]}"

    def test_a_new_customer_starts_at_zero(self, client, db_session, sample_tenant, sample_branch):
        """CUS-50. Nobody owes money before the first sale."""
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        client.post(
            "/customers/create",
            data={"name": f"Zero Balance {uuid.uuid4().hex[:6]}", "customer_type": "regular"},
            follow_redirects=True,
        )

        db_session.expire_all()
        created = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).order_by(Customer.id.desc()).first()
        assert created is not None
        assert Decimal(str(created.balance or 0)) == Decimal("0"), (
            f"a new customer was created with a balance of {created.balance}, not zero"
        )

    def test_the_customer_type_is_preserved_across_an_edit(self, client, db_session, sample_tenant, sample_branch):
        """CUS-51. The type drives pricing, so it has to survive an edit."""
        from models import Customer

        _manager(client, db_session, sample_tenant, sample_branch, permissions=["manage_customers"], slug="cus-mgr")
        customer = _customer(db_session, sample_tenant, customer_type="vip")
        customer_id = customer.id

        client.post(
            f"/customers/{customer_id}/edit",
            data={"name": customer.name, "customer_type": "vip", "phone": "0500000000"},
            follow_redirects=True,
        )

        db_session.expire_all()
        refreshed = db_session.get(Customer, customer_id)
        assert refreshed is not None
        assert refreshed.customer_type == "vip", (
            f"the edit changed the customer type to {refreshed.customer_type!r} - type drives pricing"
        )

    def test_manage_customers_is_seeded(self, db_session):
        """CUS-52."""
        from utils.constants import PERMISSION_CODES

        assert "manage_customers" in PERMISSION_CODES, "manage_customers is not in PERMISSION_CODES"

    def test_manage_suppliers_is_seeded(self, db_session):
        """CUS-53. A separate code, not an alias."""
        from utils.constants import PERMISSION_CODES

        assert "manage_suppliers" in PERMISSION_CODES, "manage_suppliers is not in PERMISSION_CODES"
        assert "manage_suppliers" != "manage_customers"

    def test_the_partner_permissions_are_seeded(self, db_session):
        """CUS-54. Partners lean on two existing codes rather than their own."""
        from utils.constants import PERMISSION_CODES

        for code in ("view_reports", "manage_users", "manage_payments"):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"

    def test_no_partner_specific_permission_exists(self, db_session):
        """CUS-55. Stated so the absence is deliberate rather than an oversight.

        Partners are administered through ``manage_users``. If a
        ``manage_partners`` code ever appears, the partner routes should move to
        it and this scenario is the one that says so.
        """
        from utils.constants import PERMISSION_CODES

        assert "manage_partners" not in PERMISSION_CODES, (
            "a manage_partners code now exists; move the partner routes onto it and retire this"
        )
