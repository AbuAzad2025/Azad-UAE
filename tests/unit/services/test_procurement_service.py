"""Procurement service — PR/PO/GRN workflow tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models import (
    GLAccount,
    GoodsReceipt,
    PurchaseOrder,
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
