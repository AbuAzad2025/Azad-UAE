"""Fiscal position service — customer mapping, sale apply, tax compute."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestGetForCustomer:
    """get_for_customer — explicit, country auto-match, local fallback."""

    def test_returns_none_when_customer_missing(self, mocker):
        mocker.patch('services.fiscal_position_service.db.session.get', return_value=None)
        from services.fiscal_position_service import FiscalPositionService

        assert FiscalPositionService.get_for_customer(99) is None

    def test_explicit_fiscal_position_id(self, mocker):
        customer = MagicMock(tenant_id=1, fiscal_position_id=5, country=None)
        customer.fiscal_position_id = 5
        pos = MagicMock(id=5, code='export')
        mocker.patch(
            'services.fiscal_position_service.db.session.get',
            side_effect=[customer, pos],
        )

        from services.fiscal_position_service import FiscalPositionService

        assert FiscalPositionService.get_for_customer(1) is pos

    def test_auto_match_by_country(self, mocker):
        customer = MagicMock(tenant_id=1, country='SA', address_country=None)
        customer.fiscal_position_id = None
        pos = MagicMock(id=2, code='gcc')
        mocker.patch(
            'services.fiscal_position_service.db.session.get',
            side_effect=[customer, None],
        )
        fp_q = mocker.patch('services.fiscal_position_service.FiscalPosition.query')
        fp_q.filter.return_value.first.return_value = pos

        from services.fiscal_position_service import FiscalPositionService

        assert FiscalPositionService.get_for_customer(1) is pos

    def test_local_fallback_when_no_match(self, mocker):
        customer = MagicMock(tenant_id=1, country=None, address_country=None)
        customer.fiscal_position_id = None
        local = MagicMock(code='local')
        mocker.patch(
            'services.fiscal_position_service.db.session.get',
            side_effect=[customer, None],
        )
        fp_q = mocker.patch('services.fiscal_position_service.FiscalPosition.query')
        fp_q.filter.return_value.first.return_value = None
        fp_q.filter_by.return_value.first.return_value = local

        from services.fiscal_position_service import FiscalPositionService

        assert FiscalPositionService.get_for_customer(1) is local


class TestApplyAndCompute:
    """apply_to_sale / compute_tax_for_line — mapping and rate math."""

    def test_apply_to_sale_maps_tax_and_account(self, mocker):
        line = MagicMock(tax_id=10, income_account_id=200)
        sale = MagicMock(customer_id=1, lines=[line])
        pos = MagicMock()
        pos.map_tax.return_value = 11
        pos.map_account.return_value = 201
        mocker.patch(
            'services.fiscal_position_service.FiscalPositionService.get_for_customer',
            return_value=pos,
        )

        from services.fiscal_position_service import FiscalPositionService

        result = FiscalPositionService.apply_to_sale(sale)
        assert result.lines[0].tax_id == 11
        assert result.lines[0].income_account_id == 201

    def test_apply_skips_without_customer(self):
        sale = MagicMock(customer_id=None, lines=[])
        from services.fiscal_position_service import FiscalPositionService

        assert FiscalPositionService.apply_to_sale(sale) is sale

    def test_compute_tax_destination_rate(self, mocker):
        line = MagicMock(tax_id=3, unit_price=100, quantity=2)
        rule = MagicMock(destination_tax=MagicMock(rate=5))
        mocker.patch(
            'services.fiscal_position_service.FiscalPositionTaxRule.query'
        ).filter_by.return_value.first.return_value = rule

        from services.fiscal_position_service import FiscalPositionService

        tax_amount, rate = FiscalPositionService.compute_tax_for_line(line, fiscal_position_id=1)
        assert rate == Decimal('5')
        assert tax_amount == Decimal('10.000')

    def test_compute_tax_fallback_source_tax(self, mocker):
        line = MagicMock(tax_id=4, unit_price=50, quantity=1)
        mocker.patch(
            'services.fiscal_position_service.FiscalPositionTaxRule.query'
        ).filter_by.return_value.first.return_value = None
        mocker.patch(
            'services.fiscal_position_service.db.session.get',
            return_value=MagicMock(rate=10),
        )

        from services.fiscal_position_service import FiscalPositionService

        tax_amount, rate = FiscalPositionService.compute_tax_for_line(line, fiscal_position_id=2)
        assert rate == Decimal('10')
        assert tax_amount == Decimal('5.000')
