"""Unit tests for forms/payment.py — ReceiptForm validation behavior.

The form declares ``customer_id`` as a lazy-choices SelectField (coerce=int);
like any consumer of this pattern, tests populate ``choices`` before
validating. Validation messages are Arabic via flask_babel.
"""

import pytest
from werkzeug.datastructures import MultiDict

from forms.payment import ReceiptForm

REQUIRED_MSG = "هذا الحقل مطلوب."
INVALID_CHOICE_MSG = "اختيار غير صحيح."
MIN_AMOUNT_MSG = "لا يجب على الرقم ان يقل عن 0.01."
MIN_ZERO_MSG = "لا يجب على الرقم ان يقل عن 0."
INVALID_DATE_MSG = "قيمة التاريخ غير صالحة."

VALID_PAYLOAD = {
    "customer_id": "1",
    "amount": "10.50",
    "currency": "AED",
    "payment_method": "cash",
}


@pytest.fixture
def form_ctx(app):
    with app.app_context():
        yield


def _receipt_form(data):
    form = ReceiptForm(formdata=MultiDict(data))
    # Consumer-side wiring: SelectField(coerce=int) ships without choices.
    form.customer_id.choices = [(1, "Customer A"), (2, "Customer B")]
    return form


@pytest.mark.usefixtures("form_ctx")
class TestReceiptFormValid:
    def test_valid_submission_passes_and_coerces(self):
        form = _receipt_form(VALID_PAYLOAD)
        assert form.validate() is True
        assert form.errors == {}
        assert form.customer_id.data == 1
        assert str(form.amount.data) == "10.50"

    def test_defaults_apply_when_selects_omitted(self):
        form = _receipt_form({"customer_id": "2", "amount": "5"})
        assert form.validate() is True
        assert form.currency.data == "AED"
        assert form.payment_method.data == "cash"

    @pytest.mark.parametrize("method", ["cash", "card", "bank_transfer", "cheque", "e_wallet"])
    def test_every_payment_method_choice_accepted(self, method):
        form = _receipt_form({**VALID_PAYLOAD, "payment_method": method})
        assert form.validate() is True
        assert form.payment_method.data == method

    @pytest.mark.parametrize("currency", ["AED", "USD", "EUR"])
    def test_every_currency_choice_accepted(self, currency):
        form = _receipt_form({**VALID_PAYLOAD, "currency": currency})
        assert form.validate() is True
        assert form.currency.data == currency

    def test_amount_above_minimum_accepted(self):
        form = _receipt_form({**VALID_PAYLOAD, "amount": "0.02"})
        assert form.validate() is True

    def test_optional_fields_may_be_left_empty(self):
        form = _receipt_form(
            {
                **VALID_PAYLOAD,
                "exchange_rate": "",
                "reference_number": "",
                "cheque_number": "",
                "cheque_date": "",
                "bank_name": "",
                "notes": "",
            }
        )
        assert form.validate() is True

    def test_zero_exchange_rate_accepted(self):
        form = _receipt_form({**VALID_PAYLOAD, "exchange_rate": "0"})
        assert form.validate() is True

    def test_valid_cheque_date_parsed(self):
        import datetime

        form = _receipt_form({**VALID_PAYLOAD, "cheque_date": "2026-01-15"})
        assert form.validate() is True
        assert form.cheque_date.data == datetime.date(2026, 1, 15)


@pytest.mark.usefixtures("form_ctx")
class TestReceiptFormInvalid:
    def test_amount_zero_treated_as_missing(self):
        # DataRequired rejects 0 before NumberRange runs (falsy value).
        form = _receipt_form({**VALID_PAYLOAD, "amount": "0"})
        assert form.validate() is False
        assert form.errors["amount"] == [REQUIRED_MSG]

    def test_amount_missing_required(self):
        payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "amount"}
        form = _receipt_form(payload)
        assert form.validate() is False
        assert form.errors["amount"] == [REQUIRED_MSG]

    def test_negative_amount_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "amount": "-5"})
        assert form.validate() is False
        assert form.errors["amount"] == [MIN_AMOUNT_MSG]

    def test_amount_below_minimum_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "amount": "0.005"})
        assert form.validate() is False
        assert form.errors["amount"] == [MIN_AMOUNT_MSG]

    def test_negative_exchange_rate_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "exchange_rate": "-1"})
        assert form.validate() is False
        assert form.errors["exchange_rate"] == [MIN_ZERO_MSG]

    def test_customer_missing_required(self):
        form = _receipt_form({**VALID_PAYLOAD, "customer_id": ""})
        assert form.validate() is False
        assert form.errors["customer_id"] == [REQUIRED_MSG]

    def test_customer_outside_choices_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "customer_id": "9"})
        assert form.validate() is False
        assert form.errors["customer_id"] == [INVALID_CHOICE_MSG]

    def test_unknown_currency_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "currency": "GBP"})
        assert form.validate() is False
        assert form.errors["currency"] == [INVALID_CHOICE_MSG]

    def test_unknown_payment_method_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "payment_method": "bitcoin"})
        assert form.validate() is False
        assert form.errors["payment_method"] == [INVALID_CHOICE_MSG]

    def test_malformed_cheque_date_rejected(self):
        form = _receipt_form({**VALID_PAYLOAD, "cheque_date": "2026-13-45"})
        assert form.validate() is False
        assert form.errors["cheque_date"] == [INVALID_DATE_MSG]


@pytest.mark.usefixtures("form_ctx")
class TestReceiptFormLazyChoicesContract:
    def test_validate_without_choices_raises_type_error(self):
        # The class ships customer_id with choices=None; WTForms requires a
        # consumer to populate them before validation.
        form = ReceiptForm(formdata=MultiDict(VALID_PAYLOAD))
        with pytest.raises(TypeError, match="Choices cannot be None"):
            form.validate()
