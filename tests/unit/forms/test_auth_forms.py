"""Unit tests for forms/auth.py — LoginForm validation behavior.

TestConfig sets WTF_CSRF_ENABLED=False, so forms validate without a token
inside a plain app context. Validation messages are Arabic via flask_babel.
"""

import pytest
from werkzeug.datastructures import MultiDict

from forms.auth import LoginForm

REQUIRED_MSG = "هذا الحقل مطلوب."
LENGTH_MSG = "يجب على طول الحقل ان يكون ما بين 3 و 50 حرف."


@pytest.fixture
def form_ctx(app):
    with app.app_context():
        yield


def _login_form(data):
    return LoginForm(formdata=MultiDict(data))


@pytest.mark.usefixtures("form_ctx")
class TestLoginFormValid:
    def test_valid_credentials_pass(self):
        form = _login_form({"username": "cashier1", "password": "secret"})
        assert form.validate() is True
        assert form.errors == {}

    def test_username_min_boundary_accepted(self):
        form = _login_form({"username": "abc", "password": "x"})
        assert form.validate() is True

    def test_username_max_boundary_accepted(self):
        form = _login_form({"username": "a" * 50, "password": "x"})
        assert form.validate() is True

    def test_remember_flag_coerced_true(self):
        form = _login_form({"username": "cashier1", "password": "x", "remember": "y"})
        assert form.validate() is True
        assert form.remember.data is True

    def test_remember_absent_defaults_false(self):
        form = _login_form({"username": "cashier1", "password": "x"})
        assert form.validate() is True
        assert form.remember.data is False


@pytest.mark.usefixtures("form_ctx")
class TestLoginFormInvalid:
    def test_empty_username_required(self):
        form = _login_form({"username": "", "password": "x"})
        assert form.validate() is False
        assert form.errors["username"] == [REQUIRED_MSG]

    def test_missing_username_required(self):
        form = _login_form({"password": "x"})
        assert form.validate() is False
        assert form.errors["username"] == [REQUIRED_MSG]

    def test_empty_password_required(self):
        form = _login_form({"username": "cashier1", "password": ""})
        assert form.validate() is False
        assert form.errors["password"] == [REQUIRED_MSG]

    def test_both_empty_reports_both_fields(self):
        form = _login_form({"username": "", "password": ""})
        assert form.validate() is False
        assert form.errors["username"] == [REQUIRED_MSG]
        assert form.errors["password"] == [REQUIRED_MSG]

    def test_username_too_short(self):
        form = _login_form({"username": "ab", "password": "x"})
        assert form.validate() is False
        assert form.errors["username"] == [LENGTH_MSG]

    def test_username_too_long(self):
        form = _login_form({"username": "a" * 51, "password": "x"})
        assert form.validate() is False
        assert form.errors["username"] == [LENGTH_MSG]
