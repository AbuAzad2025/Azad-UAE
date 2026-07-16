"""Batch 2 — assurance tests for 95-99% source files (1-15 missed lines)."""
from __future__ import annotations

import importlib
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from decimal import Decimal

from models import Product
from services.ai_service import AIService


class TestAIServiceGetModel:
    def test_rejects_none_pk(self):
        assert AIService._get_model(Product, None) is None

    def test_rejects_leaked_unittest_mock_instance(self, mocker):
        from unittest.mock import Mock
        leaked = Mock(spec=Product)
        mocker.patch('services.ai_service.db.session.get', return_value=leaked)
        assert AIService._get_model(Product, 1) is None

    def test_rejects_product_whose_class_module_is_mock(self, mocker, db_session, sample_tenant):
        product = Product(
            tenant_id=sample_tenant.id,
            name='Leak',
            sku='LEAK-1',
            regular_price=Decimal('10'),
        )
        db_session.add(product)
        db_session.flush()
        with patch.object(type(product), '__module__', 'unittest.mock'):
            mocker.patch('services.ai_service.db.session.get', return_value=product)
            assert AIService._get_model(Product, product.id) is None


class TestModelReprQuickWins:
    @pytest.mark.parametrize('module_path,cls_name,attrs,expected', [
        ('models.branch', 'Branch', {'name': 'HQ', 'code': 'MAIN'}, 'HQ'),
        ('models.product_serial', 'ProductSerial', {'serial_number': 'SN1', 'status': 'available'}, 'SN1'),
        ('models.error_audit_log', 'ErrorAuditLog', {
            'category': 'API', 'level': 'ERROR', 'message': 'timeout on endpoint',
        }, 'API'),
        ('models.azad_platform_fee', 'AzadPlatformFee', {
            'sale_id': 1, 'fee_amount_aed': Decimal('5'),
        }, 'sale=1'),
        ('models.azad_subscription_fee', 'AzadSubscriptionFee', {
            'tenant_id': 1, 'fee_type': 'monthly', 'amount_aed': Decimal('99'),
        }, 'tenant=1'),
        ('models.product_cost_history', 'ProductCostHistory', {
            'product_id': 2, 'movement_type': 'in', 'old_average_cost': 1, 'new_average_cost': 2,
        }, 'p=2'),
        ('models.shipment', 'Shipment', {
            'source_type': 'sale', 'source_id': 9, 'status': 'shipped',
        }, 'sale#9'),
        ('models.exchange_rate_record', 'ExchangeRateRecord', {
            'from_currency': 'USD', 'to_currency': 'AED', 'rate': Decimal('3.67'),
            'effective_date': '2026-01-01',
        }, 'USD'),
        ('models.journal_entry_audit', 'JournalEntryAudit', {
            'action': 'create', 'journal_entry_id': 7,
        }, 'create'),
        ('models.product_image', 'ProductImage', {
            'product_id': 3, 'image_type': 'main', 'sort_order': 1,
        }, 'P#3'),
        ('models.product_price_tier', 'ProductPriceTier', {
            'product_id': 4, 'tier_code': 'retail', 'price': Decimal('10'),
        }, 'P#4'),
        ('models.tenant', 'Tenant', {'name': 'Acme Corp', 'slug': 'acme'}, 'Acme Corp'),
        ('models.partner', 'Partner', {'name': 'Sami', 'share_percentage': Decimal('25')}, 'Sami'),
        ('models.hr', 'Department', {'name': 'Sales'}, 'Sales'),
        ('models.hr', 'JobPosition', {'name': 'Manager'}, 'Manager'),
        ('models.hr', 'HRContract', {'user_id': 1, 'state': 'active'}, 'U1'),
        ('models.hr', 'Attendance', {'user_id': 2, 'check_in': '2026-01-01'}, 'U2'),
        ('models.hr', 'LeaveType', {'name': 'Annual'}, 'Annual'),
        ('models.hr', 'LeaveRequest', {
            'user_id': 3, 'date_from': '2026-01-01', 'date_to': '2026-01-05',
        }, 'U3'),
        ('models.crm', 'CRMStage', {'name': 'Qualified'}, 'Qualified'),
        ('models.crm', 'CRMTeam', {'name': 'Inside'}, 'Inside'),
        ('models.crm', 'CRMLead', {'name': 'Prospect'}, 'Prospect'),
        ('models.crm', 'CRMActivity', {'activity_type': 'call', 'lead_id': 7}, 'call'),
        ('models.projects', 'Project', {'name': 'ERP Rollout'}, 'ERP'),
        ('models.projects', 'TaskStage', {'name': 'Backlog'}, 'Backlog'),
        ('models.projects', 'Task', {'name': 'Deploy'}, 'Deploy'),
        ('models.projects', 'Timesheet', {'date': '2026-06-01', 'hours': Decimal('4')}, '4h'),
        ('models.projects', 'ProjectMember', {'project_id': 1, 'user_id': 2}, 'P1'),
        ('models.campaign', 'Campaign', {'name': 'Ramadan', 'campaign_type': 'percent'}, 'Ramadan'),
        ('models.campaign', 'SaleCampaign', {
            'sale_id': 9, 'campaign_id': 3, 'discount_amount': Decimal('12'),
        }, 'S#9'),
        ('models.security_alert', 'SecurityAlert', {
            'alert_type': 'brute_force', 'severity': 'high', 'title': 'x',
        }, 'brute_force'),
    ])
    def test_repr_contains_key_token(self, module_path, cls_name, attrs, expected):
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        obj = SimpleNamespace(**attrs)
        assert expected in repr(cls.__repr__(obj))


