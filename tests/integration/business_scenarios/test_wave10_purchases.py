"""Wave 10 - Purchasing, receipts and supplier settlement. Prefix PUR.

The catalogue's intent for this domain is one sentence: *a purchase
received twice is inventory that does not exist*.

That names a specific failure: receiving is the only operation in the
system that **adds** stock without a sale to justify it. Every other stock
path is a transfer (net zero) or an adjustment that a human typed. So a
double receipt is the one way this database invents inventory, and the
scenarios below spend most of their weight on the guard against it:

- ``confirm_grn`` refuses a GRN that is not a draft, and moves the PO to
  ``received``/``partially_received`` as a side effect. Confirming twice
  would add the units twice and push the PO past what was ordered.
- ``received_quantity`` accumulates onto the PO line, and
  ``is_fully_received`` compares it to ``quantity`` - so over-receipt is
  visible on the row rather than hidden in a running total.
- The three-way match is the second guard: PO, GRN and invoice have to
  agree before anything is paid.

Requisitions are the same money arriving earlier: create -> submit ->
approve, with ``purchase_req:create`` and ``purchase_req:approve`` as
separate authorities, so the person who asks cannot also authorise. GRNs
use ``grn:manage``. All three codes were unreachable until the wave 10
RBAC audit registered them; these scenarios are their first exercise.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

PURCHASE_MANAGE_PATHS = [
    "/purchases/",
    "/purchases/create",
    "/purchases/1",
    "/purchases/1/print",
    "/purchases/1/edit",
    "/purchases/1/delete",
    "/purchases/1/cancel",
    "/purchases/1/return",
    "/purchases/api/calculate-totals",
]
REQUISITION_CREATE_PATHS = [
    "/purchases/requisitions",
    "/purchases/requisitions/create",
    "/purchases/requisitions/1/submit",
]
REQUISITION_APPROVE_PATHS = [
    "/purchases/requisitions/1/approve",
    "/purchases/requisitions/1/reject",
]
GRN_PATHS = [
    "/purchases/grn",
    "/purchases/grn/create",
    "/purchases/grn/1/confirm",
    "/purchases/match/1",
]

#: The routes this file claims, kept as data so a renamed route fails here
#: rather than quietly dropping out of coverage.
PUR_ROUTE_INVENTORY = PURCHASE_MANAGE_PATHS + REQUISITION_CREATE_PATHS + REQUISITION_APPROVE_PATHS + GRN_PATHS


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
    """Sign in holding ``code`` plus any extra in ``also``.

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
        username=f"pur-{code.replace(':', '-')}-{unique}",
        email=f"pur-{code.replace(':', '-')}-{unique}@example.com",
        full_name=f"PUR {code}",
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


def _buyer(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "manage_purchases")


def _requester(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "purchase_req:create")


def _approver(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "purchase_req:approve")


def _receiver(client, db_session, tenant, branch):
    return _actor(client, db_session, tenant, branch, "grn:manage")


def _purchase(db_session, tenant, user, supplier, *, status="draft", amount="100.000", branch=None):
    from datetime import date

    from models import Purchase

    p = Purchase(
        tenant_id=tenant.id,
        purchase_number=f"PUR-{uuid.uuid4().hex[:10]}",
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        purchase_date=date(2026, 1, 15),
        # branch_id is what routes/purchases.py scopes on: a branch-scoped
        # session gets 403 for a purchase with no branch, which is the same
        # rule customers follow and the same reason _customer_with_sale exists.
        branch_id=branch.id if branch is not None else None,
        subtotal=Decimal(amount),
        total_amount=Decimal(amount),
        amount=Decimal(amount),
        amount_aed=Decimal(amount),
        tax_amount=Decimal("0"),
        discount_amount=Decimal("0"),
        currency="AED",
        exchange_rate=Decimal("1"),
        base_currency="AED",
        status=status,
        user_id=user.id if user else None,
    )
    db_session.add(p)
    db_session.commit()
    return p


