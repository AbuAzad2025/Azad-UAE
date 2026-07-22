"""
Lean external POS stock-sync service.

Delegates all stock mutation to StockService.create_movement() so row-level
locking, MWAC updates, GL posting, and negative-stock guards are inherited
with zero duplicated logic.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from extensions import db
from models import Product, SyncBatch, Warehouse
from services.stock_service import StockService
from utils.db_safety import atomic_transaction
from utils.tenanting import tenant_query


def _resolve_product(sku: str | None, barcode: str | None):
    """Resolve SKU or barcode to a tenant-scoped Product."""
    q = tenant_query(Product)
    if sku:
        product = q.filter_by(sku=sku).first()
    elif barcode:
        product = q.filter_by(barcode=barcode).first()
    else:
        raise ValueError("sku or barcode is required")
    if not product:
        raise ValueError(f"Product not found: sku={sku} barcode={barcode}")
    return product


def _resolve_warehouse(warehouse_code: str | None):
    """Resolve warehouse code to a tenant-scoped Warehouse."""
    if not warehouse_code:
        return None
    warehouse = tenant_query(Warehouse).filter_by(code=warehouse_code, is_active=True).first()
    if not warehouse:
        raise ValueError(f"Warehouse not found or inactive: {warehouse_code}")
    return warehouse


def _payload_hash(payload: dict[str, Any]) -> str:
    """Deterministic SHA-256 hash of the sorted JSON payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StockSyncService:
    """Minimal facade for inbound stock sync from external POS systems."""

    @staticmethod
    def process_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Process a sync payload atomically.

        Returns a result dict with ``batch_id``, ``movements``, ``status``.
        Duplicate ``idempotency_key`` values for the same tenant return the
        cached result (HTTP 409 semantics are handled by the caller).
        """
        idempotency_key = payload.get("idempotency_key")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise ValueError("tenant_id is required")

        # Idempotency check (outside the stock transaction is fine; we guard
        # against re-processing inside the transaction as well).
        existing = tenant_query(SyncBatch).filter_by(idempotency_key=idempotency_key, status="completed").first()
        if existing:
            return {
                "ok": True,
                "batch_id": existing.id,
                "status": "completed",
                "cached": True,
                "movements": [],
            }

        movements_data = payload.get("movements") or []
        # Also accept a single flat movement (backward compat)
        if not movements_data and payload.get("sku"):
            movements_data = [payload]

        if not movements_data:
            raise ValueError("No movements provided")

        phash = _payload_hash(payload)
        results: list[dict[str, Any]] = []

        with atomic_transaction("external_pos_stock_sync"):
            # Re-check idempotency inside the transaction to close the race.
            existing = tenant_query(SyncBatch).filter_by(idempotency_key=idempotency_key).first()
            if existing:
                return {
                    "ok": True,
                    "batch_id": existing.id,
                    "status": existing.status,
                    "cached": True,
                    "movements": [],
                }

            batch = SyncBatch(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                status="pending",
                payload_hash=phash,
            )
            db.session.add(batch)
            db.session.flush()

            for idx, mv in enumerate(movements_data):
                sku = mv.get("sku") or mv.get("barcode")
                barcode = mv.get("barcode")
                warehouse_code = mv.get("warehouse_code")
                quantity = mv.get("quantity")
                movement_type = mv.get("movement_type")
                notes = mv.get("notes", "POS sync")

                if quantity is None or movement_type is None:
                    raise ValueError(f"movement[{idx}]: quantity and movement_type are required")

                product = _resolve_product(sku if not barcode else None, barcode)
                warehouse = _resolve_warehouse(warehouse_code)
                warehouse_id = warehouse.id if warehouse else None

                movement = StockService.create_movement(
                    product_id=product.id,
                    quantity=Decimal(str(quantity)),
                    movement_type=movement_type,
                    warehouse_id=warehouse_id,
                    notes=notes,
                    reference_type="pos_sync",
                    reference_id=batch.id,
                )

                results.append(
                    {
                        "movement_id": movement.id,
                        "product_id": product.id,
                        "warehouse_id": warehouse_id,
                        "quantity": str(quantity),
                        "movement_type": movement_type,
                    }
                )

            batch.status = "completed"
            batch.processed_at = datetime.now(timezone.utc)
            db.session.flush()

        return {
            "ok": True,
            "batch_id": batch.id,
            "status": "completed",
            "cached": False,
            "movements": results,
        }

    @staticmethod
    def get_sync_status(batch_id: int) -> dict[str, Any] | None:
        """Return the status of a sync batch, or None if not found."""
        batch = tenant_query(SyncBatch).filter_by(id=batch_id).first()
        if not batch:
            return None
        return {
            "batch_id": batch.id,
            "status": batch.status,
            "idempotency_key": batch.idempotency_key,
            "payload_hash": batch.payload_hash,
            "processed_at": batch.processed_at.isoformat() if batch.processed_at else None,
            "error_message": batch.error_message,
        }
