from datetime import UTC, datetime
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
)
from utils.db_safety import atomic_transaction
from utils.helpers import generate_number


class ProcurementService:
    @staticmethod
    def _tid(user):
        from utils.tenanting import get_active_tenant_id

        return get_active_tenant_id(user)

    @classmethod
    def create_requisition(cls, data, user):
        tid = cls._tid(user)
        pr = PurchaseRequisition(
            tenant_id=tid,
            requisition_number=generate_number("PR", PurchaseRequisition, "requisition_number"),
            requester_id=user.id,
            department_id=data.get("department_id"),
            branch_id=data.get("branch_id"),
            requested_date=datetime.now(UTC).date(),
            needed_by_date=data.get("needed_by_date"),
            priority=data.get("priority", "normal"),
            justification=data.get("justification"),
            notes=data.get("notes"),
            status="draft",
        )
        db.session.add(pr)
        db.session.flush()

        lines_data = data.get("lines", [])
        for line in lines_data:
            pr_line = PurchaseRequisitionLine(
                tenant_id=tid,
                requisition_id=pr.id,
                product_id=int(line["product_id"]),
                quantity=Decimal(str(line["quantity"])),
                unit_cost_estimate=Decimal(str(line.get("unit_cost_estimate", 0))),
                notes=line.get("notes"),
            )
            db.session.add(pr_line)

        db.session.flush()
        return pr

    @classmethod
    def submit_requisition(cls, requisition):
        if requisition.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن إرسالها."))
        requisition.status = "pending_approval"
        db.session.flush()
        return requisition

    @classmethod
    def approve_requisition(cls, requisition, user):
        if requisition.status != "pending_approval":
            raise ValueError(gettext("طلب غير في حالة انتظار الموافقة."))
        requisition.status = "approved"
        requisition.approved_by = user.id
        requisition.approved_at = datetime.now(UTC)
        db.session.flush()
        return requisition

    @classmethod
    def reject_requisition(cls, requisition, user, reason=""):
        if requisition.status != "pending_approval":
            raise ValueError(gettext("طلب غير في حالة انتظار الموافقة."))
        requisition.status = "rejected"
        requisition.rejected_reason = reason
        requisition.approved_by = user.id
        requisition.approved_at = datetime.now(UTC)
        db.session.flush()
        return requisition

    @classmethod
    def convert_to_po(cls, requisition, supplier_id, user, warehouse_id=None, branch_id=None):
        if requisition.status != "approved":
            raise ValueError(gettext("يجب الموافقة على الطلب أولاً."))

        tid = requisition.tenant_id
        from models import Supplier

        supplier = Supplier.query.filter_by(id=supplier_id, tenant_id=tid).first()
        if not supplier:
            raise ValueError(gettext("المورد غير موجود."))

        po = PurchaseOrder(
            tenant_id=tid,
            po_number=generate_number("PO", PurchaseOrder, "po_number"),
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            branch_id=branch_id or requisition.branch_id,
            requisition_id=requisition.id,
            order_date=datetime.now(UTC).date(),
            status="draft",
            created_by=user.id,
        )
        db.session.add(po)
        db.session.flush()

        for pr_line in requisition.lines:
            po_line = PurchaseOrderLine(
                tenant_id=tid,
                po_id=po.id,
                product_id=pr_line.product_id,
                quantity=pr_line.quantity,
                unit_cost=pr_line.unit_cost_estimate or Decimal("0"),
                line_total=(pr_line.quantity * (pr_line.unit_cost_estimate or Decimal("0"))).quantize(Decimal("0.001")),
            )
            db.session.add(po_line)

        po.calculate_totals()
        requisition.status = "converted_to_po"
        requisition.po_id = None
        db.session.flush()
        return po

    @classmethod
    def submit_po(cls, po):
        if po.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن إرسالها."))
        po.status = "submitted"
        db.session.flush()
        return po

    @classmethod
    def confirm_po(cls, po, user):
        if po.status not in ("draft", "submitted"):
            raise ValueError(gettext("طلب شراء غير صالح للتأكيد."))
        po.status = "confirmed"
        po.confirmed_by = user.id
        po.confirmed_at = datetime.now(UTC)
        db.session.flush()
        return po

    @classmethod
    def create_grn(cls, po_id, data, user):
        tid = cls._tid(user)
        po = PurchaseOrder.query.filter_by(id=po_id, tenant_id=tid).first()
        if not po:
            raise ValueError(gettext("طلب الشراء غير موجود."))
        if po.status not in ("confirmed", "partially_received"):
            raise ValueError(gettext("يجب تأكيد طلب الشراء قبل الاستلام."))

        grn = GoodsReceipt(
            tenant_id=tid,
            grn_number=generate_number("GRN", GoodsReceipt, "grn_number"),
            po_id=po.id,
            supplier_id=po.supplier_id,
            warehouse_id=po.warehouse_id,
            branch_id=po.branch_id,
            received_date=datetime.now(UTC).date(),
            received_by=user.id,
            status="draft",
            notes=data.get("notes"),
        )
        db.session.add(grn)
        db.session.flush()

        lines_data = data.get("lines", [])
        for line in lines_data:
            po_line_id = int(line["po_line_id"])
            po_line = PurchaseOrderLine.query.filter_by(id=po_line_id, po_id=po.id, tenant_id=tid).first()
            if not po_line:
                raise ValueError(gettext(f"سطر طلب الشراء #{po_line_id} غير موجود."))

            received_qty = Decimal(str(line["received_quantity"]))
            grn_line = GoodsReceiptLine(
                tenant_id=tid,
                grn_id=grn.id,
                po_line_id=po_line_id,
                product_id=po_line.product_id,
                ordered_quantity=po_line.quantity,
                received_quantity=received_qty,
                condition=line.get("condition", "acceptable"),
                notes=line.get("notes"),
            )
            db.session.add(grn_line)

        db.session.flush()
        return grn

    @classmethod
    def confirm_grn(cls, grn):
        if grn.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن تأكيدها."))

        with atomic_transaction("confirm_grn"):
            po = grn.purchase_order
            for grn_line in grn.lines:
                po_line = grn_line.po_line
                po_line.received_quantity = (po_line.received_quantity or Decimal("0")) + grn_line.received_quantity

                # Create an immediate stock-in movement for every received line.
                from services.stock_service import StockService

                StockService.add_stock(
                    product_id=po_line.product_id,
                    quantity=grn_line.received_quantity,
                    warehouse_id=grn.warehouse_id,
                    reference_type="GRN",
                    reference_id=grn.id,
                    notes=gettext(f"استلام بضاعة من {grn.grn_number}"),
                )

            if po.is_fully_received:
                po.status = "received"
            else:
                po.status = "partially_received"

            grn.status = "confirmed"
            db.session.flush()
        return grn

    @classmethod
    def three_way_match(cls, po_id, invoice_amount, invoice_currency="AED"):
        tid = get_current_tenant_id()
        po = PurchaseOrder.query.filter_by(id=po_id, tenant_id=tid).first()
        if not po:
            raise ValueError(gettext("طلب الشراء غير موجود."))

        results = {"po_id": po.id, "po_number": po.po_number, "line_matches": [], "overall": True}

        for po_line in po.lines:
            grn_qty = Decimal("0")
            for grn in po.goods_receipts:
                if grn.status == "confirmed":
                    for gl in grn.lines:
                        if gl.po_line_id == po_line.id:
                            grn_qty += gl.received_quantity

            po_qty = po_line.quantity or Decimal("0")
            qty_variance = grn_qty - po_qty
            price_variance = Decimal("0")

            unit_cost = po_line.unit_cost or Decimal("0")
            if grn_qty > 0 and unit_cost > 0:
                po_value = po_qty * unit_cost
                grn_value = grn_qty * unit_cost
                price_variance = grn_value - po_value

            line_match = {
                "po_line_id": po_line.id,
                "product_id": po_line.product_id,
                "po_quantity": float(po_qty),
                "received_quantity": float(grn_qty),
                "unit_cost": float(unit_cost),
                "quantity_variance": float(qty_variance),
                "price_variance": float(price_variance),
                "matched": qty_variance == 0,
            }
            results["line_matches"].append(line_match)
            if qty_variance != 0:
                results["overall"] = False

        invoice_dec = Decimal(str(invoice_amount))
        po_total = po.total_amount or Decimal("0")
        results["po_total"] = float(po_total)
        results["invoice_amount"] = float(invoice_dec)
        results["amount_variance"] = float(invoice_dec - po_total)
        if invoice_dec != po_total:
            results["overall"] = False

        return results


def get_current_tenant_id():
    from flask_login import current_user

    from utils.tenanting import get_active_tenant_id

    if current_user and current_user.is_authenticated:
        return get_active_tenant_id(current_user)
    return None
