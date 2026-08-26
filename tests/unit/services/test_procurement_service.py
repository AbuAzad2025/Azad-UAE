"""Procurement service — PR/PO/GRN workflow tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models import (
    GLAccount,
    GoodsReceipt,
    PurchaseOrder,
    PurchaseOrderLine,
    StockMovement,
)
from services.procurement_service import ProcurementService


def _make_gl_account(tenant_id, code, name="Account", is_header=False):
    from extensions import db

    acct = GLAccount(
        tenant_id=tenant_id,
        code=code,
        name=name,
        name_ar=name,
        type="expense",
        is_active=True,
        is_header=is_header,
    )
    db.session.add(acct)
    db.session.flush()
    return acct


class TestPRWorkflow:
    def test_create_requisition(self, db_session, sample_tenant, sample_user, sample_product):
        data = {
            "lines": [
                {"product_id": str(sample_product.id), "quantity": "10", "unit_cost_estimate": "50"},
            ]
        }
        pr = ProcurementService.create_requisition(data, sample_user)
        assert pr.id is not None
        assert pr.status == "draft"
        assert pr.requisition_number.startswith("PR")
        assert len(pr.lines) == 1
        assert pr.lines[0].quantity == Decimal("10")

    def test_submit_requisition(self, db_session, sample_tenant, sample_user, sample_product):
        data = {
            "lines": [
                {"product_id": str(sample_product.id), "quantity": "5", "unit_cost_estimate": "100"},
            ]
        }
        pr = ProcurementService.create_requisition(data, sample_user)
        ProcurementService.submit_requisition(pr)
        assert pr.status == "pending_approval"

    def test_submit_non_draft_raises(self, db_session, sample_tenant, sample_user, sample_product):
        data = {
            "lines": [
                {"product_id": str(sample_product.id), "quantity": "5", "unit_cost_estimate": "100"},
            ]
        }
        pr = ProcurementService.create_requisition(data, sample_user)
        ProcurementService.submit_requisition(pr)
        with pytest.raises(ValueError):
            ProcurementService.submit_requisition(pr)

    def test_approve_requisition(self, db_session, sample_tenant, sample_user, sample_product):
        data = {
            "lines": [
                {"product_id": str(sample_product.id), "quantity": "5", "unit_cost_estimate": "100"},
            ]
        }
        pr = ProcurementService.create_requisition(data, sample_user)
        ProcurementService.submit_requisition(pr)
        ProcurementService.approve_requisition(pr, sample_user)
        assert pr.status == "approved"
        assert pr.approved_by == sample_user.id

    def test_reject_requisition(self, db_session, sample_tenant, sample_user, sample_product):
        data = {
            "lines": [
                {"product_id": str(sample_product.id), "quantity": "5", "unit_cost_estimate": "100"},
            ]
        }
        pr = ProcurementService.create_requisition(data, sample_user)
        ProcurementService.submit_requisition(pr)
        ProcurementService.reject_requisition(pr, sample_user, reason="Too expensive")
        assert pr.status == "rejected"
        assert pr.rejected_reason == "Too expensive"


class TestPOWorkflow:
    def test_submit_po(self, db_session, sample_tenant, sample_user, sample_product, sample_supplier):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-TEST-001",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="draft",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        ProcurementService.submit_po(po)
        assert po.status == "submitted"

    def test_confirm_po(self, db_session, sample_tenant, sample_user, sample_product, sample_supplier):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-TEST-002",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="submitted",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        ProcurementService.confirm_po(po, sample_user)
        assert po.status == "confirmed"
        assert po.confirmed_by == sample_user.id

    def test_confirm_po_from_draft(self, db_session, sample_tenant, sample_user, sample_supplier):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-TEST-003",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="draft",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        ProcurementService.confirm_po(po, sample_user)
        assert po.status == "confirmed"


class TestGRNWorkflow:
    def test_confirm_grn_updates_po(self, db_session, sample_tenant, sample_user, sample_product, sample_supplier):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-GRN-001",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="confirmed",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        from models import PurchaseOrderLine

        po_line = PurchaseOrderLine(
            tenant_id=sample_tenant.id,
            po_id=po.id,
            product_id=sample_product.id,
            quantity=Decimal("100"),
            unit_cost=Decimal("50"),
            line_total=Decimal("5000"),
        )
        db_session.add(po_line)
        db_session.flush()

        grn = GoodsReceipt(
            tenant_id=sample_tenant.id,
            grn_number="GRN-TEST-001",
            po_id=po.id,
            supplier_id=sample_supplier.id,
            received_date=date.today(),
            received_by=sample_user.id,
            status="draft",
        )
        db_session.add(grn)
        db_session.flush()

        from models import GoodsReceiptLine

        grn_line = GoodsReceiptLine(
            tenant_id=sample_tenant.id,
            grn_id=grn.id,
            po_line_id=po_line.id,
            product_id=sample_product.id,
            ordered_quantity=Decimal("100"),
            received_quantity=Decimal("60"),
        )
        db_session.add(grn_line)
        db_session.flush()

        ProcurementService.confirm_grn(grn)
        assert grn.status == "confirmed"
        assert po.status == "partially_received"
        db_session.refresh(po_line)
        assert po_line.received_quantity == Decimal("60")

    def test_confirm_grn_creates_stock_movement(
        self, db_session, sample_tenant, sample_user, sample_product, sample_supplier
    ):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-GRN-002",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="confirmed",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        from models import PurchaseOrderLine

        po_line = PurchaseOrderLine(
            tenant_id=sample_tenant.id,
            po_id=po.id,
            product_id=sample_product.id,
            quantity=Decimal("50"),
            unit_cost=Decimal("20"),
            line_total=Decimal("1000"),
        )
        db_session.add(po_line)
        db_session.flush()

        grn = GoodsReceipt(
            tenant_id=sample_tenant.id,
            grn_number="GRN-TEST-002",
            po_id=po.id,
            supplier_id=sample_supplier.id,
            received_date=date.today(),
            received_by=sample_user.id,
            status="draft",
        )
        db_session.add(grn)
        db_session.flush()

        from models import GoodsReceiptLine

        grn_line = GoodsReceiptLine(
            tenant_id=sample_tenant.id,
            grn_id=grn.id,
            po_line_id=po_line.id,
            product_id=sample_product.id,
            ordered_quantity=Decimal("50"),
            received_quantity=Decimal("25"),
        )
        db_session.add(grn_line)
        db_session.flush()

        ProcurementService.confirm_grn(grn)
        db_session.flush()

        movement = (
            StockMovement.query.filter_by(
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                reference_type="GRN",
                reference_id=grn.id,
            )
            .order_by(StockMovement.id.desc())
            .first()
        )
        assert movement is not None
        assert movement.quantity == Decimal("25")
        assert movement.movement_type == "purchase"


class TestOvertimeCalc:
    def test_calculate_overtime_pay_standard(self):
        from services.hr_service import OvertimeService

        result = OvertimeService.calculate_overtime_pay(
            base_salary=Decimal("10000"),
            hours=Decimal("4"),
            rate_multiplier=Decimal("1.25"),
        )
        assert result > 0
        daily = Decimal("10000") / Decimal("26")
        hourly = daily / Decimal("8")
        expected = (hourly * Decimal("4") * Decimal("1.25")).quantize(Decimal("0.01"))
        assert result == expected

    def test_calculate_overtime_pay_zero_hours(self):
        from services.hr_service import OvertimeService

        result = OvertimeService.calculate_overtime_pay(
            base_salary=Decimal("10000"),
            hours=Decimal("0"),
            rate_multiplier=Decimal("1.25"),
        )
        assert result == Decimal("0.00")


def _q3(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


def _approved_requisition(db_session, sample_tenant, sample_user, product, qty="10", cost="50"):
    data = {
        "lines": [{"product_id": str(product.id), "quantity": qty, "unit_cost_estimate": cost}],
    }
    pr = ProcurementService.create_requisition(data, sample_user)
    ProcurementService.submit_requisition(pr)
    ProcurementService.approve_requisition(pr, sample_user)
    return pr


class TestConvertToPO:
    def test_convert_copies_lines_and_totals(
        self, db_session, sample_tenant, sample_user, sample_product, sample_supplier, sample_warehouse
    ):
        pr = _approved_requisition(db_session, sample_tenant, sample_user, sample_product, qty="8", cost="12.5")

        po = ProcurementService.convert_to_po(
            pr,
            sample_supplier.id,
            sample_user,
            warehouse_id=sample_warehouse.id,
            branch_id=None,
        )

        assert po.id is not None
        assert po.po_number.startswith("PO")
        assert po.status == "draft"
        assert po.supplier_id == sample_supplier.id
        assert po.requisition_id == pr.id
        assert po.warehouse_id == sample_warehouse.id
        assert po.created_by == sample_user.id

        assert len(po.lines) == 1
        po_line = po.lines[0]
        assert po_line.product_id == sample_product.id
        assert po_line.quantity == _q3("8")
        assert po_line.unit_cost == _q3("12.5")
        assert po_line.line_total == _q3("100")
        # totals computed from copied lines
        assert po.subtotal == _q3("100")
        assert po.total_amount == _q3("100")

        assert pr.status == "converted_to_po"

    def test_convert_uses_requisition_branch_when_none_given(
        self, db_session, sample_tenant, sample_user, sample_product, sample_supplier, sample_branch
    ):
        """Regression: warehouse_id must never receive the requisition's branch PK."""
        data = {
            "branch_id": sample_branch.id,
            "lines": [{"product_id": str(sample_product.id), "quantity": "3", "unit_cost_estimate": "7"}],
        }
        pr = ProcurementService.create_requisition(data, sample_user)
        ProcurementService.submit_requisition(pr)
        ProcurementService.approve_requisition(pr, sample_user)

        po = ProcurementService.convert_to_po(pr, sample_supplier.id, sample_user)

        assert po.branch_id == sample_branch.id
        # no explicit warehouse supplied → stays NULL (never branch id)
        assert po.warehouse_id is None

    def test_convert_unapproved_raises(self, db_session, sample_tenant, sample_user, sample_product, sample_supplier):
        pr = ProcurementService.create_requisition(
            {"lines": [{"product_id": str(sample_product.id), "quantity": "1"}]},
            sample_user,
        )
        with pytest.raises(ValueError):
            ProcurementService.convert_to_po(pr, sample_supplier.id, sample_user)

    def test_convert_unknown_supplier_raises(
        self, db_session, sample_tenant, sample_user, sample_product, sample_supplier
    ):
        pr = _approved_requisition(db_session, sample_tenant, sample_user, sample_product)
        with pytest.raises(ValueError):
            ProcurementService.convert_to_po(pr, 99999999, sample_user)


