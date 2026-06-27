"""Localization engine base — coerce_decimal and default strategy hooks."""
from __future__ import annotations

from decimal import Decimal

import pytest

from utils.localization.engine import LocalizationStrategy, coerce_decimal


class TestCoerceDecimal:
    def test_none_returns_default(self):
        assert coerce_decimal(None, default=Decimal('0')) == Decimal('0')

    def test_valid_string(self):
        assert coerce_decimal('12.5') == Decimal('12.5')

    @pytest.mark.parametrize('bad', ['not-a-number', object(), {}])
    def test_invalid_returns_default(self, bad):
        assert coerce_decimal(bad, default=Decimal('1')) == Decimal('1')


class _StubStrategy(LocalizationStrategy):
    country_code = 'TST'

    def calculate_tax(self, amount, tax_rate=None):
        return {'tax_amount': Decimal('0'), 'net_amount': amount, 'total_amount': amount, 'rate_applied': Decimal('0')}

    def format_tax_return(self, output_vat, input_vat, period_start, period_end):
        return {}

    def generate_einvoice(self, sale):
        return {}


class TestLocalizationStrategyBase:
    def test_validate_tax_number_min_length(self):
        s = _StubStrategy()
        assert s.validate_tax_number('12345') is True
        assert s.validate_tax_number('1234') is False
        assert s.validate_tax_number('') is False

    def test_get_wps_format_not_implemented(self):
        s = _StubStrategy()
        with pytest.raises(NotImplementedError, match='WPS not supported'):
            s.get_wps_format([])
