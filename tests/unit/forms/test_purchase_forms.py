"""Unit tests for forms/purchase.py — PurchaseForm validation behavior.

TestConfig sets WTF_CSRF_ENABLED=False, so forms validate without a token
inside a plain app context. Validation messages are Arabic via flask_babel.
"""

from decimal import Decimal

import pytest
from werkzeug.datastructures import MultiDict

from forms.purchase import PurchaseForm

REQUIRED_MSG = "هذا الحقل مطلوب."
INVALID_CHOICE_MSG = "اختيار غير صحيح."
INVALID_EMAIL_MSG = "البريد الالكتروني غير صالح."
RANGE_TAX_MSG = "يجب على الرقم ان يكون ما بين 0 و 100."
MIN_ZERO_MSG = "لا يجب على الرقم ان يقل عن 0."


@pytest.fixture
def form_ctx(app):
    with app.app_context():
        yield


def _purchase_form(data):
    return PurchaseForm(formdata=MultiDict(data))


@pytest.mark.usefixtures("form_ctx")
class TestPurchaseFormValid:
    def test_minimal_valid_submission(self):
        form = _purchase_form({"supplier_name": "Supplier Co", "currency": "AED"})
        assert form.validate() is True
        assert form.errors == {}

    def test_numeric_defaults_are_zero_decimal(self):
        form = _purchase_form({"supplier_name": "Supplier Co", "currency": "AED"})
        assert form.validate() is True
        assert form.discount_amount.data == Decimal("0")
        assert form.tax_rate.data == Decimal("0")

    @pytest.mark.parametrize("currency", ["AED", "USD", "EUR"])
    def test_every_currency_choice_accepted(self, currency):
        form = _purchase_form({"supplier_name": "S", "currency": currency})
        assert form.validate() is True
        assert form.currency.data == currency

    def test_tax_rate_boundaries_accepted(self):
        for rate in ("0", "100"):
            form = _purchase_form(
                {"supplier_name": "S", "currency": "AED", "tax_rate": rate}
            )
            assert form.validate() is True
            assert form.tax_rate.data == Decimal(rate)

    def test_optional_fields_may_be_left_empty(self):
        form = _purchase_form(
            {
                "supplier_name": "S",
                "currency": "AED",
                "supplier_phone": "",
                "supplier_email": "",
                "exchange_rate": "",
                "notes": "",
            }
        )
        assert form.validate() is True

    def test_valid_email_and_amounts_accepted(self):
        form = _purchase_form(
            {
                "supplier_name": "S",
                "currency": "USD",
                "supplier_email": "sup@example.com",
                "exchange_rate": "3.67",
                "discount_amount": "12.5",
                "tax_rate": "5",
            }
        )
        assert form.validate() is True


@pytest.mark.usefixtures("form_ctx")
class TestPurchaseFormInvalid:
    def test_empty_supplier_name_required(self):
        form = _purchase_form({"supplier_name": "", "currency": "AED"})
        assert form.validate() is False
        assert form.errors["supplier_name"] == [REQUIRED_MSG]

    def test_missing_supplier_name_required(self):
        form = _purchase_form({"currency": "AED"})
        assert form.validate() is False
        assert form.errors["supplier_name"] == [REQUIRED_MSG]

    def test_unknown_currency_rejected(self):
        form = _purchase_form({"supplier_name": "S", "currency": "GBP"})
        assert form.validate() is False
        assert form.errors["currency"] == [INVALID_CHOICE_MSG]

    def test_malformed_email_rejected(self):
        form = _purchase_form(
            {"supplier_name": "S", "currency": "AED", "supplier_email": "bad"}
        )
        assert form.validate() is False
        assert form.errors["supplier_email"] == [INVALID_EMAIL_MSG]

    def test_tax_rate_above_100_rejected(self):
        form = _purchase_form(
            {"supplier_name": "S", "currency": "AED", "tax_rate": "101"}
        )
        assert form.validate() is False
        assert form.errors["tax_rate"] == [RANGE_TAX_MSG]

    def test_negative_tax_rate_rejected(self):
        form = _purchase_form(
            {"supplier_name": "S", "currency": "AED", "tax_rate": "-1"}
        )
        assert form.validate() is False
        assert form.errors["tax_rate"] == [RANGE_TAX_MSG]

    def test_negative_discount_rejected(self):
        form = _purchase_form(
            {"supplier_name": "S", "currency": "AED", "discount_amount": "-0.5"}
        )
        assert form.validate() is False
        assert form.errors["discount_amount"] == [MIN_ZERO_MSG]

    def test_negative_exchange_rate_rejected(self):
        form = _purchase_form(
            {"supplier_name": "S", "currency": "AED", "exchange_rate": "-2"}
        )
        assert form.validate() is False
        assert form.errors["exchange_rate"] == [MIN_ZERO_MSG]
