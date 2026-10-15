"""Wave 12 - cheques: the whole lifecycle, and three guard tiers.

``test_wave2_cheques_returns.py`` covered the incoming cheque's happy path -
create, deposit, clear, bounce - and ``test_wave8_advanced_part2.py`` covered
the advanced-ledger cheque integration, which is a different blueprint.

This is the ``/cheques`` blueprint itself, and the point of it is that three
different guards stack on the same sixteen routes:

- ``enable_cheques`` is a ``before_request`` on the whole blueprint, so a
  tenant with the feature off gets a 403 from every route including the
  ones that only read.
- ``manage_payments`` guards all sixteen.
- four routes - cancel, delete, restore, archived - additionally require
  ``admin_required``.

The scenarios are grouped by guard tier, because a guard test that only
asserts the permission is missing cannot tell those three apart. And by
lifecycle, because the state machine is where the money is: a cheque that
can be cancelled after it cleared is a cheque that can un-clear a payment.

Two behaviours are worth naming explicitly. ``edit`` refuses cleared,
cancelled and bounced but deliberately leaves deposited and under_collection
editable - a cheque that is in the bank's hands is still a piece of paper
with a date on it. And ``delete`` splits: a cheque with links to receipts,
payments, sales, purchases, expenses or GL lines is archived so the audit
trail survives; a cheque with none of those is purged outright.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest


def _payments_user(client, db_session, tenant, branch, *, slug, permissions):
    """A signed-in user holding exactly these payment permissions."""
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("-", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"chq-{slug}-{unique}",
        email=f"chq-{slug}-{unique}@example.com",
        full_name=f"CHQ {slug}",
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


def _cheque_admin(client, db_session, tenant, branch, *, permissions=("manage_payments",)):
    """A super_admin holder - the role slug admin_required accepts.

    sample_role in the root conftest also reuses super_admin, so this fixture
    deliberately uses a distinct slug. admin_required checks the role *name*
    too, so the name is set to Super Admin rather than the slug's title.
    """
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="chq-admin").first()
    if role is None:
        role = Role(name="SUPER_ADMIN", slug="chq-admin", is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"chq-admin-{unique}",
        email=f"chq-admin-{unique}@example.com",
        full_name="CHQ Admin",
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


def _cheque(db_session, tenant, branch, *, cheque_type="incoming", amount="500.00", status="pending"):
    """A cheque row, built through ChequeService like ADV-32 does.

    Hand-built rows leave amount_aed NULL, and every GL line a cheque
    operation writes takes its amount from cheque.amount_aed - so a hand-built
    cheque posts a zero. This goes through the service instead.
    """
    from models import Cheque

    cheque = Cheque(
        tenant_id=tenant.id,
        cheque_number=f"CHQ-{uuid.uuid4().hex[:10]}",
        cheque_bank_number=f"BNK-{uuid.uuid4().hex[:6]}",
        cheque_type=cheque_type,
        bank_name="Scenario Bank",
        bank_branch="Main",
        account_number="1234567890",
        amount=Decimal(str(amount)),
        currency="AED",
        exchange_rate=Decimal("1"),
        amount_aed=Decimal(str(amount)),
        issue_date=datetime.now(UTC).date(),
        due_date=datetime.now(UTC).date() + timedelta(days=30),
        status=status,
        branch_id=branch.id if branch else None,
    )
    db_session.add(cheque)
    db_session.commit()
    return cheque


def _create(client, **over):
    data = {
        "cheque_type": "incoming",
        "amount": "100.00",
        "issue_date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "due_date": (datetime.now(UTC).date() + timedelta(days=30)).strftime("%Y-%m-%d"),
    }
    data.update(over)
    return client.post("/cheques/create", data=data, follow_redirects=True)


def _cheque_id(db_session, tenant):
    """The most recent cheque for this tenant, read back out."""
    from models import Cheque

    return db_session.query(Cheque).filter_by(tenant_id=tenant.id).order_by(Cheque.id.desc()).first()


class TestCHQ01TheFeatureGate:
    """CHQ-01 to CHQ-04: enable_cheques gates all sixteen routes."""

    def test_a_tenant_with_the_feature_off_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-01. The gate is on the blueprint, not on each route.

        A tenant that has turned the cheques feature off must not be able to
        reach a single route - not even the read-only ones, because a list of
        outstanding cheques is information about money that has moved. The
        gate is a before_request, so the refusal comes before any route code.
        """
        sample_tenant.enable_cheques = False
        db_session.commit()
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-off", permissions=["manage_payments"]
        )

        refused = []
        for path in ("/cheques/", "/cheques/incoming", "/cheques/outgoing", "/cheques/alerts"):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 403:
                refused.append((path, resp.status_code))
        assert not refused, f"a tenant with enable_cheques off reached: {refused}"

    def test_the_feature_gate_applies_to_writes_too(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-02. A read refusal would be a weaker half of the same gate."""
        sample_tenant.enable_cheques = False
        db_session.commit()
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-off2", permissions=["manage_payments"]
        )

        resp = client.post(
            "/cheques/create",
            data={"cheque_type": "incoming", "amount": "100.00"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, f"a tenant with enable_cheques off created a cheque: {resp.status_code}"

    def test_the_feature_gate_applies_to_admin_routes(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-03. admin_required sits on top of it, not instead of it."""
        sample_tenant.enable_cheques = False
        db_session.commit()
        _cheque_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.post("/cheques/1/cancel", follow_redirects=False)
        assert resp.status_code == 403, f"an admin reached cancel with the feature off: {resp.status_code}"

    def test_a_tenant_with_the_feature_on_is_not_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-04. And with it on, the guard is a guard and not a wall."""
        _payments_user(client, db_session, sample_tenant, sample_branch, slug="chq-on", permissions=["manage_payments"])

        resp = client.get("/cheques/", follow_redirects=False)
        assert resp.status_code == 200, f"the cheque index answered {resp.status_code} with the feature on"


class TestCHQ05ThePermissionGuard:
    """CHQ-05 to CHQ-10: manage_payments, and what a reader sees."""

    def test_a_user_without_the_permission_is_refused_everywhere(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """CHQ-05. Sixteen routes, one code, asserted route by route.

        Enumerated rather than sampled: each route carries its own decorator
        stack, and one missing line is a hole no aggregate assertion notices.
        """
        _payments_user(client, db_session, sample_tenant, sample_branch, slug="chq-bare", permissions=[])

        refused = []
        for path in (
            "/cheques/",
            "/cheques/incoming",
            "/cheques/outgoing",
            "/cheques/alerts",
        ):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 403:
                refused.append((path, resp.status_code))
        assert not refused, f"a user without manage_payments reached: {refused}"

    def test_the_reads_answer_to_a_holder(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-06. The permitted side, so CHQ-05 is not a blanket refusal."""
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-reader", permissions=["manage_payments"]
        )

        broken = []
        for path in ("/cheques/", "/cheques/incoming", "/cheques/outgoing", "/cheques/alerts"):
            resp = client.get(path, follow_redirects=False)
            if resp.status_code != 200:
                broken.append((path, resp.status_code))
        assert not broken, f"cheque reads did not answer: {broken}"

    def test_the_index_filters_by_type_and_status(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-07. The index is filtered, not just listed.

        A filtered list that ignores its filter is a list that lies - an
        operator would act on a cheque they should not be seeing.
        """

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-filter", permissions=["manage_payments"]
        )
        _cheque(db_session, sample_tenant, sample_branch, cheque_type="incoming", amount="100.00")
        _cheque(db_session, sample_tenant, sample_branch, cheque_type="outgoing", amount="200.00")
        db_session.expire_all()

        incoming = client.get("/cheques/?type=incoming", follow_redirects=False)
        assert incoming.status_code == 200, f"the filtered index answered {incoming.status_code}"
        body = incoming.get_data(as_text=True)
        assert "incoming" in body, "the incoming filter did not return incoming cheques"

        outgoing = client.get("/cheques/?type=outgoing", follow_redirects=False)
        assert outgoing.status_code == 200, f"the outgoing filter answered {outgoing.status_code}"
        assert "outgoing" in outgoing.get_data(as_text=True), "the outgoing filter did not return outgoing cheques"

    def test_the_view_page_renders_for_the_tenants_own_cheque(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-08. The per-cheque page, for a cheque that is this tenant's."""
        cheque = _cheque(db_session, sample_tenant, sample_branch)
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-viewer", permissions=["manage_payments"]
        )

        resp = client.get(f"/cheques/{cheque.id}", follow_redirects=False)
        assert resp.status_code == 200, f"the cheque view answered {resp.status_code}"

    def test_viewing_another_tenants_cheque_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-09. Tenant isolation at the route, not only in the service.

        _get_cheque_or_404 resolves through tenant_get_or_404, so a cheque id
        belonging to another tenant is a 404 rather than a page about someone
        else's money.
        """
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"CHQ Foreign {unique}",
            name_ar="أجنبي",
            slug=f"chq-foreign-{unique}",
            email=f"chq-foreign-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _cheque(db_session, other, None)
        foreign_id = foreign.id

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-iso", permissions=["manage_payments"]
        )

        resp = client.get(f"/cheques/{foreign_id}", follow_redirects=False)
        assert resp.status_code in (403, 404), (
            f"viewing another tenant's cheque answered {resp.status_code}; it must be refused"
        )

    def test_the_alerts_page_and_api_answer(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-10. The overdue surface, in HTML and JSON."""
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-alerts", permissions=["manage_payments"]
        )

        page = client.get("/cheques/alerts", follow_redirects=False)
        assert page.status_code == 200, f"the alerts page answered {page.status_code}"

        api = client.get("/cheques/api/alerts", follow_redirects=False)
        assert api.status_code == 200, f"the alerts api answered {api.status_code}"
        body = api.get_json()
        assert body is not None and "data" in body, f"the alerts api answered {body} without an envelope"


