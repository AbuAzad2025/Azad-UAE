"""Serial tracking + shipment service — IMEI, transfers, delivery lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestSerialTracking:
    """SerialTrackingService — assignment, IMEI, transfer guards."""

    def test_validate_imei_requires_15_digits(self):
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.validate_imei("123456789012345") is True
        assert SerialTrackingService.validate_imei("12345") is False
        assert SerialTrackingService.validate_imei("") is False
        assert SerialTrackingService.validate_imei("12345678901234a") is False

    def test_assign_serial_not_found_returns_none(self, mocker):
        mocker.patch(
            "models.product_serial.ProductSerial.query"
        ).get.return_value = None
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.assign_serial_to_warehouse(99, 1) is None

    def test_get_serial_by_serial_number(self, mocker):
        found = MagicMock()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = found
        mocker.patch("models.product_serial.ProductSerial.query", mock_q)
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.get_serial_by_serial_number("SN-1", 1) is found
        mock_q.filter_by.assert_called_with(tenant_id=1, serial_number="SN-1")

    def test_assign_serial_rejects_double_assignment(self, mocker):
        serial = MagicMock(warehouse_id=1)
        mocker.patch(
            "models.product_serial.ProductSerial.query"
        ).get.return_value = serial
        from services.serial_tracking_service import SerialTrackingService

        with pytest.raises(ValueError, match="already assigned"):
            SerialTrackingService.assign_serial_to_warehouse(1, 2)

    def test_assign_serial_success(self, mocker):
        serial = MagicMock(warehouse_id=None)
        mocker.patch(
            "models.product_serial.ProductSerial.query"
        ).get.return_value = serial
        from services.serial_tracking_service import SerialTrackingService

        result = SerialTrackingService.assign_serial_to_warehouse(1, 9)
        assert result.warehouse_id == 9

    def test_transfer_serial_wrong_warehouse_returns_none(self, mocker):
        serial = MagicMock(warehouse_id=2)
        mocker.patch(
            "models.product_serial.ProductSerial.query"
        ).get.return_value = serial
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.transfer_serial(1, 1, 3) is None

    def test_transfer_serial_success(self, mocker):
        serial = MagicMock(warehouse_id=1)
        mocker.patch(
            "models.product_serial.ProductSerial.query"
        ).get.return_value = serial
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.transfer_serial(1, 1, 5).warehouse_id == 5

    def test_get_serial_by_imei_tenant_scoped(self, mocker):
        found = MagicMock()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = found
        mocker.patch("models.product_serial.ProductSerial.query", mock_q)
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.get_serial_by_imei("123456789012345", 1) is found

    def test_get_serials_in_warehouse(self, mocker):
        mocker.patch(
            "models.product_serial.ProductSerial.query"
        ).filter_by.return_value.all.return_value = []
        from services.serial_tracking_service import SerialTrackingService

        assert SerialTrackingService.get_serials_in_warehouse(3) == []


class TestShipmentService:
    """ShipmentService — create, status transitions, source queries."""

    def test_create_shipment_defaults_pending(self, app, mocker):
        mock_session = mocker.patch("services.shipment_service.db.session")
        from services.shipment_service import ShipmentService

        with app.app_context():
            shipment = ShipmentService.create_shipment(
                "sale", 10, "DHL", "TRK-1", tenant_id=1
            )
        assert shipment.status == "pending"
        assert shipment.shipping_cost == 0
        mock_session.add.assert_called_once()

    def test_update_status_delivered_sets_timestamp(self, mocker):
        shipment = MagicMock(status="in_transit", actual_delivery=None)
        mocker.patch("models.shipment.Shipment.query").get.return_value = shipment
        from services.shipment_service import ShipmentService

        ShipmentService.update_status(1, "delivered")
        assert shipment.status == "delivered"
        assert shipment.actual_delivery is not None

    def test_update_status_missing_shipment_noop(self, mocker):
        mocker.patch("models.shipment.Shipment.query").get.return_value = None
        from services.shipment_service import ShipmentService

        ShipmentService.update_status(99, "delivered")

    def test_get_shipments_for_sale(self, mocker):
        rows = [MagicMock()]
        mocker.patch(
            "models.shipment.Shipment.query"
        ).filter_by.return_value.all.return_value = rows
        from services.shipment_service import ShipmentService

        assert ShipmentService.get_shipments_for_sale(5) == rows

    def test_get_shipments_for_purchase(self, mocker):
        mocker.patch(
            "models.shipment.Shipment.query"
        ).filter_by.return_value.all.return_value = []
        from services.shipment_service import ShipmentService

        assert ShipmentService.get_shipments_for_purchase(8) == []
