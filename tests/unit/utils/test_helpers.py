from __future__ import annotations

import io
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from utils import helpers as h


class TestNormalizeBranchCode:
    def test_empty_returns_none(self):
        assert h._normalize_branch_code(None) is None
        assert h._normalize_branch_code('') is None

    def test_strips_non_alnum(self):
        assert h._normalize_branch_code(' br-01 ') == 'BR01'


class TestResolveBranchCode:
    def test_from_explicit_code(self):
        assert h._resolve_branch_code(branch_code='x-1') == 'X1'

    def test_from_branch_id_lookup(self, app):
        branch = MagicMock(code='MAIN')
        with patch('utils.helpers.db.session.get', return_value=branch):
            assert h._resolve_branch_code(branch_id=3) == 'MAIN'

    def test_fallback_synthetic_code(self, app):
        with patch('utils.helpers.db.session.get', return_value=None):
            assert h._resolve_branch_code(branch_id=7) == 'BR07'

    def test_lookup_exception_fallback(self, app):
        with patch('utils.helpers.db.session.get', side_effect=RuntimeError('db')):
            assert h._resolve_branch_code(branch_id=2) == 'BR02'


class TestGenerateNumber:
    def test_first_number_without_branch(self, app):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = None
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.generate_number('INV', MagicMock(), field_name='sale_number', tenant_id=1)
        assert result.endswith('-0001')

    def test_increments_from_latest(self, app):
        latest = MagicMock(sale_number='INV-2026-0007')
        model = MagicMock()
        model.tenant_id = 1
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = latest
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.generate_number('INV', model, field_name='sale_number', tenant_id=1)
        assert result.endswith('-0008')

    def test_invalid_suffix_starts_at_one(self, app):
        latest = MagicMock(sale_number='INV-2026-XYZ')
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = latest
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.generate_number('INV', MagicMock(tenant_id=1), field_name='sale_number')
        assert result.endswith('-0001')

    def test_with_branch_code(self, app):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = None
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.generate_number('SO', MagicMock(tenant_id=1), field_name='num', branch_code='BR01')
        assert '-BR01-' in result


class TestGenerateNumberAndSave:
    def test_saves_on_first_try(self, app):
        save = MagicMock(return_value='saved')
        with patch('utils.helpers.generate_number', return_value='N-1'):
            assert h.generate_number_and_save('P', MagicMock(), 'num', save) == 'saved'

    def test_retries_on_integrity_error(self, app):
        save = MagicMock(side_effect=[IntegrityError('dup', {}, None), 'ok'])
        with patch('utils.helpers.generate_number', side_effect=['N-1', 'N-2']), \
             patch('utils.helpers.db.session.rollback'):
            assert h.generate_number_and_save('P', MagicMock(), 'num', save) == 'ok'

    def test_raises_after_max_attempts(self, app):
        save = MagicMock(side_effect=IntegrityError('dup', {}, None))
        with patch('utils.helpers.generate_number', return_value='N-1'), \
             patch('utils.helpers.db.session.rollback'):
            with pytest.raises(RuntimeError):
                h.generate_number_and_save('P', MagicMock(), 'num', save, max_attempts=2)


class TestGetNextNumber:
    def test_with_branch_code(self, app):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = None
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.get_next_number('PO', MagicMock(), number_field='number', branch_code='BR01')
        assert '-BR01-' in result

    def test_no_records(self, app):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = None
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.get_next_number('PO', MagicMock(), number_field='number')
        assert result.endswith('-0001')

    def test_increments(self, app):
        rec = MagicMock(number='PO-2026-0003')
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value.first.return_value = rec
        with patch('utils.helpers.db.session.query', return_value=q):
            result = h.get_next_number('PO', MagicMock(), number_field='number')
        assert result.endswith('-0004')


class TestDiscountAndVat:
    def test_calculate_discount(self):
        assert h.calculate_discount(100, 10) == Decimal('10.00')

    def test_calculate_vat(self):
        assert h.calculate_vat(200, 5) == Decimal('10.00')


