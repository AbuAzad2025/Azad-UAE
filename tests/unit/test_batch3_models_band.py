"""Batch 3 — models/utils/smaller services in the 80-94% band."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestPurchaseReturnBaseAmount:
    def test_base_amount_alias(self):
        from models.purchase_return import PurchaseReturn

        pr = PurchaseReturn(
            tenant_id=1,
            return_number='PR-1',
            purchase_id=1,
            supplier_id=1,
            subtotal=Decimal('0'),
            total_amount=Decimal('100'),
            amount_aed=Decimal('100'),
        )
        assert pr.base_amount == Decimal('100')
        pr.base_amount = Decimal('200')
        assert pr.amount_aed == Decimal('200')


class TestFiscalPositionMapping:
    def test_repr_and_map_tax(self, mocker):
        from models.fiscal_position import FiscalPosition, FiscalPositionTaxRule

        fp = FiscalPosition(tenant_id=1, code='export', name='Export')
        assert 'export' in repr(fp)

        rule = MagicMock(destination_tax_id=99)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = rule
        mocker.patch.object(FiscalPositionTaxRule, 'query', mock_q)
        assert fp.map_tax(5) == 99

    def test_map_tax_passthrough_without_rule(self, mocker):
        from models.fiscal_position import FiscalPosition, FiscalPositionTaxRule

        fp = FiscalPosition(tenant_id=1, code='local', name='Local')
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(FiscalPositionTaxRule, 'query', mock_q)
        assert fp.map_account(12) == 12


class TestHelpdeskModels:
    @pytest.mark.parametrize('cls_name,attrs,token', [
        ('TicketCategory', {'name': 'Billing'}, 'Billing'),
        ('TicketPriority', {'name': 'Urgent'}, 'Urgent'),
        ('Ticket', {'number': 'T-1', 'subject': 'Help'}, 'T-1'),
        ('TicketComment', {'id': 3, 'ticket_id': 9}, 'T9'),
    ])
    def test_repr(self, cls_name, attrs, token):
        from models import helpdesk as mod

        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert token in repr(cls.__repr__(obj))

    def test_ticket_to_dict(self):
        from models.helpdesk import Ticket

        ticket = Ticket(
            tenant_id=1,
            number='T-42',
            subject='Printer',
            status='open',
            source='portal',
        )
        d = ticket.to_dict()
        assert d['number'] == 'T-42'
        assert d['subject'] == 'Printer'


class TestModelReprBand:
    @pytest.mark.parametrize('module_path,cls_name,attrs,token', [
        ('models.archive', 'ArchivedRecord', {'table_name': 'sales', 'record_id': 9}, 'sales'),
        ('models.login_history', 'LoginHistory', {
            'username': 'admin', 'login_time': '2026-01-01',
        }, 'admin'),
        ('models.api_key', 'APIKey', {'name': 'mobile', 'service': 'pos'}, 'pos'),
        ('models.partner_transaction', 'PartnerTransaction', {
            'transaction_type': 'dividend', 'amount': Decimal('50'), 'balance_after': Decimal('100'),
        }, 'dividend'),
        ('models.package', 'Package', {'name_ar': 'Starter'}, 'Starter'),
        ('models.payroll_settings', 'PayrollSettings', {'tenant_id': 1}, 'tenant=1'),
    ])
    def test_repr_contains_token(self, module_path, cls_name, attrs, token):
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert token in repr(cls.__repr__(obj))
