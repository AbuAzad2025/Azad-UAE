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

        return ProductSerial.query.filter_by(warehouse_id=warehouse_id, status=status).all()

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
        return not (not imei or len(imei) != 15 or not imei.isdigit())

    @staticmethod
    def get_serial_by_serial_number(serial_number, tenant_id):
        from models.product_serial import ProductSerial

        return ProductSerial.query.filter_by(tenant_id=tenant_id, serial_number=serial_number).first()

    @staticmethod
    def issue_serials(
        product_id: int,
        warehouse_id: int,
        quantity: int,
        *,
        tenant_id: int,
        reference_type: str,
        reference_id: int | None = None,
    ) -> list[str]:
        """Mark serials as issued for a product in a warehouse.

        Finds up to ``quantity`` available serials for the product in the
        warehouse, marks them as issued, links them to the reference line,
        and returns their serial numbers. A product with no serials
        registered (or fewer than the quantity) returns whatever it can:
        the quantity is still the truth for the stock movement, and the
        serial list is a best-effort trace.

        ``reference_type`` is ``sale`` or ``maintenance``; it decides which
        foreign key on ``ProductSerial`` is written. The two ledgers never
        share a key, so a serial consumed by a maintenance job is never
        mistaken for one sold.
        """
        from models.product_serial import ProductSerial

        if quantity <= 0:
            return []

        serials = (
            ProductSerial.query.filter_by(
                tenant_id=tenant_id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                status="available",
            )
            .order_by(ProductSerial.id.asc())
            .limit(quantity)
            .all()
        )

        issued_numbers: list[str] = []
        # The status the serial carries depends on the ledger it left:
        # a sale makes it "sold", a maintenance job makes it "issued".
        # The two are kept distinct so a serial sold to a customer is
        # never mistaken for one consumed by a workshop.
        issued_status = "sold" if reference_type == "sale" else "issued"
        for serial in serials:
            serial.status = issued_status
            if reference_type == "sale" and reference_id is not None:
                serial.sale_line_id = reference_id
            elif reference_type == "maintenance" and reference_id is not None:
                serial.maintenance_order_line_id = reference_id
            issued_numbers.append(serial.serial_number)

        return issued_numbers

    @staticmethod
    def restore_serials(
        serial_numbers: list[str],
        *,
        tenant_id: int,
    ) -> None:
        """Mark previously issued serials as available again.

        Used by the maintenance return path and the sale return path: the
        goods went back on the shelf, so their serials are available for
        the next issue.
        """
        from models.product_serial import ProductSerial

        if not serial_numbers:
            return
        serials = ProductSerial.query.filter(
            ProductSerial.tenant_id == tenant_id,
            ProductSerial.serial_number.in_(serial_numbers),
            ProductSerial.status == "issued",
        ).all()
        for serial in serials:
            serial.status = "available"
            serial.sale_line_id = None
            serial.maintenance_order_line_id = None
