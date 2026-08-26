"""StockSyncService — real-DB behavioral coverage.

Exercises the full inbound sync path against real rows: idempotency
(cold + in-transaction race guard), product/warehouse resolution,
movement creation through StockService, batch completion, and the
atomic rollback guarantee when a movement fails validation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from models import Product, StockMovement, SyncBatch, Warehouse
from services.stock_sync_service import StockSyncService


@pytest.fixture
def warehouse(db_session, sample_tenant, sample_branch):
    w = Warehouse(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        name="Sync WH",
        code=f"SYNCWH-{uuid.uuid4().hex[:6].upper()}",
        is_active=True,
    )
    db_session.add(w)
    db_session.commit()
    return w


@pytest.fixture
def product(db_session, sample_tenant):
    p = Product(
        tenant_id=sample_tenant.id,
        name="Synced Product",
        sku=f"SYNC-{uuid.uuid4().hex[:8]}",
        barcode=f"BC-{uuid.uuid4().hex[:10]}",
        cost_price=Decimal("5.000"),
        regular_price=Decimal("9.000"),
    )
    db_session.add(p)
    db_session.commit()
    return p


def _payload(product, tenant_id, **over):
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "movements": [
            {
                "sku": product.sku,
                "warehouse_code": None,
                "quantity": 5,
                "movement_type": "purchase",
                "notes": "POS sync",
            }
        ],
    }
    payload.update(over)
    return payload


class TestProcessSyncPayload:
    def test_creates_batch_and_movements_end_to_end(self, db_session, sample_tenant, product, warehouse):
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[
                {
                    "sku": product.sku,
                    "warehouse_code": warehouse.code,
                    "quantity": 7,
                    "movement_type": "purchase",
                }
            ],
        )
        result = StockSyncService.process_sync_payload(payload)

        assert result["ok"] is True
        assert result["cached"] is False
        assert result["status"] == "completed"
        batch = db_session.get(SyncBatch, result["batch_id"])
        assert batch.status == "completed"
        assert batch.tenant_id == sample_tenant.id
        assert batch.idempotency_key == payload["idempotency_key"]
        assert len(batch.payload_hash) == 64
        assert batch.processed_at is not None

        mv = db_session.get(StockMovement, result["movements"][0]["movement_id"])
        assert mv.product_id == product.id
        assert mv.warehouse_id == warehouse.id
        assert Decimal(str(mv.quantity)) == Decimal("7")
        assert mv.reference_type == "pos_sync"
        assert mv.reference_id == batch.id

    def test_flat_single_movement_backward_compat(self, db_session, sample_tenant, product):
        """A bare payload with a sku (no movements list) still syncs."""
        payload = {
            "idempotency_key": f"flat-{uuid.uuid4().hex[:12]}",
            "tenant_id": sample_tenant.id,
            "sku": product.sku,
            "quantity": 3,
            "movement_type": "adjustment",
        }
        result = StockSyncService.process_sync_payload(payload)

        assert result["ok"] is True
        assert len(result["movements"]) == 1
        mv = db_session.get(StockMovement, result["movements"][0]["movement_id"])
        assert mv.product_id == product.id

    def test_resolves_product_by_barcode_when_no_sku(self, db_session, sample_tenant, product, warehouse):
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[{"barcode": product.barcode, "quantity": 2, "movement_type": "purchase"}],
        )
        result = StockSyncService.process_sync_payload(payload)

        mv = db_session.get(StockMovement, result["movements"][0]["movement_id"])
        assert mv.product_id == product.id

    def test_completed_batch_is_returned_cached_without_reprocessing(self, db_session, sample_tenant, product):
        payload = _payload(product, sample_tenant.id)
        first = StockSyncService.process_sync_payload(payload)
        assert first["cached"] is False

        second = StockSyncService.process_sync_payload(payload)
        assert second["cached"] is True
        assert second["batch_id"] == first["batch_id"]
        assert second["status"] == "completed"
        # No duplicate movements were created.
        assert second["movements"] == []

    def test_in_transaction_race_guard_returns_existing_pending_batch(self, db_session, sample_tenant, product):
        """A pending batch with the same key short-circuits inside the
        transaction — no second batch row may be created."""
        key = f"race-{uuid.uuid4().hex[:12]}"
        existing = SyncBatch(tenant_id=sample_tenant.id, idempotency_key=key, status="pending")
        db_session.add(existing)
        db_session.commit()

        result = StockSyncService.process_sync_payload(_payload(product, sample_tenant.id, idempotency_key=key))
        db_session.rollback()

        assert result["cached"] is True
        assert result["status"] == "pending"
        batches = db_session.query(SyncBatch).filter(SyncBatch.idempotency_key == key).all()
        assert len(batches) == 1

    def test_failed_movement_rolls_back_entire_batch(self, db_session, sample_tenant, product):
        """Second movement references an unknown SKU → ValueError; the
        atomic_transaction must roll back so NO batch row survives."""
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[
                {"sku": product.sku, "quantity": 1, "movement_type": "purchase"},
                {"sku": "GHOST-SKU-404", "quantity": 1, "movement_type": "purchase"},
            ],
        )
        key = payload["idempotency_key"]

        with pytest.raises(ValueError, match="Product not found"):
            StockSyncService.process_sync_payload(payload)

        db_session.rollback()
        assert db_session.query(SyncBatch).filter(SyncBatch.idempotency_key == key).first() is None

    def test_missing_quantity_raises_and_leaves_no_batch(self, db_session, sample_tenant, product):
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[{"sku": product.sku, "movement_type": "purchase"}],
        )
        key = payload["idempotency_key"]
        with pytest.raises(ValueError, match="quantity and movement_type are required"):
            StockSyncService.process_sync_payload(payload)
        db_session.rollback()
        assert db_session.query(SyncBatch).filter(SyncBatch.idempotency_key == key).first() is None

    def test_unknown_warehouse_code_rejected(self, db_session, sample_tenant, product):
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[{"sku": product.sku, "warehouse_code": "NOPE-404", "quantity": 1, "movement_type": "purchase"}],
        )
        with pytest.raises(ValueError, match="Warehouse not found"):
            StockSyncService.process_sync_payload(payload)
        db_session.rollback()

    def test_requires_idempotency_key_and_tenant(self):
        with pytest.raises(ValueError, match="idempotency_key"):
            StockSyncService.process_sync_payload({"tenant_id": 1})
        with pytest.raises(ValueError, match="tenant_id"):
            StockSyncService.process_sync_payload({"idempotency_key": "x"})
        with pytest.raises(ValueError, match="No movements provided"):
            StockSyncService.process_sync_payload({"idempotency_key": "x", "tenant_id": 1})


class TestGetSyncStatus:
    def test_returns_status_for_completed_batch(self, db_session, sample_tenant, product):
        result = StockSyncService.process_sync_payload(_payload(product, sample_tenant.id))

        status = StockSyncService.get_sync_status(result["batch_id"])
        assert status is not None
        assert status["batch_id"] == result["batch_id"]
        assert status["status"] == "completed"
        assert status["idempotency_key"].startswith("idem-")
        assert status["payload_hash"]
        assert status["processed_at"] is not None
        assert status["error_message"] is None

    def test_pending_batch_reports_null_processed_at(self, db_session, sample_tenant):
        batch = SyncBatch(tenant_id=sample_tenant.id, idempotency_key=f"p-{uuid.uuid4().hex[:8]}", status="pending")
        db_session.add(batch)
        db_session.commit()

        status = StockSyncService.get_sync_status(batch.id)
        assert status["status"] == "pending"
        assert status["processed_at"] is None

    def test_unknown_batch_returns_none(self, db_session):
        assert StockSyncService.get_sync_status(987654321) is None
