"""Unit tests for forms/customer.py — CustomerForm validation behavior.

TestConfig sets WTF_CSRF_ENABLED=False, so forms validate without a token
inside a plain app context. Validation messages are Arabic via flask_babel.
"""

import pytest
from werkzeug.datastructures import MultiDict

from forms.customer import CustomerForm

REQUIRED_MSG = "هذا الحقل مطلوب."
INVALID_CHOICE_MSG = "اختيار غير صحيح."
INVALID_EMAIL_MSG = "البريد الالكتروني غير صالح."


@pytest.fixture
def form_ctx(app):
    with app.app_context():
        yield


def _customer_form(data):
    return CustomerForm(formdata=MultiDict(data))


@pytest.mark.usefixtures("form_ctx")
class TestCustomerFormValid:
    def test_minimal_valid_submission(self):
        form = _customer_form({"name": "Ahmed", "customer_type": "regular"})
        assert form.validate() is True
        assert form.errors == {}

    @pytest.mark.parametrize("ctype", ["regular", "merchant", "partner"])
    def test_every_customer_type_choice_accepted(self, ctype):
        form = _customer_form({"name": "Ahmed", "customer_type": ctype})
        assert form.validate() is True
        assert form.customer_type.data == ctype

    @pytest.mark.parametrize("currency", ["AED", "USD", "EUR", "ILS"])
    def test_every_currency_choice_accepted(self, currency):
        form = _customer_form(
            {
                "name": "Ahmed",
                "customer_type": "regular",
                "preferred_currency": currency,
            }
        )
        assert form.validate() is True
        assert form.preferred_currency.data == currency

    def test_optional_fields_may_be_left_empty(self):
        form = _customer_form(
            {
                "name": "Ahmed",
                "customer_type": "regular",
                "name_ar": "",
                "phone": "",
                "email": "",
                "address": "",
                "tax_number": "",
                "notes": "",
            }
        )
        assert form.validate() is True

    def test_valid_email_accepted(self):
        form = _customer_form(
            {
                "name": "Ahmed",
                "customer_type": "regular",
                "email": "ahmed@example.com",
            }
        )
        assert form.validate() is True

    def test_is_active_checkbox_semantics(self):
        # BooleanField behaves like an HTML checkbox: absent key means False
        # when formdata is present; a truthy posted value means True.
        off = _customer_form({"name": "Ahmed", "customer_type": "regular"})
        assert off.validate() is True
        assert off.is_active.data is False

        on = _customer_form(
            {"name": "Ahmed", "customer_type": "regular", "is_active": "y"}
        )
        assert on.validate() is True
        assert on.is_active.data is True


@pytest.mark.usefixtures("form_ctx")
class TestCustomerFormInvalid:
    def test_empty_name_required(self):
        form = _customer_form({"name": "", "customer_type": "regular"})
        assert form.validate() is False
        assert form.errors["name"] == [REQUIRED_MSG]

    def test_missing_name_required(self):
        form = _customer_form({"customer_type": "regular"})
        assert form.validate() is False
        assert form.errors["name"] == [REQUIRED_MSG]

    def test_unknown_customer_type_rejected(self):
        form = _customer_form({"name": "Ahmed", "customer_type": "vip"})
        assert form.validate() is False
        assert form.errors["customer_type"] == [INVALID_CHOICE_MSG]

    def test_missing_customer_type_required(self):
        form = _customer_form({"name": "Ahmed"})
        assert form.validate() is False
        assert form.errors["customer_type"] == [REQUIRED_MSG]

    def test_unknown_currency_rejected(self):
        form = _customer_form(
            {
                "name": "Ahmed",
                "customer_type": "regular",
                "preferred_currency": "GBP",
            }
        )
        assert form.validate() is False
        assert form.errors["preferred_currency"] == [INVALID_CHOICE_MSG]

    def test_malformed_email_rejected(self):
        form = _customer_form(
            {
                "name": "Ahmed",
                "customer_type": "regular",
                "email": "not-an-email",
            }
        )
        assert form.validate() is False
        assert form.errors["email"] == [INVALID_EMAIL_MSG]