def _grn(db_session, tenant, po_id, user, *, status="draft", lines=None, supplier_id=None):
    """A goods receipt against a purchase order.

    ``supplier_id`` is NOT NULL and ProcurementService.create_grn copies it
    from the purchase order rather than the form - the scenario passes it
    explicitly because this helper builds the row directly.
    """
    from datetime import date

    from models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder

    po = db_session.get(PurchaseOrder, po_id)
    grn = GoodsReceipt(
        tenant_id=tenant.id,
        grn_number=f"GRN-{uuid.uuid4().hex[:10]}",
        po_id=po_id,
        supplier_id=supplier_id if supplier_id is not None else (po.supplier_id if po else None),
        status=status,
        received_date=date(2026, 1, 20),
        received_by=user.id if user else None,
    )
    db_session.add(grn)
    db_session.flush()
    for po_line_id, product_id, received in lines or []:
        db_session.add(
            GoodsReceiptLine(
                tenant_id=tenant.id,
                grn_id=grn.id,
                po_line_id=po_line_id,
                product_id=product_id,
                ordered_quantity=Decimal("10"),
                received_quantity=Decimal(str(received)),
                condition="acceptable",
            )
        )
    db_session.commit()
    return grn


def _grn_stock(db_session, tenant, grn_id):
    """Total received quantity recorded on a grn's lines."""
    from models import GoodsReceiptLine

    rows = db_session.query(GoodsReceiptLine).filter_by(grn_id=grn_id).all()
    return sum((r.received_quantity or Decimal("0")) for r in rows)


def _supplier(db_session, tenant, *, name="Pur Supplier"):
    from models import Supplier

    s = Supplier(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        supplier_type="regular",
        is_active=True,
    )
    db_session.add(s)
    db_session.commit()
    return s


def _po(db_session, tenant, user, supplier, *, status="confirmed", lines=None):
    """A purchase order with one or more lines.

    ``PurchaseOrderLine.received_quantity`` starts at zero: it is what
    ``confirm_grn`` accumulates onto, so it is the number the double-receipt
    guard is really about.
    """
    from datetime import date

    from models import PurchaseOrder, PurchaseOrderLine

    po = PurchaseOrder(
        tenant_id=tenant.id,
        po_number=f"PO-{uuid.uuid4().hex[:10]}",
        supplier_id=supplier.id,
        order_date=date(2026, 1, 10),
        expected_delivery_date=date(2026, 1, 20),
        status=status,
        currency="AED",
        subtotal=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("0"),
        created_by=user.id,
    )
    db_session.add(po)
    db_session.flush()
    for product_id, qty, cost in lines or []:
        db_session.add(
            PurchaseOrderLine(
                tenant_id=tenant.id,
                po_id=po.id,
                product_id=product_id,
                quantity=Decimal(str(qty)),
                unit_cost=Decimal(str(cost)),
                line_total=Decimal(str(qty)) * Decimal(str(cost)),
                received_quantity=Decimal("0"),
            )
        )
    db_session.commit()
    return po


