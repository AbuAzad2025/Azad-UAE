"""Supplier model — balances, statistics, display helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock


def _supplier_stub(**kwargs):
    from models.supplier import Supplier

    class Stub:
        id = kwargs.get("id", 1)
        tenant_id = kwargs.get("tenant_id", 1)
        name = kwargs.get("name", "Parts Co")
        name_en = kwargs.get("name_en", "Parts Co EN")
        company_name = kwargs.get("company_name", "Parts LLC")
        phone = kwargs.get("phone", "0500000000")
        email = kwargs.get("email", "parts@test.com")
        supplier_type = kwargs.get("supplier_type", "parts")
        rating = kwargs.get("rating", 4)
        total_purchases_aed = kwargs.get("total_purchases_aed", Decimal("1000"))
        total_paid_aed = kwargs.get("total_paid_aed", Decimal("400"))
        is_active = kwargs.get("is_active", True)
        is_verified = kwargs.get("is_verified", True)
        country = kwargs.get("country", "AE")
        city = kwargs.get("city", "Dubai")
        purchases = kwargs.get("purchases", MagicMock())

        last_purchase_date = kwargs.get("last_purchase_date")
        total_purchases_base = Supplier.total_purchases_base
        total_paid_base = Supplier.total_paid_base
        get_balance_aed = Supplier.get_balance_aed
        get_balance_base = Supplier.get_balance_base
        apply_purchase = Supplier.apply_purchase
        apply_payment = Supplier.apply_payment
        apply_purchase_base = Supplier.apply_purchase_base
        apply_payment_base = Supplier.apply_payment_base
        get_display_name = Supplier.get_display_name
        get_type_display = Supplier.get_type_display
        get_rating_stars = Supplier.get_rating_stars
        update_statistics = Supplier.update_statistics
        to_dict = Supplier.to_dict
        __repr__ = Supplier.__repr__

    return Stub()


class TestSupplierBalances:
    def test_repr(self):
        assert "Parts Co" in repr(_supplier_stub())

    def test_balance_aliases(self):
        s = _supplier_stub(
            total_purchases_aed=Decimal("1000"), total_paid_aed=Decimal("250")
        )
        assert s.get_balance_aed() == Decimal("750")
        assert s.get_balance_base() == Decimal("750")

    def test_base_property_setters(self):
        s = _supplier_stub()
        s.total_purchases_base = Decimal("200")
        s.total_paid_base = Decimal("50")
        assert s.total_purchases_aed == Decimal("200")
        assert s.total_paid_aed == Decimal("50")

    def test_apply_purchase_and_payment(self):
        s = _supplier_stub(
            total_purchases_aed=Decimal("100"), total_paid_aed=Decimal("20")
        )
        s.apply_purchase(Decimal("50"))
        s.apply_payment(Decimal("10"))
        s.apply_purchase_base(Decimal("5"))
        s.apply_payment_base(Decimal("5"))
        assert s.total_purchases_aed == Decimal("155")
        assert s.total_paid_aed == Decimal("35")


class TestSupplierDisplay:
    def test_get_display_name(self):
        assert _supplier_stub().get_display_name("en") == "Parts Co EN"
        assert _supplier_stub(name_en=None).get_display_name("en") == "Parts Co"

    def test_get_type_display(self):
        assert _supplier_stub(supplier_type="equipment").get_type_display() == "معدات"
        assert _supplier_stub(supplier_type="custom").get_type_display() == "custom"

    def test_get_rating_stars(self):
        assert "⭐" in _supplier_stub(rating=3).get_rating_stars()
        assert _supplier_stub(rating=0).get_rating_stars() == "☆☆☆☆☆"

    def test_supplier_base_getters(self):
        s = _supplier_stub(
            total_purchases_aed=Decimal("10"), total_paid_aed=Decimal("3")
        )
        assert s.total_purchases_base == Decimal("10")
        assert s.total_paid_base == Decimal("3")

    def test_to_dict(self):
        data = _supplier_stub().to_dict()
        assert data["balance_aed"] == 600.0
        assert data["type_display"] == "قطع غيار"


class TestSupplierStatistics:
    def test_update_statistics(self, mocker):
        purchase = MagicMock(
            status="confirmed",
            amount_aed=Decimal("300"),
            purchase_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        purchases = MagicMock()
        purchases.filter_by.return_value.all.return_value = [purchase]
        s = _supplier_stub(purchases=purchases)

        amount_q = MagicMock()
        amount_q.filter.return_value.scalar.return_value = Decimal("100")
        mocker.patch("models.supplier.db.session.query", return_value=amount_q)

        s.update_statistics()
        assert s.total_purchases_aed == Decimal("300")
        assert s.total_paid_aed == Decimal("100")
        assert s.last_purchase_date == purchase.purchase_date
