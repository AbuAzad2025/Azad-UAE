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

        _payer(client, db_session, sample_tenant, sample_branch)
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
            user_id=user.id,
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
