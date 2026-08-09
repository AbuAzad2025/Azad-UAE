"""Tests for services/stock_sync_service.py uncovered lines."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_product():
    product = MagicMock()
    product.id = 1
    product.sku = "SKU001"
    product.barcode = "BAR001"
    return product


@pytest.fixture
def mock_warehouse():
    warehouse = MagicMock()
    warehouse.id = 1
    warehouse.code = "WH001"
    return warehouse


@pytest.fixture
def mock_sync_batch():
    batch = MagicMock()
    batch.id = 1
    batch.status = "completed"
    batch.idempotency_key = "idem-001"
    batch.payload_hash = "hash123"
    batch.processed_at = None
    batch.error_message = None
    return batch


def test_resolve_product_by_sku(mock_product):
    """Test _resolve_product with SKU."""
    from services.stock_sync_service import _resolve_product

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = mock_product
        result = _resolve_product("SKU001", None)
        assert result == mock_product


def test_resolve_product_by_barcode(mock_product):
    """Test _resolve_product with barcode."""
    from services.stock_sync_service import _resolve_product

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = mock_product
        result = _resolve_product(None, "BAR001")
        assert result == mock_product


def test_resolve_product_not_found():
    """Test _resolve_product when product not found."""
    from services.stock_sync_service import _resolve_product

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = None
        with pytest.raises(ValueError, match="Product not found"):
            _resolve_product("NONEXISTENT", None)


def test_resolve_product_no_sku_or_barcode():
    """Test _resolve_product with no SKU or barcode."""
    from services.stock_sync_service import _resolve_product

    with pytest.raises(ValueError, match="sku or barcode is required"):
        _resolve_product(None, None)


def test_resolve_warehouse_found(mock_warehouse):
    """Test _resolve_warehouse when warehouse exists."""
    from services.stock_sync_service import _resolve_warehouse

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = mock_warehouse
        result = _resolve_warehouse("WH001")
        assert result == mock_warehouse


def test_resolve_warehouse_not_found():
    """Test _resolve_warehouse when warehouse not found."""
    from services.stock_sync_service import _resolve_warehouse

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = None
        with pytest.raises(ValueError, match="Warehouse not found"):
            _resolve_warehouse("NONEXISTENT")


def test_resolve_warehouse_no_code():
    """Test _resolve_warehouse with no code."""
    from services.stock_sync_service import _resolve_warehouse

    result = _resolve_warehouse(None)
    assert result is None


def test_payload_hash():
    """Test _payload_hash produces deterministic hash."""
    from services.stock_sync_service import _payload_hash

    payload = {"b": 2, "a": 1}
    hash1 = _payload_hash(payload)
    hash2 = _payload_hash({"a": 1, "b": 2})
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex digest


def test_payload_hash_different():
    """Test _payload_hash produces different hashes for different payloads."""
    from services.stock_sync_service import _payload_hash

    hash1 = _payload_hash({"a": 1})
    hash2 = _payload_hash({"a": 2})
    assert hash1 != hash2


def test_get_sync_status_found(mock_sync_batch):
    """Test get_sync_status when batch exists."""
    from services.stock_sync_service import StockSyncService

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = mock_sync_batch
        result = StockSyncService.get_sync_status(1)
        assert result is not None
        assert result["batch_id"] == 1
        assert result["status"] == "completed"
        assert result["idempotency_key"] == "idem-001"


def test_get_sync_status_not_found():
    """Test get_sync_status when batch not found."""
    from services.stock_sync_service import StockSyncService

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = None
        result = StockSyncService.get_sync_status(999)
        assert result is None


def test_process_sync_payload_idempotent(mock_sync_batch):
    """Test process_sync_payload with existing idempotency key."""
    from services.stock_sync_service import StockSyncService

    with patch("services.stock_sync_service.tenant_query") as mock_q:
        mock_q.return_value.filter_by.return_value.first.return_value = mock_sync_batch
        result = StockSyncService.process_sync_payload(
            {
                "idempotency_key": "idem-001",
                "tenant_id": 1,
                "movements": [{"sku": "X", "quantity": 1, "movement_type": "adjustment"}],
            }
        )
        assert result["ok"] is True
        assert result["cached"] is True


def test_process_sync_payload_no_idempotency_key():
    """Test process_sync_payload without idempotency key."""
    from services.stock_sync_service import StockSyncService

    with pytest.raises(ValueError, match="idempotency_key is required"):
        StockSyncService.process_sync_payload({"tenant_id": 1})


def test_process_sync_payload_no_tenant_id():
    """Test process_sync_payload without tenant_id."""
    from services.stock_sync_service import StockSyncService

    with pytest.raises(ValueError, match="tenant_id is required"):
        StockSyncService.process_sync_payload({"idempotency_key": "x"})


def test_process_sync_payload_no_movements():
    """Test process_sync_payload without movements."""
    from services.stock_sync_service import StockSyncService

    with pytest.raises(ValueError, match="No movements provided"):
        StockSyncService.process_sync_payload({"idempotency_key": "x", "tenant_id": 1})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
