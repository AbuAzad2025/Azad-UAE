"""Comprehensive tests for all form modules."""
import pytest


class TestLoginForm:
    def test_login_form_valid(self, app):
        from forms.auth import LoginForm
        with app.test_request_context():
            form = LoginForm(username="admin", password="secret")
            assert form.validate() is True

    def test_login_form_invalid(self, app):
        from forms.auth import LoginForm
        with app.test_request_context():
            form = LoginForm(username="", password="")
            assert form.validate() is False

    def test_login_form_fields(self, app):
        from forms.auth import LoginForm
        with app.test_request_context():
            form = LoginForm()
            assert "username" in form.data
            assert "password" in form.data
            assert "remember" in form.data


class TestCustomerForm:
    def test_customer_form_valid(self, app):
        from forms.customer import CustomerForm
        with app.test_request_context():
            form = CustomerForm(name="Test Customer", customer_type="regular")
            assert form.validate() is True

    def test_customer_form_invalid(self, app):
        from forms.customer import CustomerForm
        with app.test_request_context():
            form = CustomerForm(name="", customer_type="")
            assert form.validate() is False

    def test_customer_form_all_fields(self, app):
        from forms.customer import CustomerForm
        with app.test_request_context():
            form = CustomerForm(
                name="Test", name_ar="تجربة",
                customer_type="merchant", phone="0500000000",
                email="test@test.com", address="Address",
                tax_number="12345", preferred_currency="USD",
                is_active=True, notes="Test notes"
            )
            assert form.validate() is True


class TestSaleForm:
    def _make_sale_form(self, **kwargs):
        from forms.sale import SaleForm
        form = SaleForm(**kwargs)
        form.customer_id.choices = [(1, "Test Customer")]
        return form

    def test_sale_form_valid(self, app):
        with app.test_request_context():
            form = self._make_sale_form(customer_id=1, currency="AED")
            assert form.validate() is True

    def test_sale_form_invalid(self, app):
        with app.test_request_context():
            form = self._make_sale_form()
            assert form.validate() is False

    def test_sale_form_choices(self, app):
        from forms.sale import SaleForm
        with app.test_request_context():
            form = SaleForm()
            choices = dict(form.currency.choices)
            assert "AED" in choices
            assert "USD" in choices


class TestPurchaseForm:
    def test_purchase_form_valid(self, app):
        from forms.purchase import PurchaseForm
        with app.test_request_context():
            form = PurchaseForm(supplier_name="Test Supplier", currency="AED")
            assert form.validate() is True

    def test_purchase_form_invalid(self, app):
        from forms.purchase import PurchaseForm
        with app.test_request_context():
            form = PurchaseForm(supplier_name="")
            assert form.validate() is False


class TestProductForm:
    def _make_product_form(self, **kwargs):
        from forms.product import ProductForm
        form = ProductForm(**kwargs)
        form.category_id.choices = [(0, "None"), (1, "Category 1")]
        return form

    def test_product_form_valid(self, app):
        with app.test_request_context():
            form = self._make_product_form(name="Test Product", regular_price=100)
            assert form.validate() is True

    def test_product_form_invalid(self, app):
        with app.test_request_context():
            form = self._make_product_form(name="", regular_price=-1)
            assert form.validate() is False

    def test_product_form_all_fields(self, app):
        with app.test_request_context():
            form = self._make_product_form(
                name="Product", name_ar="منتج",
                barcode="12345", regular_price=100,
                cost_price=50, current_stock=10,
            )
            assert form.validate() is True


class TestReceiptForm:
    def _make_receipt_form(self, **kwargs):
        from forms.payment import ReceiptForm
        form = ReceiptForm(**kwargs)
        form.customer_id.choices = [(1, "Test Customer")]
        return form

    def test_receipt_form_valid(self, app):
        with app.test_request_context():
            form = self._make_receipt_form(
                customer_id=1, amount=100,
                currency="AED", payment_method="cash"
            )
            assert form.validate() is True

    def test_receipt_form_invalid(self, app):
        with app.test_request_context():
            form = self._make_receipt_form(amount=-1)
            assert form.validate() is False
