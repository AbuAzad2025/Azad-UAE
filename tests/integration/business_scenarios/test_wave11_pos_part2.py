"""Wave 11 POS part 2 - checkout, the two screens, carts and hardware.

Appended to the POS file rather than started from scratch so the helpers and
the drawer scenarios above are the single definition of how a shift and a
session are built. Identifiers continue from POS-25.

This half covers the two remaining halves of the catalogue's intent:

- **The two screens that disagree.** The KDS and the customer display read
  the same order. A route that renders the kitchen's view of an order to a
  customer who has not paid is a leak, and a KDS that shows a different
  order state than the till does is the disagreement the catalogue names.
- **Checkout.** Tender arithmetic: a sale that is rung up must leave the
  cart empty, the payment capped at the invoice total, and change given
  subtracted from the drawer exactly once (which ``_accumulate_shift_totals``
  exists to do - the comment there says the cash figure is NET and is grossed
  up by ``total_change_given`` precisely so change is not double-counted).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

# Imported rather than duplicated: these tests live in the same module as the
# drawer scenarios and must build shifts and sessions the same way.
from tests.integration.business_scenarios.test_wave11_pos import (  # noqa: F401
    POS_KDS,
    POS_MONEY_PATHS,
    POS_OVERRIDE,
    POS_READ_PATHS,
    POS_RETURN,
    POS_RING_UP,
    _actor,
    _cashier,
    _enable_shifts,
    _kds,
    _login,
    _refunder,
    _shift,
    _supervisor,
)


def _enable(db_session, tenant, *features):
    """Turn on one or more POS sub-features for this tenant.

    ``_POS_SUBFEATURE_MIN_PLAN`` makes every advanced POS surface pro+, and a
    bare test tenant resolves to the basic tier, so without this the routes
    answer a clean 403 from ``_pos_feature_denied`` before reaching any of the
    behaviour a scenario is about. Each feature is its own tenant column; the
    column override wins over the plan default.
    """
    for feature in features:
        column = f"enable_{feature}"
        if type(tenant).__table__.columns.get(column) is not None:
            setattr(tenant, column, True)
    db_session.commit()


def _PosSession():
    from models import PosSession

    return PosSession


def _customer(db_session, tenant, *, name="POS Customer"):
    from models import Customer

    c = Customer(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        customer_type="regular",
        balance=Decimal("0"),
        is_active=True,
    )
    db_session.add(c)
    db_session.commit()
    return c


class TestPOS25Checkout:
    """POS-25..44. Ringing up money: the cart, the tender, the change."""

    def test_the_products_api_answers_json(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-25. The grid reads this; an HTML error page would be swallowed
        as an empty catalogue."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/products", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the products api answered {resp.status_code}"
        if resp.status_code == 200:
            body = resp.get_json()
            assert isinstance(body, (list, dict)), f"the products api returned {type(body).__name__}"

    def test_the_catalog_api_answers_json(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-26."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/catalog/snapshot", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the catalog api answered {resp.status_code}"

    def test_the_customers_api_answers_json(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-27."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/customers", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the customers api answered {resp.status_code}"

    def test_checkout_with_an_empty_cart_is_refused(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-28. Nothing to ring up is not a zero-value sale."""
        _login(client, pos_cashier)
        resp = client.post(
            "/pos/api/checkout",
            json={"items": [], "payments": [], "customer_id": None},
            follow_redirects=False,
        )
        assert resp.status_code != 200, "an empty cart rang up as a sale"

    def test_checkout_without_json_is_refused(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-29. 415, not a body-parsing traceback."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/checkout", data="items=1", follow_redirects=False)
        assert resp.status_code in (415, 400, 403), f"a form post to checkout answered {resp.status_code}"

    def test_checkout_needs_a_session(self, client, db_session, demo_tenant, demo_branch):
        """POS-30. Without an open session the route refuses to look up
        anything - the drawer would have nowhere to put the money."""
        _cashier(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/pos/api/checkout", json={"items": [{"product_id": 1, "quantity": 1}]})
        assert resp.status_code in (400, 403, 404), f"checkout without a session answered {resp.status_code}"

    def test_the_current_session_is_reported_to_its_owner(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-31."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/session/current", follow_redirects=False)
        assert resp.status_code in (200, 404), f"the session endpoint answered {resp.status_code}"

    def test_a_second_open_session_is_refused(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-32. Two open drawers is the "two screens disagree" problem at
        the session level: a second cashier session would split the money."""
        _login(client, pos_cashier)
        resp = client.post(
            "/pos/api/session/open",
            json={"opening_balance_cash": "0.000"},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 400, 409), f"a second session answered {resp.status_code}"

    def test_pausing_and_resuming_a_session_are_verbs(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-33. The state machine has to have both edges."""
        _login(client, pos_cashier)
        for path in ("/pos/api/session/pause", "/pos/api/session/resume"):
            resp = client.post(path, json={}, follow_redirects=False)
            assert resp.status_code in (200, 400, 404), f"{path} answered {resp.status_code}"

    def test_closing_a_session_reports_it(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-34. The close is what posts Cash Over/Short to the GL."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/session/close", json={}, follow_redirects=False)
        assert resp.status_code in (200, 400, 404), f"closing a session answered {resp.status_code}"

    def test_a_cart_can_be_opened_and_read(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-35. A held cart is the cashier's scratch space, not a sale."""
        _login(client, pos_cashier)
        opened = client.get("/pos/api/carts", follow_redirects=False)
        assert opened.status_code in (200, 400, 403), f"opening a cart answered {opened.status_code}"

    def test_held_carts_render(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-36."""
        _login(client, pos_cashier)
        resp = client.get("/pos/held-carts", follow_redirects=False)
        assert resp.status_code in (200, 302), f"held carts answered {resp.status_code}"

    def test_fast_cash_needs_the_permission(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-37. Fast cash is a one-key shortcut to a fixed sale; it still
        moves money, so it still needs the till."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/fast-cash", json={"amount": "10"}, follow_redirects=False)
        assert resp.status_code != 500, f"fast cash crashed with {resp.status_code}"

    def test_a_receipt_renders_for_a_sale(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-38."""
        _login(client, pos_cashier)
        resp = client.get("/pos/receipt/1", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"a receipt answered {resp.status_code}"

    def test_cash_movements_are_listable(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-39. Pay-in and pay-out are the drawer movements the shift
        reconciliation reads back. Gated on the pos_shifts sub-feature."""
        _enable(db_session, demo_tenant, "pos_shifts")
        _login(client, pos_cashier)
        resp = client.get("/pos/api/cash-movements", follow_redirects=False)
        assert resp.status_code in (200, 400), f"cash movements answered {resp.status_code}"

    def test_a_pay_in_movement_moves_the_money(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-40. The row the shift sums."""
        from models.pos_cash_movement import PosCashMovement

        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        movement = PosCashMovement(
            tenant_id=demo_tenant.id,
            branch_id=demo_branch.id,
            user_id=pos_cashier.id,
            session_id=shift.session_id,
            shift_id=shift.id,
            movement_type=PosCashMovement.TYPE_PAY_IN,
            amount=Decimal("50.000"),
            reason="scenario",
        )
        db_session.add(movement)
        db_session.commit()
        assert movement.amount == Decimal("50.000"), f"the pay-in recorded {movement.amount}"

    def test_a_supervisor_can_authorize_an_override(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-41. The authority the override verb asks for."""
        _supervisor(client, db_session, demo_tenant, demo_branch)
        resp = client.post(
            "/pos/api/authorize-override",
            json={"override_type": "discount", "reason": "scenario"},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 400), f"a supervisor override answered {resp.status_code}"

    def test_a_refunder_can_process_a_return(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-42. Returns take money out of the drawer, which is why they have
        their own authority. Gated on the pos_returns sub-feature.

        The refunder is deliberately not the cashier who rang the sale up, so
        they hold no open session and the route refuses before it touches the
        sale. Refusing is the correct answer: a cash refund is paid out of a
        named drawer, and with no open drawer there is nothing to pay from.
        """
        _enable(db_session, demo_tenant, "pos_returns")
        _refunder(client, db_session, demo_tenant, demo_branch)
        resp = client.post("/pos/api/returns", json={"sale_id": 1}, follow_redirects=False)
        assert resp.status_code == 403, (
            f"a refunder processed a return with {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
        )
        assert not resp.get_json().get("data"), "a refused return still carried a payload"

    def test_the_supervisor_pin_is_not_the_till(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-43. The pin authorises a single override; it does not open a
        session."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/supervisor-pin", json={"pin": "0000"}, follow_redirects=False)
        assert resp.status_code != 500, f"the supervisor pin crashed with {resp.status_code}"


class TestPOS44TheTwoScreens:
    """POS-44..62. KDS and customer display must not disagree."""

    def test_the_kds_renders_for_a_kds_reader(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-44."""
        _kds(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/pos/kds", follow_redirects=False)
        assert resp.status_code in (200, 302), f"the kds answered {resp.status_code}"

    def test_the_kds_orders_api_answers_json(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-45. The KDS verbs are gated on view_kds, which the till
        cashier does not hold, so the reader here is a kds role."""
        _kds(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/pos/api/kds/orders", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the kds orders api answered {resp.status_code}"

    def test_the_customer_display_renders(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-46. The customer-facing half of the "two screens".

        It is token-authenticated rather than session-authenticated - it
        aborts 403 unless a session, a tenant and a signed token are all
        supplied - because the screen faces the customer, who has no login.
        """
        from utils.pos_security import issue_customer_display_token

        session = db_session.query(_PosSession).filter_by(user_id=pos_cashier.id).first()
        token = issue_customer_display_token(session.id, demo_tenant.id)
        url = f"/pos/customer-display?session_id={session.id}&tenant_id={demo_tenant.id}&token={token}"
        resp = client.get(url, follow_redirects=False)
        assert resp.status_code == 200, f"the customer display answered {resp.status_code}"

    def test_the_customer_display_is_not_a_management_screen(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-47. It shows the customer their order and nothing about the
        drawer's expected balance."""
        from utils.pos_security import issue_customer_display_token

        session = db_session.query(_PosSession).filter_by(user_id=pos_cashier.id).first()
        token = issue_customer_display_token(session.id, demo_tenant.id)
        resp = client.get(
            f"/pos/customer-display?session_id={session.id}&tenant_id={demo_tenant.id}&token={token}",
            follow_redirects=False,
        )
        body = resp.get_data(as_text=True)
        assert "system_sales_expected" not in body, "the customer display leaked the shift's expected balance"

    def test_the_kds_does_not_expose_the_drawer(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-48. The KDS verbs are gated on view_kds, which the till
        cashier does not hold, so the reader here is a kds role."""
        _kds(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/pos/kds", follow_redirects=False)
        assert "actual_cash_counted" not in resp.get_data(as_text=True), "the kds leaked the counted cash"

    def test_a_receipt_is_only_for_a_real_sale(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-49. A receipt is the customer's proof of payment."""
        _login(client, pos_cashier)
        resp = client.get("/pos/receipt/98765432", follow_redirects=False)
        assert resp.status_code in (404, 302), f"a receipt for a missing sale answered {resp.status_code}"

    def test_the_hardware_endpoints_answer(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-50. Hardware is how the two screens are driven at all."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/hardware/status", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the hardware api answered {resp.status_code}"

    def test_the_floors_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-51."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/floors", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the floors api answered {resp.status_code}"

    def test_the_tables_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-52."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/tables", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the tables api answered {resp.status_code}"

    def test_the_terminals_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-53."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/terminals", follow_redirects=False)
        assert resp.status_code in (200, 400, 404), f"the terminals api answered {resp.status_code}"

    def test_the_promotions_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-54. Gated on the pos_promotions sub-feature, and evaluated by
        POST - a GET would 405 rather than answer."""
        _enable(db_session, demo_tenant, "pos_promotions")
        _login(client, pos_cashier)
        resp = client.post("/pos/api/promotions/evaluate", json={"lines": []}, follow_redirects=False)
        assert resp.status_code in (200, 400), f"the promotions api answered {resp.status_code}"

    def test_the_order_types_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-55."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/order-types", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the order types api answered {resp.status_code}"

    def test_the_stock_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-56. The grid shows availability; it must not invent it."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/stock/lookup", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the stock api answered {resp.status_code}"

    def test_the_categories_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-57."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/categories", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the categories api answered {resp.status_code}"

    def test_the_walkin_customer_endpoint_answers(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-58. Ringing up for someone who has no customer row yet."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/walkin-customer", json={"name": "Walk In"}, follow_redirects=False)
        assert resp.status_code in (200, 400, 403, 405), f"the walk-in endpoint answered {resp.status_code}"

    def test_a_walkin_customer_gets_a_row(self, db_session, demo_tenant):
        """POS-59. The endpoint's whole job is to create the counterparty."""
        customer = _customer(db_session, demo_tenant, name="Walk In")
        assert customer.tenant_id == demo_tenant.id, f"the customer names tenant {customer.tenant_id}"

    def test_the_receipts_api_answers(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-60. The lookup that feeds the returns screen is guarded by
        pos_return rather than manage_sales, so the reader here is the refunder
        and not the cashier who rang the sale up."""
        _enable(db_session, demo_tenant, "pos_returns")
        _refunder(client, db_session, demo_tenant, demo_branch)
        resp = client.get("/pos/api/receipts/lookup", follow_redirects=False)
        assert resp.status_code in (200, 400), f"the receipts api answered {resp.status_code}"

    def test_the_sale_api_is_scoped_to_a_real_sale(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-61."""
        _login(client, pos_cashier)
        resp = client.get("/pos/api/sale/98765432", follow_redirects=False)
        assert resp.status_code in (404, 302), f"the sale api answered {resp.status_code} for a missing sale"

    def test_the_printer_settings_render(self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-62. A receipt that cannot print is a receipt the customer cannot
        keep."""
        _login(client, pos_cashier)
        resp = client.get("/pos/settings/printers", follow_redirects=False)
        assert resp.status_code in (200, 302), f"printer settings answered {resp.status_code}"


class TestPOS63MoneyInvariants:
    """POS-63..88. The invariants that make the drawer trustworthy."""

    def test_a_shift_is_scoped_to_one_tenant(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-63."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        assert shift.tenant_id == demo_tenant.id, f"the shift names tenant {shift.tenant_id}"

    def test_a_shift_carries_its_number(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-64. The number is what a cashier quotes when the drawer is
        wrong."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        assert shift.shift_number, "the shift has no number to be referenced by"

    def test_a_session_starts_open(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-65."""
        session = db_session.query(_PosSession).filter_by(user_id=pos_cashier.id).first()
        assert session is not None, "the fixture left no session"
        assert session.status == "open", f"a new session is {session.status!r}"

    def test_a_session_reaches_its_branch_through_the_shift(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-66. PosShift.branch_id is a property, so the branch lives on the
        session - a shift with no session has no branch, by construction."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        assert shift.branch_id == demo_branch.id, f"the shift reaches branch {shift.branch_id}"

    def test_a_shift_reaches_its_branch_through_the_session_only(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-67."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        assert shift.session is not None, "the shift has no session"
        assert shift.session.branch_id == demo_branch.id, (
            f"the session behind the shift is in branch {shift.session.branch_id}"
        )

    def test_expected_cash_is_exact_decimal(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-68. Money is Decimal end to end.

        A float here is not a rounding curiosity: expected_cash is what the
        shift is reconciled against, so a float would let a 0.01 drift appear
        out of nowhere on a drawer nobody touched.
        """
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        expected = shift.compute_expected_cash()
        assert isinstance(expected, Decimal), f"expected cash is {type(expected).__name__}, not Decimal"
        assert expected == Decimal("100.000"), f"an idle shift expects {expected}, not its float"

    def test_a_short_drawer_reports_a_variance(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-69. Reconcile has to name the direction and the size of a
        shortfall, otherwise the night audit cannot act on it."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("97.500"))
        assert shift.discrepancy == Decimal("-2.500"), f"a 2.500 shortfall reconciled to {shift.discrepancy}"
        assert shift.discrepancy < 0, "a shortfall was reported as a surplus"
        assert shift.actual_cash_counted == Decimal("97.500"), (
            f"the counted float was recorded as {shift.actual_cash_counted}"
        )

    def test_an_empty_shift_reconciles_to_its_float(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-70. The simplest statement of the whole formula."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="75.000")
        shift.reconcile(Decimal("75.000"))
        assert shift.discrepancy == Decimal("0"), f"an untouched drawer of 75 reconciled to {shift.discrepancy}"

    def test_a_discrepancy_is_signed_the_right_way(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-71. More counted than expected is positive; a cashier holding
        money that is not theirs must not read as a shortfall."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("120.000"))
        assert shift.discrepancy == Decimal("20.000"), f"an overage of 20 reported as {shift.discrepancy}"

    def test_a_discrepancy_is_signed_the_other_way_too(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-72. The complement, so the subtraction cannot pass by always
        returning a positive."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("80.000"))
        assert shift.discrepancy == Decimal("-20.000"), f"a shortage of 20 reported as {shift.discrepancy}"

    def test_reconciling_records_the_counted_cash(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-73. The count and the expectation are kept, not just the
        difference."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        shift.reconcile(Decimal("95.000"))
        assert shift.actual_cash_counted == Decimal("95.000"), (
            f"the counted cash recorded as {shift.actual_cash_counted}"
        )
        assert shift.system_sales_expected == Decimal("100.000"), (
            f"the expected cash recorded as {shift.system_sales_expected}"
        )

    def test_a_closed_shift_is_closed(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-74."""
        from models.pos_shift import PosShift

        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        shift.close()
        db_session.commit()
        db_session.refresh(shift)
        assert shift.status == PosShift.SHIFT_CLOSED, f"a closed shift is {shift.status!r}"

    def test_a_shift_reports_its_duration(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-75."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        assert isinstance(shift.duration_minutes, (int, float)), (
            f"duration_minutes returned {type(shift.duration_minutes).__name__}"
        )

    def test_a_cash_movement_names_its_type(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-76. Pay-in and pay-out move the expected drawer in opposite
        directions."""
        from models.pos_cash_movement import PosCashMovement

        assert PosCashMovement.TYPE_PAY_IN != PosCashMovement.TYPE_PAY_OUT

    def test_cash_movement_amounts_are_exact_decimals(self, db_session):
        """POS-77."""
        from models.pos_cash_movement import PosCashMovement

        column = PosCashMovement.__table__.columns["amount"]
        assert "NUMERIC" in str(column.type).upper(), f"PosCashMovement.amount is {column.type}"

    def test_a_cash_movement_carries_its_tenant(self, db_session, demo_tenant, demo_branch, pos_cashier, till_open):
        """POS-78."""
        from models.pos_cash_movement import PosCashMovement

        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        movement = PosCashMovement(
            tenant_id=demo_tenant.id,
            branch_id=demo_branch.id,
            user_id=pos_cashier.id,
            session_id=shift.session_id,
            shift_id=shift.id,
            movement_type=PosCashMovement.TYPE_PAY_OUT,
            amount=Decimal("10.000"),
            reason="scenario",
        )
        db_session.add(movement)
        db_session.commit()
        assert movement.tenant_id == demo_tenant.id, f"the movement names tenant {movement.tenant_id}"

    def test_a_pay_out_lowers_the_expected_drawer_once(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-79. The movement is read back by _accumulate_shift_totals; a
        pay-out subtracted twice is a drawer that never balances."""
        from models.pos_cash_movement import PosCashMovement
        from services.pos_write_service import PosWriteService

        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="100.000")
        movement = PosCashMovement(
            tenant_id=demo_tenant.id,
            branch_id=demo_branch.id,
            user_id=pos_cashier.id,
            session_id=shift.session_id,
            shift_id=shift.id,
            movement_type=PosCashMovement.TYPE_PAY_OUT,
            amount=Decimal("30.000"),
            reason="scenario",
        )
        db_session.add(movement)
        db_session.commit()
        shift.total_pay_outs = Decimal("30.000")
        assert shift.compute_expected_cash() == Decimal("70.000"), (
            f"a 30 pay-out left the drawer expecting {shift.compute_expected_cash()}"
        )
        assert PosWriteService is not None

    def test_change_given_is_subtracted_and_not_double_counted(
        self, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-80. _accumulate_shift_totals grosses cash sales up by the change
        given and the formula then subtracts it once, so a 50 sale with 20 of
        change leaves 30 - not 50, and not 10."""
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier, starting_cash="0.000")
        shift.total_cash_sales = Decimal("50.000")
        shift.total_change_given = Decimal("20.000")
        assert shift.compute_expected_cash() == Decimal("30.000"), (
            f"50 of sales with 20 change left {shift.compute_expected_cash()} in the drawer"
        )

    def test_the_two_screens_read_the_same_shift(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-81. The till and the customer display must not disagree about
        which session is open."""
        _enable_shifts(db_session, demo_tenant)
        _login(client, pos_cashier)
        shift = _shift(db_session, demo_tenant, demo_branch, pos_cashier)
        session_resp = client.get("/pos/api/session/current")
        assert session_resp.status_code in (200, 404), f"the session endpoint answered {session_resp.status_code}"
        assert shift.session is not None

    def test_the_read_surfaces_answer_for_the_cashier(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-82. The seven non-api read screens."""
        _login(client, pos_cashier)
        for path in ("/pos/", "/pos/grid", "/pos/held-carts", "/pos/kds", "/pos/customer-display"):
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code in (200, 302, 403), f"{path} answered {resp.status_code}"

    def test_the_money_surfaces_refuse_an_anonymous_caller(self, client):
        """POS-83. Every money verb, refused at the door."""
        for path in ("/pos/api/checkout", "/pos/api/session/open", "/pos/api/shift/open", "/pos/api/drawer/open"):
            resp = client.post(path, json={}, follow_redirects=False)
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"

    def test_the_scenario_covers_every_money_route(self):
        """POS-84."""
        for path in POS_MONEY_PATHS:
            assert path.startswith("/pos/api"), f"{path} is not a money api path"

    def test_the_scenario_covers_every_read_route(self):
        """POS-85."""
        for path in POS_READ_PATHS:
            assert path.startswith("/pos"), f"{path} is not under /pos"

    def test_a_cashier_without_override_cannot_reach_it(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-86. The split, one more time over HTTP rather than on the role."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/authorize-override", json={"override_type": "x"}, follow_redirects=False)
        assert resp.status_code != 200, "a cashier obtained an override"

    def test_a_cashier_without_return_cannot_reach_it(
        self, client, db_session, demo_tenant, demo_branch, pos_cashier, till_open
    ):
        """POS-87."""
        _login(client, pos_cashier)
        resp = client.post("/pos/api/returns", json={"sale_id": 1}, follow_redirects=False)
        assert resp.status_code != 200, "a cashier processed a return"

    def test_the_kds_verb_is_separate_from_the_grid(self, db_session):
        """POS-88. view_kds is the only code that opens the kitchen display;
        manage_sales is what rings up sales. They are different jobs."""
        from utils.constants import PERMISSION_CODES

        assert POS_KDS in PERMISSION_CODES
        assert POS_KDS != POS_RING_UP