class TestCreateGRN:
    def _confirmed_po(self, db_session, sample_tenant, sample_user, sample_supplier, product, qty="100", cost="20"):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number=f"PO-CGRN-{db_session.query(PurchaseOrder).count()}-{product.id}",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="draft",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        po_line = PurchaseOrderLine(
            tenant_id=sample_tenant.id,
            po_id=po.id,
            product_id=product.id,
            quantity=Decimal(qty),
            unit_cost=Decimal(cost),
            line_total=(Decimal(qty) * Decimal(cost)),
        )
        db_session.add(po_line)
        db_session.flush()
        ProcurementService.confirm_po(po, sample_user)
        return po, po_line

    def test_create_grn_happy_path(self, db_session, sample_tenant, sample_user, sample_supplier, sample_product):
        po, po_line = self._confirmed_po(db_session, sample_tenant, sample_user, sample_supplier, sample_product)

        grn = ProcurementService.create_grn(
            po.id,
            {
                "notes": "first delivery",
                "lines": [{"po_line_id": po_line.id, "received_quantity": "40", "condition": "acceptable"}],
            },
            sample_user,
        )

        assert grn.id is not None
        assert grn.grn_number.startswith("GRN")
        assert grn.status == "draft"
        assert grn.po_id == po.id
        assert grn.supplier_id == sample_supplier.id
        assert grn.received_by == sample_user.id
        assert len(grn.lines) == 1
        gl = grn.lines[0]
        assert gl.po_line_id == po_line.id
        assert gl.received_quantity == _q3("40")
        assert gl.ordered_quantity == _q3("100")

    def test_create_grn_unknown_po_raises(self, db_session, sample_tenant, sample_user):
        with pytest.raises(ValueError):
            ProcurementService.create_grn(99999999, {"lines": []}, sample_user)

    def test_create_grn_unconfirmed_po_raises(
        self, db_session, sample_tenant, sample_user, sample_supplier, sample_product
    ):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-CGRN-DRAFT",
            supplier_id=sample_supplier.id,
            order_date=date.today(),
            status="draft",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        with pytest.raises(ValueError):
            ProcurementService.create_grn(po.id, {"lines": []}, sample_user)

    def test_create_grn_bad_po_line_raises(
        self, db_session, sample_tenant, sample_user, sample_supplier, sample_product
    ):
        po, _ = self._confirmed_po(db_session, sample_tenant, sample_user, sample_supplier, sample_product)
        with pytest.raises(ValueError):
            ProcurementService.create_grn(po.id, {"lines": [{"po_line_id": 99999999, "received_quantity": "1"}]}, sample_user)


