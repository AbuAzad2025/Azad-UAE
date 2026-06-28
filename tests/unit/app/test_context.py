from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask


@pytest.fixture
def ctx_app():
    from flask_login import LoginManager

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test'
    app.config['DEVELOPER_NAME'] = 'Dev'
    app.config['DEVELOPER_NAME_AR'] = 'مطور'
    app.config['DEVELOPER_LOGO'] = 'assets/logo.png'
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(_):
        return None

    with patch('app.context.LoggingCore.log_error'), \
         patch('utils.ai_access.get_ai_access_state', return_value={'allowed': True, 'global_enabled': True, 'tenant_enabled': True}), \
         patch('utils.report_registry.get_reports_by_category', return_value={}), \
         patch('utils.report_registry.REPORT_REGISTRY', {}), \
         patch('utils.report_registry.REPORT_CATEGORIES', []):
        from app.context import register_context_processors
        register_context_processors(app)
        yield app


class TestContextProcessor:
    def _ctx(self, app):
        funcs = [f for f in app.template_context_processors[None]]
        with app.app_context():
            for func in reversed(funcs):
                ctx = func()
                if 'tenant_name_ar' in ctx:
                    return ctx
            return funcs[-1]()

    def test_tenant_document_logo_global(self, ctx_app):
        with ctx_app.app_context(), patch('utils.tenant_branding.document_logo_relative_path', return_value='/logo.png'):
            fn = ctx_app.jinja_env.globals['tenant_document_logo']
            assert fn(settings=None, tenant_id=1) == '/logo.png'

    def test_utility_processor_tenant_loaded(self, ctx_app):
        tenant = MagicMock(
            name_ar='شركة', name_en='Co', name='Co', phone_1='050', mobile='', email='a@b.com',
            address_ar='addr', logo_url='/l.png', logo_dark_url='', favicon_url='',
            default_currency='AED', enable_tax=True, default_tax_rate=5, enable_pos=True, id=1,
        )
        with patch('models.Tenant.get_current', return_value=tenant), \
             patch('utils.tenant_branding.resolve_tenant_branding', return_value={}), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'د.إ'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = 5
            sys.enable_pos = False
            sys_set.return_value = sys
            ctx = self._ctx(ctx_app)
        assert ctx['tenant_name_ar'] == 'شركة'
        assert ctx['company_name'] == 'Co'

    def test_utility_processor_invoice_fallback(self, ctx_app):
        inv = MagicMock(
            company_name_ar='من الفاتورة', company_name_en='From Inv', phone_1='111',
            email='i@b.com', address_ar='addr', logo_url='/inv.png',
        )
        with patch('models.Tenant.get_current', return_value=None), \
             patch('models.invoice_settings.InvoiceSettings.get_active', return_value=inv), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            sys_set.return_value = sys
            ctx = self._ctx(ctx_app)
        assert ctx['tenant_name_ar'] == 'من الفاتورة'

    def test_utility_processor_tenant_exception(self, ctx_app):
        with patch('models.Tenant.get_current', side_effect=RuntimeError('db fail')), \
             patch('models.system_settings.SystemSettings.get_current', side_effect=RuntimeError('sys fail')), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)), \
             patch('app.context.LoggingCore.log_error') as log_err:
            ctx = self._ctx(ctx_app)
        assert ctx['developer_name'] is not None or ctx['developer_name'] == ''
        assert log_err.called

    def test_developer_logo_path_sanitization(self, ctx_app):
        with patch('models.Tenant.get_current', return_value=None), \
             patch('models.invoice_settings.InvoiceSettings.get_active', return_value=None), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            sys = MagicMock()
            sys.get_custom_setting.side_effect = lambda k: {
                'developer_logo': 'C:\\bad\\path.png',
                'developer_whatsapp': '00971501234567',
            }.get(k, '')
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            with patch('models.system_settings.SystemSettings.get_current', return_value=sys):
                ctx = self._ctx(ctx_app)
        assert ':\\' not in ctx['developer_logo']

    def test_global_tenant_user_lists_tenants(self, ctx_app):
        user = MagicMock(is_authenticated=True)
        user.has_permission.return_value = True
        t = MagicMock(id=1)
        with patch('models.Tenant.get_current', return_value=MagicMock(id=1, name_ar='T')), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('utils.tenanting.is_global_tenant_user', return_value=True), \
             patch('utils.tenanting.get_active_tenant_id', return_value=1), \
             patch('models.tenant.Tenant') as TenantModel, \
             patch('app.context.current_user', user), \
             patch('utils.branching.get_active_branch', return_value=None), \
             patch('utils.branching.get_active_branch_mode', return_value='single'):
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            sys_set.return_value = sys
            TenantModel.query.filter_by.return_value.order_by.return_value.limit.return_value.all.return_value = [t]
            with ctx_app.test_request_context():
                ctx = self._ctx(ctx_app)
        assert 'available_tenants' in ctx

    def test_branding_name_fallback(self, ctx_app):
        tenant = MagicMock(
            name_ar='', name_en='', name='', phone_1='', mobile='', email='',
            address_ar='', logo_url='', logo_dark_url='', favicon_url='',
            default_currency='AED', enable_tax=True, default_tax_rate=5, enable_pos=True, id=1,
        )
        tenant.name = ''
        with patch('models.Tenant.get_current', return_value=tenant), \
             patch('models.invoice_settings.InvoiceSettings.get_active', return_value=None), \
             patch('utils.tenant_branding.resolve_tenant_branding', return_value={'company_name_ar': 'من العلامة', 'company_name_en': 'Brand Co'}), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            sys_set.return_value = sys
            ctx = self._ctx(ctx_app)
        assert ctx['tenant_name_ar'] == 'من العلامة'
        assert ctx['tenant_name'] == 'Brand Co'

    def test_developer_logo_static_prefix_stripped(self, ctx_app):
        with patch('models.Tenant.get_current', return_value=None), \
             patch('models.invoice_settings.InvoiceSettings.get_active', return_value=None), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            sys = MagicMock()
            sys.get_custom_setting.side_effect = lambda k: '/static/assets/logo.png' if k == 'developer_logo' else ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            with patch('models.system_settings.SystemSettings.get_current', return_value=sys):
                ctx = self._ctx(ctx_app)
        assert ctx['developer_logo'].startswith('assets/')

    def test_authenticated_user_permissions(self, ctx_app):
        user = MagicMock(is_authenticated=True)
        user.has_permission = lambda c: c == 'manage_sales'
        with patch('models.Tenant.get_current', return_value=MagicMock(id=1, name_ar='T')), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('app.context.current_user', user), \
             patch('utils.branching.get_active_branch', return_value=None), \
             patch('utils.branching.get_active_branch_mode', return_value='single'), \
             patch('utils.tenanting.is_global_tenant_user', return_value=False), \
             patch('utils.constants.PERMISSION_CODES', ['manage_sales', 'manage_customers']):
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            sys_set.return_value = sys
            ctx = self._ctx(ctx_app)
        assert 'manage_sales' in ctx['current_user_permissions']

    def test_available_tenants_exception_logged(self, ctx_app):
        user = MagicMock(is_authenticated=True)
        with patch('models.Tenant.get_current', return_value=MagicMock(id=1, name_ar='T')), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('utils.tenanting.is_global_tenant_user', return_value=True), \
             patch('utils.tenanting.get_active_tenant_id', side_effect=RuntimeError('tenant fail')), \
             patch('app.context.current_user', user), \
             patch('app.context.LoggingCore.log_error') as log_err:
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            sys_set.return_value = sys
            ctx = self._ctx(ctx_app)
        assert ctx['available_tenants'] == []
        assert log_err.called

    def test_developer_logo_static_prefix_without_leading_slash(self, ctx_app):
        with patch('models.Tenant.get_current', return_value=None), \
             patch('models.invoice_settings.InvoiceSettings.get_active', return_value=None), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            sys = MagicMock()
            sys.get_custom_setting.side_effect = lambda k: 'static/assets/logo.png' if k == 'developer_logo' else ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            with patch('models.system_settings.SystemSettings.get_current', return_value=sys):
                ctx = self._ctx(ctx_app)
        assert ctx['developer_logo'].startswith('assets/')

    def test_available_tenants_nested_log_failure(self, ctx_app):
        user = MagicMock(is_authenticated=True)
        with patch('models.Tenant.get_current', return_value=MagicMock(id=1, name_ar='T')), \
             patch('models.system_settings.SystemSettings.get_current') as sys_set, \
             patch('utils.tenanting.is_global_tenant_user', return_value=True), \
             patch('utils.tenanting.get_active_tenant_id', side_effect=RuntimeError('tenant fail')), \
             patch('app.context.current_user', user), \
             patch('app.context.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            sys = MagicMock()
            sys.get_custom_setting.return_value = ''
            sys.default_currency = 'AED'
            sys.currency_symbol = 'AED'
            sys.currency_position = 'after'
            sys.decimal_places = 2
            sys.enable_tax = True
            sys.default_tax_rate = None
            sys.enable_pos = False
            sys_set.return_value = sys
            ctx = self._ctx(ctx_app)
        assert ctx['available_tenants'] == []

    def test_system_settings_log_failure_nested(self, ctx_app):
        with patch('models.Tenant.get_current', return_value=None), \
             patch('models.system_settings.SystemSettings.get_current', side_effect=RuntimeError('sys')), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)), \
             patch('app.context.LoggingCore.log_error', side_effect=RuntimeError('log fail')):
            ctx = self._ctx(ctx_app)
        assert ctx['developer_name'] is not None or ctx['developer_name'] == ''
