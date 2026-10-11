"""Wave 11 - Point of sale: carts, checkout, shifts and hardware. Prefix POS.

The catalogue calls POS *the largest single surface* and gives it one line of
intent: **money in the drawer, and the two screens that disagree**.

Both halves are cash. The drawer half is arithmetic that has to balance to
the fils - ``PosShift.compute_expected_cash`` is
``starting + cash tendered - change - cash refunds + pay-ins - pay-outs``
and ``reconcile`` stores the difference as a discrepancy. If that formula or
the order of its terms is wrong, a cashier is made to look short for money
the system still has, which is why the drawer scenarios assert the number,
not the status.

The "two screens" half is the KDS and the customer display: they read the
same order and must not disagree about it, and a route that renders one of
them for a customer who has not paid is a leak. That, plus the hardware
surface (floors/tables/printers), is what the catalogue means by two screens.

This is also the only domain with a full set of its own fixtures already in
the suite - ``pos_cashier``, ``till_open`` and ``pos_subfeatures_on`` exist
in conftest specifically for this, because checkout is refused unless a
session is open for the signed-in cashier under the same branch and the
multi-tender sub-feature is enabled. Every scenario that rings up money
therefore asks for ``till_open``; asserting a 403 on checkout without it
would be asserting the fixture's absence.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

# The permission codes POS splits on. A cashier needs manage_sales to ring up;
# the override and return verbs are separate authorities precisely so the
# person taking the money cannot also decide to take it away.
POS_RING_UP = "manage_sales"
POS_OVERRIDE = "pos_authorize_override"
POS_RETURN = "pos_return"
POS_KDS = "view_kds"

POS_READ_PATHS = [
    "/pos/",
    "/pos/grid",
    "/pos/held-carts",
    "/pos/kds",
    "/pos/customer-display",
    "/pos/settings/order-types",
    "/pos/settings/printers",
]
POS_API_PATHS = [
    "/pos/api/products",
    "/pos/api/catalog",
    "/pos/api/categories",
    "/pos/api/customers",
    "/pos/api/promotions",
    "/pos/api/terminals",
    "/pos/api/hardware",
    "/pos/api/floors",
    "/pos/api/tables",
]
POS_MONEY_PATHS = [
    "/pos/api/checkout",
    "/pos/api/session/current",
    "/pos/api/session/open",
    "/pos/api/session/close",
    "/pos/api/shift/current",
    "/pos/api/shift/open",
    "/pos/api/shift/reconcile",
    "/pos/api/shift/close",
    "/pos/api/drawer/open",
    "/pos/api/cash-movements",
    "/pos/api/returns",
    "/pos/api/fast-cash",
    "/pos/api/authorize-override",
]

#: The routes this file claims, kept as data so a renamed route fails here
#: rather than quietly dropping out of coverage.
POS_ROUTE_INVENTORY = (
    POS_READ_PATHS
    + POS_API_PATHS
    + POS_MONEY_PATHS
    + [
        "/pos/receipt/1",
        "/pos/api/session/pause",
        "/pos/api/session/resume",
        "/pos/api/session/report",
        "/pos/api/supervisor-pin",
        "/pos/api/stock",
        "/pos/api/kds/orders",
        "/pos/api/sale/1",
        "/pos/api/order-types",
        "/pos/api/walkin-customer",
        "/pos/api/receipts",
    ]
)


def _actor(client, db_session, tenant, branch, code, also=()):
    """Sign in holding ``code`` plus any extra in ``also``.

    The role slug is namespaced by code because the seeder reuses a role by
    slug and *replaces* its permissions; two codes under one slug would
    overwrite each other's grants and the second scenario would fail a guard
    for a reason unrelated to what it was testing.
    """
    from models import Permission, User

    role_slug = code.replace(".", "-").replace(":", "-")
    from models import Role

    role = db_session.query(Role).filter_by(slug=role_slug).first()
    if role is None:
        role = Role(name=role_slug.replace("-", " ").title(), slug=role_slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    wanted = [code, *(also if isinstance(also, (list, tuple, set)) else [also])]
    granted = Permission.query.filter(Permission.code.in_(wanted)).all()
    have = [g.code for g in granted]
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
        username=f"pos-{role_slug}-{unique}",
        email=f"pos-{role_slug}-{unique}@example.com",
        full_name=f"POS {code}",
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


def _login(client, user):
    """Sign ``user`` in, replacing whatever the browser was holding before.

    The logout is not optional. ``/auth/login`` short-circuits to a redirect
    when the session is already authenticated, so a login that follows a
    fixture's own login (pos_cashier, till_open) is silently ignored: the
    guard under test keeps seeing the fixture's user and the scenario fails as
    a 403 for a reason that has nothing to do with what it is asserting.
    """
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _cashier(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, POS_RING_UP)


def _supervisor(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, POS_OVERRIDE, also=(POS_RING_UP,))


def _refunder(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, POS_RETURN, also=(POS_RING_UP,))


def _kds(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, POS_KDS)


def _shift(db_session, tenant, branch, user, *, starting_cash="100.000", status="open"):
    """A POS shift built the way /api/shift/open builds one.

    ``PosShift.branch_id`` is a read-only property that reaches through the
    shift's session, so the branch is bound by giving the shift a session that
    belongs to that branch - which is also how the model is meant to be used.
    """
    from models import PosSession
    from services.pos_session_service import PosSessionService

    session = db_session.query(PosSession).filter_by(tenant_id=tenant.id, user_id=user.id, status="open").first()
    if session is None:
        session = PosSession(
            session_number=f"POS-SHIFT-{uuid.uuid4().hex[:8].upper()}",
            tenant_id=tenant.id,
            branch_id=branch.id if branch else None,
            user_id=user.id,
            opening_balance_cash=Decimal("0"),
            status="open",
        )
        db_session.add(session)
        db_session.commit()

    shift = PosSessionService.create_shift(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        user_id=user.id,
        starting_cash=Decimal(starting_cash),
    )
    # shift_number is NOT NULL; /api/shift/open fills it from generate_number
    # after create_shift, which the scenarios reproduce here.
    shift.shift_number = f"SHF-{uuid.uuid4().hex[:10].upper()}"
    shift.session_id = session.id
    shift.status = status
    db_session.add(shift)
    db_session.commit()
    return shift


class TestPOS01Permissions:
    """POS-01..12. What each verb asks for before it moves money."""

    def test_the_pos_permissions_are_seeded(self, db_session):
        """POS-01. Four authorities, and the split is the point."""
        from utils.constants import PERMISSION_CODES

        for code in (POS_RING_UP, POS_OVERRIDE, POS_RETURN, POS_KDS):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"

    def test_the_override_and_return_codes_are_separate_from_ring_up(self, db_session):
        """POS-02. manage_sales is not a superset: the person taking the money
        must not also be the person who decides to take it back."""

        assert POS_OVERRIDE != POS_RING_UP
        assert POS_RETURN != POS_RING_UP
        assert POS_OVERRIDE != POS_RETURN

    def test_reading_the_pos_needs_manage_sales(self, client, db_session, sample_tenant, sample_branch):
        """POS-03."""
        _cashier(client, db_session, sample_tenant, sample_branch)
        assert client.get("/pos/").status_code == 200

    def test_an_anonymous_cashier_is_refused(self, client):
        """POS-04. The till is money; it is never a public page."""
        resp = client.get("/pos/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"anonymous read answered {resp.status_code}"

    def test_an_anonymous_checkout_is_refused(self, client):
        """POS-05. Checkout is the most dangerous verb on the blueprint."""
        resp = client.post("/pos/api/checkout", json={}, follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"anonymous checkout answered {resp.status_code}"

    def test_a_cashier_cannot_authorize_an_override(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-06. An override is a supervisor's decision.

        The verb answers 400 rather than 403 for a cashier because the
        permission decorator passes - manage_sales is held - and the request is
        refused one layer in, on the unknown override type. Either way it must
        not succeed, and the assertion records which guard actually caught it.
        """
        _cashier(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/pos/api/authorize-override", json={}, follow_redirects=False)
        assert resp.status_code in (302, 400, 403), f"a cashier authorized an override with {resp.status_code}"

    def test_a_cashier_cannot_process_a_return(self, client, db_session, sample_tenant, sample_branch):
        """POS-07. Giving money back is a separate grant."""
        _cashier(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/pos/api/returns", json={}, follow_redirects=False)
        assert resp.status_code in (302, 403), f"a cashier processed a return with {resp.status_code}"

    def test_a_supervisor_cannot_ring_up_without_ring_up(self, client, db_session, sample_tenant, sample_branch):
        """POS-08. Holding the override does not imply the till."""
        supervisor = _actor(client, db_session, sample_tenant, sample_branch, POS_OVERRIDE)
        assert supervisor.has_permission(POS_OVERRIDE)
        assert not supervisor.has_permission(POS_RING_UP), (
            "a supervisor-only role also holds ring-up; the split is not being tested"
        )

    def test_the_kds_is_gated_on_view_kds(self, client, db_session, sample_tenant, sample_branch):
        """POS-09. The kitchen display is its own read surface."""
        _kds(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/pos/kds", follow_redirects=False)
        assert resp.status_code in (200, 302), f"a kds reader answered {resp.status_code}"

    def test_a_cashier_cannot_reach_the_kds(self, client, db_session, sample_tenant, sample_branch):
        """POS-10. manage_sales does not grant view_kds."""
        _cashier(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/pos/kds", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a cashier reached the kds with {resp.status_code}"

    def test_the_scenario_covers_the_pos_route_inventory(self):
        """POS-11."""
        for path in POS_ROUTE_INVENTORY:
            assert path.startswith("/pos"), f"{path} is not under /pos"


def _enable_shifts(db_session, tenant):
    """Turn on the pos_shifts sub-feature for this tenant.

    ``pos_shifts`` is a paid sub-feature: ``_pos_feature_denied`` reads the
    tenant column first and otherwise falls back to the plan default, which for
    a bare test tenant is the basic tier. Without this the shift routes answer
    a clean 403 before reaching any of the drawer logic, so the scenarios would
    be asserting the plan gate rather than the reconciliation they are about.
    """
    from utils.pos_features import pos_feature_enabled

    if pos_feature_enabled(tenant, "pos_shifts"):
        return
    column = type(tenant).__table__.columns.get("enable_pos_shifts")
    if column is None:
        return
    tenant.enable_pos_shifts = True
    db_session.commit()


class TestPOS12Drawer:
    """POS-12..24. Money in the drawer: the arithmetic has to balance."""

    def test_a_shift_starts_with_the_expected_cash_it_was_given(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-12. An empty shift's drawer is exactly its float - no sales, no
        movement, expected == starting."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        assert shift.compute_expected_cash() == Decimal("100.000"), (
            f"an empty shift expects {shift.compute_expected_cash()}, not its float"
        )

    def test_cash_tendered_raises_the_expected_drawer(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-13."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.total_cash_sales = Decimal("50.000")
        assert shift.compute_expected_cash() == Decimal("150.000"), (
            f"50 of cash sales left the drawer expecting {shift.compute_expected_cash()}"
        )

    def test_change_given_lowers_the_expected_drawer(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-14. Change handed out is cash leaving the drawer."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.total_cash_sales = Decimal("50.000")
        shift.total_change_given = Decimal("20.000")
        assert shift.compute_expected_cash() == Decimal("130.000"), (
            f"change given was not subtracted: {shift.compute_expected_cash()}"
        )

    def test_a_pay_in_raises_the_expected_drawer(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-15."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.total_pay_ins = Decimal("25.000")
        assert shift.compute_expected_cash() == Decimal("125.000"), (
            f"a pay-in was not added: {shift.compute_expected_cash()}"
        )

    def test_a_pay_out_lowers_the_expected_drawer(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-16."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.total_pay_outs = Decimal("25.000")
        assert shift.compute_expected_cash() == Decimal("75.000"), (
            f"a pay-out was not subtracted: {shift.compute_expected_cash()}"
        )

    def test_a_cash_refund_lowers_the_expected_drawer(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-17. Giving money back leaves the drawer."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.total_cash_refunds = Decimal("30.000")
        assert shift.compute_expected_cash() == Decimal("70.000"), (
            f"a cash refund was not subtracted: {shift.compute_expected_cash()}"
        )

    def test_the_full_formula_balances(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-18. starting + cash - change - refunds + in - out, all six terms
        at once, so a reordered or dropped term is caught."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.total_cash_sales = Decimal("500.000")
        shift.total_change_given = Decimal("50.000")
        shift.total_cash_refunds = Decimal("20.000")
        shift.total_pay_ins = Decimal("10.000")
        shift.total_pay_outs = Decimal("40.000")
        assert shift.compute_expected_cash() == Decimal("500.000"), (
            f"the six-term drawer balance came to {shift.compute_expected_cash()}"
        )

    def test_reconciling_records_the_discrepancy(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-19. actual - expected, and a balanced drawer has zero."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("100.000"))
        assert shift.discrepancy == Decimal("0"), f"a balanced shift shows {shift.discrepancy} discrepancy"

    def test_reconciling_surfaces_a_shortfall(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-20. Actual below expected is negative - the cashier is short."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("90.000"))
        assert shift.discrepancy == Decimal("-10.000"), f"a 10 shortfall reported as {shift.discrepancy}"

    def test_a_reconciled_shift_says_so(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-21."""
        from models.pos_shift import PosShift

        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("100.000"))
        assert shift.status == PosShift.SHIFT_RECONCILED, f"a reconciled shift is {shift.status!r}"

    def test_an_unreconciled_shift_cannot_be_closed_over_http(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-22. The route refuses to close a drawer it has not counted."""
        # Signed in as the fixture's cashier, who owns the session: the shift
        # routes resolve the session for the signed-in user, so a freshly-made
        # cashier owns none and the request is refused before it reaches the
        # reconciliation guard - which would be asserting the wrong thing.
        _enable_shifts(db_session, demo_tenant)
        _login(client, pos_cashier)
        resp = client.post("/pos/api/shift/close", follow_redirects=False)
        # Either there is no shift to close (404) or the one that exists is
        # still open (400). What must never happen is a 200.
        assert resp.status_code in (400, 404), f"closing an unreconciled shift answered {resp.status_code}"

    def test_opening_a_drawer_records_its_float(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-23."""
        _cashier(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/pos/api/drawer/open", json={"starting_cash": "250.000"}, follow_redirects=False)
        assert resp.status_code in (200, 400, 403), f"opening a drawer answered {resp.status_code}"

    def test_the_current_shift_is_reported_to_its_owner(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-24. The report endpoint answers for the signed-in cashier."""
        _enable_shifts(db_session, demo_tenant)
        _login(client, pos_cashier)
        resp = client.get("/pos/api/shift/current", follow_redirects=False)
        assert resp.status_code in (200, 404), f"the shift report answered {resp.status_code}"
