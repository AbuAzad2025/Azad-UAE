from datetime import UTC, datetime
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import WarehouseTransfer, WarehouseTransferLine
from utils.helpers import generate_number


class TransferService:
    @staticmethod
    def _tid(user):
        from utils.tenanting import get_active_tenant_id

        return get_active_tenant_id(user)

    @classmethod
    def create_transfer(cls, data, user):
        tid = cls._tid(user)
        from_wh = int(data["from_warehouse_id"])
        to_wh = int(data["to_warehouse_id"])
        if from_wh == to_wh:
            raise ValueError(gettext("المستودعان يجب أن يكونا مختلفين."))

        t = WarehouseTransfer(
            tenant_id=tid,
            transfer_number=generate_number("TR", WarehouseTransfer, "transfer_number"),
            from_warehouse_id=from_wh,
            to_warehouse_id=to_wh,
            branch_id=data.get("branch_id"),
            status="draft",
            transfer_date=datetime.now(UTC).date(),
            requested_by=user.id,
            notes=data.get("notes"),
        )
        db.session.add(t)
        db.session.flush()

        for line_data in data.get("lines", []):
            line = WarehouseTransferLine(
                tenant_id=tid,
                transfer_id=t.id,
                product_id=int(line_data["product_id"]),
                requested_quantity=Decimal(str(line_data.get("quantity", 0))),
                notes=line_data.get("notes"),
                sort_order=line_data.get("sort_order", 0),
            )
            db.session.add(line)

        db.session.flush()
        return t

    @classmethod
    def approve_transfer(cls, transfer, user):
        if transfer.status != "draft":
            raise ValueError(gettext("فقط المسودات يمكن الموافقة عليها."))
        transfer.status = "approved"
        transfer.approved_by = user.id
        db.session.flush()
        return transfer

    @classmethod
    def ship_transfer(cls, transfer):
        if transfer.status != "approved":
            raise ValueError(gettext("يجب الموافقة على النقل أولاً."))
        transfer.status = "in_transit"
        db.session.flush()
        return transfer

    @classmethod
    def complete_transfer(cls, transfer, user):
        if transfer.status != "in_transit":
            raise ValueError(gettext("النقل يجب أن يكون قيد النقل لإتمامه."))

        from services.stock_service import StockService

        for line in transfer.lines:
            qty = line.received_quantity or line.requested_quantity
            if qty > 0:
                StockService.transfer_stock(
                    product_id=line.product_id,
                    from_warehouse_id=transfer.from_warehouse_id,
                    to_warehouse_id=transfer.to_warehouse_id,
                    quantity=qty,
                    tenant_id=transfer.tenant_id,
                )

        transfer.status = "completed"
        transfer.completed_date = datetime.now(UTC).date()
        transfer.received_by = user.id
        db.session.flush()
        return transfer

    @classmethod
    def cancel_transfer(cls, transfer):
        if transfer.status in ("completed",):
            raise ValueError(gettext("النقل المكتمل لا يمكن إلغاؤه."))
        transfer.status = "cancelled"
        db.session.flush()
        return transfer

    @classmethod
    def confirm_receive(cls, transfer, user, line_receives=None):
        if transfer.status != "in_transit":
            raise ValueError(gettext("النقل يجب أن يكون قيد النقل."))
        if line_receives:
            for line in transfer.lines:
                if str(line.id) in line_receives:
                    line.received_quantity = Decimal(str(line_receives[str(line.id)]))
        else:
            for line in transfer.lines:
                line.received_quantity = line.requested_quantity
        transfer.received_by = user.id
        db.session.flush()
        return transfer

    @classmethod
    def get_transfer(cls, transfer_id, tenant_id=None):
        t = db.session.get(WarehouseTransfer, transfer_id)
        if not t:
            raise ValueError(gettext("طلب النقل غير موجود."))
        if tenant_id and t.tenant_id != tenant_id:
            raise ValueError(gettext("غير مصرح."))
        return t

    @classmethod
    def list_transfers(cls, tenant_id, filters=None):
        q = WarehouseTransfer.query.filter_by(tenant_id=tenant_id)
        if filters:
            if filters.get("status"):
                q = q.filter_by(status=filters["status"])
            if filters.get("from_warehouse_id"):
                q = q.filter_by(from_warehouse_id=int(filters["from_warehouse_id"]))
            if filters.get("to_warehouse_id"):
                q = q.filter_by(to_warehouse_id=int(filters["to_warehouse_id"]))
        return q.order_by(WarehouseTransfer.created_at.desc()).all()
