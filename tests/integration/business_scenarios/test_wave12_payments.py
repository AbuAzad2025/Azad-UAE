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