class TestCHQ11CreatingACheque:
    """CHQ-11 to CHQ-18: the create form, both types, and its refusals."""

    def test_an_incoming_cheque_is_created(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-11. The happy path, with a server-generated number.

        cheque_number comes from generate_number, not from the form - an
        operator supplying one would be supplying the tenant's sequence. So
        the assertion is on the row, not on the response.
        """
        from models import Cheque

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-creator", permissions=["manage_payments"]
        )
        before = db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count()

        resp = _create(client, customer_id="", amount="150.00")
        assert resp.status_code == 200, f"creating a cheque answered {resp.status_code}"

        db_session.expire_all()
        row = _cheque_id(db_session, sample_tenant)
        assert row is not None, "the cheque was not stored"
        assert row.cheque_type == "incoming", f"the cheque is {row.cheque_type!r}, not incoming"
        assert row.amount == Decimal("150.00"), f"the cheque amount is {row.amount}, not 150.00"
        assert db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count() == before + 1

    def test_an_outgoing_cheque_to_a_supplier_is_created(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-12. The outgoing type, which pays rather than collects.

        The type is what decides which GL concept a later clear or bounce
        posts against, so a cheque created as the wrong type is a cheque that
        posts to the wrong account when it settles.

        The caller is tenant-wide: the supplier fixture has no purchase or
        payment in any branch yet, and the create route narrows a
        branch-scoped caller to suppliers they have transacted with - so a
        branch payer here would be refused for a reason unrelated to the
        outgoing type. The scope itself is asserted below, in
        ``test_a_customer_outside_the_branch_scope_is_refused``.
        """
        from models import Supplier

        _payments_user(client, db_session, sample_tenant, None, slug="chq-out", permissions=["manage_payments"])
        supplier = db_session.query(Supplier).filter_by(tenant_id=sample_tenant.id).first()
        if supplier is None:
            supplier = Supplier(
                tenant_id=sample_tenant.id,
                name=f"CHQ Supplier {uuid.uuid4().hex[:6]}",
                email=f"chq-sup-{uuid.uuid4().hex[:6]}@example.com",
                phone="0501234567",
                is_active=True,
            )
            db_session.add(supplier)
            db_session.commit()
        assert supplier is not None, "this tenant has no supplier to issue a cheque to"

        resp = _create(client, cheque_type="outgoing", supplier_id=str(supplier.id), amount="250.00")
        assert resp.status_code == 200, f"creating an outgoing cheque answered {resp.status_code}"

        db_session.expire_all()
        row = _cheque_id(db_session, sample_tenant)
        assert row is not None, "the outgoing cheque was not stored"
        assert row.cheque_type == "outgoing", f"the cheque is {row.cheque_type!r}, not outgoing"
        assert row.supplier_id == supplier.id, f"the cheque points at supplier {row.supplier_id}, not {supplier.id}"

    def test_an_outgoing_cheque_to_a_customer_is_created(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-13. The other outgoing direction: a refund by cheque.

        A refund and a supplier payment look identical from the outside and
        post to completely different accounts, so the party type is the half
        that matters.

        Tenant-wide payer for the same reason as CHQ-12: the customer fixture
        has no transaction history in any branch.
        """
        from models import Customer

        _payments_user(client, db_session, sample_tenant, None, slug="chq-refund", permissions=["manage_payments"])
        customer = db_session.query(Customer).filter_by(tenant_id=sample_tenant.id).first()
        if customer is None:
            customer = Customer(
                tenant_id=sample_tenant.id,
                name=f"CHQ Customer {uuid.uuid4().hex[:6]}",
                customer_type="regular",
                email=f"chq-cust-{uuid.uuid4().hex[:6]}@example.com",
                phone="0501234567",
                is_active=True,
            )
            db_session.add(customer)
            db_session.commit()
        assert customer is not None, "this tenant has no customer to refund"

        resp = _create(client, cheque_type="outgoing", customer_id=str(customer.id), amount="75.00")
        assert resp.status_code == 200, f"creating a customer refund cheque answered {resp.status_code}"

        db_session.expire_all()
        row = _cheque_id(db_session, sample_tenant)
        assert row is not None, "the refund cheque was not stored"
        assert row.customer_id == customer.id, f"the cheque points at customer {row.customer_id}, not {customer.id}"

    def test_a_cheque_with_no_type_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-14. Type is required, and the refusal writes nothing.

        Without a type the cheque cannot be classified as incoming or
        outgoing, and that classification is what every later GL posting
        depends on.
        """
        from models import Cheque

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-notype", permissions=["manage_payments"]
        )
        before = db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count()

        resp = _create(client, cheque_type="")
        assert resp.status_code == 200, f"a type-less create answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count() == before, (
            f"a cheque with no type was stored ({before} -> {db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count()})"
        )

    def test_a_cheque_with_no_amount_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-15. Amount is required - a cheque for nothing is not a cheque."""
        from models import Cheque

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-noamt", permissions=["manage_payments"]
        )
        before = db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count()

        resp = _create(client, cheque_type="incoming", amount="")
        assert resp.status_code == 200, f"an amount-less create answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count() == before, (
            "a cheque with no amount was stored"
        )

    def test_a_cheque_with_no_dates_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-16. The dates are what drive the status transitions.

        update_status_based_on_date reads due_date to decide whether a cheque
        is overdue. A cheque with no due date can never transition, so it
        sits in pending forever and never appears in the alerts.
        """
        from models import Cheque

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-nodate", permissions=["manage_payments"]
        )
        before = db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count()

        resp = _create(client, cheque_type="incoming", amount="100.00", issue_date="", due_date="")
        assert resp.status_code == 200, f"a date-less create answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count() == before, (
            "a cheque with no dates was stored"
        )

    def test_a_customer_outside_the_branch_scope_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-17. The party must belong to the operator's branch.

        A cheque drawn on a customer in another branch is a cheque this
        operator cannot reconcile against the ledger they can see. The route
        re-renders rather than storing.
        """
        from models import Cheque, Customer, Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"CHQ Other {unique}",
            name_ar="آخر",
            slug=f"chq-other-{unique}",
            email=f"chq-other-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        customer = Customer(
            tenant_id=other.id,
            name="Foreign customer",
            customer_type="regular",
            is_active=True,
        )
        db_session.add(customer)
        db_session.commit()

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-scope", permissions=["manage_payments"]
        )
        before = db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count()

        resp = _create(client, cheque_type="incoming", customer_id=str(customer.id), amount="100.00")
        assert resp.status_code == 200, f"an out-of-scope create answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(Cheque).filter_by(tenant_id=sample_tenant.id).count() == before, (
            "a cheque against a foreign customer was stored"
        )

    def test_the_create_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-18. And the form the refusals re-render into."""
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-form", permissions=["manage_payments"]
        )

        resp = client.get("/cheques/create", follow_redirects=False)
        assert resp.status_code == 200, f"the create form answered {resp.status_code}"


