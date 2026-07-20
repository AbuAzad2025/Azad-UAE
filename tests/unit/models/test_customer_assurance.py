"""Customer model — balance mutations, classification, serialization."""

from __future__ import annotations

from decimal import Decimal

import pytest


def _customer_stub(**kwargs):
    from models.customer import Customer

    class Stub:
        id = kwargs.get("id", 1)
        name = kwargs.get("name", "Ali")
        name_ar = kwargs.get("name_ar", "علي")
        customer_type = kwargs.get("customer_type", "regular")
        customer_classification = kwargs.get("customer_classification", "regular")
        balance = kwargs.get("balance", Decimal("0"))
        total_purchases = kwargs.get("total_purchases", Decimal("0"))
        phone = kwargs.get("phone", "0501234567")
        email = kwargs.get("email", "ali@test.com")
        is_active = kwargs.get("is_active", True)

        get_balance_aed = Customer.get_balance_aed
        get_balance_base = Customer.get_balance_base
        apply_sale = Customer.apply_sale
        apply_receipt = Customer.apply_receipt
        apply_return = Customer.apply_return
        adjust_balance = Customer.adjust_balance
        set_balance = Customer.set_balance
        get_display_name = Customer.get_display_name
        get_type_display = Customer.get_type_display
        get_classification_display = Customer.get_classification_display
        update_classification = Customer.update_classification
        to_dict = Customer.to_dict
        __repr__ = Customer.__repr__

    return Stub()


class TestCustomerBalance:
    def test_repr(self):
        assert "Ali" in repr(_customer_stub())

    def test_balance_aliases(self):
        c = _customer_stub(balance=Decimal("25.5"))
        assert c.get_balance_aed() == Decimal("25.5")
        assert c.get_balance_base() == Decimal("25.5")

    def test_apply_sale_reduces_balance(self):
        c = _customer_stub(balance=Decimal("100"))
        c.apply_sale(50)
        assert c.balance == Decimal("50")

    def test_apply_receipt_and_return_increase_balance(self):
        c = _customer_stub(balance=Decimal("10"))
        c.apply_receipt(5)
        c.apply_return(3)
        assert c.balance == Decimal("18")

    def test_adjust_and_set_balance(self):
        c = _customer_stub(balance=Decimal("0"))
        c.adjust_balance(-20)
        c.set_balance("15")
        assert c.balance == Decimal("15")


class TestCustomerLabels:
    def test_get_display_name(self):
        assert _customer_stub().get_display_name() == "علي"
        assert _customer_stub(name_ar=None).get_display_name() == "Ali"

    def test_get_type_display(self):
        assert _customer_stub(customer_type="merchant").get_type_display() == "تاجر"

    def test_get_classification_display(self):
        assert _customer_stub(customer_classification="vip").get_classification_display() == "VIP - عميل مميز"

    @pytest.mark.parametrize(
        "total,expected",
        [
            (Decimal("120000"), "vip"),
            (Decimal("60000"), "premium"),
            (Decimal("1000"), "regular"),
        ],
    )
    def test_update_classification(self, total, expected):
        c = _customer_stub(total_purchases=total)
        c.update_classification()
        assert c.customer_classification == expected

    def test_to_dict(self):
        c = _customer_stub(balance=Decimal("-50"), total_purchases=Decimal("1000"))
        data = c.to_dict()
        assert data["balance"] == -50.0
        assert data["balance_aed"] == -50.0