class TestConfirmGRNFullReceipt:
    def test_full_receipt_marks_po_received_and_stocks_warehouse(
        self, db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
    ):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-FULL-001",
            supplier_id=sample_supplier.id,
            warehouse_id=sample_warehouse.id,
            order_date=date.today(),
            status="confirmed",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        po_line = PurchaseOrderLine(
            tenant_id=sample_tenant.id,
            po_id=po.id,
            product_id=sample_product.id,
            quantity=Decimal("25"),
            unit_cost=Decimal("4"),
            line_total=Decimal("100"),
        )
        db_session.add(po_line)
        db_session.flush()

        grn = ProcurementService.create_grn(
            po.id,
            {"lines": [{"po_line_id": po_line.id, "received_quantity": "25"}]},
            sample_user,
        )
        result = ProcurementService.confirm_grn(grn)

        assert result.status == "confirmed"
        db_session.refresh(po_line)
        assert po_line.received_quantity == _q3("25")
        db_session.refresh(po)
        assert po.status == "received"

        movement = StockMovement.query.filter_by(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            reference_type="GRN",
            reference_id=grn.id,
        ).one()
        assert movement.quantity == _q3("25")
        assert movement.movement_type == "purchase"
        assert movement.warehouse_id == sample_warehouse.id

    def test_confirm_non_draft_grn_raises(
        self, db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
    ):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number="PO-FULL-002",
            supplier_id=sample_supplier.id,
            warehouse_id=sample_warehouse.id,
            order_date=date.today(),
            status="confirmed",
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        po_line = PurchaseOrderLine(
            tenant_id=sample_tenant.id,
            po_id=po.id,
            product_id=sample_product.id,
            quantity=Decimal("5"),
            unit_cost=Decimal("2"),
            line_total=Decimal("10"),
        )
        db_session.add(po_line)
        db_session.flush()

        grn = GoodsReceipt(
            tenant_id=sample_tenant.id,
            grn_number="GRN-NONDRAFT",
            po_id=po.id,
            supplier_id=sample_supplier.id,
            warehouse_id=sample_warehouse.id,
            received_date=date.today(),
            received_by=sample_user.id,
            status="confirmed",
        )
        db_session.add(grn)
        db_session.flush()

        with pytest.raises(ValueError):
            ProcurementService.confirm_grn(grn)