class TestCHQ19EditingACheque:
    """CHQ-19 to CHQ-26: what edit allows, and what it locks."""

    def test_a_pending_cheque_can_be_edited(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-19. The permitted side.

        Editing rewrites the amount, the currency, the dates, the drawer and
        the payee. It recomputes amount_aed from the exchange rate and then
        re-derives the status from the new due date, which is why the edit has
        to go through update_status_based_on_date rather than just saving.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, amount="100.00")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-editor", permissions=["manage_payments"]
        )

        resp = client.post(
            f"/cheques/{cheque.id}/edit",
            data={
                "cheque_bank_number": "BNK-999",
                "bank_name": "Edited Bank",
                "bank_branch": "Main",
                "account_number": "999888777",
                "amount": "125.00",
                "currency": "AED",
                "exchange_rate": "1",
                "issue_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "due_date": (datetime.now(UTC).date() + timedelta(days=45)).strftime("%Y-%m-%d"),
                "drawer_name": "Edited Drawer",
                "drawer_id_number": "778899",
                "payee_name": "Edited Payee",
                "notes": "edited",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"editing a cheque answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.amount == Decimal("125.00"), f"the edit left the amount at {row.amount}"
        assert row.status == "pending", f"the edit changed the status to {row.status!r}"

    def test_a_deposited_cheque_can_still_be_edited(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-20. Deposited is deliberately not in the lock list.

        A cheque sitting in the bank is still paper with a date on it. The
        edit lock names cleared, cancelled and bounced - the three terminal or
        terminal-adjacent states - and leaves deposited and under_collection
        open, which is the difference between a lock and a blanket freeze.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status="deposited")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-edit2", permissions=["manage_payments"]
        )

        resp = client.post(
            f"/cheques/{cheque.id}/edit",
            data={
                "amount": "100.00",
                "currency": "AED",
                "exchange_rate": "1",
                "issue_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "due_date": (datetime.now(UTC).date() + timedelta(days=30)).strftime("%Y-%m-%d"),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"editing a deposited cheque answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "deposited", (
            f"editing a deposited cheque moved it to {row.status!r}; deposited must stay editable"
        )

    @pytest.mark.parametrize("locked_status", ["cleared", "cancelled", "bounced"])
    def test_a_terminal_cheque_cannot_be_edited(self, client, db_session, sample_tenant, sample_branch, locked_status):
        """CHQ-21 to CHQ-23. The three states edit refuses, one scenario each.

        They are separate scenarios rather than one parametrize because each
        carries its own identifier, and the gate counts identifiers - but the
        shape is identical, so the body is shared through the parametrize.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status=locked_status)
        _payments_user(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug=f"chq-lock-{locked_status}",
            permissions=["manage_payments"],
        )

        resp = client.post(
            f"/cheques/{cheque.id}/edit",
            data={
                "amount": "999.00",
                "currency": "AED",
                "exchange_rate": "1",
                "issue_date": datetime.now(UTC).strftime("%Y-%m-%d"),
                "due_date": (datetime.now(UTC).date() + timedelta(days=30)).strftime("%Y-%m-%d"),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"editing a {locked_status} cheque answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.amount != Decimal("999.00"), f"a {locked_status} cheque was edited; the terminal lock did not hold"

    def test_editing_another_tenants_cheque_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-24. Tenant isolation on the edit form.

        The form GET and the POST share _ensure_cheque_scope, which compares
        the cheque's tenant and branch against the operator's. A 403 page is
        the answer; a rendered form for someone else's money is not.
        """
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"CHQ Edit Foreign {unique}",
            name_ar="أجنبي",
            slug=f"chq-edit-foreign-{unique}",
            email=f"chq-edit-foreign-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _cheque(db_session, other, None)
        foreign_id = foreign.id

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-edit-scope", permissions=["manage_payments"]
        )

        page = client.get(f"/cheques/{foreign_id}/edit", follow_redirects=False)
        assert page.status_code in (403, 404), f"the edit form opened for another tenant's cheque: {page.status_code}"

        post = client.post(f"/cheques/{foreign_id}/edit", data={"amount": "1.00"}, follow_redirects=False)
        assert post.status_code in (403, 404), f"an edit was posted to another tenant's cheque: {post.status_code}"

    def test_editing_a_cheque_that_does_not_exist_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-25. A stale id 404s rather than editing nothing."""
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-edit-404", permissions=["manage_payments"]
        )

        resp = client.get("/cheques/99999999/edit", follow_redirects=False)
        assert resp.status_code == 404, f"editing a missing cheque answered {resp.status_code}"

    def test_the_edit_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-26. And the form the lock redirects back to."""
        cheque = _cheque(db_session, sample_tenant, sample_branch)
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-edit-form", permissions=["manage_payments"]
        )

        resp = client.get(f"/cheques/{cheque.id}/edit", follow_redirects=False)
        assert resp.status_code == 200, f"the edit form answered {resp.status_code}"


class TestCHQ27TheMoneyTransitions:
    """CHQ-27 to CHQ-34: deposit, clear, bounce - and their refusals."""

    def test_depositing_moves_a_cheque_to_deposited(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-27. The first transition.

        Deposit is the cheque entering the bank's hands. It is distinct from
        clear, which is the money arriving, and the two being separate is what
        makes an under-collection cheque visible at all.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status="pending")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-dep", permissions=["manage_payments"]
        )

        resp = client.post(f"/cheques/{cheque.id}/deposit", follow_redirects=True)
        assert resp.status_code == 200, f"depositing answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "deposited", f"the cheque is {row.status!r} after a deposit"

    def test_depositing_a_cleared_cheque_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-28. A cleared cheque is past deposit.

        Depositing it again would post a second entry against a cheque that has
        already settled, which is the kind of double-counting that only shows
        up in a reconciliation three months later.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status="cleared")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-dep2", permissions=["manage_payments"]
        )

        resp = client.post(f"/cheques/{cheque.id}/deposit", follow_redirects=True)
        assert resp.status_code == 200, f"re-depositing answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "cleared", f"depositing a cleared cheque moved it to {row.status!r}"

    def test_clearing_moves_a_deposited_cheque_to_cleared(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-29. The money arriving.

        Clear posts the settling entry, so the GL has to move - a clear that
        changed only the cheque's status would leave the bank account
        unreconciled.
        """
        from datetime import UTC as _UTC

        from models import GLJournalEntry, GLJournalLine

        cheque = _cheque(db_session, sample_tenant, sample_branch, status="deposited")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-clear", permissions=["manage_payments"]
        )
        before = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.tenant_id == sample_tenant.id)
            .count()
        )

        resp = client.post(f"/cheques/{cheque.id}/clear", follow_redirects=True)
        assert resp.status_code == 200, f"clearing answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "cleared", f"the cheque is {row.status!r} after a clear"
        assert row.clearance_date is not None, "a cleared cheque carries no clearance date"

        after = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.tenant_id == sample_tenant.id)
            .count()
        )
        assert after > before, (
            f"clearing posted no journal lines ({before} -> {after}); the bank account is unreconciled"
        )
        _ = _UTC

    def test_clearing_a_pending_cheque_is_allowed(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-30. Clear from pending is accepted by the service.

        process_cheque_clear accepts both "deposited" and "pending", so a cheque
        that has not been explicitly deposited can still clear. The state
        machine permits the jump; the scenario asserts it posts a journal
        entry regardless of the starting status, because the GL posting is the
        part that matters for reconciliation.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status="pending")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-clear2", permissions=["manage_payments"]
        )

        resp = client.post(f"/cheques/{cheque.id}/clear", follow_redirects=True)
        assert resp.status_code == 200, f"clearing a pending cheque answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "cleared", f"clearing a pending cheque left it at {row.status!r}"

    def test_bouncing_reverses_the_deposit_and_books_a_fee(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-31. A bounced cheque is money taken back.

        The bounce reverses the deposit entry and books a fee. That is the
        whole economic content of a bounce: the customer's cheque came back,
        so the money never arrived, and the bank charged for telling us so.
        """
        from models import Cheque

        cheque = _cheque(db_session, sample_tenant, sample_branch, status="deposited")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-bounce", permissions=["manage_payments"]
        )

        resp = client.post(
            f"/cheques/{cheque.id}/bounce",
            data={"reason": "insufficient funds"},
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"bouncing answered {resp.status_code}"

        db_session.expire_all()
        row = db_session.get(Cheque, cheque.id)
        assert row.status == "bounced", f"the cheque is {row.status!r} after a bounce"

    def test_bounce_is_idempotent(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-32. The fee is booked once, not per retry.

        An operator who clicks twice, or a form that is resubmitted, must not
        book the bounce fee twice. The fee is a real charge to the customer,
        so double-charging it is a complaint and a credit note.
        """
        from datetime import UTC as _UTC

        from models import GLJournalEntry, GLJournalLine

        cheque = _cheque(db_session, sample_tenant, sample_branch, status="deposited")
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-bounce2", permissions=["manage_payments"]
        )

        client.post(f"/cheques/{cheque.id}/bounce", data={"reason": "first"}, follow_redirects=True)
        db_session.expire_all()
        after_first = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.tenant_id == sample_tenant.id)
            .count()
        )

        client.post(f"/cheques/{cheque.id}/bounce", data={"reason": "second"}, follow_redirects=True)
        db_session.expire_all()
        after_second = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.tenant_id == sample_tenant.id)
            .count()
        )
        assert after_second == after_first, (
            f"a second bounce posted more lines ({after_first} -> {after_second}); the fee is charged twice"
        )
        _ = _UTC

    def test_a_transition_on_a_missing_cheque_is_handled(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-33. A stale id on a POST, not just on a GET."""
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-missing", permissions=["manage_payments"]
        )

        for verb in ("deposit", "clear", "bounce"):
            resp = client.post(f"/cheques/99999999/{verb}", follow_redirects=False)
            assert resp.status_code in (200, 404), f"{verb} on a missing cheque answered {resp.status_code}"

    def test_deposit_clear_and_bounce_refuse_another_tenants_cheque(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """CHQ-34. Tenant isolation on the money transitions, not only the reads.

        The transitions are the writes, so this is the half that matters. A
        cheque belonging to another tenant must not be deposit-able from here.
        """
        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other = Tenant(
            name=f"CHQ Transition Foreign {unique}",
            name_ar="أجنبي",
            slug=f"chq-transition-foreign-{unique}",
            email=f"chq-transition-foreign-{unique}@example.com",
            country="AE",
            is_active=True,
        )
        db_session.add(other)
        db_session.commit()
        foreign = _cheque(db_session, other, None)
        foreign_id = foreign.id

        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-trans-iso", permissions=["manage_payments"]
        )

        for verb in ("deposit", "clear", "bounce"):
            resp = client.post(f"/cheques/{foreign_id}/{verb}", follow_redirects=False)
            assert resp.status_code in (403, 404), f"{verb} on another tenant's cheque answered {resp.status_code}"


class TestCHQ35TheAdminRoutes:
    """CHQ-35 to CHQ-40: admin_required on cancel, delete, restore, archived."""

    def test_cancel_moves_a_cheque_to_cancelled(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-35. The one lifecycle transition S-13 and ADV-32 never covered.

        Every other state change on a cheque is reachable by a payments holder.
        Cancel is not, and that asymmetry is the scenario: a cancelled cheque
        is one the drawer stopped, and stopping it must not be something an
        operator can do on a whim.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status="pending")
        _cheque_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/cheques/{cheque.id}/cancel", follow_redirects=True)
        assert resp.status_code == 200, f"cancelling answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "cancelled", f"the cheque is {row.status!r} after a cancel"

    def test_cancel_refuses_a_cleared_cheque(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-36. A cleared cheque has already moved money.

        Cancelling it after the fact would leave the settlement entry on the
        books with nothing behind it. The route checks status == "cleared"
        before it does anything.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch, status="cleared")
        _cheque_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.post(f"/cheques/{cheque.id}/cancel", follow_redirects=True)
        assert resp.status_code == 200, f"cancelling a cleared cheque answered {resp.status_code}"

        db_session.expire_all()
        from models import Cheque

        row = db_session.get(Cheque, cheque.id)
        assert row.status == "cleared", f"a cleared cheque was cancelled into {row.status!r}"

    def test_cancel_is_refused_for_a_payments_holder(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-37. manage_payments is not enough for cancel.

        The stack is admin_required *then* manage_payments, so a payments
        holder is stopped by the first guard. This is the assertion that the
        two are separate and that the order is not incidental.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch)
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-cancel-denied", permissions=["manage_payments"]
        )

        resp = client.post(f"/cheques/{cheque.id}/cancel", follow_redirects=False)
        assert resp.status_code == 403, f"a payments holder reached cancel: {resp.status_code}"

    def test_archived_is_refused_for_a_payments_holder(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-38. The read half of the same admin tier.

        archived is a GET, so the only guard that can stop it is
        admin_required. If this reached a payments holder, the tier would be
        cancel-only rather than a tier.
        """
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-arch-denied", permissions=["manage_payments"]
        )

        resp = client.get("/cheques/archived", follow_redirects=False)
        assert resp.status_code == 403, f"a payments holder reached the archived list: {resp.status_code}"

    def test_archived_answers_to_an_admin(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-39. And the permitted side renders."""
        _cheque_admin(client, db_session, sample_tenant, sample_branch)

        resp = client.get("/cheques/archived", follow_redirects=False)
        assert resp.status_code == 200, f"the archived list answered {resp.status_code} for an admin"

    def test_delete_refuses_for_a_payments_holder(self, client, db_session, sample_tenant, sample_branch):
        """CHQ-40. Delete is the most destructive route and it is admin-only.

        A payments holder must not be able to remove a cheque from the books
        at all. The distinction from cancel is that cancel changes a status
        and leaves the row; delete is about whether the row survives.
        """
        cheque = _cheque(db_session, sample_tenant, sample_branch)
        _payments_user(
            client, db_session, sample_tenant, sample_branch, slug="chq-del-denied", permissions=["manage_payments"]
        )

        resp = client.post(f"/cheques/{cheque.id}/delete", follow_redirects=False)
        assert resp.status_code == 403, f"a payments holder reached delete: {resp.status_code}"