class TestResolveFormatCurrencySettings:
    def test_system_settings_exception_uses_tenant(self, app):
        tenant = MagicMock(default_currency='SAR')
        with patch('models.system_settings.SystemSettings.get_current', side_effect=RuntimeError('no settings')), \
             patch('models.Tenant.get_current', return_value=tenant):
            currency, symbol, position, decimals = h._resolve_format_currency_settings()
        assert currency == 'SAR'

    def test_tenant_lookup_exception(self, app):
        with patch('models.system_settings.SystemSettings.get_current', return_value=MagicMock(
            default_currency='AED', currency_symbol='', currency_position='', decimal_places=2,
        )), patch('models.Tenant.get_current', side_effect=RuntimeError('no tenant')):
            currency, _, _, _ = h._resolve_format_currency_settings()
        assert currency == 'AED'


class TestFormatCurrency:
    def test_zero_amount(self):
        assert h.format_currency(0) == '0.00'

    def test_ar_default_position(self, app):
        with patch('utils.helpers._resolve_format_currency_settings', return_value=(None, None, None, None)), \
             patch('utils.currency_utils.get_system_default_currency', return_value='AED'), \
             patch('utils.currency_utils.get_currency_symbol', return_value='د.إ'):
            result = h.format_currency(1234.5, lang='ar')
        assert '1,234.50' in result

    def test_en_before_position(self, app):
        with patch('utils.helpers._resolve_format_currency_settings', return_value=('USD', '$', 'before', 2)), \
             patch('utils.currency_utils.get_currency_symbol', return_value='$'):
            result = h.format_currency(10, currency='USD', lang='en')
        assert result.startswith('$')

    def test_invalid_amount_fallback(self):
        class BadDecimal:
            def __format__(self, spec):
                raise ValueError('bad')
        assert 'BadDecimal' in h.format_currency(BadDecimal())


class TestTimeago:
    def test_empty_date(self):
        assert h.timeago(None) == ''

    def test_invalid_year(self):
        assert h.timeago(datetime(1800, 1, 1)) == ''

    def test_moments(self):
        now = datetime.now(timezone.utc) - timedelta(seconds=30)
        assert h.timeago(now) == 'منذ لحظات'

    def test_minutes(self):
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert 'دقيقة' in h.timeago(now)

    def test_hours(self):
        now = datetime.now(timezone.utc) - timedelta(hours=2)
        assert 'ساعة' in h.timeago(now)

    def test_days(self):
        now = datetime.now(timezone.utc) - timedelta(days=2)
        assert 'يوم' in h.timeago(now)

    def test_weeks_fallback_date(self):
        now = datetime.now(timezone.utc) - timedelta(days=10)
        assert h.timeago(now).count('-') == 2

    def test_naive_datetime(self):
        naive = datetime.now() - timedelta(minutes=1)
        assert h.timeago(naive) != ''

    def test_exception_returns_str(self):
        bad = MagicMock(spec=[])
        bad.tzinfo = timezone.utc
        bad.__sub__ = MagicMock(side_effect=TypeError('bad'))
        bad.__str__ = MagicMock(return_value='bad datetime')
        assert h.timeago(bad) == 'bad datetime'


