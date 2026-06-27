"""Advanced accounting models — taxes, expenses, calculation rules."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.advanced_accounting import (
    AdvancedExpense,
    CustomsTax,
    TaxCalculationRule,
)


def _tax(**kwargs):
    return CustomsTax(
        tenant_id=kwargs.get('tenant_id', 1),
        name=kwargs.get('name', 'VAT'),
        name_ar=kwargs.get('name_ar', 'ضريبة'),
        tax_type=kwargs.get('tax_type', 'vat'),
        rate=kwargs.get('rate', Decimal('0.05')),
        gl_account_id=kwargs.get('gl_account_id', 1),
        effective_from=kwargs.get('effective_from', date(2025, 1, 1)),
    )


def _expense(**kwargs):
    exp = AdvancedExpense(
        tenant_id=kwargs.get('tenant_id', 1),
        expense_number=kwargs.get('expense_number', 'EXP-001'),
        expense_date=kwargs.get('expense_date', date(2025, 6, 1)),
        description=kwargs.get('description', 'Office supplies'),
        description_ar=kwargs.get('description_ar', 'مستلزمات'),
        category_id=kwargs.get('category_id', 5),
        amount=kwargs.get('amount', Decimal('100')),
        amount_aed=kwargs.get('amount_aed', Decimal('100')),
        created_by=kwargs.get('created_by', 1),
        branch_id=kwargs.get('branch_id'),
        tax_exempt=kwargs.get('tax_exempt', False),
        customs_exempt=kwargs.get('customs_exempt', False),
        taxable_amount=kwargs.get('taxable_amount', Decimal('100')),
        tax_rate=kwargs.get('tax_rate', Decimal('0.05')),
        customs_rate=kwargs.get('customs_rate', Decimal('0.02')),
        is_reversed=kwargs.get('is_reversed', False),
    )
    exp.category = kwargs.get('category', SimpleNamespace(gl_account=SimpleNamespace(code='6100')))
    return exp


def _rule(**kwargs):
    return TaxCalculationRule(
        tenant_id=kwargs.get('tenant_id', 1),
        name=kwargs.get('name', 'Rule'),
        name_ar=kwargs.get('name_ar', 'قاعدة'),
        rule_type=kwargs.get('rule_type', 'expense'),
        condition_field=kwargs.get('condition_field', 'category_id'),
        condition_operator=kwargs.get('condition_operator', '='),
        condition_value=kwargs.get('condition_value', '5'),
        tax_id=kwargs.get('tax_id', 1),
        is_active=kwargs.get('is_active', True),
    )


class TestCustomsTax:
    def test_repr(self):
        assert 'ضريبة' in repr(_tax())

    @pytest.mark.parametrize('tax_type,label', [
        ('customs', 'جمارك'),
        ('vat', 'ضريبة القيمة المضافة'),
        ('excise', 'ضريبة استهلاك'),
        ('income', 'ضريبة دخل'),
        ('corporate', 'ضريبة الشركات'),
        ('other', 'other'),
    ])
    def test_tax_type_ar(self, tax_type, label):
        assert _tax(tax_type=tax_type).tax_type_ar == label


class TestAdvancedExpenseProperties:
    def test_repr(self):
        assert 'EXP-001' in repr(_expense())

    @pytest.mark.parametrize('method,label', [
        ('cash', 'نقداً'),
        ('bank_transfer', 'تحويل بنكي'),
        ('cheque', 'شيك'),
        ('credit_card', 'بطاقة ائتمان'),
        ('wire', 'wire'),
    ])
    def test_payment_method_ar(self, method, label):
        exp = _expense()
        exp.payment_method = method
        assert exp.payment_method_ar == label

    @pytest.mark.parametrize('status,label', [
        ('pending', 'معلق'),
        ('paid', 'مدفوع'),
        ('partial', 'مدفوع جزئياً'),
        ('overdue', 'متأخر'),
        ('unknown', 'unknown'),
    ])
    def test_payment_status_ar(self, status, label):
        exp = _expense()
        exp.payment_status = status
        assert exp.payment_status_ar == label

    @pytest.mark.parametrize('status,label', [
        ('pending', 'في انتظار الموافقة'),
        ('approved', 'موافق عليه'),
        ('rejected', 'مرفوض'),
        ('unknown', 'unknown'),
    ])
    def test_approval_status_ar(self, status, label):
        exp = _expense()
        exp.approval_status = status
        assert exp.approval_status_ar == label


class TestAdvancedExpenseCalculations:
    def test_calculate_taxes_normal(self):
        exp = _expense()
        exp.calculate_taxes()
        assert exp.tax_amount == Decimal('5.000')
        assert exp.customs_amount == Decimal('2.000')

    def test_calculate_taxes_exempt(self):
        exp = _expense(tax_exempt=True, customs_exempt=True)
        exp.calculate_taxes()
        assert exp.tax_amount == 0
        assert exp.customs_amount == 0

    def test_get_total_amount(self):
        exp = _expense()
        exp.calculate_taxes()
        assert exp.get_total_amount() == Decimal('107.000')


class TestAdvancedExpenseReverse:
    def test_reverse_expense_creates_gl_entry(self, mocker, mock_db):
        exp = _expense(branch_id=3)
        user = MagicMock(id=9)
        mocker.patch(
            'models.advanced_accounting.gl_get_default_liquidity_account',
            return_value='1100',
        )
        gl_create = mocker.patch('models.advanced_accounting.gl_create_manual_entry')
        exp.reverse_expense('duplicate', user)
        assert exp.is_reversed is True
        assert exp.reversed_by == 9
        assert exp.reversal_reason == 'duplicate'
        assert exp.reversed_at is not None
        gl_create.assert_called_once()
        kwargs = gl_create.call_args[1]
        assert kwargs['branch_id'] == 3
        assert kwargs['created_by'] == 9

    def test_reverse_expense_already_reversed(self, mock_db):
        exp = _expense(is_reversed=True)
        with pytest.raises(ValueError, match='معكوس مسبقاً'):
            exp.reverse_expense('reason', MagicMock(id=1))


class TestTaxCalculationRule:
    def test_repr(self):
        assert 'قاعدة' in repr(_rule())

    def test_matches_inactive_rule(self):
        rule = _rule(is_active=False)
        assert rule.matches(_expense()) is False

    def test_matches_non_expense_rule_type(self):
        rule = _rule(rule_type='income')
        assert rule.matches(_expense()) is False

    def test_matches_category_id(self):
        rule = _rule(condition_field='category_id', condition_value='5')
        assert rule.matches(_expense(category_id=5)) is True
        assert rule.matches(_expense(category_id=9)) is False

    @pytest.mark.parametrize('operator,value,amount,expected', [
        ('>', '50', Decimal('100'), True),
        ('<', '50', Decimal('100'), False),
        ('>=', '100', Decimal('100'), True),
        ('<=', '100', Decimal('100'), True),
        ('=', '100', Decimal('100'), True),
    ])
    def test_matches_amount_operators(self, operator, value, amount, expected):
        rule = _rule(
            condition_field='amount',
            condition_operator=operator,
            condition_value=value,
        )
        assert rule.matches(_expense(amount_aed=amount)) is expected

    def test_matches_unknown_field_returns_false(self):
        rule = _rule(condition_field='unknown_field')
        assert rule.matches(_expense()) is False

    def test_matches_unknown_amount_operator(self):
        rule = _rule(
            condition_field='amount',
            condition_operator='LIKE',
            condition_value='100',
        )
        assert rule.matches(_expense()) is False
