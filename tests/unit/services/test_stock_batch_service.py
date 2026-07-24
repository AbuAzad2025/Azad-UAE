"""FEFO batch layer tests — real DB, toggle-gated behind ``enable_batches``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from models import StockBatch, SystemSettings
from services.stock_batch_service import StockBatchService
from services.stock_service import StockService


@pytest.fixture
def batches_on(db_session):
    settings = SystemSettings.get_current()
    settings.enable_batches = True
    db_session.flush()
    return settings


def _batches(db_session, product_id, warehouse_id):
    return (
        db_session.query(StockBatch)
        .filter_by(product_id=product_id, warehouse_id=warehouse_id)
        .order_by(StockBatch.id.asc())
        .all()
    )


class TestBatchesToggle:
    def test_disabled_by_default(self, db_session):
        SystemSettings.get_current()
        assert StockBatchService.batches_enabled() is False

    def test_enabled_reads_global_settings(self, db_session, batches_on):
        assert StockBatchService.batches_enabled() is True


class TestConsumeFefo:
    def test_fefo_order_soonest_expiry_first(
        self, db_session, sample_tenant, sample_product, sample_warehouse, batches_on
    ):
        tid = sample_tenant.id
        StockBatchService.record_receipt(
            tid, sample_product.id, sample_warehouse.id, 5, 10, expiry_date=date(2026, 8, 1)
        )
        StockBatchService.record_receipt(
            tid, sample_product.id, sample_warehouse.id, 5, 20, expiry_date=date(2026, 7, 1)
        )
        StockBatchService.record_receipt(tid, sample_product.id, sample_warehouse.id, 5, 30)

        qty, value = StockBatchService.consume_fefo(sample_product.id, sample_warehouse.id, 7, tid)

        assert qty == Decimal("7")
        assert value == Decimal("120.000")
        b1, b2, b3 = _batches(db_session, sample_product.id, sample_warehouse.id)
        assert b2.quantity == Decimal("0")
        assert b1.quantity == Decimal("3.000")
        assert b3.quantity == Decimal("5.000")

    def test_fifo_fallback_when_no_expiry(
        self, db_session, sample_tenant, sample_product, sample_warehouse, batches_on
    ):
        tid = sample_tenant.id
        StockBatchService.record_receipt(tid, sample_product.id, sample_warehouse.id, 3, 10)
        StockBatchService.record_receipt(tid, sample_product.id, sample_warehouse.id, 3, 20)

        qty, value = StockBatchService.consume_fefo(sample_product.id, sample_warehouse.id, 4, tid)

        assert qty == Decimal("4")
        assert value == Decimal("50.000")

    def test_partial_when_batches_run_out(
        self, db_session, sample_tenant, sample_product, sample_warehouse, batches_on
    ):
        tid = sample_tenant.id
        StockBatchService.record_receipt(tid, sample_product.id, sample_warehouse.id, 2, 10)

        qty, value = StockBatchService.consume_fefo(sample_product.id, sample_warehouse.id, 5, tid)

        assert qty == Decimal("2")
        assert value == Decimal("20.000")

    def test_zero_quantity_is_neutral(self, db_session, sample_tenant, sample_product, sample_warehouse, batches_on):
        qty, value = StockBatchService.consume_fefo(sample_product.id, sample_warehouse.id, 0, sample_tenant.id)
        assert qty == Decimal("0")
        assert value == Decimal("0")


def _sale(product_id, quantity, tenant_id, warehouse_id):
    line = MagicMock()
    line.product_id = product_id
    line.quantity = Decimal(str(quantity))
    line.cost_price = None
    sale = MagicMock()
    sale.id = 9001
    sale.sale_number = "SALE-FEFO-1"
    sale.tenant_id = tenant_id
    sale.warehouse_id = warehouse_id
    sale.lines = [line]
    return sale


class TestFefoCogsIntegration:
    def test_cogs_uses_fefo_cost_not_mwac(
        self, app, db_session, sample_tenant, sample_product, sample_warehouse, batches_on
    ):
        tid = sample_tenant.id
        StockService._update_wac_on_receipt(
            tid, sample_product.id, sample_warehouse.id, Decimal("10"), Decimal("10"), "purchase", 1
        )
        StockService._update_wac_on_receipt(
            tid, sample_product.id, sample_warehouse.id, Decimal("10"), Decimal("20"), "purchase", 2
        )

        app.config["ENABLE_MWAC"] = True
        sale = _sale(sample_product.id, 5, tid, sample_warehouse.id)
        total = StockService.calculate_sale_cogs_and_deduct(sale)

        # MWAC would price 5 @ 15.000; FEFO prices the oldest lot @ 10.000.
        assert total == Decimal("50.000")
        b1, b2 = _batches(db_session, sample_product.id, sample_warehouse.id)
        assert b1.quantity == Decimal("5.000")
        assert b2.quantity == Decimal("10.000")

    def test_receipt_toggle_off_creates_no_batches(self, db_session, sample_tenant, sample_product, sample_warehouse):
        tid = sample_tenant.id
        StockService._update_wac_on_receipt(
            tid, sample_product.id, sample_warehouse.id, Decimal("10"), Decimal("10"), "purchase", 1
        )
        assert _batches(db_session, sample_product.id, sample_warehouse.id) == []

    def test_reverse_sale_restores_batch_at_original_cost(
        self, app, db_session, sample_tenant, sample_product, sample_warehouse, batches_on
    ):

        tid = sample_tenant.id
        StockService._update_wac_on_receipt(
            tid, sample_product.id, sample_warehouse.id, Decimal("10"), Decimal("10"), "purchase", 1
        )

        app.config["ENABLE_MWAC"] = True
        sale = _sale(sample_product.id, 4, tid, sample_warehouse.id)
        StockService.calculate_sale_cogs_and_deduct(sale)
        assert _batches(db_session, sample_product.id, sample_warehouse.id)[0].quantity == Decimal("6.000")

        StockService.reverse_sale(sale)

        batches = _batches(db_session, sample_product.id, sample_warehouse.id)
        reversal = next(b for b in batches if b.reference_type == "sale_reversal")
        assert reversal.quantity == Decimal("4.000")
        assert reversal.unit_cost == Decimal("10.0000")
        assert reversal.reference_id == sale.id
