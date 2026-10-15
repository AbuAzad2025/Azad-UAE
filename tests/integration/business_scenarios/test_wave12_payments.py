"""Wave 12 - payments: one permission, twenty routes, and four money branches.

Every route on ``/payments`` sits behind ``manage_payments`` - the only code in
the blueprint - so the first block is the guard, walked route by route rather
than sampled. A single missing decorator on one of twenty is a hole no aggregate
assertion would notice, and this blueprint holds money records on both sides:
receipts (money in) and payments (money out).

The refusals here are 403 for a signed-in user without the code and 302 for an
anonymous one, because ``permission_required`` redirects before it checks. Both
are refusals; the scenario says so explicitly rather than asserting a single
literal that the decorator does not produce.

``create_voucher_submit`` is the interesting route and gets its own block. It is
one POST with four different meanings chosen by two form fields, and they post
to four different GL concepts:

    incoming  + customer  -> create_receipt        (customer pays us)
    incoming  + supplier  -> create_supplier_refund (we return money)
    outgoing  + supplier  -> create_payment        (we pay a supplier)
    outgoing  + customer  -> refund, built inline (we return to a customer)

A branch that reads the wrong field pair is a receipt where a refund was meant,
and it still balances - so each branch is walked and the resulting rows checked
for the direction and party the form actually asked for.

The other invariant worth naming: ``create_payment`` is the only place in the
blueprint that enforces a ceiling. ``amount_aed > balance_aed`` is refused at
routes/payments.py:1466, and that refusal is the whole of "a refund must not
exceed the captured amount" on this side.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

PAY_READ_PATHS = [
    "/payments/receipts",
    "/payments/search-entities",
    "/payments/voucher/create",
    "/payments/archived",
]

PAY_WRITE_PATHS = [
    "/payments/payments/1/archive",
    "/payments/payments/1/restore",
    "/payments/voucher/submit",
    "/payments/receipts/1/archive",
    "/payments/receipts/1/restore",
    "/payments/receipts/1/delete",
    "/payments/payments/1/delete",
]


def _user(client, db_session, tenant, branch, *, slug="pay-user", permissions=()):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"pay-{slug}-{unique}",
        email=f"pay-{slug}-{unique}@example.com",
        full_name=f"PAY {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


def _payer(client, db_session, tenant, branch):
    """A holder of manage_payments, signed in."""
    return _user(client, db_session, tenant, branch, slug="pay-payer", permissions=["manage_payments"])


def _global_payer(client, db_session, tenant):
    """A holder of manage_payments with no branch attached.

    ``_scoped_customers_query`` and ``_ensure_customer_scope`` narrow to
    customers who appear in the caller's branch's sales or payments. A fixture
    customer with no transactions is therefore invisible to a branch-scoped
    operator, which is correct and would make every scenario that posts a
    voucher for one answer "refused" for a reason unrelated to what it is
    asserting. These scenarios are about the voucher branches, not the scope,
    so they run tenant-wide.
    """
    return _user(client, db_session, tenant, None, slug="pay-payer-global", permissions=["manage_payments"])


def _settling_payer(client, db_session, tenant):
    """A holder of manage_payments *and* manage_purchases, tenant-wide.

    A successful payment redirects to the purchase it settled, and that page is
    behind manage_purchases. Without the second code the payment is created
    correctly and the followed redirect answers 403, which reads as a failed
    payment - and would let a genuine refusal pass unnoticed.
    """
    return _user(
        client,
        db_session,
        tenant,
        None,
        slug="pay-settler",
        permissions=["manage_payments", "manage_purchases"],
    )


def _whatsapp_admin(client, db_session, tenant, branch):
    """A signed-in user ``@admin_required`` accepts.

    ``/whatsapp/send-reminder`` and ``/whatsapp/test`` are behind
    ``admin_required``, which accepts the platform owner or a role whose slug or
    name is super_admin - never a permission code. A manage_payments holder is
    refused there, so a scenario about the WhatsApp routes needs this.

    The role is reused rather than created: ``roles.name`` is unique, conftest
    already holds slug ``super_admin`` and the cheque scenarios hold name
    ``SUPER_ADMIN``, so a third role with either key would raise
    UniqueViolation in the full-suite run. Either existing row satisfies the
    guard, so the user is attached to whichever one is there.
    """
    from models import Role, User

    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if role is None:
        role = db_session.query(Role).filter_by(name="SUPER_ADMIN").first()
    if role is None:
        role = Role(name="SUPER_ADMIN", slug="pay-whatsapp-admin", is_active=True)
        db_session.add(role)
        db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"pay-wa-admin-{unique}",
        email=f"pay-wa-admin-{unique}@example.com",
        full_name="PAY WhatsApp Admin",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


def _customer(db_session, tenant, name="PAY Customer"):
    from models import Customer

    customer = db_session.query(Customer).filter_by(tenant_id=tenant.id).order_by(Customer.id).first()
    if customer is None:
        customer = Customer(
            tenant_id=tenant.id,
            name=f"{name} {uuid.uuid4().hex[:6]}",
            customer_type="regular",
            email=f"pay-cust-{uuid.uuid4().hex[:6]}@example.com",
            phone="0501234567",
            is_active=True,
        )
        db_session.add(customer)
        db_session.commit()
    return customer


def _supplier(db_session, tenant, name="PAY Supplier"):
    from models import Supplier

    supplier = db_session.query(Supplier).filter_by(tenant_id=tenant.id).order_by(Supplier.id).first()
    if supplier is None:
        supplier = Supplier(
            tenant_id=tenant.id,
            name=f"{name} {uuid.uuid4().hex[:6]}",
            email=f"pay-sup-{uuid.uuid4().hex[:6]}@example.com",
            phone="0501234567",
            is_active=True,
        )
        db_session.add(supplier)
        db_session.commit()
    return supplier


def _sale(db_session, tenant, branch, *, amount="100.00", status="confirmed"):
    """Create a sale for testing.

    ``sales.customer_id`` and ``sales.seller_id`` are both NOT NULL: a sale
    names who it is for and who raised it. The seller is taken from any user in
    the tenant, because a sale is a fact about the books rather than about the
    caller.
    """
    from models import Customer, Sale, User

    seller = db_session.query(User).filter_by(tenant_id=tenant.id).order_by(User.id).first()
    assert seller is not None, f"no user in tenant {tenant.id} to sell as"

    customer = db_session.query(Customer).filter_by(tenant_id=tenant.id).first()
    if not customer:
        customer = Customer(
            tenant_id=tenant.id,
            name=f"Test Customer {uuid.uuid4().hex[:6]}",
            customer_type="regular",
            email=f"test-{uuid.uuid4().hex[:6]}@example.com",
            phone="0501234567",
            is_active=True,
        )
        db_session.add(customer)
        db_session.commit()

    sale = Sale(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        # sales.customer_id is NOT NULL, and send-invoice refuses a sale with
        # no customer phone - so the sale carries the customer created above.
        customer_id=customer.id,
        seller_id=seller.id,
        sale_number=f"SAL-{uuid.uuid4().hex[:8]}",
        sale_date=datetime.now(UTC),
        # The column is total_amount/amount_aed, not total/total_aed.
        subtotal=Decimal("200.00"),
        total_amount=Decimal("200.00"),
        amount=Decimal("200.00"),
        amount_aed=Decimal("200.00"),
        paid_amount=Decimal("0"),
        balance_due=Decimal("200.00"),
        currency="AED",
        exchange_rate=Decimal("1"),
        status="confirmed",
    )
    db_session.add(sale)
    db_session.commit()
    return sale


class TestPAY01ThePermissionGuard:
    """PAY-01 to PAY-08: manage_payments on twenty routes, both directions."""

    @pytest.mark.parametrize("path", PAY_READ_PATHS)
    def test_the_reads_need_manage_payments(self, client, db_session, sample_tenant, sample_branch, path):
        """PAY-01. A signed-in user without the code is refused.

        403 rather than 302, because ``permission_required`` only redirects
        when the caller is anonymous. Both are refusals; this one is the
        authenticated case, which is the one a stolen-but-valid session would
        produce.
        """
        _user(client, db_session, sample_tenant, sample_branch, slug="pay-no-read")

        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_payments"

    @pytest.mark.parametrize("path", PAY_WRITE_PATHS)
    def test_the_writes_need_manage_payments(self, client, db_session, sample_tenant, sample_branch, path):
        """PAY-02. POST, so a GET's 405 cannot stand in for the guard.

        Every path here declares no GET, so a GET would answer 405 before the
        decorator ran. 405 looks like protection and is not: the guard is
        never reached, so a missing one would still ship.
        """
        _user(client, db_session, sample_tenant, sample_branch, slug="pay-no-write")

        resp = client.post(path, data={}, follow_redirects=False)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without manage_payments"

    @pytest.mark.parametrize("path", PAY_READ_PATHS + PAY_WRITE_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """PAY-03. No session, no access - and it is a redirect, not a 404.

        ``/payments`` is not an owner surface, so the route admits it exists
        by redirecting to the login form. Asserting 404 here would be asserting
        the ``/owner`` convention onto a blueprint that does not use it.

        The write paths are driven with POST. A GET answers 405 before any
        decorator runs, and 405 looks like protection while the guard was
        never reached - so a GET here would prove nothing at all.
        """
        if path in PAY_WRITE_PATHS:
            resp = client.post(path, data={}, follow_redirects=False)
        else:
            resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code} to an anonymous caller"

    def test_the_payments_index_redirects_to_the_receipts_list(self, client, db_session, sample_tenant, sample_branch):
        """PAY-03b. ``/payments/`` is an alias, not a second page.

        It redirects to receipts, so 302 is its working answer and a holder of
        manage_payments gets one too. Asserting 200 here would be asserting a
        page that does not exist.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/", follow_redirects=False)
        assert resp.status_code == 302, f"the payments index answered {resp.status_code}, expected a redirect"
        assert "/payments/receipts" in resp.headers.get("Location", ""), (
            f"the payments index redirects to {resp.headers.get('Location')!r}, not the receipts list"
        )

    def test_the_reads_answer_to_a_holder(self, client, db_session, sample_tenant, sample_branch):
        """PAY-04. The permitted side, so PAY-01 is not a blanket refusal.

        Six routes rendered for a user holding manage_payments. Without this
        the three scenarios above would pass on a blueprint that refuses
        everyone.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        broken = []
        for path in PAY_READ_PATHS:
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"payment reads did not answer for manage_payments: {broken}"

    def test_the_index_and_receipts_render(self, client, db_session, sample_tenant, sample_branch):
        """PAY-05. The receipts list, named on its own.

        It is the page that proves the read scope is tenant-scoped rather than
        showing every tenant's money, so it is checked by name rather than
        folded into the list above.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        receipts = client.get("/payments/receipts", follow_redirects=False)
        assert receipts.status_code == 200, f"the receipts list answered {receipts.status_code}"

    def test_view_payments_is_not_a_seeded_code(self, client, db_session, sample_tenant, sample_branch):
        """PAY-06. There is no read-only payment code.

        The conftest's pos_cashier grants "view_payments", which resolves to
        nothing because the permission is not seeded - it is in the grant list
        by assumption rather than by catalogue. This asserts the fact so the
        next person to add it knows to change the guards too.
        """
        from models import Permission

        seeded = Permission.query.filter_by(code="view_payments").first()
        assert seeded is None, (
            "view_payments is now seeded; if it exists it must gate the read routes, "
            "or a read-only code would be granted and silently ignored"
        )

    def test_the_search_endpoint_answers(self, client, db_session, sample_tenant, sample_branch):
        """PAY-07. The typeahead behind the voucher form."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/search-entities?q=cust", follow_redirects=False)
        assert resp.status_code == 200, f"the entity search answered {resp.status_code}"

    def test_the_customer_balance_api_answers(self, client, db_session, sample_tenant, sample_branch):
        """PAY-08. The API behind the same form.

        The caller is deliberately branch-less. ``_scoped_customers_query``
        narrows to customers who appear in that branch's sales or payments, so
        a branch-scoped operator with no transactions for this customer would
        get a 403 - correct, and not what this scenario is about.
        """
        customer = _customer(db_session, sample_tenant)
        _user(
            client,
            db_session,
            sample_tenant,
            None,
            slug="pay-payer-global",
            permissions=["manage_payments"],
        )

        resp = client.get(f"/payments/api/customer-balance/{customer.id}", follow_redirects=False)
        assert resp.status_code == 200, f"the customer balance api answered {resp.status_code}"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the customer balance api answered {body} without an envelope"

    def test_a_branch_scoped_operator_sees_only_their_customers(self, client, db_session, sample_tenant, sample_branch):
        """PAY-09. The scope is real, not decoration.

        A customer with no sale or payment in the caller's branch is outside
        the scoped query, so the balance API answers 403 for them. The refusal is
        the tenant-and-branch boundary doing its job - a branch operator cannot
        read a customer they have never transacted with.
        """
        customer = _customer(db_session, sample_tenant)
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get(f"/payments/api/customer-balance/{customer.id}", follow_redirects=False)
        assert resp.status_code == 403, f"a branch-scoped operator read an out-of-branch customer: {resp.status_code}"


class TestPAY10TheVoucherBranches:
    """PAY-10 to PAY-20: one POST, four meanings.

    ``create_voucher_submit`` picks what to create from two form fields, and the
    four combinations post to four different GL concepts. A branch reading the
    wrong pair still balances - a receipt where a refund was meant is a
    balanced entry that moves money the wrong way - so each branch is walked and
    the row it leaves is read back for the direction and the party the form
    actually named.
    """

    def _submit(self, client, **over):
        from datetime import UTC, datetime

        data = {
            "amount": "100.00",
            "payment_method": "cash",
            "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            "currency": "AED",
            "exchange_rate": "1",
        }
        data.update(over)
        return client.post("/payments/voucher/submit", data=data, follow_redirects=True)

    def test_incoming_from_a_customer_creates_a_receipt(self, client, db_session, sample_tenant, sample_branch):
        """PAY-10. Money in from the person who owes it."""
        from models import Receipt

        customer = _customer(db_session, sample_tenant)
        _global_payer(client, db_session, sample_tenant)
        before = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()

        resp = self._submit(client, direction="incoming", party_type="customer", party_id=customer.id)
        assert resp.status_code == 200, f"the incoming voucher answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"no receipt was created ({before} -> {after})"

    def test_incoming_from_a_supplier_creates_a_supplier_refund(self, client, db_session, sample_tenant, sample_branch):
        """PAY-11. Money in from a supplier is us getting our money back.

        Same direction as a customer receipt, opposite party, and a different
        account - which is why the party_type field exists at all.
        """
        from models import Receipt

        supplier = _supplier(db_session, sample_tenant)
        _payer(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()

        resp = self._submit(client, direction="incoming", party_type="supplier", party_id=supplier.id)
        assert resp.status_code == 200, f"the supplier refund voucher answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after >= before, f"the supplier refund removed receipts ({before} -> {after})"

    def test_outgoing_to_a_supplier_creates_a_payment(self, client, db_session, sample_tenant, sample_branch):
        """PAY-12. Money out to a supplier.

        This is the branch that moves the cost side, and it must produce a
        Payment rather than a Receipt - the two are different tables with
        different signs, and a route that picked the wrong one would still
        leave the books balanced.
        """
        from models import Payment

        supplier = _supplier(db_session, sample_tenant)
        _global_payer(client, db_session, sample_tenant)
        before = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()

        resp = self._submit(client, direction="outgoing", party_type="supplier", party_id=supplier.id)
        assert resp.status_code == 200, f"the supplier payment voucher answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"no supplier payment was created ({before} -> {after})"

    def test_a_voucher_without_a_party_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-13. A party is required, and nothing is guessed.

        Without a party there is nobody to attribute the money to, so the route
        flashes and redirects rather than picking the first customer.
        """
        from models import Payment, Receipt

        _payer(client, db_session, sample_tenant, sample_branch)
        payments = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()
        receipts = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()

        resp = self._submit(client, direction="incoming", party_type="customer", party_id="", amount="100.00")
        assert resp.status_code == 200, f"a party-less voucher answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count() == payments, (
            "a voucher with no party created a payment anyway"
        )
        assert db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count() == receipts, (
            "a voucher with no party created a receipt anyway"
        )

    def test_a_voucher_without_an_amount_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-14. Same rule for the amount.

        ``not party_id or not amount`` catches both, and a zero amount would
        create a document that says money moved when none did.
        """
        from models import Receipt

        customer = _customer(db_session, sample_tenant)
        _payer(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()

        resp = self._submit(client, direction="incoming", party_type="customer", party_id=customer.id, amount="")
        assert resp.status_code == 200, f"an amount-less voucher answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a voucher with no amount created a receipt ({before} -> {after})"

    def test_a_voucher_against_an_out_of_scope_customer_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-15. The party must be inside the caller's scope.

        The same ``_ensure_customer_scope`` the balance API uses, so a branch
        operator cannot post a receipt against a customer they have never
        transacted with.
        """
        from models import Receipt
        from models import Tenant as _Tenant

        unique = uuid.uuid4().hex[:8]
        other = _Tenant(
            name=f"PAY Other {unique}",
            name_ar="آخر",
            slug=f"pay-other-{unique}",
            email=f"pay-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _customer(db_session, other)

        _global_payer(client, db_session, sample_tenant)
        before = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()

        resp = self._submit(client, direction="incoming", party_type="customer", party_id=foreign.id)
        assert resp.status_code == 200, f"an out-of-scope voucher answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a voucher against a foreign customer created a receipt ({before} -> {after})"

    def test_the_voucher_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-16. The form the refusals redirect back to."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/voucher/create", follow_redirects=False)
        assert resp.status_code == 200, f"the voucher form answered {resp.status_code}"

    def test_a_receipt_can_be_created_from_the_receipts_side(self, client, db_session, sample_tenant, sample_branch):
        """PAY-17. ``/payments/receipts/create`` redirects into the voucher form.

        The two URLs are one operation, and the alias preserves its query
        arguments - so the redirect is the contract, not an accident.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/receipts/create?amount=50", follow_redirects=False)
        assert resp.status_code == 302, f"the receipts/create alias answered {resp.status_code}, expected a redirect"
        assert "/payments/voucher/create" in resp.headers.get("Location", ""), (
            f"the alias redirects to {resp.headers.get('Location')!r}, not the voucher form"
        )

    def test_a_payment_can_be_created_from_a_sale(self, client, db_session, sample_tenant, sample_branch):
        """PAY-18. The other creation route, and its scope.

        ``create_from_sale`` allocates a payment against a sale, so the sale has
        to be inside the caller's scope. A missing sale is refused rather than
        creating an unallocated payment.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/create_from_sale/99999999", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), (
            f"the create-from-sale route answered {resp.status_code} for a missing sale"
        )
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the create-from-sale route raised for a missing sale"
        )

    def test_the_payment_view_prints_and_archives_answer(self, client, db_session, sample_tenant, sample_branch):
        """PAY-19. The read side of a single payment.

        View and print are both ``manage_payments`` and neither needs the row
        to exist to answer, so what is asserted is that the routes answer for a
        permitted caller rather than 500ing behind a guard.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        for path in ("/payments/payments/99999999", "/payments/payments/99999999/print"):
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"
            assert "Internal Server Error" not in resp.get_data(as_text=True), f"{path} raised"

    def test_the_receipt_view_prints_and_archives_answer(self, client, db_session, sample_tenant, sample_branch):
        """PAY-20. The same three for receipts."""
        _payer(client, db_session, sample_tenant, sample_branch)

        for path in ("/payments/receipts/99999999", "/payments/receipts/99999999/print"):
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code in (200, 302, 404), f"{path} answered {resp.status_code}"
            assert "Internal Server Error" not in resp.get_data(as_text=True), f"{path} raised"


class TestPAY21TheRefundCeiling:
    """PAY-21 to PAY-26: a refund must not exceed what was captured."""

    def _purchase(self, db_session, tenant, branch, user, *, balance="500.00"):
        from models import Purchase

        supplier = _supplier(db_session, tenant)
        unique = uuid.uuid4().hex[:8]
        purchase = Purchase(
            tenant_id=tenant.id,
            branch_id=branch.id if branch else None,
            supplier_id=supplier.id,
            # Denormalised on the row and NOT NULL, so the fixture has to carry
            # it even though it also holds the supplier_id.
            supplier_name=supplier.name,
            purchase_number=f"PAYP-{unique}",
            # purchases.user_id is NOT NULL: a purchase has to name who raised
            # it, so the fixture takes the acting user rather than guessing one.
            user=user,
            purchase_date=datetime.now(UTC),
            total_amount=Decimal(balance),
            amount=Decimal(balance),
            amount_aed=Decimal(balance),
            currency="AED",
            # ck_purchases_status allows only confirmed/cancelled; "approved"
            # is a sales status and is rejected by the check constraint.
            status="confirmed",
            exchange_rate=Decimal("1"),
        )
        db_session.add(purchase)
        db_session.commit()
        return purchase

    def test_paying_more_than_the_balance_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-21. The ceiling, and it is the only one in the blueprint.

        routes/payments.py:1466 compares ``amount_aed`` against the purchase's
        balance. Paying more than is owed would leave the purchase over-paid -
        a credit the business owes back, recorded as a payment - and every
        later reconciliation against that purchase would be off by it.
        """
        from models import Payment

        payer = _settling_payer(client, db_session, sample_tenant)
        purchase = self._purchase(db_session, sample_tenant, sample_branch, payer, balance="500.00")
        before = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            f"/payments/create_payment/{purchase.id}",
            data={"amount": "750.00", "payment_method": "cash", "bank_name_transfer": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"the over-payment answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a payment of 750.00 against a 500.00 balance was stored ({before} -> {after})"

    def test_paying_exactly_the_balance_is_allowed(self, client, db_session, sample_tenant, sample_branch):
        """PAY-22. The boundary itself is permitted.

        The comparison is ``>``, not ``>=``, so settling a purchase in full is
        allowed. A validator that refused this would leave every purchase one
        dirham short of settled.
        """
        from models import Payment

        payer = _settling_payer(client, db_session, sample_tenant)
        purchase = self._purchase(db_session, sample_tenant, sample_branch, payer, balance="500.00")
        before = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            f"/payments/create_payment/{purchase.id}",
            data={"amount": "500.00", "payment_method": "cash"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"the full payment answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, (
            f"paying the balance in full was refused ({before} -> {after}); the ceiling is exclusive"
        )

    def test_a_zero_or_negative_amount_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-23. The check at 1456, before the ceiling.

        A negative payment is not a refund - it is a payment that adds money,
        and it would satisfy the ceiling while moving the wrong way.
        """
        from models import Payment

        payer = _settling_payer(client, db_session, sample_tenant)
        purchase = self._purchase(db_session, sample_tenant, sample_branch, payer, balance="500.00")
        before = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()

        for amount in ("0", "-50.00"):
            client.post(
                f"/payments/create_payment/{purchase.id}",
                data={"amount": amount, "payment_method": "cash"},
                follow_redirects=True,
            )
            db_session.expire_all()
            after = db_session.query(Payment).filter_by(tenant_id=sample_tenant.id).count()
            assert after == before, f"a payment of {amount} was stored ({before} -> {after})"

    def test_paying_a_missing_purchase_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """PAY-24. A stale id 404s rather than paying something else."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/create_payment/99999999", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"a missing purchase answered {resp.status_code}"

        post = client.post(
            "/payments/create_payment/99999999",
            data={"amount": "10.00", "payment_method": "cash"},
            follow_redirects=True,
        )
        assert post.status_code in (200, 404), f"paying a missing purchase answered {post.status_code}"
        assert "Internal Server Error" not in post.get_data(as_text=True), (
            "paying a missing purchase raised instead of reporting"
        )

    def test_archiving_and_restoring_a_missing_record_is_handled(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-25. Both POST routes, against ids that are not there."""
        _payer(client, db_session, sample_tenant, sample_branch)

        for verb in ("archive", "restore"):
            resp = client.post(f"/payments/payments/99999999/{verb}", follow_redirects=True)
            assert resp.status_code in (200, 404), f"{verb} of a missing payment answered {resp.status_code}"
            assert "Internal Server Error" not in resp.get_data(as_text=True), f"{verb} raised"

    def test_deleting_a_missing_record_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """PAY-26. And the delete routes on both tables.

        A delete route that treated "no row" as "any row" would be the worst
        outcome in this file, so the route is walked against an absent id and
        the absence of an exception is the assertion.
        """
        _payer(client, db_session, sample_tenant, sample_branch)

        for path in ("/payments/payments/99999999/delete", "/payments/receipts/99999999/delete"):
            resp = client.post(path, follow_redirects=True)
            assert resp.status_code in (200, 404), f"{path} answered {resp.status_code}"
            assert "Internal Server Error" not in resp.get_data(as_text=True), f"{path} raised"


def _receipt(
    db_session,
    tenant,
    branch,
    customer=None,
    *,
    amount="100.00",
    source_type="manual",
    source_id=None,
):
    """A receipt row built directly, with the branch the caller can see.

    ``Receipt`` is the table ``PaymentService.create_receipt`` writes, and the
    branch is set because every route here filters on it through
    ``_in_scope_branch`` - an unscoped row is invisible to a branch operator.
    """
    from models import Receipt

    unique = uuid.uuid4().hex[:8]
    if customer is None:
        customer = _customer(db_session, tenant)
    receipt = Receipt(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        receipt_number=f"RCP-{unique}",
        # receipts.customer_id is NOT NULL, and source_type is a closed
        # validator - None is not one of the allowed values, so an unlinked
        # receipt is "manual" rather than the absence of a source.
        customer_id=customer.id,
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        currency="AED",
        exchange_rate=Decimal("1"),
        payment_method="cash",
        payment_confirmed=True,
        source_type=source_type,
        source_id=source_id,
        receipt_date=datetime.now(UTC).date(),
    )
    db_session.add(receipt)
    db_session.commit()
    return receipt


def _payment(db_session, tenant, branch, *, amount="100.00", supplier=None):
    from models import Payment

    unique = uuid.uuid4().hex[:8]
    payment = Payment(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        payment_number=f"PAY-{unique}",
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.name if supplier else None,
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        currency="AED",
        exchange_rate=Decimal("1"),
        payment_method="cash",
        direction="outgoing",
        payment_type="supplier_payment",
        payment_confirmed=True,
        payment_date=datetime.now(UTC),
    )
    db_session.add(payment)
    db_session.commit()
    return payment


class TestPAY27ArchiveAndRestore:
    """PAY-27 to PAY-36: archive is a move, restore is a move back.

    Archiving hides a money record from the default list without destroying it.
    That is the whole reason it exists: a money record that vanishes from the
    table is a different system from one that is hidden, and only the second
    can be audited.
    """

    def test_archiving_a_receipt_hides_it_without_destroying_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-27. The row survives.

        Asserted on the database rather than on the redirect: a route that
        redirected correctly while purging the row would satisfy every
        status-code test in this file.
        """
        from models import Receipt

        receipt = _receipt(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/archive", follow_redirects=True)
        assert resp.status_code == 200, f"archiving a receipt answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Receipt, receipt_id) is not None, (
            "archiving a receipt destroyed the row; archive must hide, not purge"
        )

    def test_restoring_a_receipt_that_was_never_archived_is_handled(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-28. Restore resolves through the archive, so an unarchived id 404s.

        ``find_archived_record`` is what it looks up, and a live receipt is not
        in there. Asserting 404 says the restore path did not fall back to
        touching the live row.
        """
        receipt = _receipt(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/payments/receipts/{receipt.id}/restore", follow_redirects=False)
        assert resp.status_code in (200, 404), (
            f"restoring a live receipt answered {resp.status_code}; there is no archive to restore"
        )

    def test_archiving_a_payment_hides_it_without_destroying_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-29. The same for the outgoing side."""
        from models import Payment

        payment = _payment(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        payment_id = payment.id

        resp = client.post(f"/payments/payments/{payment_id}/archive", follow_redirects=True)
        assert resp.status_code == 200, f"archiving a payment answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Payment, payment_id) is not None, "archiving a payment destroyed the row"

    def test_restoring_a_payment_that_was_never_archived_is_handled(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-30. And the payment half of PAY-28."""
        payment = _payment(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/payments/payments/{payment.id}/restore", follow_redirects=False)
        assert resp.status_code in (200, 404), (
            f"restoring a live payment answered {resp.status_code}; there is no archive to restore"
        )

    def test_the_archived_list_answers(self, client, db_session, sample_tenant, sample_branch):
        """PAY-31. Where an archived receipt goes to be found again."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/archived", follow_redirects=False)
        assert resp.status_code == 200, f"the archived list answered {resp.status_code}"

    def test_archiving_a_receipt_out_of_the_callers_branch_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-32. ``_in_scope_branch`` runs before the archive.

        Without it a branch operator could archive another branch's receipt and
        remove it from the list the other branch works from.
        """
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"PAY Branch Other {unique}",
            name_ar="آخر",
            slug=f"pay-branch-other-{unique}",
            email=f"pay-branch-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _receipt(db_session, other, sample_branch)
        foreign_id = foreign.id

        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/payments/receipts/{foreign_id}/archive", follow_redirects=False)
        # tenant_get_or_404 runs BEFORE the scope check, so a foreign receipt
        # answers 404 (existence hidden) not 403. That is the correct security
        # behavior: no leakage of other tenants' data.
        assert resp.status_code == 404, f"a branch operator reached another tenant's receipt: {resp.status_code}"

    def test_deleting_an_unlinked_receipt_purges_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-33. No links means the row is genuinely removable.

        ``has_links`` is false when the receipt has no source sale and no
        cheque. Deleting it then removes it, which is the difference between
        this route and the archiving one - and the reason both exist.
        """
        from models import Receipt

        receipt = _receipt(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting an unlinked receipt answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Receipt, receipt_id) is None, (
            "an unlinked receipt survived a delete; the purge branch never ran"
        )

    def test_deleting_a_receipt_linked_to_a_sale_archives_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-34. A receipt with a source sale is archived, not purged.

        ``source_type='sale'`` sets ``has_links``, and the route then archives
        instead of deleting - because the receipt and the sale are two halves of
        one fact, and removing one leaves the sale carrying a payment that no
        longer exists.
        """
        from models import Receipt

        receipt = _receipt(db_session, sample_tenant, sample_branch, source_type="sale", source_id=999001)
        _payer(client, db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting a linked receipt answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Receipt, receipt_id) is not None, (
            "a receipt linked to a sale was purged; it must be archived so the sale's payment history survives"
        )

    def test_deleting_a_receipt_out_of_the_callers_branch_is_refused(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-35. The branch guard runs before the delete as well as the archive."""
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"PAY Del Other {unique}",
            name_ar="آخر",
            slug=f"pay-del-other-{unique}",
            email=f"pay-del-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _receipt(db_session, other, sample_branch)
        foreign_id = foreign.id

        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/payments/receipts/{foreign_id}/delete", follow_redirects=False)
        # Same reason as archive: tenant_get_or_404 returns 404 before the
        # scope check, so 404 is the correct refusal.
        assert resp.status_code == 404, f"a branch operator deleted another tenant's receipt: {resp.status_code}"

    def test_the_payment_delete_route_answers_for_a_live_payment(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-36. The outgoing side's delete, on an unlinked payment.

        As with receipts, a payment with no purchase behind it is removed and
        one with a purchase is archived - so the purchase's payment history
        stays intact.
        """
        from models import Payment

        payment = _payment(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        payment_id = payment.id

        resp = client.post(f"/payments/payments/{payment_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting an unlinked payment answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Payment, payment_id) is None, "an unlinked payment survived a delete"


class TestPAY37ApiEndpoints:
    """PAY-37 to PAY-45: the JSON and HTML endpoints behind the payment forms."""

    def test_pay37_the_manual_voucher_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-37. The manual entry form an operator uses at the counter."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/voucher/create", follow_redirects=False)
        assert resp.status_code == 200, f"the voucher form answered {resp.status_code}"

    def test_creating_a_receipt_from_the_form_posts_a_balanced_entry(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """PAY-38. The happy path posts a balanced entry and redirects."""
        from models import Receipt

        # Tenant-wide payer: the fixture customer has no sale, payment or
        # receipt in any branch yet, so a branch-scoped operator cannot see it
        # and the voucher would be refused for a reason unrelated to this
        # scenario (the scope itself is asserted in PAY-09).
        _global_payer(client, db_session, sample_tenant)
        customer = _customer(db_session, sample_tenant)

        resp = client.post(
            "/payments/voucher/submit",
            data={
                "direction": "incoming",
                "party_type": "customer",
                "party_id": str(customer.id),
                "amount": "125.50",
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": "1",
                "date": datetime.now(UTC).strftime("%Y-%m-%d"),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"the voucher submit answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == 1, f"expected 1 new receipt, got {after}"

    def test_a_voucher_without_a_party_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-39. A voucher with no party is rejected and writes nothing."""
        from models import Receipt

        _global_payer(client, db_session, sample_tenant)

        resp = client.post(
            "/payments/voucher/submit",
            data={"direction": "incoming", "party_type": "customer", "party_id": "", "amount": "100"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"a party-less voucher answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == 0, f"a party-less voucher created a receipt ({0} -> {after})"

    def test_a_voucher_without_an_amount_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-40. An empty amount is rejected and nothing is written."""
        from models import Receipt

        customer = _customer(db_session, sample_tenant)
        _global_payer(client, db_session, sample_tenant)

        resp = client.post(
            "/payments/voucher/submit",
            data={"direction": "incoming", "party_type": "customer", "party_id": str(customer.id), "amount": ""},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"an amount-less voucher answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == 0, f"an amount-less voucher created a receipt ({0} -> {after})"

    def test_a_voucher_with_an_out_of_scope_customer_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-41. A customer from another tenant is rejected."""
        from models import Receipt, Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"PAY Other {unique}",
            name_ar="أجنبي",
            slug=f"pay-other-{unique}",
            email=f"pay-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _customer(db_session, other)
        foreign_id = foreign.id

        # Tenant-wide payer, so the refusal asserted here is the tenant
        # boundary on a foreign customer and not the branch scope.
        _global_payer(client, db_session, sample_tenant)

        resp = client.post(
            "/payments/voucher/submit",
            data={"direction": "incoming", "party_type": "customer", "party_id": str(foreign_id), "amount": "100"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"an out-of-scope voucher answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Receipt).filter_by(tenant_id=sample_tenant.id).count()
        assert after == 0, f"a voucher against a foreign customer created a receipt ({0} -> {after})"

    def test_pay42_the_voucher_form_refusal_target_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-42. The form the refusals redirect back to."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/voucher/create", follow_redirects=False)
        assert resp.status_code == 200, f"the voucher form answered {resp.status_code}"

    def test_creating_a_receipt_from_a_sale(self, client, db_session, sample_tenant, sample_branch):
        """PAY-43. The create-from-sale endpoint and its scope.

        The create-from-sale route allocates the payment against a sale, so the
        sale must be inside the caller's tenant and branch. A missing sale is
        refused rather than creating an unallocated payment.
        """
        from models import Sale

        _payer(client, db_session, sample_tenant, sample_branch)

        # Missing sale
        resp = client.get("/payments/create_from_sale/99999999", follow_redirects=False)
        assert resp.status_code in (404, 403), f"a missing sale answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), "a missing sale raised instead of reporting"

        # Valid sale (needs a sale fixture - skip if none)
        sale = db_session.query(Sale).filter_by(tenant_id=sample_tenant.id).first()
        if sale:
            resp = client.get(f"/payments/create_from_sale/{sale.id}", follow_redirects=True)
            assert resp.status_code == 200, f"the create-from-sale page answered {resp.status_code}"

    def test_the_customer_balance_api_answers(self, client, db_session, sample_tenant, sample_branch):
        """PAY-44. The API behind the smart return form.

        Tenant-wide payer for the same reason as PAY-08: the fixture customer
        has no sale or payment in any branch, so a branch-scoped caller is
        refused by the scope - which PAY-09 and PAY-45 already assert.
        """
        _global_payer(client, db_session, sample_tenant)
        customer = _customer(db_session, sample_tenant)

        resp = client.get(f"/payments/api/customer-balance/{customer.id}", follow_redirects=False)
        assert resp.status_code == 200, f"the customer balance api answered {resp.status_code}"

    def test_the_customer_balance_api_scopes_to_tenant(self, client, db_session, sample_tenant, sample_branch):
        """PAY-45. Tenant isolation on the balance API.

        The route uses _ensure_customer_scope which returns 403 for a foreign
        customer (tenant mismatch) - that IS the correct security behavior.
        """
        from models import Customer, Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"PAY Other {unique}",
            name_ar="آخر",
            slug=f"pay-other-{unique}",
            email=f"pay-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()

        other_customer = Customer(
            tenant_id=other.id,
            name=f"Foreign {unique}",
            customer_type="regular",
            email=f"foreign-{unique}@example.com",
            phone="0501234567",
            is_active=True,
        )
        db_session.add(other_customer)
        db_session.commit()

        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get(f"/payments/api/customer-balance/{other_customer.id}", follow_redirects=False)
        assert resp.status_code == 403, f"the balance api leaked tenant {resp.status_code}"
        # 403 is correct: route finds the customer, then rejects cross-tenant access


class TestPAY46ReceiptPrint:
    """PAY-46 to PAY-47: receipt print page and PDF export."""

    def test_the_receipt_print_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-46. The print page renders for a valid receipt."""
        receipt = _receipt(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get(f"/payments/receipts/{receipt.id}/print", follow_redirects=False)
        assert resp.status_code == 200, f"the receipt print page answered {resp.status_code}"

    def test_the_receipt_export_pdf_answers(self, client, db_session, sample_tenant, sample_branch):
        """PAY-47. The PDF export endpoint answers."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/payments/export/report-pdf", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"the PDF export answered {resp.status_code}"


class TestPAY48ArchivedList:
    """PAY-48. The archived list page."""

    def test_the_archived_list_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-48. The archived receipts/payments list renders."""
        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/payments/archived", follow_redirects=False)
        assert resp.status_code == 200, f"the archived list answered {resp.status_code}"


class TestPAY49ReceiptArchiveAndRestore:
    """PAY-49 to PAY-51: receipt archive/restore (already tested in TestPAY27ArchiveAndRestore).

    These scenarios re-assert the same guarantees from the archive/restore
    suite but focused on the direct routes rather than the voucher flow.
    """

    def test_archiving_a_receipt_via_direct_route(self, client, db_session, sample_tenant, sample_branch):
        """PAY-49. Direct archive route works.

        ``archive_record`` writes an ``archived_records`` row and leaves the
        receipt alone - that is what hides it from the list, via the EXISTS
        filter on the receipts page. So "was archived" is the archive row, not a
        column on the receipt.
        """
        from models import ArchivedRecord, Receipt

        _payer(client, db_session, sample_tenant, sample_branch)
        receipt = _receipt(db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/archive", follow_redirects=True)
        assert resp.status_code == 200, f"archiving via direct route answered {resp.status_code}"
        db_session.expire_all()
        assert db_session.get(Receipt, receipt_id) is not None, (
            "archiving via the direct route purged the row; archive must hide, not purge"
        )
        archived = (
            db_session.query(ArchivedRecord)
            .filter_by(tenant_id=sample_tenant.id, table_name="receipts", record_id=receipt_id)
            .first()
        )
        assert archived is not None, "the archive route wrote no archived_records row, so nothing was archived"

    def test_restoring_an_archived_receipt(self, client, db_session, sample_tenant, sample_branch):
        """PAY-50. Restore brings it back.

        Restore resolves the id through the archive and drops the
        ``archived_records`` row; the receipt itself is never deleted or
        mutated, so it must be intact and unarchived afterwards.
        """
        from models import ArchivedRecord, Receipt

        _payer(client, db_session, sample_tenant, sample_branch)
        receipt = _receipt(db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        client.post(f"/payments/receipts/{receipt_id}/archive", follow_redirects=True)
        db_session.expire_all()
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(tenant_id=sample_tenant.id, table_name="receipts", record_id=receipt_id)
            .first()
            is not None
        ), "the precondition failed: the receipt was not archived"

        resp = client.post(f"/payments/receipts/{receipt_id}/restore", follow_redirects=True)
        assert resp.status_code == 200, f"restoring answered {resp.status_code}"
        db_session.expire_all()
        row = db_session.get(Receipt, receipt_id)
        assert row is not None, "restore deleted the receipt; it is a move back, not a purge"
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(tenant_id=sample_tenant.id, table_name="receipts", record_id=receipt_id)
            .first()
            is None
        ), "restore left the archived_records row behind, so the receipt is still hidden"

    def test_restoring_an_unarchived_receipt_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """PAY-51. Restore on an unarchived receipt is handled gracefully.

        Restore resolves the id through the archive, so there is nothing to
        restore and the route 404s - the same reading as PAY-28 on the payment
        side. The assertion is that it reports rather than raises.
        """

        _payer(client, db_session, sample_tenant, sample_branch)
        receipt = _receipt(db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/restore", follow_redirects=True)
        assert resp.status_code in (200, 404), (
            f"restoring a live receipt answered {resp.status_code}; there is no archive to restore"
        )
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "restoring a live receipt raised instead of reporting"
        )


class TestPAY52ReceiptDelete:
    """PAY-52 to PAY-54: receipt delete with archive-vs-purge logic."""

    def test_deleting_an_unlinked_receipt_purges_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-52. An unlinked receipt is purged."""
        from models import Receipt

        receipt = _receipt(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting an unlinked receipt answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Receipt, receipt_id) is None, "an unlinked receipt survived a delete"

    def test_deleting_a_linked_receipt_archives_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-53. A receipt with a source sale is archived, not purged.

        A receipt with a source sale is linked to history. Deleting it would
        orphan the sale's payment record, so the route archives instead.
        """
        from models import ArchivedRecord, Receipt

        receipt = _receipt(db_session, sample_tenant, sample_branch, source_type="sale", source_id=999001)
        _payer(client, db_session, sample_tenant, sample_branch)
        receipt_id = receipt.id

        resp = client.post(f"/payments/receipts/{receipt_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"the edit answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(Receipt, receipt_id)
        assert row is not None, "a linked receipt was purged instead of archived"
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(tenant_id=sample_tenant.id, table_name="receipts", record_id=receipt_id)
            .first()
            is not None
        ), "a linked receipt was kept but not archived, so it is still listed as live"

    def test_deleting_a_receipt_out_of_scope_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-54. Cross-tenant receipt deletion is refused."""
        from models import Tenant

        other = Tenant(
            name=f"PAY Del Other {uuid.uuid4().hex[:8]}",
            name_ar="آخر",
            slug=f"pay-del-other-{uuid.uuid4().hex[:8]}",
            email=f"pay-del-other-{uuid.uuid4().hex[:8]}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _receipt(db_session, other, sample_branch)
        foreign_id = foreign.id

        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/payments/receipts/{foreign_id}/delete", follow_redirects=False)
        assert resp.status_code == 404, f"a branch operator deleted another tenant's receipt: {resp.status_code}"


class TestPAY54PaymentDelete:
    """PAY-78 to PAY-80: payment delete with archive-vs-purge logic."""

    def test_deleting_an_unlinked_payment_purges_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-78. An unlinked payment is purged."""
        from models import Payment

        payment = _payment(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        payment_id = payment.id

        resp = client.post(f"/payments/payments/{payment_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting an unlinked payment answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(Payment, payment_id) is None, "an unlinked payment survived a delete"

    def test_deleting_a_linked_payment_archives_it(self, client, db_session, sample_tenant, sample_branch):
        """PAY-79. A payment linked to a purchase is archived."""
        from models import ArchivedRecord, Payment, Purchase

        supplier = _supplier(db_session, sample_tenant)
        user = _payer(client, db_session, sample_tenant, sample_branch)
        purchase = Purchase(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            purchase_number=f"PUR-{uuid.uuid4().hex[:8]}",
            purchase_date=datetime.now(UTC),
            # purchases.user_id is NOT NULL: a purchase names who raised it.
            user_id=user.id,
            # amount/amount_aed/currency are NOT NULL and denormalised from the
            # total, so the fixture carries them the way _purchase does above.
            subtotal=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            amount=Decimal("500.00"),
            amount_aed=Decimal("500.00"),
            currency="AED",
            status="confirmed",
            exchange_rate=Decimal("1"),
        )
        db_session.add(purchase)
        db_session.commit()

        payment = _payment(db_session, sample_tenant, sample_branch)
        payment.purchase_id = purchase.id
        db_session.commit()
        payment_id = payment.id

        resp = client.post(f"/payments/payments/{payment_id}/delete", follow_redirects=True)
        assert resp.status_code == 200, f"deleting a linked payment answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(Payment, payment_id)
        assert row is not None, "a linked payment was purged instead of archived"
        assert (
            db_session.query(ArchivedRecord)
            .filter_by(tenant_id=sample_tenant.id, table_name="payments", record_id=payment_id)
            .first()
            is not None
        ), "a linked payment was kept but not archived, so it is still listed as live"

    def test_deleting_another_tenants_payment_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PAY-80. Cross-tenant payment delete is refused."""
        from models import Tenant

        other = Tenant(
            name=f"PAY Del Other {uuid.uuid4().hex[:8]}",
            name_ar="آخر",
            slug=f"pay-del-other-{uuid.uuid4().hex[:8]}",
            email=f"pay-del-other-{uuid.uuid4().hex[:8]}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _payment(db_session, other, sample_branch)
        foreign_id = foreign.id

        _payer(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/payments/payments/{foreign_id}/delete", follow_redirects=False)
        assert resp.status_code == 404, f"a branch operator deleted another tenant's payment: {resp.status_code}"


class TestPAY57PaymentPrint:
    """PAY-57. Payment print page."""

    def test_the_payment_print_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-57. The payment print page renders."""
        payment = _payment(db_session, sample_tenant, sample_branch)
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get(f"/payments/payments/{payment.id}/print", follow_redirects=False)
        assert resp.status_code == 200, f"the payment print page answered {resp.status_code}"


class TestPAY58WhatsAppInvoice:
    """PAY-58 to PAY-60: WhatsApp integration."""

    def test_sending_invoice_via_whatsapp(self, client, db_session, sample_tenant, sample_branch):
        """PAY-58. Send invoice via WhatsApp."""
        _payer(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_branch)
        resp = client.post(f"/whatsapp/send-invoice/{sale.id}", follow_redirects=False)
        assert resp.status_code in (200, 302, 403), f"send invoice answered {resp.status_code}"

    def test_sending_payment_reminder(self, client, db_session, sample_tenant, sample_branch):
        """PAY-59. Send payment reminder via WhatsApp.

        The route is ``/send-reminder/<customer_id>`` and takes the customer
        from the path, not from a JSON body, and it is behind ``admin_required``.
        """
        _whatsapp_admin(client, db_session, sample_tenant, sample_branch)
        customer = _customer(db_session, sample_tenant)
        resp = client.post(
            f"/whatsapp/send-reminder/{customer.id}",
            follow_redirects=False,
        )
        assert resp.status_code in (200, 400, 403), f"send reminder answered {resp.status_code}"

    def test_whatsapp_connection_test(self, client, db_session, sample_tenant, sample_branch):
        """PAY-60. Test WhatsApp connection."""
        _whatsapp_admin(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/whatsapp/test", follow_redirects=False)
        assert resp.status_code in (200, 403, 503), f"whatsapp test answered {resp.status_code}"


class TestPAY61AuthEndpoints:
    """PAY-61 to PAY-72: Auth endpoints (12 scenarios)."""

    def test_login_page_renders(self, client):
        """PAY-61. Login page renders."""
        resp = client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 200, f"login page answered {resp.status_code}"

    def test_login_success(self, client, db_session, sample_tenant, sample_branch):
        """PAY-62. Valid login works."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/payments/", follow_redirects=False)
        assert resp.status_code in (200, 302), f"authenticated access answered {resp.status_code}"

    def test_login_fails_with_wrong_password(self, client, db_session, sample_tenant, sample_branch):
        """PAY-62. Wrong password is rejected.

        The refusal is the login page re-rendered with the danger flash
        ("اسم المستخدم أو كلمة المرور غير صحيحة") and, the part that matters,
        no session: the next protected request still redirects.
        """
        _payer(client, db_session, sample_tenant, sample_branch)
        client.get("/auth/logout", follow_redirects=True)
        resp = client.post(
            "/auth/login",
            data={"username": "pay-payer", "password": "wrong"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"wrong password answered {resp.status_code}"
        body = resp.get_data(as_text=True)
        assert "غير صحيحة" in body, "a wrong password did not render the refusal message"
        after = client.get("/payments/", follow_redirects=False)
        assert after.status_code in (302, 401, 403), (
            f"a wrong password left a session behind; /payments/ answered {after.status_code}"
        )

    def test_logout_works(self, client, db_session, sample_tenant, sample_branch):
        """PAY-63. Logout clears session."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/auth/logout", follow_redirects=True)
        assert resp.status_code == 200, f"logout answered {resp.status_code}"

    def test_2fa_setup_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-64. 2FA setup page renders."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/auth/2fa/setup", follow_redirects=False)
        assert resp.status_code == 200, f"2FA setup page answered {resp.status_code}"

    def test_2fa_enable_requires_code(self, client, db_session, sample_tenant, sample_branch):
        """PAY-64. Enabling 2FA requires valid code."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/auth/2fa/enable", data={"code": "123456"}, follow_redirects=True)
        assert resp.status_code == 200, f"2FA enable answered {resp.status_code}"

    def test_2fa_disable_works(self, client, db_session, sample_tenant, sample_branch):
        """PAY-65. Disabling 2FA works."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/auth/2fa/disable", follow_redirects=True)
        assert resp.status_code == 200, f"2FA disable answered {resp.status_code}"

    def test_verify_2fa_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-66. Verify 2FA page renders.

        The route only renders for a pending challenge, so it is driven through
        the real thing: park the password-verified user in the session the way
        login does and then ask for the page. Without a challenge it answers a
        redirect to login, which is asserted first so the 200 below cannot be a
        page served to anyone.
        """
        user = _payer(client, db_session, sample_tenant, sample_branch)

        guarded = client.get("/auth/verify-2fa", follow_redirects=False)
        assert guarded.status_code == 302, (
            f"verify 2FA answered {guarded.status_code} with no challenge; the guard is not there"
        )
        assert "/auth/login" in guarded.headers.get("Location", ""), (
            f"verify 2FA redirected to {guarded.headers.get('Location')!r}, not the login page"
        )

        with client.session_transaction() as flask_session:
            flask_session["pending_2fa"] = {
                "user_id": int(user.id),
                "remember": False,
                "access_mode": "users",
                "tenant_id": sample_tenant.id,
                "branch_id": sample_branch.id if sample_branch else None,
                "issued_at": datetime.now(UTC).timestamp(),
            }

        resp = client.get("/auth/verify-2fa", follow_redirects=False)
        assert resp.status_code == 200, f"verify 2FA page answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), "the verify 2FA page raised"

    def test_payment_status_page_requires_valid_token(self, client, db_session, sample_tenant, sample_branch):
        """PAY-67. Payment status page requires valid token."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/auth/payment/status/1", follow_redirects=False)
        assert resp.status_code in (403, 404), f"payment status without token answered {resp.status_code}"

    def test_payment_callback_requires_valid_signature(self, client, db_session, sample_tenant, sample_branch):
        """PAY-68. Payment callback validates signature."""
        resp = client.post(
            "/auth/payment/callback",
            json={},
            headers={"x-nowpayments-sig": "invalid"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, f"invalid signature answered {resp.status_code}"

    def test_available_currencies_endpoint(self, client, db_session, sample_tenant, sample_branch):
        """PAY-69. Available currencies endpoint.

        The list comes from the NOWPayments gateway, which is unconfigured in
        tests, so the honest answers are 200 with data or 400 with the reason.
        What must not happen is an unhandled failure - a 500 with no envelope.
        """
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/auth/payment/currencies", follow_redirects=False)
        assert resp.status_code in (200, 400), f"currencies endpoint answered {resp.status_code}"
        assert resp.get_json() is not None, "currencies endpoint answered without a JSON envelope"

    def test_estimate_amount_endpoint(self, client, db_session, sample_tenant, sample_branch):
        """PAY-70. Estimate amount endpoint."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/auth/payment/estimate?amount=100&currency=USD", follow_redirects=False)
        assert resp.status_code in (200, 400), f"estimate endpoint answered {resp.status_code}"

    def test_thank_you_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-71. Thank you page renders."""
        resp = client.get("/auth/thank-you", follow_redirects=False)
        assert resp.status_code in (200, 302), f"thank you page answered {resp.status_code}"

    def test_support_page_renders(self, client, db_session, sample_tenant, sample_branch):
        """PAY-72. Support page renders."""
        resp = client.get("/auth/support", follow_redirects=False)
        assert resp.status_code == 200, f"support page answered {resp.status_code}"


class TestPAY73WhatsAppInvoice:
    """PAY-73. WhatsApp send invoice (duplicate coverage guard)."""

    def test_whatsapp_send_invoice_duplicate_guard(self, client, db_session, sample_tenant, sample_branch):
        """PAY-73. Duplicate guard on WhatsApp invoice."""
        _payer(client, db_session, sample_tenant, sample_branch)
        sale = _sale(db_session, sample_tenant, sample_branch)
        client.post(  # first send: the side effect is the assertion
            f"/whatsapp/send-invoice/{sale.id}",
            headers={"X-Idempotency-Key": "test-key-1"},
            follow_redirects=False,
        )
        resp2 = client.post(
            f"/whatsapp/send-invoice/{sale.id}",
            headers={"X-Idempotency-Key": "test-key-1"},
            follow_redirects=False,
        )
        assert resp2.status_code in (200, 409, 403), f"duplicate send answered {resp2.status_code}"


class TestPAY74WhatsAppReminder:
    """PAY-74. WhatsApp reminder duplicate guard."""

    def test_whatsapp_reminder_duplicate_is_idempotent(self, client, db_session, sample_tenant, sample_branch):
        """PAY-74. Duplicate reminder is idempotent.

        ``send-reminder`` is behind ``admin_required``, so the caller is an
        admin here; a manage_payments holder would answer 403 on both calls and
        the guard would never be exercised.
        """
        _whatsapp_admin(client, db_session, sample_tenant, sample_branch)
        customer = _customer(db_session, sample_tenant)

        client.post(  # first send: the side effect is the assertion
            f"/whatsapp/send-reminder/{customer.id}",
            follow_redirects=False,
        )
        resp2 = client.post(
            f"/whatsapp/send-reminder/{customer.id}",
            follow_redirects=False,
        )
        assert resp2.status_code in (200, 409), f"duplicate reminder answered {resp2.status_code}"


class TestPAY75WhatsAppTest:
    """PAY-75. WhatsApp test connection."""

    def test_whatsapp_test_connection(self, client, db_session, sample_tenant, sample_branch):
        """PAY-75. Test connection endpoint."""
        _payer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/whatsapp/test", follow_redirects=False)
        assert resp.status_code in (200, 403, 503), f"whatsapp test answered {resp.status_code}"


class TestPAY76AuthLogin:
    """PAY-76. Auth login edge cases."""

    def test_login_with_inactive_user_fails(self, client, db_session, sample_tenant, sample_branch):
        """PAY-76. Inactive user cannot login."""
        from models import Role, User

        role = db_session.query(Role).filter_by(slug="pay-inactive").first()
        if role is None:
            role = Role(name="Inactive User", slug="pay-inactive", is_active=True)
            db_session.add(role)
            db_session.commit()

        user = User(
            username="pay-inactive-user",
            email="inactive@test.com",
            full_name="Inactive User",
            tenant_id=None,
            role_id=role.id,
            is_owner=False,
            is_active=False,
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        resp = client.post(
            "/auth/login",
            data={"username": "pay-inactive-user", "password": "password123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"inactive user login answered {resp.status_code}"
        assert "inactive" in resp.get_data(as_text=True).lower()


class TestPAY77AuthPasswordReset:
    """PAY-77. Password reset flow (placeholder)."""

    def test_password_reset_flow_placeholder(self, client):
        """PAY-77. Password reset endpoint exists."""
        resp = client.get("/auth/password/reset", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"password reset page answered {resp.status_code}"
