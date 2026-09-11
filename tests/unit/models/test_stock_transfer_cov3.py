"""Gap coverage for models/stock_transfer.py — status labels and reprs."""

from __future__ import annotations

import pytest

from models.stock_transfer import WarehouseTransfer, WarehouseTransferLine


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("draft", "مسودة"),
        ("approved", "موافق عليه"),
        ("in_transit", "قيد النقل"),
        ("completed", "مكتمل"),
        ("cancelled", "ملغي"),
        ("mystery", "mystery"),
    ],
)
def test_status_ar_matrix(status, expected):
    assert WarehouseTransfer(status=status).status_ar == expected


def test_transfer_repr():
    assert "TR-COV3" in repr(WarehouseTransfer(transfer_number="TR-COV3"))


def test_line_repr():
    line = WarehouseTransferLine(product_id=4, requested_quantity=7)
    text = repr(line)
    assert "product=4" in text
    assert "qty=7" in text