class TestUtilsConstants:
    def test_normalize_payment_method_code_none_passthrough(self):
        from utils.constants import normalize_payment_method_code
        assert normalize_payment_method_code(None) is None


class TestLocalizationSaleTotal:
    def test_ksa_sale_total_defaults_to_zero(self):
        from utils.localization.ksa import KSAStrategy
        sale = SimpleNamespace()
        assert KSAStrategy()._sale_total(sale) == Decimal('0')

    def test_palestine_sale_total_defaults_to_zero(self):
        from utils.localization.palestine import PalestineStrategy
        sale = SimpleNamespace()
        assert PalestineStrategy()._sale_total(sale) == Decimal('0')


class TestBackupGitSha:
    def test_git_short_sha_success(self, mocker):
        from services.backup_service import BackupService
        mocker.patch(
            'services.backup_exec.run_git',
            return_value=subprocess.CompletedProcess([], 0, stdout='abcdef1234567890\n'),
        )
        assert BackupService._git_short_sha() == 'abcdef123456'


class TestIntegrationSettingsQuick:
    def test_repr_enabled_flag(self):
        from models.integration_settings import IntegrationSettings
        obj = SimpleNamespace(service_name='redis', enabled=True)
        assert 'redis' in IntegrationSettings.__repr__(obj)
        assert '✅' in IntegrationSettings.__repr__(obj)

    def test_get_config_invalid_json(self):
        from models.integration_settings import IntegrationSettings
        row = IntegrationSettings(service_name='smtp', enabled=False)
        row.config_data = '{not-json'
        assert row.get_config() == {}


class TestSanitizerQuick:
    def test_sanitize_html_with_bleach(self, mocker):
        mocker.patch('utils.sanitizer._BLEACH_AVAILABLE', True)
        bleach = mocker.patch('utils.sanitizer.bleach')
        bleach.clean.return_value = 'clean'
        from utils.sanitizer import InputSanitizer
        assert InputSanitizer.sanitize_html('<b>x</b>', allow_tags=True) == 'clean'


class TestExtensionsCompressImport:
    def test_compress_import_error_sets_unavailable(self):
        mod_name = 'extensions'
        saved = sys.modules.pop(mod_name, None)
        try:
            real_import = __import__

            def blocked(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
                if name == 'flask_compress':
                    raise ImportError('blocked for test')
                return real_import(name, globals_dict, locals_dict, fromlist, level)

            with patch('builtins.__import__', side_effect=blocked):
                mod = importlib.import_module(mod_name)
            assert mod.COMPRESS_AVAILABLE is False
            assert mod.compress is None
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            importlib.import_module(mod_name)
