"""Print service — tenant context, PDF, audit, bulk print."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestGetTenantContext:
    def test_builds_print_context(self, mocker):
        tenant, settings, company = MagicMock(), MagicMock(), MagicMock()
        mocker.patch(
            'models.invoice_settings.InvoiceSettings.company_print_context',
            return_value=(tenant, settings, company),
        )
        mocker.patch('utils.tenant_branding.get_print_header_context', return_value={'logo': 'x'})
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=5)

        from services.print_service import PrintService
        ctx = PrintService._get_tenant_context(5)
        assert ctx['tenant'] is tenant
        assert ctx['print_tenant_id'] == 5


class TestUserContext:
    def test_returns_user_metadata(self, mocker):
        user = MagicMock(full_name='Ali', username='ali', id=9)
        mocker.patch('services.print_service.current_user', user)
        from services.print_service import PrintService
        ctx = PrintService._user_context()
        assert ctx['print_user_name'] == 'Ali'
        assert ctx['print_user_id'] == 9

    def test_fallback_username(self, mocker):
        user = MagicMock(full_name=None, username='ali', id=9)
        mocker.patch('services.print_service.current_user', user)
        from services.print_service import PrintService
        assert PrintService._user_context()['print_user_name'] == 'ali'

    def test_exception_returns_dash(self, mocker):
        bad_user = MagicMock()
        type(bad_user).full_name = property(lambda self: (_ for _ in ()).throw(RuntimeError('no user')))
        mocker.patch('services.print_service.current_user', bad_user)
        from services.print_service import PrintService
        ctx = PrintService._user_context()
        assert ctx['print_user_name'] == '—'
        assert ctx['print_user_id'] is None


class TestRenderPrint:
    def test_merges_contexts(self, app, mocker):
        mocker.patch('services.print_service.PrintService._get_tenant_context', return_value={'tenant': 1})
        mocker.patch('services.print_service.PrintService._user_context', return_value={'print_user_id': 2})
        mock_render = mocker.patch('services.print_service.render_template', return_value='<html/>')
        from services.print_service import PrintService
        with app.app_context():
            PrintService.render_print('print/tmpl.html', {'doc': 'x'}, tenant_id=1)
        assert mock_render.call_args.kwargs['doc'] == 'x'


class TestRenderPdf:
    def test_weasyprint_success(self, app, mocker):
        mocker.patch('services.print_service.PrintService.render_print', return_value='<html>doc</html>')
        fake_wp = MagicMock()
        fake_wp.HTML.return_value.write_pdf.return_value = b'%PDF-1.4'
        mocker.patch.dict('sys.modules', {'weasyprint': fake_wp})
        from services.print_service import PrintService
        with app.app_context():
            pdf = PrintService.render_pdf('t.html', filename='inv.pdf')
        assert pdf.startswith(b'%PDF')

    def test_import_error_fallback_html_wrapper(self, app, mocker):
        mocker.patch('services.print_service.PrintService.render_print', return_value='<body>x</body>')
        import builtins
        real_import = builtins.__import__

        def fake_import(name, globals_dict=None, locals_dict=None, fromlist=(), level=0):
            if name == 'weasyprint':
                raise ImportError('no weasyprint')
            return real_import(name, globals_dict, locals_dict, fromlist, level)

        mocker.patch('builtins.__import__', side_effect=fake_import)
        from services.print_service import PrintService
        with app.app_context():
            result = PrintService.render_pdf('t.html')
        assert b'WeasyPrint' in result

    def test_generation_error_returns_html_bytes(self, app, mocker):
        mocker.patch('services.print_service.PrintService.render_print', return_value='<html/>')
        fake_wp = MagicMock()
        fake_wp.HTML.return_value.write_pdf.side_effect = RuntimeError('render fail')
        mocker.patch.dict('sys.modules', {'weasyprint': fake_wp})
        from services.print_service import PrintService
        with app.app_context():
            result = PrintService.render_pdf('t.html')
        assert result == b'<html/>'


class TestAuditPrint:
    def test_records_print_history(self, app, mocker):
        mock_session = mocker.patch('extensions.db.session')
        mocker.patch('models.print_history.PrintHistory')
        mocker.patch('services.print_service.PrintService._user_context', return_value={'print_user_id': 3})
        from services.print_service import PrintService
        with app.app_context():
            PrintService.audit_print(1, 'invoice', 99, user_id=3)
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_audit_failure_non_blocking(self, app, mocker):
        mocker.patch('models.print_history.PrintHistory', side_effect=RuntimeError('db'))
        from services.print_service import PrintService
        with app.app_context():
            PrintService.audit_print(1, 'invoice', 99)


class TestBulkPrint:
    def test_empty_documents_message(self, app, mocker):
        from services.print_service import PrintService
        with app.app_context():
            html = PrintService.bulk_print_documents([], {})
        assert 'لا توجد مستندات' in html

    def test_skips_unknown_doc_types(self, app, mocker):
        mocker.patch('services.print_service.PrintService.render_print', return_value='<page/>')
        docs = [{'type': 'unknown', 'context': {}}]
        from services.print_service import PrintService
        with app.app_context():
            html = PrintService.bulk_print_documents(docs, {'invoice': 'inv.html'})
        assert 'لا توجد مستندات' in html

    def test_combines_pages_with_breaks(self, app, mocker):
        mocker.patch('services.print_service.PrintService.render_print', side_effect=['<p1/>', '<p2/>'])
        docs = [
            {'type': 'invoice', 'context': {'id': 1}},
            {'type': 'invoice', 'context': {'id': 2}},
        ]
        from services.print_service import PrintService
        with app.app_context():
            html = PrintService.bulk_print_documents(docs, {'invoice': 'inv.html'}, tenant_id=1)
        assert 'page-break' in html
        assert '<p1/>' in html and '<p2/>' in html