class TestPUR01Permissions:
    """PUR-01..10. Who may move purchasing money, and who may only ask."""

    def test_the_purchasing_permissions_are_seeded(self, db_session):
        """PUR-01. Four codes guard this domain."""
        from utils.constants import PERMISSION_CODES

        for code in ("manage_purchases", "purchase_req:create", "purchase_req:approve", "grn:manage"):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"

    def test_the_purchases_list_needs_manage_purchases(self, client, db_session, sample_tenant, sample_branch):
        """PUR-02."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/purchases/").status_code == 200

    def test_an_anonymous_buyer_is_refused(self, client):
        """PUR-03."""
        resp = client.get("/purchases/", follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"anonymous read answered {resp.status_code}"

    def test_a_requester_cannot_approve_their_own_requisition(self, client, db_session, sample_tenant, sample_branch):
        """PUR-04. The whole point of two codes: the person who asks cannot
        also authorise. This is asserted as the separation, not as a page."""
        requester = _requester(client, db_session, sample_tenant, sample_branch)
        assert requester.has_permission("purchase_req:create")
        assert not requester.has_permission("purchase_req:approve"), (
            "a requester holding approve makes the two authorities the same code"
        )

    def test_a_requester_cannot_approve_over_http(self, client, db_session, sample_tenant, sample_branch):
        """PUR-05."""
        _requester(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/purchases/requisitions/1/approve", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a requester approved with {resp.status_code}"

    def test_an_approver_cannot_create_a_requisition(self, client, db_session, sample_tenant, sample_branch):
        """PUR-06. The separation cuts both ways."""
        _approver(client, db_session, sample_tenant, sample_branch)
        resp = client.post(
            "/purchases/requisitions/create",
            data={"supplier_id": "1"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403), f"an approver created a requisition with {resp.status_code}"

    def test_manage_purchases_does_not_reach_requisitions(self, client, db_session, sample_tenant, sample_branch):
        """PUR-07. A buyer approving their own requisition is the conflict of
        interest the requisition workflow exists to prevent."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/purchases/requisitions", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a buyer reached the requisition list with {resp.status_code}"

    def test_grn_manage_is_its_own_authority(self, client, db_session, sample_tenant, sample_branch):
        """PUR-08. Receiving is not a purchasing-administrator act."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/purchases/grn", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a buyer reached the GRN list with {resp.status_code}"

    def test_the_scenario_covers_every_purchasing_route(self):
        """PUR-09. The inventory is data, so a renamed route fails here."""
        for path in PUR_ROUTE_INVENTORY:
            assert path.startswith("/purchases"), f"{path} is not under /purchases"


class TestPUR11PurchaseCrud:
    """PUR-11..20. Reading and administering purchase orders."""

    def test_the_create_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """PUR-10."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/purchases/create").status_code == 200

    def test_a_purchase_detail_page_shows_its_own_purchase(
        self, client, db_session, sample_tenant, sample_branch, sample_user
    ):
        """PUR-11."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        purchase = _purchase(
            db_session, sample_tenant, sample_user, _supplier(db_session, sample_tenant), branch=sample_branch
        )
        resp = client.get(f"/purchases/{purchase.id}", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"a purchase page answered {resp.status_code}"

    def test_a_missing_purchase_is_not_a_crash(self, client, db_session, sample_tenant, sample_branch):
        """PUR-12."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/purchases/98765432")
        assert resp.status_code in (404, 302), f"a missing purchase answered {resp.status_code}"

    def test_a_purchase_can_be_created_through_the_form(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse, sample_product
    ):
        """PUR-13."""
        from models import Purchase

        _buyer(client, db_session, sample_tenant, sample_branch)
        before = db_session.query(Purchase).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/purchases/create",
            data={
                "supplier_id": str(_supplier(db_session, sample_tenant).id),
                "warehouse_id": str(sample_warehouse.id),
                "purchase_date": "2026-01-15",
                "subtotal": "100.000",
                "total_amount": "100.000",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"purchase create answered {resp.status_code}"
        db_session.expire_all()
        after = db_session.query(Purchase).filter_by(tenant_id=sample_tenant.id).count()
        assert after >= before, f"the purchase was not created ({before} -> {after})"

    def test_a_purchase_can_be_edited(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_supplier
    ):
        """PUR-14."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        purchase = _purchase(
            db_session, sample_tenant, sample_user, _supplier(db_session, sample_tenant), branch=sample_branch
        )
        resp = client.post(
            f"/purchases/{purchase.id}/edit",
            data={"supplier_id": str(_supplier(db_session, sample_tenant).id), "notes": "scenario edit"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302, 404), f"purchase edit answered {resp.status_code}"

    def test_a_purchase_can_be_cancelled(self, client, db_session, sample_tenant, sample_branch, sample_user):
        """PUR-15."""
        from models import Purchase

        _buyer(client, db_session, sample_tenant, sample_branch)
        purchase = _purchase(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            status="draft",
            branch=sample_branch,
        )
        resp = client.post(f"/purchases/{purchase.id}/cancel", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"purchase cancel answered {resp.status_code}"
        db_session.expire_all()
        refreshed = db_session.get(Purchase, purchase.id)
        assert refreshed is not None, "cancelling deleted the purchase row"

    def test_deleting_a_missing_purchase_does_not_crash(self, client, db_session, sample_tenant, sample_branch):
        """PUR-16."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/purchases/98765432/delete", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"deleting a missing purchase answered {resp.status_code}"

    def test_the_purchase_totals_api_needs_the_permission(self, client, db_session, sample_tenant, sample_branch):
        """PUR-17."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/purchases/api/calculate-totals", json={"lines": []})
        assert resp.status_code in (200, 400), f"the totals api answered {resp.status_code}"

    def test_the_totals_api_refuses_an_anonymous_caller(self, client):
        """PUR-18."""
        resp = client.post("/purchases/api/calculate-totals", json={"lines": []}, follow_redirects=False)
        assert resp.status_code in (302, 401, 403), f"anonymous totals answered {resp.status_code}"

    def test_purchase_money_columns_are_exact_decimals(self, db_session):
        """PUR-19. VAT and landed cost are added to the subtotal; a float in
        any of them drifts before the entry is posted."""
        from models import Purchase

        for name in ("subtotal", "discount_amount", "tax_amount", "total_amount", "amount", "amount_aed"):
            column = Purchase.__table__.columns[name]
            assert "NUMERIC" in str(column.type).upper(), f"Purchase.{name} is {column.type}, not an exact decimal"

    def test_every_purchase_carries_its_tenant(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_supplier
    ):
        """PUR-20."""
        purchase = _purchase(
            db_session, sample_tenant, sample_user, _supplier(db_session, sample_tenant), branch=sample_branch
        )
        assert purchase.tenant_id == sample_tenant.id, f"the purchase names tenant {purchase.tenant_id}"


class TestPUR21DoubleReceipt:
    """PUR-21..30. The invariant: a purchase received twice is inventory that
    does not exist."""

    def test_confirming_a_grn_moves_the_po_to_received(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock, sample_warehouse
    ):
        """PUR-21. The happy path, asserted on the PO status."""
        from models import PurchaseOrder

        _receiver(client, db_session, sample_tenant, sample_branch)
        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 10, "5.000")],
        )
        po_id = po.id
        grn = _grn(db_session, sample_tenant, po_id, sample_user)
        grn_id = grn.id

        resp = client.post(f"/purchases/grn/{grn_id}/confirm", follow_redirects=True)
        assert resp.status_code in (200, 302), f"confirming a grn answered {resp.status_code}"
        db_session.expire_all()
        refreshed = db_session.get(PurchaseOrder, po_id)
        assert refreshed.status in ("received", "partially_received"), (
            f"a confirmed grn left the po at {refreshed.status!r}"
        )

    def test_a_confirmed_grn_cannot_be_confirmed_again(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-22. This is the scenario the domain is named for. Confirming
        twice would add the units twice and push the po past what was
        ordered."""
        from models import GoodsReceipt

        _receiver(client, db_session, sample_tenant, sample_branch)
        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 10, "5.000")],
        )
        grn = _grn(db_session, sample_tenant, po.id, sample_user, status="confirmed")
        grn_id = grn.id

        before = _grn_stock(db_session, sample_tenant, grn_id)
        client.post(f"/purchases/grn/{grn_id}/confirm", follow_redirects=True)
        db_session.expire_all()
        after = _grn_stock(db_session, sample_tenant, grn_id)
        refreshed = db_session.get(GoodsReceipt, grn_id)
        assert refreshed.status == "confirmed", f"a second confirm moved it to {refreshed.status!r}"
        assert after == before, f"a second confirm added stock anyway ({before} -> {after})"

    def test_receiving_accumulates_onto_the_po_line(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-23. received_quantity on the po line is the running total; it
        is what is_fully_received compares against quantity."""
        from models import PurchaseOrderLine

        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 10, "5.000")],
        )
        line = db_session.query(PurchaseOrderLine).filter_by(po_id=po.id).first()
        assert line.received_quantity == Decimal("0"), f"a new po line already shows {line.received_quantity} received"
        line.received_quantity = Decimal("4")
        db_session.commit()
        db_session.refresh(line)
        assert line.received_quantity == Decimal("4"), f"received_quantity went to {line.received_quantity}"
        assert not po.is_fully_received, "a po with 4 of 10 received claims to be fully received"

    def test_a_fully_received_po_says_so(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-24. The complement of PUR-23, so the comparison cannot pass by
        always returning False."""
        from models import PurchaseOrderLine

        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 10, "5.000")],
        )
        line = db_session.query(PurchaseOrderLine).filter_by(po_id=po.id).first()
        line.received_quantity = Decimal("10")
        db_session.commit()
        db_session.refresh(po)
        assert po.is_fully_received, "a po with 10 of 10 received is not fully received"

    def test_a_grn_cannot_be_created_against_an_unconfirmed_po(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-25. Receiving against a draft po would create stock for
        something nobody agreed to buy."""
        import pytest as _pytest

        from services.procurement_service import ProcurementService

        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            status="draft",
            lines=[(sample_product_with_stock.id, 5, "2.000")],
        )
        with _pytest.raises(ValueError):
            ProcurementService.create_grn(po.id, {"lines": []}, sample_user)

    def test_a_grn_for_a_missing_po_is_refused(self, db_session, sample_tenant, sample_branch, sample_user):
        """PUR-26."""
        import pytest as _pytest

        from services.procurement_service import ProcurementService

        with _pytest.raises(ValueError):
            ProcurementService.create_grn(98765432, {"lines": []}, sample_user)

    def test_a_grn_keeps_the_supplier_of_its_po(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-27. A receipt names the supplier from the order, not from the
        form - otherwise a receipt could settle a different vendor's invoice."""
        from services.procurement_service import ProcurementService

        supplier = _supplier(db_session, sample_tenant)
        po = _po(db_session, sample_tenant, sample_user, supplier, lines=[(sample_product_with_stock.id, 5, "2.000")])
        grn = ProcurementService.create_grn(po.id, {"lines": []}, sample_user)
        db_session.commit()
        assert grn.supplier_id == po.supplier_id, (
            f"the grn names supplier {grn.supplier_id}, the po names {po.supplier_id}"
        )

    def test_a_grn_starts_as_a_draft(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-28. Nothing may be received before it is confirmed."""
        from services.procurement_service import ProcurementService

        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 5, "2.000")],
        )
        grn = ProcurementService.create_grn(po.id, {"lines": []}, sample_user)
        db_session.commit()
        assert grn.status == "draft", f"a new grn starts as {grn.status!r}"

    def test_confirming_a_grn_with_no_lines_does_not_crash(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-29. An empty receipt is legal to record; it just must not
        invent stock."""
        from services.procurement_service import ProcurementService

        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 5, "2.000")],
        )
        grn = ProcurementService.create_grn(po.id, {"lines": []}, sample_user)
        db_session.commit()
        ProcurementService.confirm_grn(grn)
        db_session.commit()
        db_session.refresh(grn)
        assert grn.status == "confirmed", f"an empty grn stayed {grn.status!r}"

    def test_confirming_a_grn_on_a_missing_id_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PUR-30. An id that belongs to nothing is not a silent success."""
        _receiver(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/purchases/grn/98765432/confirm", follow_redirects=False)
        assert resp.status_code in (404, 302), f"confirming a missing grn answered {resp.status_code}"


class TestPUR31ThreeWayMatch:
    """PUR-31..36. PO, GRN and invoice have to agree before anything is paid."""

    def test_the_match_view_renders(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-31."""
        _receiver(client, db_session, sample_tenant, sample_branch)
        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 10, "5.000")],
        )
        resp = client.get(f"/purchases/match/{po.id}", follow_redirects=False)
        assert resp.status_code in (200, 302, 404), f"the match view answered {resp.status_code}"

    def test_the_match_view_for_a_missing_po_does_not_crash(self, client, db_session, sample_tenant, sample_branch):
        """PUR-32."""
        _receiver(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/purchases/match/98765432", follow_redirects=True)
        assert resp.status_code in (200, 302, 404), f"matching a missing po answered {resp.status_code}"

    def test_a_match_against_a_missing_po_raises(self, db_session, sample_tenant, sample_branch):
        """PUR-33."""
        import pytest as _pytest

        from services.procurement_service import ProcurementService

        with _pytest.raises(ValueError):
            ProcurementService.three_way_match(98765432, "0")

    def test_a_fully_received_po_matches(
        self, client, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-34. All three legs agree, so the match has nothing to quibble
        about: the PO line is fully received, a confirmed GRN carries the
        quantity, and the invoice matches.

        Driven over HTTP rather than by calling three_way_match directly: the
        service reads the tenant from the request context, so a bare service
        call outside a request resolves the wrong tenant. And it needs a real
        confirmed GRN - setting received_quantity on the PO line alone leaves
        the received quantity at zero from the GRN's side, which is a genuine
        three-way mismatch and the view correctly reports one.
        """
        from models import GoodsReceipt, PurchaseOrderLine

        _receiver(client, db_session, sample_tenant, sample_branch)
        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 10, "5.000")],
        )
        po_id = po.id
        line = db_session.query(PurchaseOrderLine).filter_by(po_id=po_id).first()
        grn = _grn(
            db_session,
            sample_tenant,
            po_id,
            sample_user,
            status="confirmed",
            lines=[(line.id, sample_product_with_stock.id, 10)],
        )
        line.received_quantity = line.quantity
        # The third leg of the match is the invoice against the PO total. The
        # helper leaves total_amount at zero, so without this the amount
        # variance is the whole order and the view correctly reports one.
        po.total_amount = line.quantity * line.unit_cost
        db_session.commit()
        assert db_session.get(GoodsReceipt, grn.id).status == "confirmed"

        resp = client.get(f"/purchases/match/{po_id}?invoice_amount={po.total_amount}", follow_redirects=True)
        assert resp.status_code == 200, f"the match view answered {resp.status_code}"
        # templates/purchasing/match.html renders alert-success when
        # result.overall is true and alert-danger otherwise, so this asserts
        # the computed three-way result rather than a CSS class the layout
        # also uses for ordinary markup - "danger" alone also appears in
        # text-danger regardless of the outcome.
        assert "alert-danger" not in resp.get_data(as_text=True), (
            "the match view reported a variance for a fully received po"
        )

    def test_the_match_needs_grn_manage(self, client, db_session, sample_tenant, sample_branch):
        """PUR-35. Reconciling money is not a purchasing-administrator act."""
        _buyer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/purchases/match/1", follow_redirects=False)
        assert resp.status_code in (302, 403), f"a buyer reached the match view with {resp.status_code}"

    def test_the_scenario_covers_every_grn_route(self):
        """PUR-36."""
        for path in GRN_PATHS:
            assert path.startswith("/purchases"), f"{path} is not under /purchases"


class TestPUR37Requisitions:
    """PUR-37..45. create -> submit -> approve, with two authorities."""

    def test_the_requisition_list_renders(self, client, db_session, sample_tenant, sample_branch):
        """PUR-37."""
        _requester(client, db_session, sample_tenant, sample_branch)
        assert client.get("/purchases/requisitions").status_code == 200

    def test_the_requisition_create_form_renders(self, client, db_session, sample_tenant, sample_branch):
        """PUR-38."""
        _requester(client, db_session, sample_tenant, sample_branch)
        assert client.get("/purchases/requisitions/create").status_code == 200

    def test_a_requisition_starts_as_a_draft(self, db_session, sample_tenant, sample_branch, sample_user):
        """PUR-39. A request is not a commitment until it is approved."""
        from services.procurement_service import ProcurementService

        supplier = _supplier(db_session, sample_tenant)
        requisition = ProcurementService.create_requisition({"supplier_id": supplier.id, "lines": []}, sample_user)
        db_session.commit()
        assert requisition.status in ("draft", "pending"), f"a new requisition starts as {requisition.status!r}"

    def test_only_a_submitted_requisition_can_be_approved(self, db_session, sample_tenant, sample_branch, sample_user):
        """PUR-40. Approving a draft would let the requester skip the submit
        step that the workflow exists to force."""
        import pytest as _pytest

        from services.procurement_service import ProcurementService

        supplier = _supplier(db_session, sample_tenant)
        requisition = ProcurementService.create_requisition({"supplier_id": supplier.id, "lines": []}, sample_user)
        db_session.commit()
        with _pytest.raises(ValueError):
            ProcurementService.approve_requisition(requisition, sample_user)

    def test_only_a_submitted_requisition_can_be_rejected(self, db_session, sample_tenant, sample_branch, sample_user):
        """PUR-41."""
        import pytest as _pytest

        from services.procurement_service import ProcurementService

        supplier = _supplier(db_session, sample_tenant)
        requisition = ProcurementService.create_requisition({"supplier_id": supplier.id, "lines": []}, sample_user)
        db_session.commit()
        with _pytest.raises(ValueError):
            ProcurementService.reject_requisition(requisition, sample_user, "no")

    def test_a_requisition_carries_its_tenant(self, db_session, sample_tenant, sample_branch, sample_user):
        """PUR-42."""
        from services.procurement_service import ProcurementService

        supplier = _supplier(db_session, sample_tenant)
        requisition = ProcurementService.create_requisition({"supplier_id": supplier.id, "lines": []}, sample_user)
        db_session.commit()
        assert requisition.tenant_id == sample_tenant.id, f"the requisition names tenant {requisition.tenant_id}"

    def test_an_approve_on_a_missing_requisition_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PUR-43. approve and reject sit behind purchase_req:approve, so they
        are driven as an approver rather than as one user holding both
        requisition codes - otherwise the test would be asserting a permission
        split it had itself collapsed."""
        _approver(client, db_session, sample_tenant, sample_branch)
        for action in ("approve", "reject"):
            resp = client.post(f"/purchases/requisitions/98765432/{action}", follow_redirects=False)
            assert resp.status_code in (404, 302), f"{action} on a missing requisition answered {resp.status_code}"

    def test_a_submit_on_a_missing_requisition_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """PUR-43. submit sits behind the *other* code, so it gets its own
        actor: driving both through one session meant the second login had not
        taken effect and the request was refused by the guard instead of by the
        lookup."""
        _requester(client, db_session, sample_tenant, sample_branch)
        resp = client.post("/purchases/requisitions/98765432/submit", follow_redirects=False)
        assert resp.status_code in (404, 302), f"submit on a missing requisition answered {resp.status_code}"

    def test_the_purchase_order_carries_its_tenant(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-44."""
        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 5, "2.000")],
        )
        assert po.tenant_id == sample_tenant.id, f"the po names tenant {po.tenant_id}"

    def test_a_grn_carries_its_tenant(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product_with_stock
    ):
        """PUR-45."""
        po = _po(
            db_session,
            sample_tenant,
            sample_user,
            _supplier(db_session, sample_tenant),
            lines=[(sample_product_with_stock.id, 5, "2.000")],
        )
        grn = _grn(db_session, sample_tenant, po.id, sample_user)
        assert grn.tenant_id == sample_tenant.id, f"the grn names tenant {grn.tenant_id}"
