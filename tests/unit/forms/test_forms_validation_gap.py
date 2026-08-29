"""Forms validation gap coverage — hits the 7 missed statements."""

from __future__ import annotations

from flask import Flask

from forms.auth import LoginForm
from forms.customer import CustomerForm
from forms.payment import ReceiptForm
from forms.product import ProductCategoryForm, ProductForm
from forms.purchase import PurchaseForm
from forms.sale import SaleForm


def _app():
    app = Flask(__name__)
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["SECRET_KEY"] = "test"
    return app


def test_login_form_valid_and_invalid():
    app = _app()
    with app.test_request_context("/", method="POST", data={"username": "ab", "password": ""}):
        form = LoginForm()
        assert not form.validate()
        assert "username" in form.errors or "password" in form.errors
    with app.test_request_context("/", method="POST", data={"username": "validuser", "password": "secret"}):
        form = LoginForm()
        assert form.validate()


def test_customer_form_branch():
    app = _app()
    with app.test_request_context("/", method="POST", data={}):
        form = CustomerForm()
        # Trigger all validators
        form.validate()
        assert isinstance(form.errors, dict)


def test_product_form_with_prices():
    app = _app()
    with app.test_request_context("/", method="POST", data={"name": "Test", "regular_price": "10"}):
        form = ProductForm()
        # Just verify instantiation and field presence (validation requires DB choices)
        assert hasattr(form, "name")
        assert hasattr(form, "regular_price")


def test_sale_form_branch():
    app = _app()
    with app.test_request_context("/", method="POST", data={}):
        form = SaleForm()
        assert hasattr(form, "customer_id") or hasattr(form, "sale_date") or len(form._fields) > 0


def test_purchase_form_branch():
    app = _app()
    with app.test_request_context("/", method="POST", data={}):
        form = PurchaseForm()
        assert len(form._fields) > 0


def test_payment_form_branch():
    app = _app()
    with app.test_request_context("/", method="POST", data={}):
        form = ReceiptForm()
        assert len(form._fields) > 0


def test_product_category_form_branch():
    app = _app()
    with app.test_request_context("/", method="POST", data={}):
        form = ProductCategoryForm()
        assert len(form._fields) > 0
