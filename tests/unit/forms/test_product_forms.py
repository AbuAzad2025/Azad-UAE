"""Unit tests for forms/product.py — ProductForm and ProductCategoryForm validation."""

import pytest
from werkzeug.datastructures import MultiDict

from forms.product import ProductCategoryForm, ProductForm

REQUIRED_MSG = "هذا الحقل مطلوب."
INVALID_CHOICE_MSG = "اختيار غير صحيح."
MIN_ZERO_MSG = "لا يجب على الرقم ان يقل عن 0."

VALID_PRODUCT = {
    "name": "Widget",
    "regular_price": "10.00",
}


@pytest.fixture
def form_ctx(app):
    with app.app_context():
        yield


def _product_form(data):
    form = ProductForm(formdata=MultiDict(data))
    form.category_id.choices = [(1, "Cat A"), (2, "Cat B")]
    return form


@pytest.mark.usefixtures("form_ctx")
class TestProductFormValid:
    def test_valid_minimal_passes(self):
        form = _product_form(VALID_PRODUCT)
        assert form.validate() is True
        assert form.errors == {}
        assert form.name.data == "Widget"
        assert str(form.regular_price.data) == "10.00"

    def test_all_units_accepted(self):
        for unit in ["", "piece", "kg", "liter", "meter", "box", "set"]:
            form = _product_form({**VALID_PRODUCT, "unit": unit})
            assert form.validate() is True, unit

    def test_all_warranty_units_accepted(self):
        for w in ["days", "months", "years"]:
            form = _product_form({**VALID_PRODUCT, "warranty_unit": w})
            assert form.validate() is True, w

    def test_is_returnable_choices(self):
        for v in ["1", "0"]:
            form = _product_form({**VALID_PRODUCT, "is_returnable": v})
            assert form.validate() is True
            assert form.is_returnable.data in (0, 1)

    def test_optional_fields_empty(self):
        form = _product_form(
            {
                **VALID_PRODUCT,
                "name_ar": "",
                "commercial_name": "",
                "part_number": "",
                "barcode": "",
                "category_id": "",
                "country_of_origin": "",
                "merchant_price": "",
                "partner_price": "",
                "cost_price": "",
                "current_stock": "",
                "min_stock_alert": "",
                "warranty_period": "",
                "return_period_days": "",
                "description": "",
                "notes": "",
            }
        )
        assert form.validate() is True

    def test_zero_cost_price_accepted(self):
        form = _product_form({**VALID_PRODUCT, "cost_price": "0"})
        assert form.validate() is True

    def test_defaults(self):
        form = _product_form(VALID_PRODUCT)
        assert form.validate() is True
        assert form.unit.data == "piece"
        assert form.warranty_unit.data == "months"
        assert form.is_returnable.data == 1


@pytest.mark.usefixtures("form_ctx")
class TestProductFormInvalid:
    def test_name_required(self):
        form = _product_form({k: v for k, v in VALID_PRODUCT.items() if k != "name"})
        assert form.validate() is False
        assert form.errors["name"] == [REQUIRED_MSG]

    def test_name_empty(self):
        form = _product_form({**VALID_PRODUCT, "name": ""})
        assert form.validate() is False
        assert form.errors["name"] == [REQUIRED_MSG]

    def test_regular_price_required(self):
        form = _product_form({"name": "Widget"})
        assert form.validate() is False
        assert form.errors["regular_price"] == [REQUIRED_MSG]

    def test_regular_price_negative(self):
        form = _product_form({**VALID_PRODUCT, "regular_price": "-1"})
        assert form.validate() is False
        assert form.errors["regular_price"] == [MIN_ZERO_MSG]

    def test_merchant_price_negative(self):
        form = _product_form({**VALID_PRODUCT, "merchant_price": "-5"})
        assert form.validate() is False
        assert form.errors["merchant_price"] == [MIN_ZERO_MSG]

    def test_partner_price_negative(self):
        form = _product_form({**VALID_PRODUCT, "partner_price": "-5"})
        assert form.validate() is False
        assert form.errors["partner_price"] == [MIN_ZERO_MSG]

    def test_cost_price_negative(self):
        form = _product_form({**VALID_PRODUCT, "cost_price": "-0.01"})
        assert form.validate() is False
        assert form.errors["cost_price"] == [MIN_ZERO_MSG]

    def test_current_stock_negative(self):
        form = _product_form({**VALID_PRODUCT, "current_stock": "-1"})
        assert form.validate() is False
        assert form.errors["current_stock"] == [MIN_ZERO_MSG]

    def test_min_stock_alert_negative(self):
        form = _product_form({**VALID_PRODUCT, "min_stock_alert": "-1"})
        assert form.validate() is False
        assert form.errors["min_stock_alert"] == [MIN_ZERO_MSG]

    def test_warranty_period_negative(self):
        form = _product_form({**VALID_PRODUCT, "warranty_period": "-1"})
        assert form.validate() is False
        assert form.errors["warranty_period"] == [MIN_ZERO_MSG]

    def test_return_period_negative(self):
        form = _product_form({**VALID_PRODUCT, "return_period_days": "-1"})
        assert form.validate() is False
        assert form.errors["return_period_days"] == [MIN_ZERO_MSG]

    def test_invalid_unit(self):
        form = _product_form({**VALID_PRODUCT, "unit": "invalid"})
        assert form.validate() is False
        assert form.errors["unit"] == [INVALID_CHOICE_MSG]

    def test_invalid_warranty_unit(self):
        form = _product_form({**VALID_PRODUCT, "warranty_unit": "weeks"})
        assert form.validate() is False
        assert form.errors["warranty_unit"] == [INVALID_CHOICE_MSG]

    def test_invalid_is_returnable(self):
        form = _product_form({**VALID_PRODUCT, "is_returnable": "2"})
        assert form.validate() is False
        assert form.errors["is_returnable"] == [INVALID_CHOICE_MSG]

    def test_category_outside_choices(self):
        form = _product_form({**VALID_PRODUCT, "category_id": "9"})
        assert form.validate() is False
        assert form.errors["category_id"] == [INVALID_CHOICE_MSG]


@pytest.mark.usefixtures("form_ctx")
class TestProductFormLazyChoices:
    def test_validate_without_choices_raises(self):
        form = ProductForm(formdata=MultiDict(VALID_PRODUCT))
        with pytest.raises(TypeError, match="Choices cannot be None"):
            form.validate()


@pytest.mark.usefixtures("form_ctx")
class TestProductCategoryForm:
    def test_valid(self):
        form = ProductCategoryForm(formdata=MultiDict({"name": "Cat"}))
        assert form.validate() is True

    def test_name_required(self):
        form = ProductCategoryForm(formdata=MultiDict({"name": ""}))
        assert form.validate() is False
        assert form.errors["name"] == [REQUIRED_MSG]

    def test_optional_fields(self):
        form = ProductCategoryForm(formdata=MultiDict({"name": "Cat", "name_ar": "", "description": ""}))
        assert form.validate() is True
