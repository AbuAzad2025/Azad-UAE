"""Purchase requisition/order/GRN model helpers (unsaved-instance unit tests)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from models.purchase import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
)


def _req(status="draft", priority="normal"):
    return PurchaseRequisition(
        requisition_number="PR-1",
        status=status,
        priority=priority,
    )


class TestBaseCurrencyDisplay:
    def test_display_alias_mirrors_base_currency(self):
        from models.purchase import Purchase

        po = Purchase(base_currency="AED")
        assert po.base_currency == po.base_currency_display


class TestPurchaseRequisitionHelpers:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("draft", "مسودة"),
            ("pending_approval", "بانتظار الموافقة"),
            ("approved", "تمت الموافقة"),
            ("rejected", "مرفوض"),
            ("converted_to_po", "تم التحويل لطلب شراء"),
            ("unknown-x", "unknown-x"),
        ],
    )
    def test_status_ar_matrix(self, status, expected):
        assert _req(status).status_ar == expected

    @pytest.mark.parametrize(
        ("priority", "expected"),
        [("low", "منخفضة"), ("normal", "عادية"), ("high", "عالية"), ("urgent", "عاجلة"), ("odd", "odd")],
    )
    def test_priority_ar_matrix(self, priority, expected):
        assert _req(priority=priority).priority_ar == expected

    def test_reprs(self):
        assert "<PurchaseRequisition PR-1>" in repr(_req())
        line = PurchaseRequisitionLine(product_id=3, quantity=Decimal("2"))
        assert "<PurchaseRequisitionLine 3 x 2" in repr(line)


class TestPurchaseOrderHelpers:
    def _po(self, lines=None, status="confirmed"):
        po = PurchaseOrder(po_number="PO-9", status=status)
        if lines is not None:
            # Real ORM children are required because appending to a
            # relationship collection fires backref events.
            po.lines = [PurchaseOrderLine(**kw) for kw in lines]
        return po

    def test_calculate_totals_sums_lines_plus_tax(self):
        po = self._po([{"line_total": Decimal("12.5")}, {"line_total": Decimal("7.25")}])
        po.tax_amount = Decimal("1")
        po.calculate_totals()
        assert po.subtotal == Decimal("19.75")
        assert po.total_amount == Decimal("20.75")

    def test_received_quantity_and_completion(self):
        po = self._po(
            [
                {"received_quantity": Decimal("8"), "quantity": Decimal("8")},
                {"received_quantity": None, "quantity": Decimal("4")},
            ]
        )
        assert po.total_received_quantity == Decimal("8")
        assert po.is_fully_received is False

        done = self._po([{"received_quantity": Decimal("5"), "quantity": Decimal("5")}])
        assert done.is_fully_received is True

        empty_qty = self._po([{"quantity": None}])
        assert empty_qty.total_received_quantity == Decimal("0")
        assert empty_qty.is_fully_received is True  # no quantity-bearing lines

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            ("draft", "مسودة"),
            ("submitted", "مُرسل"),
            ("confirmed", "مؤكد"),
            ("partially_received", "تم الاستلام جزئياً"),
            ("received", "تم الاستلام"),
            ("closed", "مغلق"),
            ("cancelled", "ملغى"),
            ("other", "other"),
        ],
    )
    def test_po_status_ar_matrix(self, status, expected):
        assert self._po(status=status).status_ar == expected

    def test_po_line_total_and_repr(self):
        line = PurchaseOrderLine(product_id=6, quantity=Decimal("3"), unit_cost=Decimal("2"))
        line.calculate_line_total()
        assert line.line_total == Decimal("6")

        blank = PurchaseOrderLine()
        blank.calculate_line_total()
        assert blank.line_total == Decimal("0")
        assert "<PurchaseOrderLine 6 x 3" in repr(line)


class TestGoodsReceiptHelpers:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [("draft", "مسودة"), ("confirmed", "مؤكد"), ("cancelled", "ملغى"), ("zzz", "zzz")],
    )
    def test_grn_status_ar(self, status, expected):
        grn = GoodsReceipt(grn_number="GRN-1", status=status)
        assert grn.status_ar == expected

    def test_grn_reprs(self):
        assert "<GoodsReceipt GRN-1>" in repr(GoodsReceipt(grn_number="GRN-1"))
        line = GoodsReceiptLine(product_id=11, received_quantity=Decimal("4"))
        assert "received=4" in repr(line)
