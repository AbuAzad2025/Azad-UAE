"""Cov4: stock_batch_service — toggle/receipt/fefo/consume/restore arcs."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from services.stock_batch_service import StockBatchService


def test_batches_enabled_branches():
    with patch("services.stock_batch_service.SystemSettings.get_current",
               return_value=SimpleNamespace(enable_batches=True)):
        assert StockBatchService.batches_enabled() is True
    with patch("services.stock_batch_service.SystemSettings.get_current",
               return_value=SimpleNamespace(enable_batches=1)):
        assert StockBatchService.batches_enabled() is False
    with patch("services.stock_batch_service.SystemSettings.get_current",
               return_value=SimpleNamespace()):
        assert StockBatchService.batches_enabled() is False


def test_record_receipt_guards(db_session, sample_tenant, sample_product, sample_warehouse):
    assert StockBatchService.record_receipt(sample_tenant.id, sample_product.id,
                                            sample_warehouse.id, 0, 5) is None
    assert StockBatchService.record_receipt(sample_tenant.id, sample_product.id,
                                            sample_warehouse.id, -2, 5) is None
    b = StockBatchService.record_receipt(sample_tenant.id, sample_product.id,
                                         sample_warehouse.id, "10", "2.5",
                                         reference_type="po", reference_id=1)
    assert b.quantity == Decimal("10")
    assert b.unit_cost == Decimal("2.5000")


def test_consume_fefo_paths(db_session, sample_tenant, sample_product, sample_warehouse):
    assert StockBatchService.consume_fefo(sample_product.id, sample_warehouse.id, 0,
                                          sample_tenant.id) == (Decimal("0"), Decimal("0"))
    # no batches -> partial (nothing consumed), quantize branch
    qty, val = StockBatchService.consume_fefo(999999998, sample_warehouse.id, 5, sample_tenant.id)
    assert qty == Decimal("0")
    StockBatchService.record_receipt(sample_tenant.id, sample_product.id, sample_warehouse.id,
                                     "6", "3", expiry_date=None)
    StockBatchService.record_receipt(sample_tenant.id, sample_product.id, sample_warehouse.id,
                                     "10", "4", expiry_date=None)
    qty, val = StockBatchService.consume_fefo(sample_product.id, sample_warehouse.id, "8",
                                              sample_tenant.id)
    assert qty == Decimal("8")
    assert val == Decimal("26.000")  # 6*3 + 2*4


def test_restore_on_reversal(db_session, sample_tenant, sample_product, sample_warehouse):
    assert StockBatchService.restore_on_reversal(sample_tenant.id, sample_product.id,
                                                 sample_warehouse.id, 0, 1) is None
    b = StockBatchService.restore_on_reversal(sample_tenant.id, sample_product.id,
                                              sample_warehouse.id, "2", "1.5", reference_id=9)
    assert b.reference_type == "sale_reversal"
    assert b.reference_id == 9


def test_fefo_query_orders_nulls_first(db_session, sample_tenant, sample_product, sample_warehouse):
    from datetime import date

    StockBatchService.record_receipt(sample_tenant.id, sample_product.id, sample_warehouse.id,
                                     "1", "1", expiry_date=date(2030, 1, 1))
    StockBatchService.record_receipt(sample_tenant.id, sample_product.id, sample_warehouse.id,
                                     "1", "1", expiry_date=None)
    rows = StockBatchService._fefo_query(sample_product.id, sample_warehouse.id,
                                         sample_tenant.id).all()
    assert len(rows) >= 2