class TestCreateAuditLog:
    def test_flask_login_import_error(self, app, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def blocked_import(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
            if name == 'flask_login':
                raise ImportError('blocked')
            return real_import(name, globals_dict, locals_dict, fromlist, level)

        monkeypatch.setattr(builtins, '__import__', blocked_import)
        with app.test_request_context('/'), \
             patch('models.AuditLog') as audit_cls, \
             patch('utils.helpers.db.session.add'), \
             patch('utils.helpers.db.session.commit'):
            h.create_audit_log('script', 'sales', 1)
        audit_cls.assert_called_once()

    def test_logs_failure_via_print_without_app(self, app, monkeypatch, capsys):
        monkeypatch.setattr(h, 'current_app', None)
        with app.test_request_context('/'), \
             patch('models.AuditLog', side_effect=RuntimeError('fail')), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            h.create_audit_log('x')
        assert 'Failed to create audit log' in capsys.readouterr().out

    def test_logs_failure_when_logger_raises(self, app, mocker):
        mock_app = MagicMock()
        mock_app.logger.error.side_effect = RuntimeError('log fail')
        mocker.patch.object(h, 'current_app', mock_app)
        with app.test_request_context('/'), \
             patch('models.AuditLog', side_effect=RuntimeError('fail')), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            h.create_audit_log('x')

    def test_creates_log(self, app):
        with app.test_request_context('/'), \
             patch('models.AuditLog') as audit_cls, \
             patch('utils.helpers.db.session.add'), \
             patch('utils.helpers.db.session.commit'), \
             patch('flask_login.current_user', MagicMock(is_authenticated=True, id=7)):
            h.create_audit_log('update', 'sales', 1, {'x': 1})
        audit_cls.assert_called_once()

    def test_logs_failure_without_crash(self, app):
        with app.test_request_context('/'), \
             patch('models.AuditLog', side_effect=RuntimeError('fail')), \
             patch('flask_login.current_user', MagicMock(is_authenticated=False)):
            h.create_audit_log('x')


class TestAllowedFile:
    def test_empty_filename(self, app):
        with app.app_context():
            app.config['ALLOWED_UPLOAD_EXTENSIONS'] = {'all': {'png', 'jpg'}}
            assert h.allowed_file('') is False

    def test_allowed_extension(self, app):
        with app.app_context():
            assert h.allowed_file('photo.PNG', allowed_extensions={'.png', '.jpg'}) is True

    def test_merged_extension_sets(self, app):
        with app.app_context():
            assert h.allowed_file('doc.pdf', allowed_extensions={'.pdf'}) is True

    def test_merges_config_extension_groups(self, app):
        with app.app_context():
            app.config['ALLOWED_UPLOAD_EXTENSIONS'] = {
                'images': {'.png', '.jpg'},
                'docs': {'.pdf'},
            }
            assert h.allowed_file('scan.pdf') is True
            assert h.allowed_file('photo.jpg') is True
            assert h.allowed_file('bad.exe') is False


class TestSaveUploadedFile:
    def test_no_file(self, app):
        with app.app_context():
            assert h.save_uploaded_file(None) is None

    def test_rejects_disallowed_type(self, app):
        f = MagicMock()
        f.filename = 'virus.exe'
        with app.app_context():
            app.config['ALLOWED_UPLOAD_EXTENSIONS'] = {'all': {'png'}}
            with pytest.raises(ValueError, match='not allowed'):
                h.save_uploaded_file(f)

    def test_rejects_oversized(self, app):
        f = MagicMock()
        f.filename = 'big.png'
        f.tell.side_effect = [10 * 1024 * 1024 + 1, 0]
        f.read.return_value = b'\x89PNG'
        with app.app_context():
            with pytest.raises(ValueError, match='size'):
                h.save_uploaded_file(f, allowed_extensions={'.png'})

    def test_rejects_executable_header(self, app):
        f = MagicMock()
        f.filename = 'fake.png'
        f.tell.side_effect = [100, 0]
        f.read.return_value = b'MZ' + b'\x00' * 510
        with app.app_context():
            with pytest.raises(ValueError, match='Executable'):
                h.save_uploaded_file(f, allowed_extensions={'.png'})

    def test_saves_valid_file(self, app, tmp_path):
        f = MagicMock()
        f.filename = 'ok.png'
        f.tell.side_effect = [128, 0]
        f.read.return_value = b'\x89PNG\r\n'
        static_dir = tmp_path / 'static'
        static_dir.mkdir()
        with app.app_context():
            app.config['ALLOWED_UPLOAD_EXTENSIONS'] = {'all': {'png'}}
            app.static_folder = str(static_dir)
            with patch('utils.helpers.os.makedirs'), patch.object(f, 'save'):
                path = h.save_uploaded_file(f, upload_folder='uploads', allowed_extensions={'.png'})
        assert path.startswith('uploads/')


class TestConvertCurrency:
    def test_same_currency(self, app):
        assert h.convert_currency(100, 'AED', 'AED') == 100

    def test_converts_with_rate(self, app):
        with patch('services.currency_service.CurrencyService.get_exchange_rate', return_value=Decimal('3.67')):
            result = h.convert_currency(10, 'USD', 'AED')
        assert result == Decimal('36.70')

    def test_default_to_currency(self, app):
        tenant = MagicMock(default_currency='SAR')
        with patch('models.Tenant.get_current', return_value=tenant), \
             patch('services.currency_service.CurrencyService.get_exchange_rate', return_value=1):
            h.convert_currency(5, 'USD')

    def test_default_to_currency_tenant_lookup_failure(self, app):
        with patch('models.Tenant.get_current', side_effect=RuntimeError('no tenant')), \
             patch('services.currency_service.CurrencyService.get_exchange_rate', return_value=1):
            result = h.convert_currency(5, 'USD')
        assert result == Decimal('5')


class TestSkuBarcode:
    def test_generate_sku(self):
        assert h.generate_sku().startswith('SKU-')

    def test_generate_barcode(self):
        assert len(h.generate_barcode()) > 8
