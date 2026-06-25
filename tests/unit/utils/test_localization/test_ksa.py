from __future__ import annotations

import base64
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from utils.localization.ksa import KSAStrategy


@pytest.fixture
def strategy():
    return KSAStrategy()


class TestKSACalculateTax:
    def test_standard_vat(self, strategy):
        result = strategy.calculate_tax(Decimal('100'))
        assert result['tax_amount'] == Decimal('15.00')
        assert result['total_amount'] == Decimal('115.00')
        assert result['rate_applied'] == Decimal('15.00')

    def test_zero_rated(self, strategy):
        result = strategy.calculate_tax(Decimal('250'), tax_rate=Decimal('0'))
        assert result['tax_amount'] == Decimal('0')
        assert result['total_amount'] == Decimal('250')
        assert result['rate_applied'] == Decimal('0')

    def test_custom_rate(self, strategy):
        result = strategy.calculate_tax(Decimal('200'), tax_rate=Decimal('5'))
        assert result['tax_amount'] == Decimal('10.00')
        assert result['total_amount'] == Decimal('210.00')


class TestKSATaxReturn:
    def test_format_tax_return(self, strategy):
        result = strategy.format_tax_return(
            Decimal('1500'), Decimal('400'), '2025-01-01', '2025-01-31',
        )
        assert result['country'] == 'SA'
        assert result['net_payable'] == Decimal('1100')
        assert result['format'] == 'zatca_vat_v3'
        assert result['currency'] == 'SAR'


class TestKSAValidateTaxNumber:
    @pytest.mark.parametrize('value,expected', [
        ('300000000000003', True),
        ('3-0000-0000-000-003', True),
        ('200000000000003', False),
        ('30000000000000', False),
        ('', False),
        (None, False),
    ])
    def test_trn_validation(self, strategy, value, expected):
        assert strategy.validate_tax_number(value) is expected


class TestKSAEInvoice:
    def test_generate_einvoice_tax_inclusive(self, strategy):
        sale = MagicMock(spec=['id', 'total_aed', 'sale_date'])
        sale.id = 42
        sale.total_aed = Decimal('115')
        sale.sale_date = '2025-06-01'
        result = strategy.generate_einvoice(sale)
        assert result['format'] == 'zatca_simplified_xml'
        assert 'TaxExclusiveAmount' in result['xml_payload']
        assert '15.00' in result['xml_payload']
        assert result['qr_base64'] == base64.b64encode(b'ZATCA|15.00|115|42').decode()
        assert len(result['invoice_hash']) == 64

    def test_generate_einvoice_zero_rated_sale(self, strategy):
        sale = MagicMock(spec=['id', 'amount_aed', 'tax_rate'])
        sale.id = 7
        sale.amount_aed = Decimal('500')
        sale.tax_rate = Decimal('0')
        result = strategy.generate_einvoice(sale)
        assert 'TaxAmount currencyID="SAR">0' in result['xml_payload']

    def test_sign_zatca_payload_mocked(self, strategy):
        sale = MagicMock(spec=['id', 'total_aed'])
        sale.id = 1
        sale.total_aed = Decimal('100')
        with patch.object(strategy, 'sign_zatca_payload', return_value='mocked-signature') as signer:
            result = strategy.generate_einvoice(sale)
        assert result['invoice_hash'] == 'mocked-signature'
        signer.assert_called_once()

    def test_zatca_portal_connectivity_mocked(self, strategy):
        sale = MagicMock(spec=['id', 'total_aed'])
        sale.id = 99
        sale.total_aed = Decimal('50')
        with patch.object(
            strategy,
            'sign_zatca_payload',
            side_effect=ConnectionError('ZATCA portal unreachable'),
        ):
            with pytest.raises(ConnectionError, match='ZATCA portal'):
                strategy.generate_einvoice(sale)

    def test_amount_aed_fallback(self, strategy):
        sale = MagicMock(spec=['id', 'amount_aed'])
        sale.id = 3
        sale.amount_aed = Decimal('230')
        result = strategy.generate_einvoice(sale)
        assert '230' in result['xml_payload']


class TestKSAExtractTax:
    def test_resolve_vat_rate_from_sale(self, strategy):
        sale = MagicMock(spec=['tax_rate'])
        sale.tax_rate = Decimal('5')
        assert strategy._resolve_vat_rate(sale) == Decimal('5')

    def test_extract_tax_from_inclusive(self, strategy):
        net, tax = strategy._extract_tax_from_inclusive(Decimal('115'), Decimal('15'))
        assert net == Decimal('100.00')
        assert tax == Decimal('15.00')

    def test_extract_tax_zero_rate(self, strategy):
        net, tax = strategy._extract_tax_from_inclusive(Decimal('80'), Decimal('0'))
        assert net == Decimal('80')
        assert tax == Decimal('0')
