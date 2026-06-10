from datetime import datetime, timezone
from extensions import db


class ShipmentService:

    @staticmethod
    def create_shipment(source_type, source_id, carrier, tracking_number, **kwargs):
        from models.shipment import Shipment
        shipment = Shipment(
            tenant_id=kwargs.get('tenant_id'),
            source_type=source_type,
            source_id=source_id,
            carrier_name=carrier,
            tracking_number=tracking_number,
            tracking_url=kwargs.get('tracking_url'),
            shipping_cost=kwargs.get('shipping_cost', 0),
            customs_duty=kwargs.get('customs_duty', 0),
            insurance=kwargs.get('insurance', 0),
            status=kwargs.get('status', 'pending'),
            estimated_delivery=kwargs.get('estimated_delivery'),
            recipient_name=kwargs.get('recipient_name'),
            recipient_phone=kwargs.get('recipient_phone'),
            recipient_address=kwargs.get('recipient_address')
        )
        db.session.add(shipment)
        return shipment

    @staticmethod
    def update_status(shipment_id, status):
        from models.shipment import Shipment
        shipment = Shipment.query.get(shipment_id)
        if shipment:
            shipment.status = status
            if status == 'delivered':
                shipment.actual_delivery = datetime.now(timezone.utc)

    @staticmethod
    def get_shipments_for_sale(sale_id):
        from models.shipment import Shipment
        return Shipment.query.filter_by(source_type='sale', source_id=sale_id).all()

    @staticmethod
    def get_shipments_for_purchase(purchase_id):
        from models.shipment import Shipment
        return Shipment.query.filter_by(source_type='purchase', source_id=purchase_id).all()