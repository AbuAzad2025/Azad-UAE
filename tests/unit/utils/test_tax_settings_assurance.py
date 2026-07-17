"""Tax settings — tenant-scoped VAT configuration."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class _Col:
    def __eq__(self, other):
        return self


class TestResolveTenant:
    def test_resolve_by_id(self, mocker):
        tenant = MagicMock(id=5, enable_tax=True)
        mocker.patch("extensions.db.session.get", return_value=tenant)
        from utils.tax_settings import _resolve_tenant

        assert _resolve_tenant(5) is tenant

    def test_resolve_current_fallback(self, mocker):
        tenant = MagicMock()
        mocker.patch("models.tenant.Tenant.get_current", return_value=tenant)
        from utils.tax_settings import _resolve_tenant

        assert _resolve_tenant() is tenant

    def test_resolve_current_exception_returns_none(self, mocker):
        mocker.patch(
            "models.tenant.Tenant.get_current", side_effect=RuntimeError("no ctx")
        )
        from utils.tax_settings import _resolve_tenant

        assert _resolve_tenant() is None


class TestTaxFlags:
    def test_is_tax_enabled_no_tenant(self, mocker):
        mocker.patch("utils.tax_settings._resolve_tenant", return_value=None)
        from utils.tax_settings import is_tax_enabled

        assert is_tax_enabled() is False

    def test_is_tax_enabled_true(self, mocker):
        mocker.patch(
            "utils.tax_settings._resolve_tenant",
            return_value=MagicMock(enable_tax=True),
        )
        from utils.tax_settings import is_tax_enabled

        assert is_tax_enabled(1) is True

    def test_vat_country_defaults_ae(self, mocker):
        mocker.patch("utils.tax_settings._resolve_tenant", return_value=None)
        from utils.tax_settings import vat_country

        assert vat_country() == "AE"

    def test_vat_country_from_tenant(self, mocker):
        mocker.patch(
            "utils.tax_settings._resolve_tenant",
            return_value=MagicMock(vat_country="ps"),
        )
        from utils.tax_settings import vat_country

        assert vat_country(2) == "PS"


class TestDefaultTaxRate:
    def test_zero_when_disabled(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=False)
        from utils.tax_settings import default_tax_rate

        assert default_tax_rate(1) == Decimal("0")

    def test_stored_rate(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        mocker.patch(
            "utils.tax_settings._resolve_tenant",
            return_value=MagicMock(default_tax_rate=Decimal("5")),
        )
        from utils.tax_settings import default_tax_rate

        assert default_tax_rate(1) == Decimal("5")

    def test_zero_when_no_stored_rate(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        mocker.patch(
            "utils.tax_settings._resolve_tenant",
            return_value=MagicMock(default_tax_rate=None),
        )
        from utils.tax_settings import default_tax_rate

        assert default_tax_rate(1) == Decimal("0")


class TestPricesIncludeVat:
    def test_branch_override(self, mocker):
        branch = MagicMock(prices_include_vat=True)
        mocker.patch("extensions.db.session.get", return_value=branch)
        from utils.tax_settings import get_prices_include_vat

        assert get_prices_include_vat(branch_id=3) is True

    def test_tenant_fallback(self, mocker):
        mocker.patch("extensions.db.session.get", return_value=None)
        mocker.patch(
            "utils.tax_settings._resolve_tenant",
            return_value=MagicMock(prices_include_vat=True),
        )
        from utils.tax_settings import get_prices_include_vat

        assert get_prices_include_vat(tenant_id=1) is True

    def test_default_false(self, mocker):
        mocker.patch("utils.tax_settings._resolve_tenant", return_value=None)
        from utils.tax_settings import get_prices_include_vat

        assert get_prices_include_vat() is False


class TestNormalizeTaxRate:
    def test_zero_when_disabled(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=False)
        from utils.tax_settings import normalize_tax_rate

        assert normalize_tax_rate(15, tenant_id=1) == Decimal("0")

    def test_valid_rate(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        from utils.tax_settings import normalize_tax_rate

        assert normalize_tax_rate("5.5", tenant_id=1) == Decimal("5.5")

    @pytest.mark.parametrize("rate", [-1, 101])
    def test_out_of_range_raises(self, mocker, rate):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        from utils.tax_settings import normalize_tax_rate

        with pytest.raises(ValueError, match="0 و 100"):
            normalize_tax_rate(rate, tenant_id=1)


class TestSuggestedRate:
    def test_known_country(self):
        from utils.tax_settings import suggested_rate_for_country, VAT_RATES_BY_COUNTRY

        assert suggested_rate_for_country("AE") == VAT_RATES_BY_COUNTRY["AE"]

    def test_unknown_country_zero(self):
        from utils.tax_settings import suggested_rate_for_country

        assert suggested_rate_for_country("US") == Decimal("0")


class TestShouldPostVatGl:
    def test_delegates_to_is_tax_enabled(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        from utils.tax_settings import should_post_vat_gl

        assert should_post_vat_gl(1) is True


class TestDefaultTaxRateEdge:
    def test_stored_rate_negative_treated_as_zero(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        mocker.patch(
            "utils.tax_settings._resolve_tenant",
            return_value=MagicMock(default_tax_rate=Decimal("-1")),
        )
        from utils.tax_settings import default_tax_rate

        assert default_tax_rate(1) == Decimal("0")

    def test_missing_tenant_after_enabled(self, mocker):
        mocker.patch("utils.tax_settings.is_tax_enabled", return_value=True)
        mocker.patch("utils.tax_settings._resolve_tenant", return_value=None)
        from utils.tax_settings import default_tax_rate

        assert default_tax_rate(1) == Decimal("0")


class TestResolveMainBranch:
    def test_returns_main_branch_id(self, mocker):
        branch = MagicMock(id=9)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = branch
        mocker.patch("models.branch.Branch.query", mock_q)
        from utils.tax_settings import _resolve_main_branch

        assert _resolve_main_branch(1) == 9

    def test_returns_none_when_missing(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("models.branch.Branch.query", mock_q)
        from utils.tax_settings import _resolve_main_branch

        assert _resolve_main_branch(1) is None
