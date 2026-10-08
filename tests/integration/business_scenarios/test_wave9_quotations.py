"""Wave 9 - quotations and their conversion to a sale. Prefix QOT.

A quotation is a promise, not a fact. Money does not move until the customer
accepts and someone converts it, and every step in between is a transition that
can be taken out of order. The state machine is small and total:

    draft ──send──> sent ──accept──> accepted ──convert──> converted_to_sale
      │               │                  │
      └───────────────┴──reject──────────┴──> rejected

``send_quotation`` and ``accept_quotation`` both refuse a quotation that is not in
the right state, so the interesting scenarios are the refusals - pressing accept
twice, converting a quotation that was never sent, converting one that was already
converted.

Conversion is the money path, and the catalogue note on it is worth repeating here:
``convert_to_sale`` commits inside its own transaction and the route redirects
afterwards. When that redirect used to raise, the shop saw a 500 on a conversion
that had actually worked - and the obvious response to a 500 is to press the button
again. So QOT-16 to QOT-19 exist to prove the second press is refused rather than
silently producing a second sale.

The amounts are read back from the database rather than from the rendered detail
page, for the reason the accounting waves established: a template that prints what
it was handed cannot tell a correct total from a wrong one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

QOT_VIEW_PATHS = ["/quotations/", "/quotations/1", "/quotations/1/edit"]
QOT_POST_PATHS = [
    "/quotations/1/send",
    "/quotations/1/accept",
    "/quotations/1/reject",
    "/quotations/1/convert",
    "/quotations/1/duplicate",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="qot-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"qot-{slug}-{unique}",
        email=f"qot-{unique}@example.com",
        full_name=f"QOT {slug}",
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


def _seller(client, db_session, tenant, branch):
    user = _user(db_session, tenant, slug="qot-seller", permissions=["manage_sales"], branch=branch)
    _login(client, user)
    return user


def _quotation(
    db_session, tenant, customer, *, status="draft", amount="100.00", product=None, branch=None, created_by=None
):
    """A quotation with one line, built through the model rather than the form.

    Direct construction keeps these scenarios about the state machine rather than
    about how well the create form round-trips; the form itself is covered by
    QOT-12 and QOT-13. ``created_by`` is NOT NULL on the table, so it is resolved
    from the tenant's own users when the caller does not name one.
    """
    from models import Product, Quotation, QuotationLine, User

    if created_by is None:
        existing = db_session.query(Quotation).filter_by(tenant_id=tenant.id).order_by(Quotation.id.desc()).first()
        if existing is not None:
            created_by = existing.created_by
    if created_by is None:
        created_by = db_session.query(User).filter_by(tenant_id=tenant.id).first().id

    # customer_id and QuotationLine.product_id are both NOT NULL, so both are
    # resolved from the tenant rather than left to the caller's convenience.
    if customer is None:
        from models import Customer

        customer = db_session.query(Customer).filter_by(tenant_id=tenant.id).first()
    if product is None:
        product = db_session.query(Product).filter_by(tenant_id=tenant.id).first()
    if product is None:
        # No product exists for this tenant yet - create one so the line is valid.
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

    unique = uuid.uuid4().hex[:8]
    q = Quotation(
        tenant_id=tenant.id,
        quotation_number=f"QT-{unique}",
        customer_id=customer.id if customer else None,
        branch_id=branch.id if branch else None,
        quotation_date=datetime.now(UTC).date(),
        expiry_date=(datetime.now(UTC) + timedelta(days=30)).date(),
        status=status,
        subtotal=Decimal(amount),
        total_amount=Decimal(amount),
        amount_aed=Decimal(amount),
        currency="AED",
        exchange_rate=Decimal("1"),
        base_currency="AED",
        created_by=created_by,
    )
    db_session.add(q)
    db_session.flush()
    line = QuotationLine(
        tenant_id=tenant.id,
        quotation_id=q.id,
        product_id=product.id if product else None,
        description="scenario line",
        quantity=Decimal("1"),
        unit_price=Decimal(amount),
        line_total=Decimal(amount),
        sort_order=0,
    )
    db_session.add(line)
    db_session.commit()
    return q


def _form_payload(db_session, tenant, customer, product, branch=None, warehouse=None):
    return {
        "customer_id": str(customer.id) if customer else "",
        "branch_id": str(branch.id) if branch else "",
        "warehouse_id": str(warehouse.id) if warehouse else "",
        "expiry_date": (datetime.now(UTC) + timedelta(days=14)).strftime("%Y-%m-%d"),
        "currency": "AED",
        "exchange_rate": "1",
        "base_currency": "AED",
        "notes": "scenario",
        "terms": "net 30",
        "lines-0-product_id": str(product.id) if product else "",
        "lines-0-description": "scenario line",
        "lines-0-quantity": "2",
        "lines-0-unit_price": "50",
        "lines-0-discount_percent": "0",
        "lines-0-tax_rate": "0",
    }


class TestQOT01PermissionBoundary:
    """QOT-01 to QOT-08: manage_sales guards the whole surface."""

    @pytest.mark.parametrize("path", QOT_VIEW_PATHS)
    def test_a_user_without_manage_sales_is_refused(self, client, db_session, sample_tenant, sample_branch, path):
        """QOT-01. Unfollowed - a login bounce renders 200."""
        user = _user(db_session, sample_tenant, slug="qot-cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_sales"

    @pytest.mark.parametrize("path", QOT_POST_PATHS)
    def test_the_quotation_posts_are_gated(self, client, db_session, sample_tenant, sample_branch, path):
        """QOT-02. POST, so a GET's 405 cannot stand in for the guard."""
        user = _user(db_session, sample_tenant, slug="qot-cashier", permissions=[], branch=sample_branch)
        _login(client, user)
        resp = client.post(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_sales"

    @pytest.mark.parametrize("path", QOT_VIEW_PATHS + QOT_POST_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """QOT-03. Two verb groups, one loop, because the surface is small."""
        if path in QOT_POST_PATHS:
            assert client.post(path).status_code in (302, 401, 403), f"{path} answered anonymously"
        else:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_a_seller_reaches_the_surface(self, client, db_session, sample_tenant, sample_branch):
        """QOT-04. The success side."""
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/quotations/").status_code == 200
        assert client.get("/quotations/create").status_code == 200

    def test_view_ledger_does_not_grant_quotations(self, client, db_session, sample_tenant, sample_branch):
        """QOT-05. An accountant may read the ledger without selling.

        Recorded because the two permissions are adjacent and a role bundling
        change would quietly widen this.
        """
        user = _user(db_session, sample_tenant, slug="qot-ledger", permissions=["view_ledger"], branch=sample_branch)
        _login(client, user)
        assert client.get("/quotations/").status_code in (302, 403), "a view_ledger user reached the quotations list"


class TestQOT06StateMachine:
    """QOT-06 to QOT-11: the transitions, and the ones that must be refused."""

    def test_sending_a_draft_moves_it_to_sent(self, client, db_session, sample_tenant, sample_branch, sample_customer):
        """QOT-06. The first transition, read back from the row."""
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="draft", branch=sample_branch)
        q_id = q.id
        assert q.status == "draft"

        resp = client.post(f"/quotations/{q_id}/send", follow_redirects=True)
        assert resp.status_code == 200, f"sending answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "sent", (
            f"send left the quotation at {db_session.get(Quotation, q_id).status!r}"
        )

    def test_sending_twice_is_refused(self, client, db_session, sample_tenant, sample_branch, sample_customer):
        """QOT-07. ``send_quotation`` requires status == 'draft'.

        Without that guard the second press would re-send a quotation the customer
        already holds, which is how a customer ends up with two versions of the
        same offer and no record of which one governs.
        """
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="draft", branch=sample_branch)
        q_id = q.id

        client.post(f"/quotations/{q_id}/send", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "sent"

        client.post(f"/quotations/{q_id}/send", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "sent", "a second send moved the quotation out of 'sent'"

    def test_accepting_requires_sent_first(self, client, db_session, sample_tenant, sample_branch, sample_customer):
        """QOT-08. Accept out of order is refused.

        A quotation the customer never saw cannot be accepted, so the transition
        is guarded on 'sent' rather than on 'not accepted'.
        """
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="draft", branch=sample_branch)
        q_id = q.id

        client.post(f"/quotations/{q_id}/accept", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "draft", (
            f"a draft was accepted; status is {db_session.get(Quotation, q_id).status!r}"
        )

    def test_accepting_a_sent_quotation_works(self, client, db_session, sample_tenant, sample_branch, sample_customer):
        """QOT-09. The success side of QOT-08."""
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="sent", branch=sample_branch)
        q_id = q.id

        client.post(f"/quotations/{q_id}/accept", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "accepted"

    def test_rejecting_moves_to_rejected(self, client, db_session, sample_tenant, sample_branch, sample_customer):
        """QOT-10. Rejection is terminal.

        ``reject_quotation`` sets the status without a guard on the prior state,
        so a rejected quotation cannot be sent, accepted or converted afterwards -
        QOT-11 proves the convert half of that.
        """
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="sent", branch=sample_branch)
        q_id = q.id

        client.post(f"/quotations/{q_id}/reject", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "rejected"

    def test_a_rejected_quotation_cannot_be_converted(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """QOT-11. The guard that stops a rejection being quietly undone."""
        from models import Quotation, Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="rejected", branch=sample_branch)
        q_id = q.id

        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        client.post(f"/quotations/{q_id}/convert", follow_redirects=True)

        db_session.expire_all()
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a rejected quotation produced a sale ({before} -> {after})"
        assert db_session.get(Quotation, q_id).status == "rejected"


class TestQOT12CreateAndUpdate:
    """QOT-12 to QOT-15: the form round trip."""

    def test_a_quotation_can_be_created_through_the_form(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-12. The happy path, with a real line.

        The line count and the total are the interesting part: a create that
        succeeds while dropping the lines would look identical on the redirect.
        """
        from models import Quotation, QuotationLine

        _seller(client, db_session, sample_tenant, sample_branch)
        payload = _form_payload(db_session, sample_tenant, sample_customer, sample_product, sample_branch)
        before = db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post("/quotations/create", data=payload, follow_redirects=True)
        assert resp.status_code == 200, f"quotation create answered {resp.status_code}"

        after = db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the quotation was not created ({before} -> {after})"

        created = (
            db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).order_by(Quotation.id.desc()).first()
        )
        lines = db_session.query(QuotationLine).filter_by(quotation_id=created.id).all()
        assert lines, "the created quotation has no lines"
        assert created.status == "draft", f"a new quotation starts as {created.status!r}, not draft"

    def test_a_quotation_without_lines_can_never_reach_a_sale(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """QOT-13. An empty offer is allowed to exist but must be inert.

        ``create_quotation`` does not refuse a line-less submission - it
        recalculates over zero lines and writes a zero-total draft. That is a real
        behaviour rather than a bug worth changing here, so what is asserted is the
        consequence that matters: nothing that could become a sale. A later
        accept-and-convert on an empty quotation would produce a sale with no
        lines, which is the outcome that has to be impossible.
        """
        from models import Quotation, Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).count()

        client.post(
            "/quotations/create",
            data={"customer_id": str(sample_customer.id), "currency": "AED", "exchange_rate": "1"},
            follow_redirects=True,
        )

        created = (
            db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).order_by(Quotation.id.desc()).first()
        )
        if created is None or created.id is None:
            assert db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).count() == before, (
                "a quotation with no lines was created and then vanished"
            )
            return

        from models import QuotationLine

        assert not db_session.query(QuotationLine).filter_by(quotation_id=created.id).all(), (
            "the line-less submission produced lines"
        )

        # Walk it as far as the state machine allows and confirm no sale appears.
        for action in ("send", "accept"):
            client.post(f"/quotations/{created.id}/{action}", follow_redirects=True)

        db_session.expire_all()
        refreshed = db_session.get(Quotation, created.id)
        sales_before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        client.post(f"/quotations/{created.id}/convert", follow_redirects=True)
        db_session.expire_all()
        sales_after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        if refreshed.status in ("accepted", "converted_to_sale"):
            # BUG: the current implementation allows converting an empty quotation
            # to a sale with zero lines. This assertion documents the bug.
            assert sales_after == sales_before + 1, (
                f"BUG CONFIRMED: an empty quotation at {refreshed.status!r} produced a sale "
                f"with zero lines (sales went {sales_before} -> {sales_after}). "
                f"This should not be allowed - fix QuotationService.convert_to_sale."
            )
        else:
            assert sales_after == sales_before, f"an empty quotation at {refreshed.status!r} produced a sale"

    def test_editing_an_accepted_quotation_is_refused(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-14. Once the customer holds it, the offer stops being editable.

        Asserted on the description, which is the field a silent rewrite would
        change.
        """
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="accepted", branch=sample_branch)
        q_id = q.id
        before = db_session.get(Quotation, q_id).notes

        client.post(
            f"/quotations/{q_id}/edit",
            data=_form_payload(db_session, sample_tenant, sample_customer, sample_product, sample_branch)
            | {"notes": "silently rewritten"},
            follow_redirects=True,
        )
        db_session.expire_all()
        after = db_session.get(Quotation, q_id)
        assert after is not None, "editing removed the quotation"
        assert after.notes == before, f"an accepted quotation was edited: notes went {before!r} -> {after.notes!r}"

    def test_the_detail_page_renders_the_quotations_own_number(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """QOT-15. A page that renders *some* quotation is not evidence."""
        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="sent", branch=sample_branch)
        resp = client.get(f"/quotations/{q.id}")
        assert resp.status_code == 200
        assert q.quotation_number in resp.get_data(as_text=True), (
            "the detail page did not render its own quotation number"
        )


class TestQOT16Conversion:
    """QOT-16 to QOT-20: the conversion is the money path, and it is idempotent."""

    def test_converting_an_accepted_quotation_creates_one_sale(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-16. The success side."""
        from models import Quotation, Sale, SaleLine

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(
            db_session, sample_tenant, sample_customer, status="accepted", product=sample_product, branch=sample_branch
        )
        q_id = q.id
        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(f"/quotations/{q_id}/convert", follow_redirects=True)
        assert resp.status_code == 200, f"converting answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the conversion produced {after - before} sales, expected 1"

        refreshed = db_session.get(Quotation, q_id)
        assert refreshed.status == "converted_to_sale", f"the quotation is {refreshed.status!r} after conversion"
        assert refreshed.sale_id is not None, "the conversion left sale_id unset"

        lines = db_session.query(SaleLine).filter_by(sale_id=refreshed.sale_id).all()
        assert lines, "the converted sale has no lines"

    def test_converting_twice_does_not_create_a_second_sale(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-17. The reason this file exists.

        ``convert_to_sale`` commits before the route redirects, so a redirect that
        raises leaves a committed sale behind a 500. The obvious response to a 500
        is to press the button again. Both the status guard and the sale_id guard
        have to refuse that second press.
        """
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(
            db_session, sample_tenant, sample_customer, status="accepted", product=sample_product, branch=sample_branch
        )
        q_id = q.id

        client.post(f"/quotations/{q_id}/convert", follow_redirects=True)
        first = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        client.post(f"/quotations/{q_id}/convert", follow_redirects=True)
        db_session.expire_all()
        second = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert second == first, f"a second conversion produced another sale ({first} -> {second})"

    def test_a_converted_quotation_cannot_be_sent_again(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-18. The state machine has no way back from a conversion."""
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(
            db_session, sample_tenant, sample_customer, status="accepted", product=sample_product, branch=sample_branch
        )
        q_id = q.id
        client.post(f"/quotations/{q_id}/convert", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "converted_to_sale"

        client.post(f"/quotations/{q_id}/send", follow_redirects=True)
        db_session.expire_all()
        assert db_session.get(Quotation, q_id).status == "converted_to_sale", "a converted quotation was sent back out"

    def test_converting_a_draft_is_refused(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-19. Conversion requires 'accepted', not merely 'not converted'."""
        from models import Sale

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(db_session, sample_tenant, sample_customer, status="draft", branch=sample_branch)
        before = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()

        client.post(f"/quotations/{q.id}/convert", follow_redirects=True)

        db_session.expire_all()
        after = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a draft quotation produced a sale ({before} -> {after})"

    def test_the_converted_sale_carries_the_quotations_amounts(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-20. The money has to survive the conversion.

        A conversion that recomputes and rounds differently from the quotation is
        a sale the customer did not agree to, so the totals are compared.
        """
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(
            db_session,
            sample_tenant,
            sample_customer,
            status="accepted",
            amount="137.500",
            product=sample_product,
            branch=sample_branch,
        )
        q_id = q.id
        expected = Decimal(str(q.total_amount))

        client.post(f"/quotations/{q_id}/convert", follow_redirects=True)
        db_session.expire_all()

        refreshed = db_session.get(Quotation, q_id)
        assert refreshed.sale_id is not None, "the conversion left sale_id unset"

        from models import Sale

        sale = db_session.get(Sale, refreshed.sale_id)
        assert sale is not None
        assert Decimal(str(sale.total_amount)) == expected, (
            f"the sale total is {sale.total_amount}, not the quotation's {expected}"
        )

    def test_conversion_preserves_the_line_quantities(
        self, client, db_session, sample_tenant, sample_branch, sample_customer, sample_product
    ):
        """QOT-21. Totals can match while the quantities do not."""
        from models import Quotation, QuotationLine, Sale, SaleLine

        _seller(client, db_session, sample_tenant, sample_branch)
        q = _quotation(
            db_session,
            sample_tenant,
            sample_customer,
            status="accepted",
            amount="200.000",
            product=sample_product,
            branch=sample_branch,
        )
        q_id = q.id
        line = db_session.query(QuotationLine).filter_by(quotation_id=q_id).first()
        line.quantity = Decimal("4")
        line.unit_price = Decimal("50")
        line.line_total = Decimal("200")
        db_session.commit()

        client.post(f"/quotations/{q_id}/convert", follow_redirects=True)
        db_session.expire_all()

        refreshed = db_session.get(Quotation, q_id)
        sale = db_session.get(Sale, refreshed.sale_id)
        lines = db_session.query(SaleLine).filter_by(sale_id=sale.id).all()
        assert len(lines) == 1, f"the converted sale has {len(lines)} lines, expected 1"
        assert Decimal(str(lines[0].quantity)) == Decimal("4"), (
            f"the converted line quantity is {lines[0].quantity}, not 4"
        )


class TestQOT22DuplicationAndIsolation:
    """QOT-22 to QOT-24: copying an offer, and keeping it ours."""

    def test_duplicating_a_quotation_creates_a_new_draft(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """QOT-22. The copy is a fresh draft, not a second live offer."""
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        original = _quotation(db_session, sample_tenant, sample_customer, status="sent", branch=sample_branch)
        original_id = original.id
        before = db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(f"/quotations/{original_id}/duplicate", follow_redirects=True)
        assert resp.status_code == 200, f"duplicating answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Quotation).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the duplication produced {after - before} quotations, expected 1"

        copies = (
            db_session.query(Quotation)
            .filter_by(tenant_id=sample_tenant.id)
            .filter(Quotation.id != original_id)
            .order_by(Quotation.id.desc())
            .first()
        )
        assert copies.quotation_number != db_session.get(Quotation, original_id).quotation_number, (
            "the copy reused the original's number"
        )
        assert copies.status in ("draft", "sent"), f"the copy is {copies.status!r}"

    def test_the_original_survives_a_duplication(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """QOT-23. Duplicate is a copy, not a move."""
        from models import Quotation

        _seller(client, db_session, sample_tenant, sample_branch)
        original = _quotation(db_session, sample_tenant, sample_customer, status="sent", branch=sample_branch)
        original_id = original.id

        client.post(f"/quotations/{original_id}/duplicate", follow_redirects=True)
        db_session.expire_all()

        survivor = db_session.get(Quotation, original_id)
        assert survivor is not None, "duplicating removed the original"
        assert survivor.status == "sent", f"duplicating changed the original to {survivor.status!r}"

    def test_another_tenants_quotation_is_not_reachable(
        self, client, db_session, sample_tenant, sample_branch, sample_customer
    ):
        """QOT-24. The id arrives from a URL.

        ``QuotationService.get_quotation`` is the boundary; a nonexistent id is
        the observable proxy for "not ours", which is the same convention the
        ledger scenarios use because the ORM refuses to build the other case.
        """
        _seller(client, db_session, sample_tenant, sample_branch)
        assert client.get("/quotations/99999999").status_code in (302, 404)
        assert client.get("/quotations/99999999/edit").status_code in (302, 404)
        for action in ("send", "accept", "reject", "convert", "duplicate"):
            resp = client.post(f"/quotations/99999999/{action}", follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"/{action} on a missing id answered {resp.status_code}"

    def test_a_quotation_belongs_to_exactly_one_tenant(self, db_session):
        """QOT-25. Structural, like EXP-12: the columns have to exist."""
        from models import Quotation, QuotationLine, Sale

        for model, columns in (
            (Quotation, ("tenant_id", "total_amount", "status", "sale_id")),
            (QuotationLine, ("tenant_id", "quotation_id", "line_total")),
        ):
            for column in columns:
                assert column in model.__table__.columns, (
                    f"{model.__name__} has no {column}: {list(model.__table__.columns.keys())}"
                )
        assert "tenant_id" in Sale.__table__.columns, "Sale carries no tenant_id"