class TestThreeWayMatch:
    def _po_with_confirmed_grn(
        self, db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse,
        po_qty="10", cost="5", received="10", total="50"
    ):
        po = PurchaseOrder(
            tenant_id=sample_tenant.id,
            po_number=f"PO-TWM-{db_session.query(PurchaseOrder).count()}-{sample_product.id}",
            supplier_id=sample_supplier.id,
            warehouse_id=sample_warehouse.id,
            order_date=date.today(),
            status="confirmed",
            total_amount=Decimal(total),
            created_by=sample_user.id,
        )
        db_session.add(po)
        db_session.flush()
        po_line = PurchaseOrderLine(
            tenant_id=sample_tenant.id,
            po_id=po.id,
            product_id=sample_product.id,
            quantity=Decimal(po_qty),
            unit_cost=Decimal(cost),
            line_total=Decimal(po_qty) * Decimal(cost),
        )
        db_session.add(po_line)
        db_session.flush()

        grn = ProcurementService.create_grn(
            po.id,
            {"lines": [{"po_line_id": po_line.id, "received_quantity": received}]},
            sample_user,
        )
        ProcurementService.confirm_grn(grn)
        return po

    def test_matched_invoice_returns_overall_true(
        self, db_session, app, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
    ):
        import flask_login

        po = self._po_with_confirmed_grn(
            db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
        )
        with app.test_request_context():
            flask_login.login_user(sample_user)
            results = ProcurementService.three_way_match(po.id, "50", "AED")

        assert results["overall"] is True
        assert results["po_id"] == po.id
        line_match = results["line_matches"][0]
        assert line_match["matched"] is True
        assert line_match["quantity_variance"] == 0.0
        assert line_match["received_quantity"] == 10.0
        assert results["amount_variance"] == 0.0

    def test_qty_shortfall_fails_match(
        self, db_session, app, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
    ):
        import flask_login

        po = self._po_with_confirmed_grn(
            db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse,
            po_qty="10", cost="5", received="6", total="50"
        )
        with app.test_request_context():
            flask_login.login_user(sample_user)
            results = ProcurementService.three_way_match(po.id, "50", "AED")

        assert results["overall"] is False
        line_match = results["line_matches"][0]
        assert line_match["matched"] is False
        assert line_match["quantity_variance"] == -4.0
        assert line_match["price_variance"] == -20.0

    def test_invoice_amount_mismatch_fails_match(
        self, db_session, app, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
    ):
        import flask_login

        po = self._po_with_confirmed_grn(
            db_session, sample_tenant, sample_user, sample_supplier, sample_product, sample_warehouse
        )
        with app.test_request_context():
            flask_login.login_user(sample_user)
            results = ProcurementService.three_way_match(po.id, "55.5", "AED")

        assert results["overall"] is False
        assert results["amount_variance"] == 5.5

    def test_unknown_po_raises(self, db_session, app):
        with app.test_request_context():
            # no authenticated user → tenant None → PO not found
            with pytest.raises(ValueError):
                ProcurementService.three_way_match(99999999, "10")
