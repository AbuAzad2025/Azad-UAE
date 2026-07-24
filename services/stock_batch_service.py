"""FEFO batch layer behind the global ``enable_batches`` toggle.

When disabled (the default), every function is a no-op / returns neutral
values and the MWAC pipeline behaves exactly as before. When enabled, COGS
for sales is priced from consumed batch costs (soonest expiry first) while
ProductWarehouseCost stays the quantity ledger.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from models import StockBatch, SystemSettings

_COST_QUANTUM = Decimal("0.0001")


class StockBatchService:
    @staticmethod
    def batches_enabled() -> bool:
        """Global toggle — memoized per request via SystemSettings.get_current().

        Strict ``is True`` so a mocked/odd settings object can never flip the
        batch layer on by accident; the MWAC default stays the fallback.
        """
        return getattr(SystemSettings.get_current(), "enable_batches", None) is True

    @staticmethod
    def record_receipt(
        tenant_id,
        product_id,
        warehouse_id,
        quantity,
        unit_cost,
        reference_type=None,
        reference_id=None,
        expiry_date=None,
    ):
        """Create one batch row for an incoming lot. Must run in a transaction."""
        qty = Decimal(str(quantity))
        if qty <= 0:
            return None
        batch = StockBatch(
            tenant_id=int(tenant_id),
            product_id=int(product_id),
            warehouse_id=int(warehouse_id),
            quantity=qty,
            unit_cost=Decimal(str(unit_cost)).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP),
            expiry_date=expiry_date,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        db.session.add(batch)
        db.session.flush()
        return batch

    @staticmethod
    def _fefo_query(product_id, warehouse_id, tenant_id):
        return StockBatch.query.filter(
            StockBatch.tenant_id == int(tenant_id),
            StockBatch.product_id == int(product_id),
            StockBatch.warehouse_id == int(warehouse_id),
            StockBatch.quantity > 0,
        ).order_by(
            StockBatch.expiry_date.is_(None),
            StockBatch.expiry_date.asc(),
            StockBatch.received_at.asc(),
            StockBatch.id.asc(),
        )

    @staticmethod
    def consume_fefo(product_id, warehouse_id, quantity, tenant_id):
        """Deduct up to ``quantity`` from batches in FEFO order.

        Locks each batch row FOR UPDATE (savepoint-retry via the stock
        service's lock helper) before consuming. Returns
        ``(consumed_qty, consumed_value)`` — partial when batches run out, so
        the caller prices the remainder through the standard fallback chain.
        """
        from services.stock_service import _safe_for_update

        remaining = Decimal(str(quantity))
        consumed_qty = Decimal("0")
        consumed_value = Decimal("0")
        if remaining <= 0:
            return consumed_qty, consumed_value
        while remaining > 0:
            query = StockBatchService._fefo_query(product_id, warehouse_id, tenant_id)
            batch = _safe_for_update(query, label=f"batch p={product_id} w={warehouse_id}")
            if batch is None:
                break
            on_hand = Decimal(str(batch.quantity))
            take = remaining if remaining <= on_hand else on_hand
            batch.quantity = on_hand - take
            consumed_qty += take
            consumed_value += take * Decimal(str(batch.unit_cost))
            remaining -= take
        return consumed_qty, consumed_value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def restore_on_reversal(tenant_id, product_id, warehouse_id, quantity, unit_cost, reference_id=None):
        """Re-add reversed-sale quantity as a fresh lot at its original cost."""
        qty = Decimal(str(quantity))
        if qty <= 0:
            return None
        batch = StockBatch(
            tenant_id=int(tenant_id),
            product_id=int(product_id),
            warehouse_id=int(warehouse_id),
            quantity=qty,
            unit_cost=Decimal(str(unit_cost)).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP),
            reference_type="sale_reversal",
            reference_id=reference_id,
        )
        db.session.add(batch)
        db.session.flush()
        return batch
