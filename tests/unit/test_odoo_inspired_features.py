"""
Tests for Odoo-inspired features:
- Bank Reconciliation auto-matching + CSV import
- Smart Document Sequencing
- Fiscal Positions
"""
import pytest
from decimal import Decimal


class TestDocumentSequence:
    """Test smart document sequencing."""

    def test_sequence_generate_next_number(self, app, db_session, sample_tenant):
        from services.document_sequence_service import DocumentSequenceService
        from models import DocumentSequence
        with app.app_context():
            seq = DocumentSequenceService.get_or_create(
                tenant_id=sample_tenant.id, code='test_inv', prefix='INV',
                pattern='{prefix}-{year}-{counter:04d}', counter_reset='year'
            )
            assert seq.code == 'test_inv'
            num1 = DocumentSequenceService.next_number(tenant_id=sample_tenant.id, code='test_inv')
            assert num1.startswith('INV-')
            assert '-0001' in num1
            num2 = DocumentSequenceService.next_number(tenant_id=sample_tenant.id, code='test_inv')
            assert '-0002' in num2

    def test_sequence_preview_does_not_consume(self, app, db_session, sample_tenant):
        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            DocumentSequenceService.get_or_create(
                tenant_id=sample_tenant.id, code='preview_test', prefix='PRE'
            )
            preview1 = DocumentSequenceService.preview(tenant_id=sample_tenant.id, code='preview_test')
            preview2 = DocumentSequenceService.preview(tenant_id=sample_tenant.id, code='preview_test')
            assert preview1 == preview2

    def test_sequence_branch_scoped(self, app, db_session, sample_tenant):
        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            DocumentSequenceService.get_or_create(
                tenant_id=sample_tenant.id, code='branch_test', prefix='B',
                pattern='{prefix}-{branch}-{year}-{counter:04d}', branch_scoped=True
            )
            num = DocumentSequenceService.next_number(
                tenant_id=sample_tenant.id, code='branch_test', branch_code='DUB'
            )
            assert 'DUB' in num


class TestFiscalPosition:
    """Test fiscal position tax/account mapping."""

    def test_fiscal_position_map_tax(self, app, db_session, sample_tenant):
        from models import FiscalPosition, FiscalPositionTaxRule, CustomsTax, TaxCalculationRule
        with app.app_context():
            tax1 = CustomsTax(tenant_id=sample_tenant.id, name='VAT 5%', rate=5, type='vat', country_code='AE')
            tax2 = CustomsTax(tenant_id=sample_tenant.id, name='VAT 0%', rate=0, type='vat', country_code='AE')
            db_session.add_all([tax1, tax2])
            db_session.flush()
            rule1 = TaxCalculationRule(tenant_id=sample_tenant.id, name='R1', name_ar='R1', rule_type='sale', tax_id=tax1.id)
            rule2 = TaxCalculationRule(tenant_id=sample_tenant.id, name='R2', name_ar='R2', rule_type='sale', tax_id=tax2.id)
            db_session.add_all([rule1, rule2])
            db_session.flush()
            fp = FiscalPosition(
                tenant_id=sample_tenant.id, code='export', name='Export Zero VAT',
                country_code='US', auto_apply=True, is_active=True
            )
            db_session.add(fp)
            db_session.flush()
            rule = FiscalPositionTaxRule(
                tenant_id=sample_tenant.id, fiscal_position_id=fp.id,
                source_tax_id=rule1.id, destination_tax_id=rule2.id, rule_type='tax'
            )
            db_session.add(rule)
            db_session.flush()
            mapped = fp.map_tax(rule1.id)
            assert mapped == rule2.id
            mapped2 = fp.map_tax(999)
            assert mapped2 == 999

    def test_fiscal_position_service_get_for_customer(self, app, db_session):
        from services.fiscal_position_service import FiscalPositionService
        from models import FiscalPosition, Customer, Tenant
        with app.app_context():
            tenant = Tenant(name='FPTest2', name_ar='FPTest2', slug='fpt2', email='fp2@test.com', phone_1='050', country='AE', subscription_plan='basic')
            db_session.add(tenant)
            db_session.flush()

            fp = FiscalPosition(
                tenant_id=tenant.id, code='local', name='Local VAT 5%',
                country_code='AE', auto_apply=True, is_active=True
            )
            db_session.add(fp)
            db_session.flush()

            customer = Customer(
                tenant_id=tenant.id, name='LocalCustomer',
                country='AE', is_active=True
            )
            db_session.add(customer)
            db_session.flush()

            result = FiscalPositionService.get_for_customer(customer.id)
            assert result is not None
            assert result.code == 'local'


class TestBankReconciliationEnhancement:
    """Test bank statement import and auto-matching."""

    def test_import_bank_statement(self, app, db_session):
        from services.bank_reconciliation_service import BankReconciliationService
        from models import BankStatementLine
        with app.app_context():
            from datetime import date
            rows = [
                {'date': date(2026, 6, 1), 'reference': 'REF001', 'description': 'Payment', 'amount': '1500'},
                {'date': date(2026, 6, 2), 'reference': 'REF002', 'description': 'Transfer', 'amount': '-500'},
            ]
            count = BankReconciliationService.import_bank_statement(
                tenant_id=1, bank_account_id=1, csv_rows=rows, statement_date=date(2026, 6, 1)
            )
            assert count == 2
            lines = BankStatementLine.query.filter_by(tenant_id=1).all()
            assert len(lines) == 2
            assert lines[0].reference == 'REF001'
            assert Decimal(str(lines[0].amount)) == Decimal('1500')

    def test_auto_match_empty_returns_empty(self, app, db_session):
        from services.bank_reconciliation_service import BankReconciliationService
        from datetime import date
        with app.app_context():
            matches = BankReconciliationService.auto_match_gl_lines(
                tenant_id=9999, bank_account_id=9999,
                period_start=date(2026, 1, 1), period_end=date(2026, 12, 31)
            )
            assert matches == []
