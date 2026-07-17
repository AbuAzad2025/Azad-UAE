class SerialTrackingService:
    @staticmethod
    def assign_serial_to_warehouse(serial_id, warehouse_id):
        from models.product_serial import ProductSerial

        serial = ProductSerial.query.get(serial_id)
        if not serial:
            return None
        if serial.warehouse_id:
            raise ValueError("Serial already assigned to a warehouse")
        serial.warehouse_id = warehouse_id
        return serial

    @staticmethod
    def get_serials_in_warehouse(warehouse_id, status="available"):
        from models.product_serial import ProductSerial

        return ProductSerial.query.filter_by(
            warehouse_id=warehouse_id, status=status
        ).all()

    @staticmethod
    def get_serial_by_imei(imei, tenant_id):
        from models.product_serial import ProductSerial

        return ProductSerial.query.filter(
            ProductSerial.tenant_id == tenant_id,
            (ProductSerial.imei1 == imei) | (ProductSerial.imei2 == imei),
        ).first()

    @staticmethod
    def transfer_serial(serial_id, from_warehouse_id, to_warehouse_id):
        from models.product_serial import ProductSerial

        serial = ProductSerial.query.get(serial_id)
        if not serial or serial.warehouse_id != from_warehouse_id:
            return None
        serial.warehouse_id = to_warehouse_id
        return serial

    @staticmethod
    def validate_imei(imei):
        if not imei or len(imei) != 15 or not imei.isdigit():
            return False
        return True

    @staticmethod
    def get_serial_by_serial_number(serial_number, tenant_id):
        from models.product_serial import ProductSerial

        return ProductSerial.query.filter_by(
            tenant_id=tenant_id, serial_number=serial_number
        ).first()
