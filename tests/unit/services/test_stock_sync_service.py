"""StockSyncService — real-DB behavioral coverage.

Exercises the full inbound sync path against real rows: idempotency
(cold + in-transaction race guard), product/warehouse resolution,
movement creation through StockService, MWAC/GL valuation, batch
completion, and the atomic rollback guarantee when a movement fails
validation or cannot be valued.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from models import (
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    Product,
    ProductCostHistory,
    ProductWarehouseCost,
    StockMovement,
    SyncBatch,
    Warehouse,
)
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


class TestSyncedMovementValuation:
    """A synced movement must not commit with quantity changed but value silent.

    The GL gateway is exercised against the real tenant chart (the tests assert
    real posted journal rows), and the service-to-service boundary is mocked only
    in the delegation test below. PWC/GL amounts are compared as exact Decimals.
    """

    @staticmethod
    def _pwc(db_session, sample_tenant, product, warehouse):
        return (
            db_session.query(ProductWarehouseCost)
            .filter_by(
                tenant_id=sample_tenant.id,
                product_id=product.id,
                warehouse_id=warehouse.id,
            )
            .one()
        )

    @staticmethod
    def _sync_entry(db_session, sample_tenant, movement_id):
        from utils.gl_reference_types import GLRef, filter_entries_by_ref

        return (
            filter_entries_by_ref(db_session.query(GLJournalEntry), GLRef.INVENTORY_MIGRATION)
            .filter(
                GLJournalEntry.tenant_id == sample_tenant.id,
                GLJournalEntry.reference_id == movement_id,
                GLJournalEntry.status == "posted",
            )
            .one()
        )

    @staticmethod
    def _gl_lines_by_code(db_session, entry):
        out = {}
        for line in db_session.query(GLJournalLine).filter_by(entry_id=entry.id).all():
            code = db_session.get(GLAccount, line.account_id).code
            out[code] = (Decimal(str(line.debit or 0)), Decimal(str(line.credit or 0)))
        return out

    def test_receipt_posts_gl_and_updates_pwc(self, db_session, sample_tenant, product, warehouse):
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[
                {
                    "sku": product.sku,
                    "warehouse_code": warehouse.code,
                    "quantity": 4,
                    "movement_type": "purchase",
                    "unit_cost": 2.5,
                }
            ],
        )
        result = StockSyncService.process_sync_payload(payload)
        assert result["ok"] is True
        movement_id = result["movements"][0]["movement_id"]

        # MWAC: a first receipt at 2.5 seeds the warehouse valuation.
        pwc = self._pwc(db_session, sample_tenant, product, warehouse)
        assert Decimal(str(pwc.total_quantity)) == Decimal("4")
        assert Decimal(str(pwc.total_value)) == Decimal("10")
        assert Decimal(str(pwc.average_cost)) == Decimal("2.5")

        history = (
            db_session.query(ProductCostHistory)
            .filter_by(
                tenant_id=sample_tenant.id,
                product_id=product.id,
                warehouse_id=warehouse.id,
                movement_type="purchase",
            )
            .one()
        )
        assert Decimal(str(history.quantity_change)) == Decimal("4")
        assert Decimal(str(history.movement_unit_cost)) == Decimal("2.5")

        # The same transaction wrote a balanced, posted journal entry.
        entry = self._sync_entry(db_session, sample_tenant, movement_id)
        from services.gl_service import GLService

        asset = GLService.get_account_code_for_concept(
            "INVENTORY_ASSET", tenant_id=sample_tenant.id, branch_id=warehouse.branch_id
        )
        equity = GLService.get_account_code_for_concept(
            "OPENING_BALANCE_EQUITY", tenant_id=sample_tenant.id, branch_id=warehouse.branch_id
        )
        lines = self._gl_lines_by_code(db_session, entry)
        assert lines[asset] == (Decimal("10"), Decimal("0"))
        assert lines[equity] == (Decimal("0"), Decimal("10"))
        assert sum(d for d, _ in lines.values()) == sum(c for _, c in lines.values())

    def test_issue_decrements_pwc_and_posts_loss(self, db_session, sample_tenant, product, warehouse):
        # Seed the shelf first: 10 units at 2.5 -> value 25.
        StockSyncService.process_sync_payload(
            _payload(
                product,
                sample_tenant.id,
                movements=[
                    {
                        "sku": product.sku,
                        "warehouse_code": warehouse.code,
                        "quantity": 10,
                        "movement_type": "purchase",
                        "unit_cost": 2.5,
                    }
                ],
            )
        )
        before = self._pwc(db_session, sample_tenant, product, warehouse)
        assert Decimal(str(before.total_quantity)) == Decimal("10")
        assert Decimal(str(before.total_value)) == Decimal("25")

        result = StockSyncService.process_sync_payload(
            _payload(
                product,
                sample_tenant.id,
                movements=[
                    {
                        "sku": product.sku,
                        "warehouse_code": warehouse.code,
                        "quantity": -4,
                        "movement_type": "sale",
                    }
                ],
            )
        )
        movement_id = result["movements"][0]["movement_id"]

        # The issue is valued at the MWAC on the shelf, not the retail price.
        after = self._pwc(db_session, sample_tenant, product, warehouse)
        assert Decimal(str(after.total_quantity)) == Decimal("6")
        assert Decimal(str(after.total_value)) == Decimal("15")
        assert Decimal(str(after.average_cost)) == Decimal("2.5")
        assert Decimal(str(product.current_stock)) == Decimal("6")

        entry = self._sync_entry(db_session, sample_tenant, movement_id)
        from services.gl_service import GLService

        asset = GLService.get_account_code_for_concept(
            "INVENTORY_ASSET", tenant_id=sample_tenant.id, branch_id=warehouse.branch_id
        )
        loss = GLService.get_account_code_for_concept(
            "INVENTORY_ADJUSTMENT_LOSS", tenant_id=sample_tenant.id, branch_id=warehouse.branch_id
        )
        lines = self._gl_lines_by_code(db_session, entry)
        assert lines[loss] == (Decimal("10"), Decimal("0"))
        assert lines[asset] == (Decimal("0"), Decimal("10"))
        assert sum(d for d, _ in lines.values()) == sum(c for _, c in lines.values())

    def test_unsupported_movement_type_is_refused_and_batch_rolled_back(self, db_session, sample_tenant, product):
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[{"sku": product.sku, "quantity": 3, "movement_type": "transfer"}],
        )
        with pytest.raises(ValueError, match="Cannot value stock-sync movement type 'transfer'"):
            StockSyncService.process_sync_payload(payload)
        db_session.rollback()
        assert db_session.query(SyncBatch).filter_by(idempotency_key=payload["idempotency_key"]).first() is None

    def test_receipt_without_any_cost_is_refused(self, db_session, sample_tenant, product, warehouse):
        product.cost_price = None
        db_session.flush()
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[
                {
                    "sku": product.sku,
                    "warehouse_code": warehouse.code,
                    "quantity": 2,
                    "movement_type": "purchase",
                }
            ],
        )
        with pytest.raises(ValueError, match="no unit cost was supplied"):
            StockSyncService.process_sync_payload(payload)
        db_session.rollback()
        assert db_session.query(SyncBatch).filter_by(idempotency_key=payload["idempotency_key"]).first() is None

    def test_valuation_is_delegated_at_the_service_boundary(self, db_session, sample_tenant, product, warehouse):
        """The sync service hands the freshly created movement to StockService.

        Mocked at the service boundary only; the GL/PWC effects themselves are
        asserted end-to-end in the two tests above.
        """
        payload = _payload(
            product,
            sample_tenant.id,
            movements=[
                {
                    "sku": product.sku,
                    "warehouse_code": warehouse.code,
                    "quantity": 1,
                    "movement_type": "purchase",
                    "unit_cost": 7.25,
                }
            ],
        )
        with patch("services.stock_sync_service.StockService.value_synced_movement") as value_movement:
            result = StockSyncService.process_sync_payload(payload)

        value_movement.assert_called_once()
        (movement,) = value_movement.call_args.args
        assert movement.id == result["movements"][0]["movement_id"]
        assert value_movement.call_args.kwargs["product"].id == product.id
        assert value_movement.call_args.kwargs["warehouse"].id == warehouse.id
        assert value_movement.call_args.kwargs["unit_cost"] == Decimal("7.25")


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


def test_lookup_queries_do_not_scale_with_payload_size(db_session, sample_tenant, product, warehouse):
    """Regression: the per-movement *lookup* was an N+1 (measured ~22 SELECTs/movement).

    Product and warehouse resolution now runs once for the whole payload. The
    per-movement statements that remain are deliberate: the SELECT ... FOR UPDATE on
    product_warehouse_stock is what stops two concurrent movements from overselling,
    and the SUM recomputed from that locked row is derived from it. GL and MWAC
    valuation are also per movement by necessity, so that boundary is mocked out
    here; the assertion is about the lookups rather than the raw total.
    """
    from sqlalchemy import event

    from extensions import db

    counts: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
        head = statement.lstrip()[:6].upper()
        if not head.startswith(("SELECT", "WITH")):
            return
        normalised = " ".join(statement.split())
        upper = normalised.upper()
        if "PRODUCT_WAREHOUSE_STOCK" in upper and "FOR UPDATE" in upper:
            return
        if normalised.startswith("SELECT coalesce(sum(product_warehouse_stock"):
            return
        counts.append(normalised)

    def _run(n: int) -> list[str]:
        counts.clear()
        payload = _payload(product, sample_tenant.id)
        payload["movements"] = [dict(payload["movements"][0]) for _ in range(n)]
        event.listen(db.engine, "before_cursor_execute", _count)
        try:
            with patch("services.stock_sync_service.StockService.value_synced_movement"):
                StockSyncService.process_sync_payload(payload)
            db.session.commit()
        finally:
            event.remove(db.engine, "before_cursor_execute", _count)
        return list(counts)

    small = _run(2)
    large = _run(20)
    # The lookup set is resolved once per payload, so its cost is a constant:
    # 1 idempotency check + 1 in-transaction recheck + 1 product IN() + 1 warehouse IN()
    # (+ 2 when a movement has no warehouse code and the main warehouse is resolved).
    assert len(small) <= 8, f"unexpected baseline lookup cost: {len(small)}\n" + "\n".join(small[:10])
    assert len(large) == len(small), (
        f"lookup queries scale with payload size: {len(small)} for 2 movements, "
        f"{len(large)} for 20 - the N+1 is back:\n" + "\n".join(sorted(set(large))[:10])
    )
