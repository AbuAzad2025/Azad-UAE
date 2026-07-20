"""Currency utilities — tenant-aware defaults and symbol lookup."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSystemDefaultCurrency:
    def test_get_system_default_currency(self, mocker):
        mocker.patch("utils.currency_utils.Config", MagicMock(DEFAULT_CURRENCY="AED"))
        from utils.currency_utils import get_system_default_currency

        assert get_system_default_currency() == "AED"

    def test_get_system_default_currency_fallback(self, mocker):
        mocker.patch("utils.currency_utils.Config", MagicMock(DEFAULT_CURRENCY=None))
        from utils.currency_utils import get_system_default_currency

        assert get_system_default_currency() == "ILS"


class TestContextAwareDefault:
    def test_context_aware_from_tenant(self, mocker):
        user = MagicMock(is_authenticated=True, tenant_id=1)
        tenant = MagicMock(default_currency=" usd ")
        mocker.patch("flask.has_request_context", return_value=True)
        mocker.patch("flask_login.current_user", user)
        mocker.patch("utils.currency_utils.db.session.get", return_value=tenant)
        from utils.currency_utils import context_aware_default_currency

        assert context_aware_default_currency() == "USD"

    def test_context_aware_no_request(self, mocker):
        mocker.patch("flask.has_request_context", return_value=False)
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="AED")
        from utils.currency_utils import context_aware_default_currency

        assert context_aware_default_currency() == "AED"

    def test_context_aware_exception_fallback(self, mocker):
        mocker.patch("flask.has_request_context", side_effect=RuntimeError("ctx"))
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="ILS")
        from utils.currency_utils import context_aware_default_currency

        assert context_aware_default_currency() == "ILS"


class TestResolveDefaultCurrency:
    def test_from_tenant(self):
        tenant = MagicMock(default_currency=" eur ")
        from utils.currency_utils import resolve_default_currency

        assert resolve_default_currency(tenant) == "EUR"

    def test_from_system_settings(self, mocker):
        settings = MagicMock(default_currency="gbp")
        mocker.patch("models.system_settings.SystemSettings.get_current", return_value=settings)
        from utils.currency_utils import resolve_default_currency

        assert resolve_default_currency(None) == "GBP"

    def test_fallback_system_default(self, mocker):
        mocker.patch(
            "models.system_settings.SystemSettings.get_current",
            side_effect=RuntimeError("x"),
        )
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="ILS")
        from utils.currency_utils import resolve_default_currency

        assert resolve_default_currency(None) == "ILS"


class TestTenantBaseCurrency:
    def test_get_tenant_base_currency_from_base(self, mocker):
        tenant = MagicMock(base_currency=" aed ", default_currency="USD")
        mocker.patch("utils.currency_utils.db.session.get", return_value=tenant)
        from utils.currency_utils import get_tenant_base_currency

        assert get_tenant_base_currency(1) == "AED"

    def test_get_tenant_base_currency_from_default(self, mocker):
        tenant = MagicMock(base_currency=None, default_currency=" sar ")
        mocker.patch("utils.currency_utils.db.session.get", return_value=tenant)
        from utils.currency_utils import get_tenant_base_currency

        assert get_tenant_base_currency(2) == "SAR"

    def test_get_tenant_base_currency_fallback(self, mocker):
        mocker.patch("utils.currency_utils.db.session.get", return_value=None)
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="ILS")
        from utils.currency_utils import get_tenant_base_currency

        assert get_tenant_base_currency(99) == "ILS"

    def test_resolve_tenant_base_currency_instance(self):
        tenant = MagicMock(base_currency="QAR")
        from utils.currency_utils import resolve_tenant_base_currency

        assert resolve_tenant_base_currency(tenant=tenant) == "QAR"

    def test_resolve_tenant_base_currency_by_id(self, mocker):
        mocker.patch("utils.currency_utils.get_tenant_base_currency", return_value="OMR")
        from utils.currency_utils import resolve_tenant_base_currency

        assert resolve_tenant_base_currency(tenant_id=3) == "OMR"

    def test_get_tenant_base_currency_db_error(self, mocker):
        mocker.patch("utils.currency_utils.db.session.get", side_effect=RuntimeError("db"))
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="ILS")
        from utils.currency_utils import get_tenant_base_currency

        assert get_tenant_base_currency(1) == "ILS"

    def test_resolve_tenant_base_currency_default_only(self):
        tenant = MagicMock(base_currency=None, default_currency=" kwd ")
        from utils.currency_utils import resolve_tenant_base_currency

        assert resolve_tenant_base_currency(tenant=tenant) == "KWD"

    def test_resolve_tenant_base_currency_system_fallback(self, mocker):
        mocker.patch("utils.currency_utils.get_system_default_currency", return_value="ILS")
        from utils.currency_utils import resolve_tenant_base_currency

        assert resolve_tenant_base_currency() == "ILS"

    def test_get_currency_name_ar_unknown(self, mocker):
        mocker.patch("utils.constants.CURRENCIES", [])
        from utils.currency_utils import get_currency_name_ar

        assert get_currency_name_ar("XYZ") == "XYZ"


class TestCurrencyLabels:
    def test_get_currency_symbol_known(self, mocker):
        mocker.patch("utils.constants.CURRENCIES", [("USD", {"symbol": "$"})])
        from utils.currency_utils import get_currency_symbol

        assert get_currency_symbol("USD") == "$"

    def test_get_currency_symbol_unknown(self, mocker):
        mocker.patch("utils.constants.CURRENCIES", [])
        from utils.currency_utils import get_currency_symbol

        assert get_currency_symbol("XYZ") == "XYZ"

    def test_get_currency_name_ar(self, mocker):
        mocker.patch("utils.constants.CURRENCIES", [("AED", {"ar": "درهم"})])
        from utils.currency_utils import get_currency_name_ar

        assert get_currency_name_ar("AED") == "درهم"
