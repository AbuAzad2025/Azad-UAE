"""Unit tests for forms/sale.py — SaleForm validation behavior.

The form declares ``customer_id`` as a lazy-choices SelectField (coerce=int);
like any consumer of this pattern, tests populate ``choices`` before
validating. Validation messages are Arabic via flask_babel.
"""

from decimal import Decimal

import pytest
from werkzeug.datastructures import MultiDict

from forms.sale import SaleForm

REQUIRED_MSG = "هذا الحقل مطلوب."
INVALID_CHOICE_MSG = "اختيار غير صحيح."
RANGE_TAX_MSG = "يجب على الرقم ان يكون ما بين 0 و 100."
MIN_ZERO_MSG = "لا يجب على الرقم ان يقل عن 0."

VALID_PAYLOAD = {"customer_id": "2", "currency": "USD"}


@pytest.fixture
def form_ctx(app):
    with app.app_context():
        yield


def _sale_form(data):
    form = SaleForm(formdata=MultiDict(data))
    # Consumer-side wiring: SelectField(coerce=int) ships without choices.
    form.customer_id.choices = [(1, "Customer A"), (2, "Customer B")]
    return form


@pytest.mark.usefixtures("form_ctx")
class TestSaleFormValid:
    def test_minimal_valid_submission(self):
        form = _sale_form(VALID_PAYLOAD)
        assert form.validate() is True
        assert form.errors == {}
        assert form.customer_id.data == 2

    def test_numeric_and_currency_defaults(self):
        form = _sale_form(VALID_PAYLOAD)
        assert form.validate() is True
        assert form.exchange_rate.data == Decimal("1.0")
        assert form.discount_amount.data == Decimal("0")
        assert form.shipping_cost.data == Decimal("0")
        assert form.tax_rate.data == Decimal("0")

    def test_payment_method_defaults_to_none(self):
        form = _sale_form(VALID_PAYLOAD)
        assert form.validate() is True
        assert form.payment_method.data is None

    def test_empty_payment_method_means_credit_sale(self):
        # The "" choice is the labelled "آجل (بدون دفع)" credit option.
        form = _sale_form({**VALID_PAYLOAD, "payment_method": ""})
        assert form.validate() is True
        assert form.payment_method.data == ""

    @pytest.mark.parametrize(
        "method", ["cash", "card", "bank_transfer", "cheque", "e_wallet"]
    )
    def test_every_payment_method_choice_accepted(self, method):
        form = _sale_form({**VALID_PAYLOAD, "payment_method": method})
        assert form.validate() is True
        assert form.payment_method.data == method

    @pytest.mark.parametrize("currency", ["AED", "USD", "EUR"])
    def test_every_currency_choice_accepted(self, currency):
        form = _sale_form({"customer_id": "2", "currency": currency})
        assert form.validate() is True
        assert form.currency.data == currency

    def test_zero_amounts_accepted(self):
        form = _sale_form(
            {
                **VALID_PAYLOAD,
                "exchange_rate": "0",
                "discount_amount": "0",
                "shipping_cost": "0",
                "tax_rate": "0",
            }
        )
        assert form.validate() is True

    def test_tax_rate_boundaries_accepted(self):
        for rate in ("0", "100"):
            form = _sale_form({**VALID_PAYLOAD, "tax_rate": rate})
            assert form.validate() is True
            assert form.tax_rate.data == Decimal(rate)


@pytest.mark.usefixtures("form_ctx")
class TestSaleFormInvalid:
    def test_customer_missing_required(self):
        form = _sale_form({"customer_id": "", "currency": "USD"})
        assert form.validate() is False
        assert form.errors["customer_id"] == [REQUIRED_MSG]

    def test_non_integer_customer_treated_as_missing(self):
        # coerce=int fails on "abc", leaving no data for DataRequired.
        form = _sale_form({"customer_id": "abc", "currency": "USD"})
        assert form.validate() is False
        assert form.errors["customer_id"] == [REQUIRED_MSG]

    def test_customer_outside_choices_rejected(self):
        form = _sale_form({"customer_id": "9", "currency": "USD"})
        assert form.validate() is False
        assert form.errors["customer_id"] == [INVALID_CHOICE_MSG]

    def test_unknown_currency_rejected(self):
        form = _sale_form({"customer_id": "2", "currency": "XXX"})
        assert form.validate() is False
        assert form.errors["currency"] == [INVALID_CHOICE_MSG]

    def test_unknown_payment_method_rejected(self):
        form = _sale_form({**VALID_PAYLOAD, "payment_method": "bitcoin"})
        assert form.validate() is False
        assert form.errors["payment_method"] == [INVALID_CHOICE_MSG]

    def test_negative_exchange_rate_rejected(self):
        form = _sale_form({**VALID_PAYLOAD, "exchange_rate": "-1"})
        assert form.validate() is False
        assert form.errors["exchange_rate"] == [MIN_ZERO_MSG]

    def test_negative_discount_rejected(self):
        form = _sale_form({**VALID_PAYLOAD, "discount_amount": "-0.5"})
        assert form.validate() is False
        assert form.errors["discount_amount"] == [MIN_ZERO_MSG]

    def test_negative_shipping_rejected(self):
        form = _sale_form({**VALID_PAYLOAD, "shipping_cost": "-3"})
        assert form.validate() is False
        assert form.errors["shipping_cost"] == [MIN_ZERO_MSG]

    def test_tax_rate_above_100_rejected(self):
        form = _sale_form({**VALID_PAYLOAD, "tax_rate": "101"})
        assert form.validate() is False
        assert form.errors["tax_rate"] == [RANGE_TAX_MSG]

    def test_negative_tax_rate_rejected(self):
        form = _sale_form({**VALID_PAYLOAD, "tax_rate": "-3"})
        assert form.validate() is False
        assert form.errors["tax_rate"] == [RANGE_TAX_MSG]


@pytest.mark.usefixtures("form_ctx")
class TestSaleFormLazyChoicesContract:
    def test_validate_without_choices_raises_type_error(self):
        # The class ships customer_id with choices=None; WTForms requires a
        # consumer to populate them before validation.
        form = SaleForm(formdata=MultiDict(VALID_PAYLOAD))
        with pytest.raises(TypeError, match="Choices cannot be None"):
            form.validate()
