from datetime import UTC, datetime
from decimal import Decimal

from extensions import db


class ShipmentService:
    @staticmethod
    def create_shipment(source_type, source_id, carrier_name, tracking_number, **kwargs):
        from models.shipment import Shipment

        shipment = Shipment(
            tenant_id=kwargs.get("tenant_id"),
            source_type=source_type,
            source_id=source_id,
            sale_id=source_id if source_type == "sale" else None,
            purchase_return_id=source_id if source_type == "purchase_return" else None,
            carrier_name=carrier_name,
            tracking_number=tracking_number,
            tracking_url=kwargs.get("tracking_url"),
            shipping_cost=kwargs.get("shipping_cost", 0),
            customs_duty=kwargs.get("customs_duty", 0),
            insurance=kwargs.get("insurance", 0),
            status=kwargs.get("status", "pending"),
            estimated_delivery=kwargs.get("estimated_delivery"),
            recipient_name=kwargs.get("recipient_name"),
            recipient_phone=kwargs.get("recipient_phone"),
            recipient_address=kwargs.get("recipient_address"),
        )
        db.session.add(shipment)
        return shipment

    @staticmethod
    def update_status(shipment_id, status):
        from datetime import datetime

        from models.shipment import Shipment

        shipment = Shipment.query.get(shipment_id)
        if shipment:
            shipment.status = status
            if status == "delivered":
                shipment.actual_delivery = datetime.now(UTC)

    @staticmethod
    def get_shipments_for_sale(sale_id):
        from models.shipment import Shipment

        return Shipment.query.filter_by(source_type="sale", source_id=sale_id).all()

    @staticmethod
    def get_shipments_for_purchase(purchase_id):
        from models.shipment import Shipment

        return Shipment.query.filter_by(source_type="purchase", source_id=purchase_id).all()

    @staticmethod
    def list_shipments(tid):
        """All shipments for a tenant; empty list without scope."""
        from models.shipment import Shipment

        if not tid:
            return []
        return Shipment.query.filter_by(tenant_id=tid).order_by(Shipment.created_at.desc()).all()

    # ── Field-sales expedition (pre-invoice, Van) ──
    @staticmethod
    def _generate_shipment_number():
        try:
            from models.shipment import Shipment
            from utils.helpers import generate_number

            return generate_number("SH", Shipment, "shipment_number")
        except Exception:
            return f"SH-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    @staticmethod
    def create_field_shipment(
        *,
        from_warehouse_id,
        destination_name,
        destination_warehouse_id=None,
        destination_type="site",
        tenant_id=None,
        created_by_id=None,
        assigned_to_id=None,
        lines_data=None,
        notes=None,
    ):
        from models.shipment import Shipment, ShipmentLine

        if not from_warehouse_id:
            raise ValueError("from_warehouse_id مطلوب")
        if not destination_name or not str(destination_name).strip():
            raise ValueError("destination_name (موقع الإرسالية) مطلوب")
        if not lines_data:
            raise ValueError("يجب إضافة منتج واحد على الأقل")

        shipment = Shipment(
            shipment_number=ShipmentService._generate_shipment_number(),
            tenant_id=tenant_id,
            source_type="field_sale",
            source_id=0,
            from_warehouse_id=from_warehouse_id,
            destination_warehouse_id=destination_warehouse_id,
            destination_name=str(destination_name).strip(),
            destination_type=destination_type or "site",
            status="draft",
            notes=notes,
            created_by_id=created_by_id,
            assigned_to_id=assigned_to_id,
        )
        db.session.add(shipment)
        db.session.flush()

        for row in lines_data:
            product_id = row.get("product_id")
            qty = Decimal(str(row.get("quantity", 0)))
            if not product_id or qty <= 0:
                raise ValueError("كل بند يحتاج product_id و quantity > 0")
            unit_cost = Decimal(str(row.get("unit_cost", row.get("cost", 0) or 0)))
            unit_price = Decimal(str(row.get("unit_price", row.get("price", 0) or 0)))
            line = ShipmentLine(
                shipment_id=shipment.id,
                product_id=int(product_id),
                quantity=qty,
                unit_cost=unit_cost,
                unit_price=unit_price,
            )
            line.calculate_line_total()
            db.session.add(line)

        db.session.flush()
        shipment.calculate_totals()
        db.session.flush()
        return shipment

    @staticmethod
    def send_shipment(shipment_id, user_id=None):
        from models.shipment import Shipment

        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            raise ValueError("الإرسالية غير موجودة")
        if shipment.status != "draft":
            raise ValueError(f"لا يمكن الإرسال من حالة {shipment.status}")
        shipment.status = "in_transit"
        shipment.shipped_at = datetime.now(UTC)
        db.session.flush()
        return shipment

    @staticmethod
    def arrive_shipment(shipment_id, user_id=None):
        from models.shipment import Shipment

        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            raise ValueError("الإرسالية غير موجودة")
        if shipment.status != "in_transit":
            raise ValueError(f"لا يمكن تأكيد الوصول من حالة {shipment.status}")
        shipment.status = "arrived"
        shipment.arrived_at = datetime.now(UTC)
        db.session.flush()
        return shipment

    @staticmethod
    def start_selling(shipment_id, user_id=None):
        from models.shipment import Shipment

        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            raise ValueError("الإرسالية غير موجودة")
        if shipment.status != "arrived":
            raise ValueError(f"لا يمكن بدء البيع من حالة {shipment.status}")
        shipment.status = "selling"
        db.session.flush()
        return shipment

    @staticmethod
    def close_shipment(shipment_id, user_id=None):
        from models.shipment import Shipment

        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            raise ValueError("الإرسالية غير موجودة")
        if shipment.status not in ("arrived", "selling"):
            raise ValueError(f"لا يمكن الإغلاق من حالة {shipment.status}")
        shipment.status = "closed"
        shipment.closed_at = datetime.now(UTC)
        db.session.flush()
        return shipment

    @staticmethod
    def cancel_shipment(shipment_id, user_id=None):
        from models.shipment import Shipment

        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            raise ValueError("الإرسالية غير موجودة")
        if shipment.status == "closed":
            raise ValueError("لا يمكن إلغاء إرسالية مغلقة")
        if shipment.status == "cancelled":
            raise ValueError("الإرسالية ملغاة بالفعل")
        shipment.status = "cancelled"
        db.session.flush()
        return shipment

    @staticmethod
    def get_shipment_or_404(shipment_id):
        from flask import abort

        from models.shipment import Shipment

        shipment = db.session.get(Shipment, shipment_id)
        if not shipment:
            abort(404)
        return shipment
